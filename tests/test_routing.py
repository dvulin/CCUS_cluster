"""Routing engine: capacity bottlenecks, upgrades and offshore limits."""

from __future__ import annotations

import pytest

from ccus_core.models import (
    EconomicsConfig,
    EmissionCurve,
    Emitter,
    GeoLocation,
    Node,
    NodeKind,
    PortHub,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
)
from ccus_core.network import NetworkGraph, RoutingEngine

from .conftest import marine_state, pipeline_state, truck_state

YEARS = list(range(2027, 2036))


def build_scenario(
    *,
    edges: list[TransportEdge],
    emitter_capacity_t: float = 400_000.0,
    activation_year: int = 2027,
    sink_capacity_t: float = 10_000_000.0,
) -> ScenarioConfig:
    return ScenarioConfig(
        id="routing_case",
        name="Routing case",
        start_year=2027,
        end_year=2035,
        nodes=[
            Node(id="plant", name="Plant", kind=NodeKind.EMITTER, location=GeoLocation()),
            Node(id="hub", name="Hub", kind=NodeKind.JUNCTION),
            Node(
                id="port",
                name="Port",
                kind=NodeKind.PORT,
                location=GeoLocation(onshore=False, latitude=45.3, longitude=14.4),
                port=PortHub(
                    name="Port",
                    max_throughput_t_per_year=10_000_000.0,
                    load_rate_t_per_day=10_000.0,
                ),
            ),
            Node(id="offshore", name="Offshore", kind=NodeKind.OFFSHORE_TERMINAL, location=GeoLocation(onshore=False)),
            Node(id="sink", name="Sink", kind=NodeKind.STORAGE),
        ],
        emitters=[
            Emitter(
                id="source",
                name="Source",
                node_id="plant",
                activation_year=activation_year,
                gross_emissions=EmissionCurve.constant(emitter_capacity_t),
            )
        ],
        edges=edges,
        storage_sinks=[
            StorageSink(
                id="sink",
                node_id="sink",
                name="Sink",
                storage_type=StorageType.DSA,
                capacity_t=sink_capacity_t,
            )
        ],
        economics=EconomicsConfig(start_year=2027, end_year=2035, capex_start_year=2027),
    )


def route(scenario: ScenarioConfig, year: int):
    graph = NetworkGraph(scenario)
    engine = RoutingEngine(graph)
    supplies = {
        emitter.id: emitter.captured_emissions(year) for emitter in scenario.emitters
    }
    return engine.route(
        year=year,
        supplies=supplies,
        sink_remaining_capacity={sink.id: sink.capacity_t for sink in scenario.storage_sinks},
    )


def test_undersized_edge_leaves_mass_unrouted():
    scenario = build_scenario(
        edges=[
            TransportEdge(
                id="truck",
                name="Truck leg",
                from_node="plant",
                to_node="sink",
                states=[truck_state(valid_from_year=2027, capacity_t_per_year=120_000.0)],
            )
        ]
    )
    result = route(scenario, 2027)
    assert result.total_allocated_t == pytest.approx(120_000.0)
    assert result.unallocated["source"] == pytest.approx(280_000.0)
    assert "unrouted CO2" in " ".join(result.notes)


def test_mid_run_upgrade_lifts_the_bottleneck():
    scenario = build_scenario(
        edges=[
            TransportEdge(
                id="corridor",
                name="Corridor",
                from_node="plant",
                to_node="sink",
                states=[
                    truck_state(valid_from_year=2027, valid_until_year=2030, capacity_t_per_year=120_000.0),
                    pipeline_state(valid_from_year=2031, capacity_t_per_year=1_000_000.0),
                ],
            )
        ]
    )
    early = route(scenario, 2030)
    later = route(scenario, 2031)
    assert early.total_allocated_t == pytest.approx(120_000.0)
    assert later.total_allocated_t == pytest.approx(400_000.0)
    assert later.unallocated == {}
    assert early.allocations[0].path_edge_ids == ["corridor"]


def test_offshore_bottleneck_is_capped_by_vessels_and_weather():
    scenario = build_scenario(
        edges=[
            TransportEdge(
                id="sea",
                name="Sea leg",
                from_node="plant",
                to_node="sink",
                states=[marine_state(valid_from_year=2027, port_node_id="port")],
            )
        ]
    )
    result = route(scenario, 2027)
    # 8 000 t * 6 voyages * 2 vessels * 0.85 weather = 81 600 t
    assert result.total_allocated_t == pytest.approx(81_600.0)
    assert result.unallocated["source"] == pytest.approx(318_400.0)


def test_multi_hop_path_pays_the_sum_of_the_leg_tariffs():
    scenario = build_scenario(
        edges=[
            TransportEdge(
                id="plant_hub",
                name="Plant to hub",
                from_node="plant",
                to_node="hub",
                states=[pipeline_state(valid_from_year=2027, capacity_t_per_year=1_000_000.0, opex_eur_per_t=5.0)],
            ),
            TransportEdge(
                id="hub_sink",
                name="Hub to sink",
                from_node="hub",
                to_node="sink",
                states=[pipeline_state(valid_from_year=2027, capacity_t_per_year=1_000_000.0, opex_eur_per_t=7.0)],
            ),
        ]
    )
    result = route(scenario, 2027)
    assert result.total_allocated_t == pytest.approx(400_000.0)
    assert result.allocations[0].unit_cost_eur_per_t == pytest.approx(12.0)
    assert result.edge_flows == {"plant_hub": pytest.approx(400_000.0), "hub_sink": pytest.approx(400_000.0)}


def test_sink_capacity_is_exhausted_across_years():
    scenario = build_scenario(
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk line",
                from_node="plant",
                to_node="sink",
                states=[pipeline_state(valid_from_year=2027, capacity_t_per_year=1_000_000.0)],
            )
        ],
        sink_capacity_t=500_000.0,
    )
    remaining = 500_000.0
    routed = []
    for year in (2027, 2028):
        engine = RoutingEngine(NetworkGraph(scenario))
        result = engine.route(
            year=year,
            supplies={"source": 400_000.0},
            sink_remaining_capacity={"sink": remaining},
        )
        routed.append(result.total_allocated_t)
        remaining -= result.total_allocated_t
    assert routed[0] == pytest.approx(400_000.0)
    assert routed[1] == pytest.approx(100_000.0)
    assert remaining == pytest.approx(0.0)


def test_cheapest_path_wins_when_two_routes_exist():
    scenario = build_scenario(
        edges=[
            TransportEdge(
                id="direct",
                name="Direct",
                from_node="plant",
                to_node="sink",
                states=[pipeline_state(valid_from_year=2027, capacity_t_per_year=1_000_000.0, opex_eur_per_t=20.0)],
            ),
            TransportEdge(
                id="detour",
                name="Detour",
                from_node="plant",
                to_node="hub",
                states=[pipeline_state(valid_from_year=2027, capacity_t_per_year=1_000_000.0, opex_eur_per_t=2.0)],
            ),
            TransportEdge(
                id="hub_sink",
                name="Hub to sink",
                from_node="hub",
                to_node="sink",
                states=[pipeline_state(valid_from_year=2027, capacity_t_per_year=1_000_000.0, opex_eur_per_t=3.0)],
            ),
        ]
    )
    result = route(scenario, 2027)
    assert result.allocations[0].path_edge_ids == ["detour", "hub_sink"]
    assert result.allocations[0].unit_cost_eur_per_t == pytest.approx(5.0)