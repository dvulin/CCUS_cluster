"""Geothermal doublet: engine-side creation, one electricity credit, real pump work.

Each test is the regression that would have caught the corresponding bug:

* a sink flagged ``geothermal_coupled`` had no doublet unless the UI invented one;
* the reinjection pump used a hard-coded efficiency instead of the sink's;
* the availability factors were computed and then ignored, so the annual energy was
  the nameplate energy.
"""

from __future__ import annotations

import pytest

from ccus_core import ScenarioEngine
from ccus_core.models import GeothermalSystem, TransportEdge
from ccus_core.simulation import (
    GeothermalCoupling,
    default_doublet_for_sink,
    ensure_coupled_doublets,
)

from .test_fix_numbers import scenario_with_sinks
from .conftest import pipeline_state


def coupled_scenario(*, with_explicit_system: bool = False):
    sink = {
        "id": "sink_a",
        "name": "Sink A",
        "storage_type": "DSA",
        "capacity_t": 40_000_000.0,
        "commissioning_year": 2028,
        "geothermal_coupled": True,
    }
    scenario = scenario_with_sinks(
        sink_specs=[sink],
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk",
                from_node="plant",
                to_node="sink_node_0",
                states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)],
            )
        ],
    )
    if with_explicit_system:
        explicit = GeothermalSystem(
            id="my_doublet",
            node_id="sink_node_0",
            name="My doublet",
            d_doublet_m=2000.0,
            reservoir_temperature_c=150.0,
            eta_orc=0.18,
            p_out_bar=12.0,
            t_out_c=40.0,
            rw_production_m=0.20,
            rw_injection_m=0.20,
            h_ref_production_m=2000.0,
            h_ref_injection_m=2000.0,
            operation_start_year=2029,
            operation_end_year=2034,
        )
        scenario = scenario.model_copy(
            update={"geothermal_systems": [explicit]}
        )
    return scenario


def test_coupled_sink_gets_exactly_one_doublet_from_the_engine():
    scenario = coupled_scenario()
    assert scenario.geothermal_systems == []

    engine = ScenarioEngine(scenario)
    systems = engine.scenario.geothermal_systems
    assert [system.id for system in systems] == ["sink_a-doublet"]
    doublet = systems[0]
    assert doublet.node_id == scenario.storage_sinks[0].node_id
    assert doublet.operation_start_year == 2028
    assert doublet.operation_end_year == scenario.end_year

    # idempotent: running twice never duplicates the system (and its CAPEX)
    twice = ensure_coupled_doublets(engine.scenario)
    assert len(twice.geothermal_systems) == 1


def test_an_explicit_doublet_wins_over_the_engine_default():
    scenario = coupled_scenario(with_explicit_system=True)
    engine = ScenarioEngine(scenario)
    assert [system.id for system in engine.scenario.geothermal_systems] == ["my_doublet"]


def test_doublet_capex_is_counted_once():
    scenario = coupled_scenario()
    result = ScenarioEngine(scenario).run()
    geothermal_capex = result.cash_flow.set_index("year")["geothermal_capex"]
    paid = {int(year): float(-value) for year, value in geothermal_capex.items() if value < 0.0}
    from ccus_core.simulation.geothermal import DEFAULT_DOUBLET_CAPEX_EUR

    assert paid == {2028: pytest.approx(DEFAULT_DOUBLET_CAPEX_EUR)}


def test_pump_power_uses_the_sink_efficiency():
    scenario = coupled_scenario()
    scenario = scenario.model_copy(
        update={
            "storage_sinks": [
                sink.model_copy(update={"eta_gt_injection_pump": 0.60})
                for sink in scenario.storage_sinks
            ]
        }
    )
    engine = ScenarioEngine(scenario)
    coupling = GeothermalCoupling(
        engine.scenario.geothermal_systems[0],
        engine.scenario.storage_sinks[0].reservoir,
        eta_pump=engine.scenario.storage_sinks[0].eta_gt_injection_pump,
    )
    frame = coupling.simulate({year: 205.0 for year in range(2028, 2035)})

    # a less efficient pump needs more electricity for the same reinjection work
    reference = GeothermalCoupling(
        engine.scenario.geothermal_systems[0],
        engine.scenario.storage_sinks[0].reservoir,
        eta_pump=0.90,
    ).simulate({year: 205.0 for year in range(2028, 2035)})
    assert frame.attrs["pump_efficiency"] == pytest.approx(0.60)
    assert float(frame["pump_power_kw"].iloc[0]) > float(reference["pump_power_kw"].iloc[0]) + 1e-9
    # a lower efficiency can never produce less electrical output for the same well
    assert float(frame["net_power_kw"].iloc[0]) < float(reference["net_power_kw"].iloc[0])


