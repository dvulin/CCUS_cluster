"""Can every emitter reach a storage site?

A scenario can validate and still be useless: an emitter with no link to a sink is
only reported as "unallocated" at the end of a run.  These tests pin the check that
says so up front.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ccus_core.network.connectivity import (
    adjacency,
    connectivity_report,
    reachable_from,
    sink_nodes,
    unreachable_emitters,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "inputs" / "examples" / "ccus_cluster_v1.json"

from ccus_core.io import commented_json  # noqa: E402


def _scenario(links, emitters, sinks, extra_nodes=()):
    """A small scenario: ``links`` are ``(from, to)`` pairs."""

    nodes = [
        {"id": "A", "name": "A", "kind": "junction"},
        {"id": "B", "name": "B", "kind": "junction"},
        {"id": "SINK", "name": "Sink", "kind": "storage"},
        *extra_nodes,
    ]
    payload = {
        "id": "graph",
        "name": "Graph",
        "start_year": 2027,
        "end_year": 2030,
        "nodes": nodes,
        "edges": [
            {
                "id": f"E{index}",
                "name": f"E{index}",
                "from_node": start,
                "to_node": end,
                "states": [
                    {
                        "mode": "pipeline",
                        "valid_from_year": 2027,
                        "capacity_t_per_year": 1000.0,
                        "distance_km": 10.0,
                        "pipeline": {
                            "inner_diameter_m": 0.30,
                            "inlet_pressure_bar": 150.0,
                            "inlet_temperature_c": 20.0,
                        },
                    }
                ],
            }
            for index, (start, end) in enumerate(links)
        ],
        "emitters": [
            {
                "id": emitter,
                "name": emitter.upper(),
                "node_id": node,
                "activation_year": 2027,
                "gross_emissions": {"kind": "constant", "constant_t_per_year": 1000.0},
            }
            for emitter, node in emitters
        ],
        "storage_sinks": [
            {"id": sink, "name": sink, "node_id": node, "capacity_t": 1_000_000.0}
            for sink, node in sinks
        ],
    }
    from ccus_core.models import ScenarioConfig

    return ScenarioConfig.model_validate(payload)


# ------------------------------------------------------------------- the basics
def test_a_connected_emitter_has_no_problem():
    scenario = _scenario([("A", "SINK")], [("src", "A")], [("sink", "SINK")])

    assert unreachable_emitters(scenario) == []
    assert connectivity_report(scenario)["ok"] is True


def test_an_emitter_without_a_link_is_reported():
    scenario = _scenario([], [("src", "A")], [("sink", "SINK")])

    problems = unreachable_emitters(scenario)

    assert len(problems) == 1
    assert problems[0]["emitter_id"] == "src"
    assert "no link starts at 'A'" == problems[0]["reason"]


def test_an_emitter_that_reaches_a_dead_end_is_reported():
    # A -> B, but B has no link to the sink
    scenario = _scenario([("A", "B")], [("src", "A")], [("sink", "SINK")])

    problems = unreachable_emitters(scenario)

    assert len(problems) == 1
    assert "no path from 'A' to a storage hub" == problems[0]["reason"]


def test_a_two_hop_path_is_enough():
    scenario = _scenario(
        [("A", "B"), ("B", "SINK")], [("src", "A")], [("sink", "SINK")]
    )

    assert unreachable_emitters(scenario) == []


def test_an_emitter_injecting_on_the_spot_counts_as_connected():
    scenario = _scenario([], [("src", "SINK")], [("sink", "SINK")])

    assert unreachable_emitters(scenario) == []


def test_a_scenario_without_a_sink_blames_the_scenario():
    """Defensive branch: the model never builds this, but a caller may pass one."""

    from types import SimpleNamespace

    scenario = SimpleNamespace(
        emitters=[
            SimpleNamespace(id="src", name="Source", node_id="A"),
        ],
        storage_sinks=[],
        nodes=[],
        edges=[],
    )

    problems = unreachable_emitters(scenario)

    assert len(problems) == 1
    assert problems[0]["reason"] == "the scenario has no storage sink"


def test_only_the_cut_off_emitters_are_listed():
    scenario = _scenario(
        [("A", "SINK")],
        [("ok", "A"), ("cut", "B")],
        [("sink", "SINK")],
    )

    problems = unreachable_emitters(scenario)

    assert [item["emitter_id"] for item in problems] == ["cut"]


# ------------------------------------------------------------- graph primitives
def test_adjacency_follows_the_direction_of_a_link():
    scenario = _scenario([("A", "B")], [("src", "A")], [("sink", "SINK")])

    assert adjacency(scenario) == {"A": ["B"]}


def test_reachability_is_transitive():
    scenario = _scenario(
        [("A", "B"), ("B", "SINK")], [("src", "A")], [("sink", "SINK")]
    )

    assert reachable_from(scenario, "A") == {"A", "B", "SINK"}
    assert reachable_from(scenario, "SINK") == {"SINK"}


def test_sink_nodes_includes_storage_kinds():
    scenario = _scenario(
        [],
        [("src", "A")],
        [("sink", "SINK")],
        extra_nodes=[{"id": "G", "name": "G", "kind": "geothermal"}],
    )

    assert "SINK" in sink_nodes(scenario)
    assert "G" in sink_nodes(scenario)


# --------------------------------------------------------- the shipped scenarios
@pytest.mark.parametrize(
    "name",
    [
        "inputs/examples/ccus_cluster_v1.json",
        "inputs/examples/cluster_three_emitters.json",
        "inputs/examples/croatia_cluster_2025_2050.json",
    ],
)
def test_the_reference_scenarios_are_connected(name):
    scenario = commented_json.load_file(ROOT / name)

    assert unreachable_emitters(scenario) == []