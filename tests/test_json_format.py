"""The canonical JSON format: compact, editable, and still fully documented."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccus_core.io import commented_json

CLUSTER_JSON = Path(__file__).resolve().parents[1] / "inputs" / "examples" / "croatia_cluster_2025_2050.json"
THREE_EMITTERS = Path(__file__).resolve().parents[1] / "inputs" / "examples" / "cluster_three_emitters.json"


def test_compact_dump_stays_below_the_readability_budget():
    scenario = commented_json.load_file(CLUSTER_JSON)
    text = commented_json.dump(scenario)
    lines = text.splitlines()
    assert len(lines) < 700, f"compact document has {len(lines)} lines"
    # one line per object: no single line explodes into an unreadable block
    assert max(len(line) for line in lines) <= 400


def test_compact_document_round_trips_including_derived_edges():
    scenario = commented_json.load_file(CLUSTER_JSON)
    reloaded = commented_json.load(commented_json.dump(scenario))

    assert len(reloaded.emitters) == len(scenario.emitters)
    assert len(reloaded.connections) == len(scenario.connections)
    # edges are stored now (they carry the state timeline), not only derived
    assert len(reloaded.edges) == len(scenario.edges)
    assert reloaded.emitter_by_id("te-plomin").activation_year == 2028


def test_compact_document_keeps_the_edges_and_explains_units():
    text = commented_json.dump(commented_json.load_file(CLUSTER_JSON))
    assert '"_comments"' in text
    assert '"schema": "ccus-cluster/2.0"' in text
    # the legend documents the defaults once, instead of repeating them per sink
    assert '"storage_defaults.porosity"' in text
    assert text.count('"porosity"') <= 4  # legend + one explicit reservoir per sink
    # dropping the edges would lose the timeline, the upgrades and the designs
    assert '"edges"' in text


def test_numeric_keys_are_quoted_so_the_document_is_valid_json():
    """``points`` is keyed by year and ``onboarding_years`` by probability."""

    scenario = commented_json.load_file(THREE_EMITTERS)
    updated = scenario.model_copy(
        update={
            "onboarding_years": {1.0: 2026, 0.5: 2028, 0.1: 2033},
            "emitters": [
                emitter.model_copy(
                    update={
                        "gross_emissions": emitter.gross_emissions.model_copy(
                            update={
                                "kind": "piecewise_linear",
                                "points": {2027: 100_000.0, 2032: 250_000.0},
                                "constant_t_per_year": None,
                            }
                        )
                    }
                )
                for emitter in scenario.emitters
            ],
        }
    )
    # model_copy skips validation, so validate explicitly
    from ccus_core.models import ScenarioConfig

    updated = ScenarioConfig.model_validate(updated.model_dump())
    text = commented_json.dump(updated)

    payload = json.loads(text)  # would raise on a bare {2030: ...}
    assert payload["scenario"]["onboarding_years"]["1.0"] == 2026
    points = payload["scenario"]["emitters"][0]["gross_emissions"]["points"]
    assert points["2027"] == 100_000.0

    reloaded = commented_json.load(text)
    assert reloaded.onboarding_years is not None
    assert reloaded.onboarding_years[1.0] == 2026
    assert reloaded.emitters[0].gross_emissions.points == {2027: 100_000.0, 2032: 250_000.0}


def test_verbose_style_is_still_available():
    scenario = commented_json.load_file(CLUSTER_JSON)
    verbose = commented_json.dump(scenario, style="verbose")
    assert '"unit": "year"' in verbose
    assert len(verbose.splitlines()) > 1000
    reloaded = commented_json.load(verbose)
    assert len(reloaded.emitters) == len(scenario.emitters)


def test_round_trip_preserves_upgrades_states_and_designs():
    scenario = commented_json.load_file(THREE_EMITTERS)
    text = commented_json.dump(scenario)
    reloaded = commented_json.load(text)

    assert len(reloaded.edges) == len(scenario.edges)
    for edge in scenario.edges:
        other = reloaded.edge_by_id(edge.id)
        assert other is not None
        assert other.from_node == edge.from_node
        assert other.to_node == edge.to_node
        assert other.geometry_id == edge.geometry_id
        assert [state.model_dump() for state in other.states] == [
            state.model_dump() for state in edge.states
        ]
        assert [item.model_dump() for item in other.upgrades] == [
            item.model_dump() for item in edge.upgrades
        ]
    # a second round-trip must be byte-identical (nothing is lost or added)
    assert commented_json.dump(reloaded) == text


def test_a_stale_derived_edge_is_refreshed_from_its_connection():
    scenario = commented_json.load_file(CLUSTER_JSON)
    derived_id = scenario.connections[0].edge_id()
    stale = scenario.edge_by_id(derived_id).model_copy(
        update={
            "states": [
                state.model_copy(update={"capacity_t_per_year": 1.0})
                for state in scenario.edge_by_id(derived_id).states
            ]
        }
    )
    payload = scenario.model_copy(update={"edges": [stale]})
    # the connection still declares the real capacity: the edge must be rebuilt
    refreshed = type(scenario).model_validate(payload.model_dump())
    assert refreshed.edge_by_id(derived_id).states[0].capacity_t_per_year == (
        scenario.edge_by_id(derived_id).states[0].capacity_t_per_year
    )


def test_single_chain_example_still_loads():
    single = Path(__file__).resolve().parents[1] / "inputs" / "examples" / "ccus_cluster_v1.json"
    scenario = commented_json.load_file(single)
    assert scenario.id == "adriatic_cluster"
    assert scenario.economics is not None