"""Chronological solver: coupling of routing, reservoir, geothermal and finance."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccus_core import ScenarioEngine
from ccus_core.models import (
    EconomicsConfig,
    EmissionCurve,
    Emitter,
    GeothermalSystem,
    ReservoirProperties,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
)
from ccus_core.simulation import ChronologicalSolver, VariableRateReservoir

from .conftest import pipeline_state

EXAMPLE = Path(__file__).resolve().parents[1] / "inputs" / "examples" / "ccus_cluster_v1.json"


def build_solver_scenario() -> ScenarioConfig:
    from ccus_core.models import GeoLocation, Node, NodeKind

    reservoir = ReservoirProperties(
        area_m2=225_000_000.0,
        effective_thickness_m=155.0,
        porosity=0.15,
        top_depth_m=2000.0,
        temperature_c=150.0,
        reference_pressure_bar=200.0,
        pressure_step_bar=0.5,
        permeability_m2=5e-14,
    )
    return ScenarioConfig(
        id="solver_case",
        name="Solver case",
        start_year=2028,
        end_year=2032,
        nodes=[
            Node(id="plant", name="Plant", kind=NodeKind.EMITTER, location=GeoLocation()),
            Node(id="sink", name="Sink", kind=NodeKind.STORAGE),
        ],
        emitters=[
            Emitter(
                id="source",
                name="Source",
                node_id="plant",
                activation_year=2028,
                gross_emissions=EmissionCurve.constant(700_000.0),
            )
        ],
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk",
                from_node="plant",
                to_node="sink",
                states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=1_000_000.0)],
            )
        ],
        storage_sinks=[
            StorageSink(
                id="sink",
                node_id="sink",
                name="Sink",
                storage_type=StorageType.DSA,
                capacity_t=9_308_000.0,
                commissioning_year=2028,
                capex_eur=150_000_000.0,
                opex_eur_per_t=10.0,
                reservoir=reservoir,
            )
        ],
        geothermal_systems=[
            GeothermalSystem(
                id="doublet",
                node_id="sink",
                name="Doublet",
                d_doublet_m=1500.0,
                reservoir_temperature_c=150.0,
                eta_orc=0.2,
                p_out_bar=10.0,
                t_out_c=35.0,
                rw_production_m=0.15,
                rw_injection_m=0.15,
                h_ref_production_m=2075.0,
                h_ref_injection_m=2075.0,
                operation_start_year=2028,
                operation_end_year=2032,
                capex_eur=50_000_000.0,
                fixed_opex_eur_per_year=1_500_000.0,
            )
        ],
        economics=EconomicsConfig(start_year=2028, end_year=2032, capex_start_year=2028),
    )


def test_reservoir_curve_matches_the_legacy_constant_rate_case():
    """The variable-rate wrapper must invert the legacy pressure ramp exactly."""

    scenario = build_solver_scenario()
    sink = scenario.storage_sinks[0]
    reservoir = VariableRateReservoir(sink)
    curve = reservoir.capacity_curve()
    # 700 kt/yr * 13 years is the planned 2028-2040 window of the reference case
    schedule = {year: 700_000.0 for year in range(2028, 2041)}
    frame = reservoir.simulate(schedule)

    expected_final_mass_t = 9_100_000.0  # legacy result before the capacity limit
    assert frame["co2_cumulative_t"].iloc[-1] == pytest.approx(expected_final_mass_t, rel=0.02)
    # the legacy constant-rate run (services.ScenarioRunner) ends at 276.09 bar
    assert frame["pressure_bar"].iloc[-1] == pytest.approx(276.0935, rel=1e-3)
    assert frame["pressure_bar"].is_monotonic_increasing
    assert frame["bhp_bar"].iloc[2] > frame["pressure_bar"].iloc[2]


def test_solver_runs_end_to_end():
    scenario = build_solver_scenario()
    result = ChronologicalSolver(scenario).run()

    assert result.ledger is not None
    assert len(result.ledger) == 5
    assert result.ledger["co2_chain_t"].sum() == pytest.approx(3_500_000.0)
    assert result.ledger["co2_stored_cumulative_t"].iloc[-1] == pytest.approx(3_500_000.0)
    assert set(result.reservoir) == {"sink"}
    assert set(result.geothermal) == {"doublet"}

    reservoir = result.reservoir["sink"]
    assert reservoir["pressure_bar"].is_monotonic_increasing
    assert reservoir["pressure_bar"].iloc[0] > 200.0  # end of the first injection year
    assert reservoir["bhp_bar"].iloc[0] > 200.0

    geothermal = result.geothermal["doublet"]
    assert geothermal["operating"].any()
    assert (geothermal["orc_power_kw"] >= 0.0).all()
    assert (geothermal["net_power_kw"] <= geothermal["orc_power_kw"] + 1e-9).all()

    assert result.cash_flow is not None
    assert "cumulative_npv" in result.cash_flow.columns
    assert result.kpis["stored_co2_t"] == pytest.approx(3_500_000.0)
    assert result.kpis["npv_eur"] is not None


def test_snapshot_supports_timeline_scrubbing():
    scenario = build_solver_scenario()
    result = ScenarioEngine(scenario).run()

    first = ScenarioEngine(scenario).snapshot(result, 2028)
    assert first.totals["captured_t"] == pytest.approx(700_000.0)
    assert first.totals["routed_t"] == pytest.approx(700_000.0)
    assert first.edges[0]["mode"] == "pipeline"
    assert first.sinks[0]["injected_t"] == pytest.approx(700_000.0)

    last = ScenarioEngine(scenario).snapshot(result, 2032)
    assert last.sinks[0]["cumulative_t"] == pytest.approx(3_500_000.0)
    assert last.totals["stored_t"] == pytest.approx(3_500_000.0)


def test_example_scenario_file_is_valid():
    engine = ScenarioEngine.from_json(EXAMPLE)
    scenario = engine.scenario
    assert scenario.summary()["counts"]["emitters"] == 3
    assert scenario.summary()["counts"]["edges"] == 6
    assert scenario.summary()["first_onboarding_year"] == 2028

    edge = scenario.edge_by_id("nexe_hub")
    assert edge is not None
    assert edge.resolve_state(2029).mode.value == "truck"
    assert edge.resolve_state(2032).mode.value == "pipeline"