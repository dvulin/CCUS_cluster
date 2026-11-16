"""Pressure cascade along hub chains (Holcim → hub → hub → Ivanić, NEXE → Drava)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccus_core.models import ScenarioConfig
from ccus_core.network.pressure import LegSpec, solve_chain

from .test_solver import build_solver_scenario

CLUSTER = Path(__file__).resolve().parents[1] / "inputs" / "examples" / "cluster_three_emitters.json"


def _fluid_props():
    from engineering import FluidProperties

    return FluidProperties()


def test_backwards_cascade_adds_friction_to_the_target():
    fluid = _fluid_props()
    legs = [
        LegSpec(edge_id="holcim_hub", from_node="holcim", to_node="hub_plomin", length_m=30_000.0, flow_kg_s=18.0),
        LegSpec(edge_id="hub_ivanic", from_node="hub_plomin", to_node="hub_ivanic", length_m=200_000.0, flow_kg_s=18.0),
    ]
    states = solve_chain(legs, target_outlet_bar=10.0, fluid_props=fluid)

    # downstream leg ends exactly at the storage target
    assert states[-1].outlet_pressure_bar == pytest.approx(10.0)
    # every upstream leg adds its own friction loss
    assert states[0].inlet_pressure_bar > states[1].inlet_pressure_bar
    assert states[1].inlet_pressure_bar == pytest.approx(
        states[0].outlet_pressure_bar
    )
    # Holcim must deliver 230 km worth of friction above 10 bar
    assert states[0].inlet_pressure_bar > 10.0


def test_longer_leg_needs_more_pressure():
    fluid = _fluid_props()
    short = solve_chain(
        [LegSpec(edge_id="a", from_node="x", to_node="s", length_m=10_000.0, flow_kg_s=20.0)],
        fluid_props=fluid,
    )[0]
    long = solve_chain(
        [LegSpec(edge_id="b", from_node="x", to_node="s", length_m=200_000.0, flow_kg_s=20.0)],
        fluid_props=fluid,
    )[0]
    assert long.inlet_pressure_bar > short.inlet_pressure_bar
    assert long.dp_bar > short.dp_bar


def test_cluster_scenario_reports_pressures_per_year():
    from ccus_core import ScenarioEngine
    from ccus_core.io import load_file

    scenario = load_file(CLUSTER)
    result = ScenarioEngine(scenario).run()

    assert result.pressures is not None and not result.pressures.empty
    first_year = result.pressures[result.pressures["year"] == 2028]
    holcim = first_year[first_year["emitter_id"] == "holcim"]
    # 2028: Holcim uses the 30 km leg, the 200 km trunk and the 5 km site leg
    assert len(holcim) == 3
    assert holcim["p_out_bar"].min() == pytest.approx(10.0, abs=1e-6)
    assert holcim["p_in_bar"].max() > 10.0

    later = result.pressures[(result.pressures["year"] == 2031) & (result.pressures["emitter_id"] == "holcim")]
    # 2031: Plomin joined, so the shared trunk is recomputed for the larger flow
    assert not later.empty
    trunk_2028 = holcim.loc[holcim["edge_id"] == "hub_ivanic", "p_in_bar"].max()
    trunk_2031 = later.loc[later["edge_id"] == "hub_ivanic", "p_in_bar"].max()
    assert trunk_2031 > trunk_2028

    # both emitters see the same trunk pressure in that year
    plomin = result.pressures[(result.pressures["year"] == 2031) & (result.pressures["emitter_id"] == "plomin")]
    assert plomin.loc[plomin["edge_id"] == "hub_ivanic", "p_in_bar"].max() == pytest.approx(trunk_2031)


def test_legacy_scenario_still_runs_with_pressure_table():
    from ccus_core import ScenarioEngine

    result = ScenarioEngine(build_solver_scenario()).run()
    assert result.pressures is not None
    assert set(result.pressures["emitter_id"]) == {"source"}