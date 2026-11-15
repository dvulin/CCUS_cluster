"""Many-to-many emitter/sink connections, per-pair onboarding and defaults."""

from __future__ import annotations

import pytest

from ccus_core.models import (
    EmitterSinkConnection,
    ReservoirDefaults,
    ScenarioConfig,
    TransportMode,
)


def build(nodes, emitters, sinks, connections, **kwargs):
    return ScenarioConfig(
        id="many",
        name="Many to many",
        start_year=2025,
        end_year=2040,
        nodes=nodes,
        emitters=emitters,
        storage_sinks=sinks,
        connections=connections,
        **kwargs,
    )


NODES = [
    {"id": "a", "name": "A", "kind": "emitter"},
    {"id": "b", "name": "B", "kind": "emitter"},
    {"id": "s1", "name": "S1", "kind": "storage"},
    {"id": "s2", "name": "S2", "kind": "storage"},
]

EMITTERS = [
    {
        "id": "a",
        "name": "A",
        "node_id": "a",
        "activation_year": 2026,
        "gross_emissions": {"kind": "constant", "constant_t_per_year": 400_000.0},
    },
    {
        "id": "b",
        "name": "B",
        "node_id": "b",
        "activation_year": 2026,
        "gross_emissions": {"kind": "constant", "constant_t_per_year": 300_000.0},
    },
]

SINKS = [
    {"id": "s1", "node_id": "s1", "name": "S1", "capacity_t": 5_000_000.0},
    {"id": "s2", "node_id": "s2", "name": "S2", "capacity_t": 5_000_000.0},
]


def test_two_sinks_per_emitter_with_independent_start_years():
    scenario = build(
        NODES,
        EMITTERS,
        SINKS,
        [
            EmitterSinkConnection(
                emitter_id="a", sink_id="s1", start_year=2027, distance_km=40.0, capacity_t_per_year=400_000.0
            ),
            EmitterSinkConnection(
                emitter_id="a", sink_id="s2", start_year=2031, distance_km=90.0, capacity_t_per_year=400_000.0
            ),
        ],
    )
    assert len(scenario.edges) == 2
    by_id = {edge.id: edge for edge in scenario.edges}
    assert by_id["a__to__s1"].states[0].valid_from_year == 2027
    assert by_id["a__to__s2"].states[0].valid_from_year == 2031
    assert scenario.edge_by_id("a__to__s2").resolve_state(2030) is None
    assert scenario.edge_by_id("a__to__s2").resolve_state(2031) is not None


def test_many_emitters_can_share_one_sink():
    scenario = build(
        NODES,
        EMITTERS,
        SINKS,
        [
            EmitterSinkConnection(emitter_id="a", sink_id="s1", start_year=2026, distance_km=10.0),
            EmitterSinkConnection(emitter_id="b", sink_id="s1", start_year=2030, distance_km=20.0),
        ],
    )
    assert len(scenario.edges) == 2
    assert {edge.from_node for edge in scenario.edges} == {"a", "b"}
    assert {edge.to_node for edge in scenario.edges} == {"s1"}


def test_duplicate_connection_is_rejected():
    with pytest.raises(ValueError, match="duplicate connection"):
        build(
            NODES,
            EMITTERS,
            SINKS,
            [
                EmitterSinkConnection(emitter_id="a", sink_id="s1", start_year=2026),
                EmitterSinkConnection(emitter_id="a", sink_id="s1", start_year=2028),
            ],
        )


def test_unknown_sink_in_connection_is_rejected():
    with pytest.raises(ValueError, match="unknown storage sink"):
        build(NODES, EMITTERS, SINKS, [EmitterSinkConnection(emitter_id="a", sink_id="ghost", start_year=2026)])


def test_storage_defaults_are_applied_to_new_sites():
    scenario = build(NODES, EMITTERS, SINKS, [])
    for sink in scenario.storage_sinks:
        assert sink.reservoir is not None
        assert sink.reservoir.porosity == pytest.approx(0.20)
        assert sink.reservoir.permeability_m2 == pytest.approx(1.0e-13)  # 100 mD
        assert sink.reservoir.top_depth_m == pytest.approx(1500.0)


def test_defaults_can_be_overridden_per_scenario():
    scenario = build(
        NODES,
        EMITTERS,
        SINKS,
        [],
        storage_defaults=ReservoirDefaults(porosity=0.3, permeability_m2=5e-14, top_depth_m=2000.0),
    )
    sink = scenario.sink_by_id("s1")
    assert sink.reservoir.porosity == pytest.approx(0.3)
    assert sink.reservoir.permeability_m2 == pytest.approx(5e-14)
    assert sink.reservoir.top_depth_m == pytest.approx(2000.0)


def test_transport_mode_defaults_to_pipeline():
    scenario = build(
        NODES,
        EMITTERS,
        SINKS,
        [EmitterSinkConnection(emitter_id="a", sink_id="s1", start_year=2026)],
    )
    edge = scenario.edges[0]
    assert edge.states[0].mode is TransportMode.PIPELINE
    assert edge.states[0].pipeline is not None