def test_availability_derates_the_annual_energy():
    scenario = coupled_scenario()
    engine = ScenarioEngine(scenario)
    system = engine.scenario.geothermal_systems[0]
    sink = engine.scenario.storage_sinks[0]
    pressures = {year: 205.0 for year in range(2028, 2035)}
    reference = GeothermalCoupling(system, sink.reservoir, eta_pump=0.9).simulate(pressures)

    # ORC availability derates the electrical output, not the reinjection work
    orc_half = GeothermalCoupling(
        system.model_copy(update={"orc_availability": 0.5}), sink.reservoir, eta_pump=0.9
    ).simulate(pressures)
    assert float(orc_half["orc_power_kw"].iloc[0]) == pytest.approx(
        float(reference["orc_power_kw"].iloc[0]) * 0.5, rel=1e-9
    )
    assert float(orc_half["pump_power_kw"].iloc[0]) == pytest.approx(
        float(reference["pump_power_kw"].iloc[0]), rel=1e-9
    )

    # pump availability derates the pumping load, not the ORC output
    pump_half = GeothermalCoupling(
        system.model_copy(update={"pump_availability": 0.5}), sink.reservoir, eta_pump=0.9
    ).simulate(pressures)
    assert float(pump_half["pump_power_kw"].iloc[0]) == pytest.approx(
        float(reference["pump_power_kw"].iloc[0]) * 0.5, rel=1e-9
    )
    assert float(pump_half["orc_power_kw"].iloc[0]) == pytest.approx(
        float(reference["orc_power_kw"].iloc[0]), rel=1e-9
    )

    # well availability scales the produced (and reinjected) mass flow
    wells_half = GeothermalCoupling(
        system.model_copy(
            update={
                "production_well_availability": 0.5,
                "injection_well_availability": 0.5,
            }
        ),
        sink.reservoir,
        eta_pump=0.9,
    ).simulate(pressures)
    assert float(wells_half["production_flow_kg_s"].iloc[0]) == pytest.approx(
        float(reference["production_flow_kg_s"].iloc[0]) * 0.5, rel=1e-9
    )
    assert float(wells_half["net_power_kw"].iloc[0]) < float(
        reference["net_power_kw"].iloc[0]
    )

    # the combined availability is the annual derating reported to the ledger
    combined = GeothermalCoupling(
        system.model_copy(
            update={
                "orc_availability": 0.5,
                "pump_availability": 0.5,
                "production_well_availability": 0.5,
                "injection_well_availability": 0.5,
            }
        ),
        sink.reservoir,
        eta_pump=0.9,
    ).simulate(pressures)
    assert combined.attrs["available_hours_per_year"] == pytest.approx(8766.0 * 0.5)


def test_electricity_is_credited_once_in_the_ledger():
    """Export and import are mutually exclusive: no kWh is sold and bought."""

    scenario = coupled_scenario()
    result = ScenarioEngine(scenario).run()

    assert result.ledger is not None
    ledger = result.ledger
    assert (ledger["electricity_export_mwh"] >= 0.0).all()
    assert (ledger["electricity_import_mwh"] >= 0.0).all()
    # exactly one of the two is non-zero every year
    both = (ledger["electricity_export_mwh"] > 0.0) & (ledger["electricity_import_mwh"] > 0.0)
    assert not bool(both.any())
    net = ledger["electricity_export_mwh"] - ledger["electricity_import_mwh"]
    expected = ledger["orc_gross_mwh"] - ledger["gt_pump_mwh"] - ledger["co2_compressor_mwh"]
    assert net.to_numpy() == pytest.approx(expected.to_numpy(), abs=1e-6)


def test_default_doublet_helper_matches_the_engine_defaults():
    scenario = coupled_scenario()
    sink = scenario.storage_sinks[0]
    doublet = default_doublet_for_sink(sink, start_year=2028, end_year=2034)
    assert doublet.id == "sink_a-doublet"
    assert doublet.node_id == sink.node_id
    assert doublet.reservoir_temperature_c == pytest.approx(sink.reservoir.temperature_c)
    assert doublet.h_ref_production_m == pytest.approx(sink.reservoir.top_depth_m)

