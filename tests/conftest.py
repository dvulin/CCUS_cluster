"""Shared fixtures for the core-model test suite (no Streamlit, no physics)."""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run the slow golden regression test of the legacy ScenarioRunner",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long-running regression test (needs --runslow)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        return
    skip_slow = pytest.mark.skip(reason="needs --runslow")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)

from ccus_core.models import (
    EconomicsConfig,
    EdgeState,
    EmissionCurve,
    Emitter,
    GeoLocation,
    InfrastructureUpgrade,
    MarineDesign,
    Node,
    NodeKind,
    PipelineDesign,
    PortHub,
    PricePath,
    RoadDesign,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
    TransportMode,
    UpgradeTrigger,
)


def pipeline_state(
    *,
    valid_from_year: int,
    capacity_t_per_year: float,
    distance_km: float = 40.0,
    capex_eur: float = 25_000_000.0,
    opex_eur_per_t: float = 15.0,
    valid_until_year: int | None = None,
) -> EdgeState:
    return EdgeState(
        mode=TransportMode.PIPELINE,
        valid_from_year=valid_from_year,
        valid_until_year=valid_until_year,
        capacity_t_per_year=capacity_t_per_year,
        distance_km=distance_km,
        capex_eur=capex_eur,
        opex_eur_per_t=opex_eur_per_t,
        pipeline=PipelineDesign(
            inner_diameter_m=0.30,
            inlet_pressure_bar=150.0,
            inlet_temperature_c=20.0,
        ),
    )


def truck_state(
    *,
    valid_from_year: int,
    capacity_t_per_year: float = 120_000.0,
    distance_km: float = 25.0,
    valid_until_year: int | None = None,
    fleet_size: int | None = 10,
    capex_eur: float = 1_500_000.0,
) -> EdgeState:
    return EdgeState(
        mode=TransportMode.TRUCK,
        valid_from_year=valid_from_year,
        valid_until_year=valid_until_year,
        capacity_t_per_year=capacity_t_per_year,
        distance_km=distance_km,
        capex_eur=capex_eur,
        opex_eur_per_t=8.0,
        opex_eur_per_tkm=0.35,
        road=RoadDesign(
            vehicle_capacity_t=25.0,
            trips_per_vehicle_per_day=2.0,
            working_days_per_year=250.0,
            fleet_size=fleet_size,
        ),
    )


def marine_state(
    *,
    valid_from_year: int,
    capacity_t_per_year: float = 400_000.0,
    port_node_id: str = "port_rijeka",
) -> EdgeState:
    return EdgeState(
        mode=TransportMode.MARINE,
        valid_from_year=valid_from_year,
        capacity_t_per_year=capacity_t_per_year,
        distance_km=180.0,
        capex_eur=8_000_000.0,
        opex_eur_per_t=22.0,
        marine=MarineDesign(
            vessel_capacity_t=8_000.0,
            voyages_per_vessel_per_year=6.0,
            vessels=2,
            port_node_id=port_node_id,
            weather_availability=0.85,
        ),
    )


@pytest.fixture
def base_nodes() -> list[Node]:
    return [
        Node(id="plant_nexe", name="NEXE", kind=NodeKind.EMITTER, location=GeoLocation(onshore=True)),
        Node(id="plant_plomin", name="Plomin", kind=NodeKind.EMITTER, location=GeoLocation(onshore=True)),
        Node(id="hub_central", name="Central hub", kind=NodeKind.JUNCTION),
        Node(
            id="port_rijeka",
            name="Rijeka port",
            kind=NodeKind.PORT,
            location=GeoLocation(onshore=False, latitude=45.33, longitude=14.44),
            port=PortHub(
                name="Rijeka terminal",
                berths=2,
                max_throughput_t_per_year=600_000.0,
                load_rate_t_per_day=2_000.0,
                weather_availability=0.9,
            ),
        ),
        Node(
            id="offshore_jugo",
            name="Offshore sink Jugo",
            kind=NodeKind.OFFSHORE_TERMINAL,
            location=GeoLocation(onshore=False, latitude=42.40, longitude=16.20),
        ),
        Node(id="sink_poljana", name="Poljana DSA", kind=NodeKind.STORAGE),
    ]


@pytest.fixture
def staggered_emitters() -> list[Emitter]:
    return [
        Emitter(
            id="nexe",
            name="NEXE",
            node_id="plant_nexe",
            activation_year=2028,
            gross_emissions=EmissionCurve.constant(400_000.0),
            capture=None,
        ),
        Emitter(
            id="plomin",
            name="Plomin",
            node_id="plant_plomin",
            activation_year=2031,
            gross_emissions=EmissionCurve.ramp(
                start_year=2031,
                start_t_per_year=100_000.0,
                plateau_year=2033,
                plateau_t_per_year=300_000.0,
                decline_year=2045,
                decline_t_per_year=50_000.0,
            ),
        ),
    ]


@pytest.fixture
def sample_scenario(base_nodes, staggered_emitters) -> ScenarioConfig:
    return ScenarioConfig(
        id="demo_cluster",
        name="Demo cluster",
        start_year=2027,
        end_year=2045,
        nodes=base_nodes,
        emitters=staggered_emitters,
        edges=[
            TransportEdge(
                id="nexe_to_hub",
                name="NEXE to hub (truck then pipeline)",
                from_node="plant_nexe",
                to_node="hub_central",
                states=[
                    truck_state(valid_from_year=2027, valid_until_year=2030),
                    pipeline_state(valid_from_year=2031, capacity_t_per_year=1_000_000.0),
                ],
                upgrades=[
                    InfrastructureUpgrade(
                        id="truck_to_pipeline",
                        trigger=UpgradeTrigger(kind="year", year=2031),
                        new_state=pipeline_state(valid_from_year=2031, capacity_t_per_year=1_000_000.0),
                    )
                ],
            ),
            TransportEdge(
                id="hub_to_port",
                name="Hub to port",
                from_node="hub_central",
                to_node="port_rijeka",
                states=[pipeline_state(valid_from_year=2027, capacity_t_per_year=900_000.0)],
            ),
            TransportEdge(
                id="port_to_offshore",
                name="Rijeka to offshore",
                from_node="port_rijeka",
                to_node="offshore_jugo",
                states=[marine_state(valid_from_year=2027)],
            ),
        ],
        storage_sinks=[
            StorageSink(
                id="poljana",
                node_id="sink_poljana",
                name="Poljana",
                storage_type=StorageType.DSA,
                capacity_t=9_308_000.0,
            )
        ],
        economics=EconomicsConfig(
            start_year=2027,
            end_year=2045,
            capex_start_year=2028,
            price_path=PricePath(
                mode="conservative",
                start_year=2025,
                values_eur_per_t=[64, 68, 71, 75, 79, 82, 83, 87, 89, 92, 93, 95, 97, 99, 100, 103, 105, 107, 111, 114, 118],
            ),
        ),
    )