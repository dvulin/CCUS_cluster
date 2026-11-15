"""Multi-modal transport states, temporal upgrades and capacity limits."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ccus_core.models import (
    EdgeState,
    InfrastructureUpgrade,
    RoadDesign,
    TransportEdge,
    TransportMode,
    UpgradeTrigger,
)

from .conftest import marine_state, pipeline_state, truck_state


def build_edge(*, upgrades=None) -> TransportEdge:
    return TransportEdge(
        id="corridor",
        name="Truck then pipeline corridor",
        from_node="plant_nexe",
        to_node="sink_poljana",
        states=[
            truck_state(valid_from_year=2027, valid_until_year=2030),
            pipeline_state(valid_from_year=2031, capacity_t_per_year=1_000_000.0),
        ],
        upgrades=upgrades or [],
    )


def test_planned_upgrade_switches_mode_and_capacity():
    edge = build_edge()

    early = edge.resolve_state(2030)
    later = edge.resolve_state(2031)

    assert early is not None and early.mode is TransportMode.TRUCK
    assert early.effective_capacity_t_per_year() == pytest.approx(120_000.0)
    assert later is not None and later.mode is TransportMode.PIPELINE
    assert later.effective_capacity_t_per_year() == pytest.approx(1_000_000.0)


def test_tariff_follows_the_active_mode():
    edge = build_edge()
    # truck: 8 EUR/t + 0.35 EUR/(t km) * 25 km
    assert edge.tariff_in(2029) == pytest.approx(16.75)
    # pipeline: flat 15 EUR/t
    assert edge.tariff_in(2032) == pytest.approx(15.0)


def test_no_state_before_the_timeline_starts():
    edge = build_edge()
    assert edge.resolve_state(2026) is None
    assert edge.capacity_in(2026) == 0.0
    assert edge.tariff_in(2026) == 0.0


def test_conditional_mass_upgrade_fires_only_after_the_threshold_is_recorded():
    upgrade = InfrastructureUpgrade(
        id="build_pipeline",
        trigger=UpgradeTrigger(kind="cumulative_mass", threshold_t=500_000.0),
        new_state=pipeline_state(
            valid_from_year=2032,
            capacity_t_per_year=800_000.0,
            capex_eur=30_000_000.0,
        ),
        lead_time_years=1,
    )
    edge = TransportEdge(
        id="conditional",
        name="Conditional corridor",
        from_node="plant_nexe",
        to_node="sink_poljana",
        states=[truck_state(valid_from_year=2027)],
        upgrades=[upgrade],
    )

    # threshold not yet reached: trucks stay in service
    assert edge.resolve_state(2032, cumulative_mass_t=400_000.0).mode is TransportMode.TRUCK
    # threshold crossed this year: the upgrade still needs its lead time
    assert edge.resolve_state(2032, cumulative_mass_t=600_000.0).mode is TransportMode.TRUCK
    # solver recorded the firing year 2032 -> new state in force from 2033
    assert edge.resolve_state(2033, fired_upgrades={"build_pipeline": 2032}).mode is TransportMode.PIPELINE
    assert edge.resolve_state(2033, fired_upgrades={"build_pipeline": 2032}).capacity_t_per_year == pytest.approx(
        800_000.0
    )


def test_year_trigger_with_lead_time():
    upgrade = InfrastructureUpgrade(
        id="phase_two",
        trigger=UpgradeTrigger(kind="year", year=2035),
        new_state=pipeline_state(valid_from_year=2035, capacity_t_per_year=500_000.0),
        lead_time_years=2,
    )
    edge = TransportEdge(
        id="phased",
        name="Phased corridor",
        from_node="plant_nexe",
        to_node="sink_poljana",
        states=[truck_state(valid_from_year=2027)],
        upgrades=[upgrade],
    )
    assert edge.resolve_state(2036).mode is TransportMode.TRUCK
    assert edge.resolve_state(2037).mode is TransportMode.PIPELINE


def test_marine_capacity_is_derated_by_weather_and_limited_by_the_port():
    state = marine_state(valid_from_year=2027)
    assert state.marine is not None
    # 8 000 t * 6 voyages * 2 vessels = 96 000 t/yr nominal
    assert state.marine.nominal_capacity_t_per_year() == pytest.approx(96_000.0)
    # weather availability 0.85 -> 81 600 t/yr
    assert state.marine.effective_capacity_t_per_year() == pytest.approx(81_600.0)

    edge = TransportEdge(
        id="sea",
        name="Sea leg",
        from_node="port_rijeka",
        to_node="offshore_jugo",
        states=[state],
    )
    assert edge.capacity_in(2028) == pytest.approx(81_600.0)


def test_road_fleet_sizing():
    road = RoadDesign(
        vehicle_capacity_t=25.0,
        trips_per_vehicle_per_day=2.0,
        working_days_per_year=250.0,
    )
    assert road.annual_capacity_per_vehicle_t() == pytest.approx(12_500.0)
    assert road.required_fleet_size(100_000.0) == 8
    assert road.required_fleet_size(0.0) == 0
    assert road.required_fleet_size(12_500.0) == 1


def test_overlapping_state_windows_are_rejected():
    with pytest.raises(ValidationError):
        TransportEdge(
            id="overlap",
            name="Overlapping",
            from_node="plant_nexe",
            to_node="sink_poljana",
            states=[
                truck_state(valid_from_year=2027, valid_until_year=2030),
                pipeline_state(valid_from_year=2030, capacity_t_per_year=500_000.0),
            ],
        )


def test_mode_specific_design_is_required():
    with pytest.raises(ValidationError):
        EdgeState(mode=TransportMode.PIPELINE, valid_from_year=2027, capacity_t_per_year=1_000.0)

    with pytest.raises(ValidationError):
        EdgeState(mode=TransportMode.MARINE, valid_from_year=2027, capacity_t_per_year=1_000.0)