"""Adding a candidate link of the catalogue to a scenario.

The catalogue answers "which corridors exist", a scenario answers "which ones am I
building".  These tests pin the bridge: a candidate link must become a Routes row
that survives Apply, with an id that cannot collide and a capacity the engine
accepts - a pipeline state without one is refused by ``EdgeState``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from streamlit_app.app import (
    ROUTE_COLUMNS,
    _candidate_links,
    _edge_slug,
    _suggested_capacity,
    frames_to_scenario,
    load_scenario,
    route_row_from_candidate,
    scenario_to_frames,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "inputs" / "examples" / "ccus_cluster_v1.json"
JSON = ROOT / "json"

#: the model's ``Slug`` pattern, spelled out so the test does not use a private name
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

CANDIDATE = {
    "id": 1,
    "source_hub": "HRES002",
    "destination_hub": "HRSU006",
    "mode": "pipeline",
    "length_km": 12.5,
    "capex_eur": 1_000_000.0,
    "opex_eur_per_t": 5.0,
}


@pytest.fixture
def database(tmp_path):
    """A catalogue database built from a private copy of the snapshot."""

    from ccus_core.io import sqlite_catalogue as store

    path = tmp_path / "ccus.sqlite3"
    snapshot = tmp_path / "json"
    shutil.copytree(JSON, snapshot)
    with patch.object(store, "DEFAULT_DB_PATH", path), patch.object(
        store, "JSON_DIRECTORY", snapshot
    ), patch.object(store, "BACKUP_DIRECTORY", tmp_path / "backups"):
        connection = store.ensure_database()
        connection.close()
        yield path


# ------------------------------------------------------------------ the row
def test_a_candidate_link_becomes_a_complete_route_row():
    row = route_row_from_candidate(CANDIDATE, set(), 2027, 500_000.0)

    assert list(row) == ROUTE_COLUMNS
    assert row["from_node"] == "HRES002"
    assert row["to_node"] == "HRSU006"
    assert row["mode"] == "pipeline"
    assert row["distance_km"] == pytest.approx(12.5)
    assert row["capacity_t_per_year"] == pytest.approx(500_000.0)
    assert row["capex_eur"] == pytest.approx(1_000_000.0)
    assert row["opex_eur_per_t"] == pytest.approx(5.0)
    assert row["valid_from_year"] == 2027


def test_the_generated_id_follows_the_model_slug_pattern():
    row = route_row_from_candidate(CANDIDATE, set(), 2027, 1000.0)

    assert SLUG.fullmatch(row["id"])
    assert row["id"] == _edge_slug("HRES002-HRSU006-pipeline")


@pytest.mark.parametrize(
    "value",
    ["", "  ", "hr su 006", "čvor", "a/b", "---", "HR.CH.001", " lead", "trail "],
)
def test_the_slug_helper_stays_inside_the_pattern(value):
    assert SLUG.fullmatch(_edge_slug(value))


def test_the_generated_id_never_collides():
    base = _edge_slug("HRES002-HRSU006-pipeline")
    taken = {base, f"{base}-2"}

    row = route_row_from_candidate(CANDIDATE, taken, 2027, 1000.0)

    assert row["id"] == f"{base}-3"


# ------------------------------------------------------------------ Apply
def _scenario_with_link(capacity: float = 250_000.0):
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    row = route_row_from_candidate(
        CANDIDATE, set(frames["routes"]["id"]), scenario.start_year, capacity
    )
    frames["routes"] = pd.concat(
        [frames["routes"], pd.DataFrame([row], columns=ROUTE_COLUMNS)], ignore_index=True
    )
    return scenario, frames, row


def test_the_new_link_survives_apply():
    """The row must go through ``frames_to_scenario`` into a usable edge."""

    scenario, frames, row = _scenario_with_link()

    updated = frames_to_scenario(scenario, frames)

    edge = updated.edge_by_id(row["id"])
    assert edge is not None
    assert edge.from_node == "HRES002"
    assert edge.to_node == "HRSU006"
    assert edge.states[0].mode.value == "pipeline"
    assert edge.states[0].distance_km == pytest.approx(12.5)
    # the engine accepts the capacity instead of raising
    assert edge.states[0].effective_capacity_t_per_year() == pytest.approx(250_000.0)


def test_apply_keeps_every_original_edge():
    scenario, frames, _ = _scenario_with_link()

    updated = frames_to_scenario(scenario, frames)

    assert len(updated.edges) == len(scenario.edges) + 1
    for edge in scenario.edges:
        assert updated.edge_by_id(edge.id) is not None


def test_a_candidate_without_a_capacity_gets_the_peak_stream():
    scenario = load_scenario(str(EXAMPLE))
    capacity = _suggested_capacity(scenario)

    assert capacity > 0.0
    row = route_row_from_candidate(
        CANDIDATE, set(scenario_to_frames(scenario)["routes"]["id"]), scenario.start_year, capacity
    )
    assert row["capacity_t_per_year"] == pytest.approx(capacity)


def test_the_suggested_capacity_has_a_safe_floor():
    """An empty scenario still needs a number, or a pipeline state is refused."""

    scenario = load_scenario(str(EXAMPLE)).model_copy(update={"emitters": []})

    assert _suggested_capacity(scenario) >= 1000.0


def test_a_link_without_a_capacity_is_refused_by_the_engine():
    """Documents why the default exists: blank capacity would break the run."""

    from ccus_core.models import EdgeState, PipelineDesign

    state = EdgeState(
        mode="pipeline",
        valid_from_year=2027,
        distance_km=10.0,
        capacity_t_per_year=None,
        pipeline=PipelineDesign(
            inner_diameter_m=0.30, inlet_pressure_bar=150.0, inlet_temperature_c=20.0
        ),
    )

    with pytest.raises(ValueError, match="capacity_t_per_year"):
        state.effective_capacity_t_per_year()


# ------------------------------------------------------- candidate selection
def test_a_link_already_in_the_scenario_is_not_offered_again(monkeypatch):
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    first = frames["routes"].to_dict("records")[0]

    catalogue = [
        {
            "id": 1,
            "source_hub": first["from_node"],
            "destination_hub": first["to_node"],
            "mode": first["mode"],
            "length_km": first["distance_km"],
            "capex_eur": 0.0,
            "opex_eur_per_t": 0.0,
        },
        {**CANDIDATE, "id": 2},
    ]
    monkeypatch.setattr("streamlit_app.app.network_database_rows", lambda: catalogue)

    candidates = _candidate_links(frames["routes"])

    assert [item["id"] for item in candidates] == [2]


def test_the_candidate_list_comes_from_the_catalogue(database):
    from streamlit_app.app import network_database_rows

    scenario = load_scenario(str(EXAMPLE))
    candidates = _candidate_links(scenario_to_frames(scenario)["routes"])
    catalogue = network_database_rows()

    assert candidates, "the fixture database holds candidate links"
    offered = {
        (item["source_hub"], item["destination_hub"], item["mode"]) for item in candidates
    }
    assert offered <= {
        (row["source_hub"], row["destination_hub"], row["mode"]) for row in catalogue
    }
    # each one carries the label the picker shows
    assert all(item["label"] for item in candidates)
    assert all("\u2192" in item["label"] for item in candidates)


def test_adding_every_candidate_leaves_nothing_to_offer(database):
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)

    for candidate in _candidate_links(frames["routes"]):
        row = route_row_from_candidate(
            candidate, set(frames["routes"]["id"]), scenario.start_year, 250_000.0
        )
        frames["routes"] = pd.concat(
            [frames["routes"], pd.DataFrame([row], columns=ROUTE_COLUMNS)],
            ignore_index=True,
        )

    assert _candidate_links(frames["routes"]) == []


def test_every_added_link_has_a_unique_id(database):
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    ids = list(frames["routes"]["id"])

    for candidate in _candidate_links(frames["routes"]):
        row = route_row_from_candidate(
            candidate, set(ids), scenario.start_year, 250_000.0
        )
        ids.append(row["id"])

    assert len(ids) == len(set(ids))