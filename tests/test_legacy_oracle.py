"""Golden regression test of the legacy single-chain :class:`ScenarioRunner`.

The legacy runner is kept as the oracle for the new engine: it is slow (about 45 s)
and prints a progress log, so it only runs with ``--runslow``.  The expected values
below were captured from the unmodified ``gt-ccs-streamlit`` code with
``inputs/examples/main_inputs.json``; if they change, the physics changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "stored_co2_mt": 9.10,
    "final_storage_pressure_bar": 276.0935,
    "max_co2_bhp_bar": 334.0208,
    "compressor_nameplate_power_kw": 1301.2529,
    "final_geothermal_temperature_c": 150.0,
    "max_net_geothermal_power_kw": 2444.0264,
    "npv_eur": -481_637_164.59,
    "irr": -0.1356,
}


def test_legacy_scenario_runner_matches_the_captured_baseline():
    import sys

    sys.path.insert(0, str(REPOSITORY_ROOT))
    from services.scenario_runner import ScenarioRunner

    results = ScenarioRunner().run()
    kpis = results["operational_kpis"]
    economics = results["economic_kpis"]

    assert kpis["stored_co2_mt"] == pytest.approx(EXPECTED["stored_co2_mt"], rel=1e-3)
    assert kpis["final_storage_pressure_bar"] == pytest.approx(
        EXPECTED["final_storage_pressure_bar"], rel=1e-6
    )
    assert kpis["max_co2_bhp_bar"] == pytest.approx(EXPECTED["max_co2_bhp_bar"], rel=1e-6)
    assert kpis["compressor_nameplate_power_kw"] == pytest.approx(
        EXPECTED["compressor_nameplate_power_kw"], rel=1e-6
    )
    assert kpis["max_net_geothermal_power_kw"] == pytest.approx(
        EXPECTED["max_net_geothermal_power_kw"], rel=1e-6
    )
    assert economics["npv_eur"] == pytest.approx(EXPECTED["npv_eur"], rel=1e-4)
    assert economics["irr"] == pytest.approx(EXPECTED["irr"], abs=1e-3)

    ledger = results["annual_technical_ledger"]
    assert len(ledger) == 24  # 2027-2050 inclusive
    assert ledger["co2_chain_t"].sum() == pytest.approx(9_100_000.0, rel=1e-3)