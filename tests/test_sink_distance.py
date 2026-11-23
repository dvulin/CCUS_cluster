"""How far is the CO2 on a leg still from a storage site?

The designer shows ``total_distance_km`` next to every link, and the rule it uses
is deliberately the one a study reasons with: the distance from the *start* of a
leg to the sink, that leg included.  These tests pin the convention - especially
the last leg, which is worth its own length and not zero - and the multi-sink
behaviour the designer's expander reports.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ccus_core.models import (
    EdgeState,
    EmissionCurve,
    Emitter,
    Node,
    NodeKind,
    PipelineDesign,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
    TransportMode,
)
from ccus_core.network.connectivity import distance_to_sinks, edge_distance_to_sink


def pipeline_state(km: float, *, capacity: float = 1_000_000.0) -> EdgeState:
    return EdgeState(
        mode=TransportMode.PIPELINE,
        valid_from_year=2026,
        distance_km=km,
        capacity_t_per_year=capacity,
        pipeline=PipelineDesign(
            inner_diameter_m=0.30, inlet_pressure_bar=150.0, inlet_temperature_c=20.0
        ),
    )


def leg(edge_id: str, start: str, end: str, km: float, *, bidirectional: bool = False):
    return TransportEdge(
        id=edge_id,
        name=edge_id,
        from_node=start,
        to_node=end,
        bidirectional=bidirectional,
        states=[pipeline_state(km)],
    )


def sink(sink_id: str, node_id: str) -> StorageSink:
    return StorageSink(
        id=sink_id,
        node_id=node_id,
        name=sink_id,
        storage_type=StorageType.DSA,
        capacity_t=1_000_000.0,
    )


def build(edges, sinks) -> ScenarioConfig:
    """A scenario whose nodes are exactly the ones the legs and sinks mention."""

    node_ids: list[str] = []
    for edge in edges:
        for node_id in (edge.from_node, edge.to_node):
            if node_id not in node_ids:
                node_ids.append(node_id)
    for item in sinks:
        if item.node_id not in node_ids:
            node_ids.append(item.node_id)

    return ScenarioConfig(
        id="distance_case",
        name="Distance case",
        start_year=2026,
        end_year=2030,
        nodes=[
            Node(id=node_id, name=node_id, kind=NodeKind.JUNCTION) for node_id in node_ids
        ],
        emitters=[
            Emitter(
                id="src",
                name="Source",
                node_id=node_ids[0],
                activation_year=2026,
                gross_emissions=EmissionCurve.constant(1_000.0),
            )
        ],
        edges=list(edges),
        storage_sinks=list(sinks),
    )


#: emitter -> L2 -> L3 -> L4 -> sink, 10 + 20 + 30 + 40 km
CHAIN = [
    leg("L1", "emitter", "L2", 10.0),
    leg("L2", "L2", "L3", 20.0),
    leg("L3", "L3", "L4", 30.0),
    leg("L4", "L4", "sink", 40.0),
]


def test_every_leg_reports_the_distance_left_to_the_sink():
    scenario = build(CHAIN, [sink("S1", "sink")])

    distances = distance_to_sinks(scenario)

    assert distances["L1"] == {"S1": pytest.approx(100.0)}
    assert distances["L2"] == {"S1": pytest.approx(90.0)}
    assert distances["L3"] == {"S1": pytest.approx(70.0)}


def test_the_leg_that_enters_the_sink_is_worth_its_own_length():
    """The convention the designer documents: L4 = d(L4 -> sink), not zero."""

    scenario = build(CHAIN, [sink("S1", "sink")])

    distances = distance_to_sinks(scenario)

    assert distances["L4"] == {"S1": pytest.approx(40.0)}


def test_a_leg_with_no_path_to_a_sink_is_absent_not_zero():
    scenario = build(
        CHAIN + [leg("dead", "emitter", "nowhere", 5.0)], [sink("S1", "sink")]
    )

    distances = distance_to_sinks(scenario)

    assert "dead" not in distances
    assert edge_distance_to_sink(scenario, "S1") == {
        "L1": pytest.approx(100.0),
        "L2": pytest.approx(90.0),
        "L3": pytest.approx(70.0),
        "L4": pytest.approx(40.0),
    }


def test_a_leg_reaching_two_sinks_reports_both_distances():
    """A hub feeding two storage sites: one value per sink, never an average."""

    edges = CHAIN + [leg("B1", "L2", "X", 5.0), leg("B2", "X", "sink2", 5.0)]
    scenario = build(edges, [sink("S1", "sink"), sink("S2", "sink2")])

    distances = distance_to_sinks(scenario)

    # L1 runs towards L2, from where both sinks are reachable
    assert distances["L1"]["S1"] == pytest.approx(100.0)
    assert distances["L1"]["S2"] == pytest.approx(20.0)  # 10 + 5 + 5
    # L2 itself leads only to S1: the branch leaves *from* its downstream hub
    assert "S2" not in distances["L2"]
    assert distances["B1"] == {"S2": pytest.approx(10.0)}


def test_the_selected_sink_filters_the_mapping():
    scenario = build(
        CHAIN + [leg("B1", "L2", "X", 5.0), leg("B2", "X", "sink2", 5.0)],
        [sink("S1", "sink"), sink("S2", "sink2")],
    )

    assert edge_distance_to_sink(scenario, "S2") == {
        "L1": pytest.approx(20.0),
        "B1": pytest.approx(10.0),
        "B2": pytest.approx(5.0),
    }
    assert "L2" not in edge_distance_to_sink(scenario, "S2")


def test_a_bidirectional_leg_counts_its_cheaper_direction():
    """CO2 may enter a bidirectional leg from either end, so the nearer one wins."""

    scenario = build(
        [leg("L1", "emitter", "hub", 10.0), leg("L2", "hub", "sink", 40.0, bidirectional=True)],
        [sink("S1", "sink")],
    )

    distances = distance_to_sinks(scenario)

    assert distances["L1"] == {"S1": pytest.approx(50.0)}
    assert distances["L2"] == {"S1": pytest.approx(40.0)}


def test_a_cycle_does_not_loop_forever():
    scenario = build(
        [
            leg("L1", "emitter", "hub", 10.0),
            leg("L2", "hub", "emitter", 10.0),
            leg("L3", "hub", "sink", 5.0),
        ],
        [sink("S1", "sink")],
    )

    distances = distance_to_sinks(scenario)

    assert distances["L1"] == {"S1": pytest.approx(15.0)}
    # L2 ends at the emitter, so its CO2 still has to travel back through L1
    assert distances["L2"] == {"S1": pytest.approx(25.0)}


def test_a_scenario_without_storage_has_no_distances():
    """No sink means no distance - the function only needs ``edges``/``storage_sinks``."""

    scenario = SimpleNamespace(edges=CHAIN, storage_sinks=[])

    assert distance_to_sinks(scenario) == {}
    assert edge_distance_to_sink(scenario, "S1") == {}


def test_two_sinks_on_one_node_both_get_the_same_distance():
    """Two storage sites can share a hub; the distance is a property of the node."""

    scenario = build(CHAIN, [sink("S1", "sink"), sink("S2", "sink")])

    distances = distance_to_sinks(scenario)

    assert distances["L1"] == {"S1": pytest.approx(100.0), "S2": pytest.approx(100.0)}