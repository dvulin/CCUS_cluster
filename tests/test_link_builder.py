"""Hubs, hub-to-hub links and the map picker.

Three things changed together: the links table only offers hubs that exist, a link
can be drawn by clicking two hubs, and its length is estimated from the coordinates.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from streamlit_app.app import (
    ROUTE_COLUMNS,
    SCENARIO_NODE_COLUMNS,
    _candidate_links,
    _force_ticks,
    _hub_brief,
    _hub_options,
    _link_distance,
    _node_rows,
    _picked_hub,
    frames_to_scenario,
    load_scenario,
    route_row_from_hubs,
    scenario_to_frames,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "inputs" / "examples" / "ccus_cluster_v1.json"
JSON = ROOT / "json"


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


# ------------------------------------------------------------------- distance
def test_the_distance_of_a_known_pair():
    from ccus_core.geo.distance import great_circle_km

    # Zagreb (45.815, 15.978) - Rijeka (45.327, 14.442): about 130 km
    assert great_circle_km(45.815, 15.978, 45.327, 14.442) == pytest.approx(130, abs=3)


def test_the_distance_is_symmetric_and_zero_for_one_point():
    from ccus_core.geo.distance import great_circle_km

    a = great_circle_km(45.815, 15.978, 45.327, 14.442)
    b = great_circle_km(45.327, 14.442, 45.815, 15.978)
    assert a == pytest.approx(b)
    assert great_circle_km(45.0, 15.0, 45.0, 15.0) == pytest.approx(0.0)


# ----------------------------------------------------------------------- hubs
def test_the_hub_table_has_the_essential_columns():
    scenario = load_scenario(str(EXAMPLE))
    rows = _node_rows(scenario, scenario_to_frames(scenario)["routes"])

    assert list(rows[0]) == SCENARIO_NODE_COLUMNS
    assert len(rows) == len(scenario.nodes)
    assert all(row["id"] for row in rows)


def test_the_hub_table_counts_the_links_of_each_hub():
    scenario = load_scenario(str(EXAMPLE))
    rows = _node_rows(scenario, scenario_to_frames(scenario)["routes"])

    degrees = {row["id"]: row["links"] for row in rows}
    assert sum(degrees.values()) == 2 * sum(
        1 for row in scenario_to_frames(scenario)["routes"].to_dict("records")
    )
    assert all(value >= 0 for value in degrees.values())


def test_the_node_columns_only_offer_hubs_that_exist():
    scenario = load_scenario(str(EXAMPLE))
    routes = scenario_to_frames(scenario)["routes"]

    options = _hub_options(scenario, routes)

    assert options == sorted(options)
    assert set(options) == {node.id for node in scenario.nodes}
    # every value already in the table is offered, so editing cannot invalidate it
    for row in routes.to_dict("records"):
        assert row["from_node"] in options
        assert row["to_node"] in options


def test_a_route_to_an_unknown_node_keeps_its_value_offered():
    scenario = load_scenario(str(EXAMPLE))
    routes = scenario_to_frames(scenario)["routes"]
    routes.loc[len(routes)] = {
        **{column: None for column in ROUTE_COLUMNS},
        "id": "odd",
        "name": "Odd",
        "from_node": "ghost_hub",
        "to_node": "ghost_sink",
        "mode": "pipeline",
        "distance_km": 5.0,
        "valid_from_year": scenario.start_year,
    }

    options = _hub_options(scenario, routes)

    assert "ghost_hub" in options and "ghost_sink" in options


# ------------------------------------------------------------------ hub links
def test_a_drawn_link_becomes_a_route_row():
    row = route_row_from_hubs("A", "B", "pipeline", 12.5, set(), 2027, 250_000.0)

    assert list(row) == ROUTE_COLUMNS
    assert row["from_node"] == "A"
    assert row["to_node"] == "B"
    assert row["mode"] == "pipeline"
    assert row["distance_km"] == pytest.approx(12.5)
    assert row["capacity_t_per_year"] == pytest.approx(250_000.0)
    assert row["valid_from_year"] == 2027
    # nothing prices a corridor the user has just invented
    assert row["capex_eur"] == 0.0
    assert row["opex_eur_per_t"] == 0.0


def test_a_drawn_link_survives_apply():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    row = route_row_from_hubs(
        "hub_plomin", "hub_ivanic", "pipeline", 42.0, set(frames["routes"]["id"]),
        scenario.start_year, 250_000.0,
    )
    frames["routes"] = pd.concat(
        [frames["routes"], pd.DataFrame([row], columns=ROUTE_COLUMNS)], ignore_index=True
    )

    updated = frames_to_scenario(scenario, frames)

    edge = updated.edge_by_id(row["id"])
    assert edge is not None
    assert edge.states[0].effective_capacity_t_per_year() == pytest.approx(250_000.0)


def test_two_drawn_links_reach_a_third_hub_through_the_first():
    """A-B and B-C are enough: the router already finds A to C across two edges."""

    from ccus_core.models import ScenarioConfig
    from ccus_core.network.graph import NetworkGraph
    from ccus_core.network.routing import RoutingEngine

    def leg(edge_id, start, end):
        return {
            "id": edge_id,
            "name": edge_id,
            "from_node": start,
            "to_node": end,
            "states": [
                {
                    "mode": "pipeline",
                    "valid_from_year": 2027,
                    "capacity_t_per_year": 1000.0,
                    "distance_km": 10.0,
                    "capex_eur": 0.0,
                    "opex_eur_per_t": 1.0,
                    "pipeline": {
                        "inner_diameter_m": 0.30,
                        "inlet_pressure_bar": 150.0,
                        "inlet_temperature_c": 20.0,
                    },
                }
            ],
        }

    scenario = ScenarioConfig.model_validate(
        {
            "id": "chain",
            "name": "Chain",
            "start_year": 2027,
            "end_year": 2030,
            "nodes": [
                {"id": "A", "name": "A", "kind": "junction"},
                {"id": "B", "name": "B", "kind": "junction"},
                {"id": "SINK", "name": "Sink", "kind": "storage"},
            ],
            "edges": [leg("A-B", "A", "B"), leg("B-SINK", "B", "SINK")],
            "emitters": [
                {
                    "id": "src",
                    "name": "Source",
                    "node_id": "A",
                    "activation_year": 2027,
                    "gross_emissions": {"kind": "constant", "constant_t_per_year": 500.0},
                }
            ],
            "storage_sinks": [
                {"id": "sink", "name": "Sink", "node_id": "SINK", "capacity_t": 1_000_000.0}
            ],
        }
    )

    engine = RoutingEngine(NetworkGraph(scenario))
    result = engine.route(
        year=2028, supplies={"src": 500.0}, sink_remaining_capacity={"sink": 100_000.0}
    )

    assert result.total_allocated_t == pytest.approx(500.0)
    # the mass really crossed both legs, not one
    assert result.allocations
    assert set(result.allocations[0].path_edge_ids) == {"A-B", "B-SINK"}


def test_the_estimated_length_uses_the_coordinates():
    scenario = load_scenario(str(EXAMPLE))
    positioned = [node for node in scenario.nodes if node.location.latitude is not None]
    assert len(positioned) >= 2

    distance, source = _link_distance(scenario, positioned[0].id, positioned[1].id)

    assert distance > 0.0
    assert source == "straight"


def test_the_estimated_length_is_zero_without_coordinates():
    scenario = load_scenario(str(EXAMPLE)).model_copy(update={"nodes": []})

    assert _link_distance(scenario, "a", "b") == (0.0, "straight")


# --------------------------------------------------- distance: road vs crow-flies
def test_the_polyline_length_is_the_sum_of_its_segments():
    from ccus_core.geo.distance import path_length_km

    # one degree of latitude is about 111.2 km, so two half-degree legs are 111.2
    line = [[15.0, 45.0], [15.0, 45.5], [15.0, 46.0]]

    assert path_length_km(line) == pytest.approx(111.2, abs=1.0)
    # two full degrees
    assert path_length_km([[15.0, 45.0], [15.0, 46.0], [15.0, 47.0]]) == pytest.approx(
        222.4, abs=1.0
    )
    assert path_length_km([[15.0, 45.0]]) == 0.0
    assert path_length_km([]) == 0.0


def test_a_road_link_stores_the_road_distance(monkeypatch):
    """A road is longer than the crow flies, and the cost model charges per km."""

    from streamlit_app import app as app_module

    scenario = load_scenario(str(EXAMPLE))
    monkeypatch.setattr(
        "streamlit_app.map_layers.road_length_km",
        lambda *args, **kwargs: 262.1,
    )

    straight, _ = app_module._link_distance(
        scenario, "plant_plomin", "hub_central", mode="truck", follow_roads=False
    )
    road, source = app_module._link_distance(
        scenario, "plant_plomin", "hub_central", mode="truck", follow_roads=True
    )

    assert source == "road"
    assert road == pytest.approx(262.1)
    assert road > straight


def test_a_pipeline_link_keeps_the_crow_flies_distance(monkeypatch):
    from streamlit_app import app as app_module

    scenario = load_scenario(str(EXAMPLE))
    monkeypatch.setattr(
        "streamlit_app.map_layers.road_length_km", lambda *a, **k: 262.1
    )

    km, source = app_module._link_distance(
        scenario, "plant_plomin", "hub_central", mode="pipeline", follow_roads=True
    )

    assert source == "straight"
    assert km > 0.0


def test_the_distance_falls_back_when_the_router_is_down(monkeypatch):
    from streamlit_app import app as app_module
    from streamlit_app import map_layers

    scenario = load_scenario(str(EXAMPLE))
    monkeypatch.setattr(map_layers, "_ROAD_CACHE", {})
    monkeypatch.setattr(map_layers, "_fetch_osrm", lambda *a, **k: None)

    km, source = app_module._link_distance(
        scenario, "plant_plomin", "hub_central", mode="truck", follow_roads=True
    )

    assert source == "straight"
    assert km > 0.0


def test_the_road_distance_is_cached(monkeypatch):
    from streamlit_app import map_layers

    calls = []

    def fake_fetch(start, end, timeout=6.0):
        calls.append((start, end))
        return [[15.0, 45.0], [15.1, 45.1]]

    monkeypatch.setattr(map_layers, "_fetch_osrm", fake_fetch)
    monkeypatch.setattr(map_layers, "_ROAD_CACHE", {})

    first = map_layers.road_length_km((15.0, 45.0), (15.1, 45.1))
    second = map_layers.road_length_km((15.0, 45.0), (15.1, 45.1))

    assert first == second
    assert first is not None and first > 0.0
    assert len(calls) == 1, "a rerun must not ask the router again"


# -------------------------------------------------------------- map selection
def test_the_picker_reads_the_clicked_hub():
    state = {
        "selection": {
            "indices": {"hubs": [2]},
            "objects": {"hubs": [{"id": "C", "name": "Gamma", "position": [15.14, 45.0]}]},
        }
    }

    assert _picked_hub(state) == "C"


@pytest.mark.parametrize(
    "state",
    [None, {}, {"selection": {}}, {"selection": {"indices": {}, "objects": {}}},
     {"selection": {"objects": {"hubs": []}}}, {"selection": {"objects": {}}}],
)
def test_the_picker_tolerates_an_empty_selection(state):
    assert _picked_hub(state) is None


# ----------------------------------------------------------- candidate labels
def test_a_candidate_label_names_the_hubs(database):
    scenario = load_scenario(str(EXAMPLE))

    candidates = _candidate_links(scenario_to_frames(scenario)["routes"], scenario)

    assert candidates
    label = candidates[0]["label"]
    # the two ids, the mode and the length - and what kind of hub they are
    assert "\u2192" in label
    assert "\u00b7 pipeline \u00b7" in label
    assert label.count("(") >= 1


def test_a_hub_outside_the_scenario_is_marked_as_new(database):
    scenario = load_scenario(str(EXAMPLE))

    brief = _hub_brief("HRES002", {}, set())

    assert "HRES002" in brief
    assert "new hub" in brief


def test_a_known_hub_is_not_marked_as_new():
    brief = _hub_brief("hub_plomin", {}, {"hub_plomin"})

    assert brief == "hub_plomin"
    assert "new hub" not in brief


def test_the_label_carries_the_country_when_there_is_one():
    brief = _hub_brief(
        "HR.CH.001", {"HR.CH.001": {"category": "chain", "country": "HR"}}, {"HR.CH.001"}
    )

    assert brief == "HR.CH.001 (chain, HR)"