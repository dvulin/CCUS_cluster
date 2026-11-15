"""Emission-change curves, policy rules and the commented JSON format."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccus_core.io import commented_json, load
from ccus_core.models import (
    EmissionCurve,
    Emitter,
    EtsAllowanceSchedule,
    FinancialParameters,
    PolicyConfig,
    ScenarioConfig,
    TransportCostParameters,
)
from ccus_core.models.scenario import DEFAULT_ONBOARDING_YEARS

WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "examples" / "CCS TABLICE 2015-2022 example.xlsx"


def test_power_law_matches_the_workbook_values():
    """TE PLOMIN: E0=1 118 203.087 t (2025), a=-0.03, c=1.5."""

    curve = EmissionCurve.power_law(e0_t_per_year=1_118_203.087, reference_year=2025, a=-0.03, c=1.5)
    assert curve.value_at(2025) == pytest.approx(1_118_203.087, rel=1e-9)
    assert curve.value_at(2026) == pytest.approx(1_084_656.9944, rel=1e-9)
    assert curve.value_at(2028) == pytest.approx(943_892.4766, rel=1e-9)
    assert curve.value_at(2035) == pytest.approx(57_382.4945, rel=1e-6)
    assert curve.value_at(2036) == 0.0


def test_power_law_holds_the_base_value_before_the_reference_year():
    curve = EmissionCurve.power_law(e0_t_per_year=1_000.0, reference_year=2030, a=-0.05)
    assert curve.value_at(2025) == pytest.approx(1_000.0)
    assert curve.value_at(2030) == pytest.approx(1_000.0)
    assert curve.value_at(2031) < 1_000.0


def test_net_zero_year_is_the_first_zero_year():
    plomin = EmissionCurve.power_law(e0_t_per_year=1_118_203.087, reference_year=2025, a=-0.03, c=1.5)
    zagreb = EmissionCurve.power_law(e0_t_per_year=908_701.999, reference_year=2025, a=-0.025, c=1.5)
    assert plomin.net_zero_year() == 2036
    assert zagreb.net_zero_year() == 2037


def test_ets_allowance_phase_out_matches_the_thesis_schedule():
    ets = EtsAllowanceSchedule()
    assert [step.free_allowance_share for step in ets.steps] == [0.50, 0.475, 0.425, 0.325, 0.175, 0.0]
    assert ets.share_in(2024) == pytest.approx(0.50)
    assert ets.share_in(2025) == pytest.approx(0.50)
    assert ets.share_in(2028) == pytest.approx(0.325)
    assert ets.share_in(2030) == pytest.approx(0.0)
    assert ets.share_in(2045) == pytest.approx(0.0)
    # 1 Mt in 2028 -> 325 kt free, 675 kt paid
    assert ets.taxable_emissions(2028, 1_000_000.0) == pytest.approx(675_000.0)
    assert ets.taxable_emissions(2031, 1_000_000.0) == pytest.approx(1_000_000.0)


def test_transport_opex_rule():
    costs = TransportCostParameters()
    assert costs.opex_eur_per_t(0.0) == pytest.approx(15.0)
    assert costs.opex_eur_per_t(40.0) == pytest.approx(15.0)
    assert costs.opex_eur_per_t(45.0) == pytest.approx(15.0)
    # workbook: 221 km -> 38.7596 EUR/t
    assert costs.opex_eur_per_t(221.0) == pytest.approx(38.759579433, rel=1e-9)


def test_fisher_nominal_rate_is_12_36_percent():
    financial = FinancialParameters(real_rate=0.06, inflation_rate=0.06)
    assert financial.nominal_rate == pytest.approx(0.1236, rel=1e-9)


def test_implementation_probability_maps_to_onboarding_year():
    scenario = ScenarioConfig(
        id="onboarding",
        name="Onboarding",
        start_year=2025,
        end_year=2040,
        nodes=[
            {"id": "plant", "name": "Plant", "kind": "emitter"},
            {"id": "sink", "name": "Sink", "kind": "storage"},
        ],
        emitters=[
            {
                "id": "high",
                "name": "High",
                "node_id": "plant",
                "implementation_probability": 1.0,
                "gross_emissions": {"kind": "constant", "constant_t_per_year": 100.0},
            },
            {
                "id": "mid",
                "name": "Mid",
                "node_id": "plant",
                "implementation_probability": 0.5,
                "gross_emissions": {"kind": "constant", "constant_t_per_year": 100.0},
            },
            {
                "id": "low",
                "name": "Low",
                "node_id": "plant",
                "implementation_probability": 0.1,
                "gross_emissions": {"kind": "constant", "constant_t_per_year": 100.0},
            },
        ],
        storage_sinks=[{"id": "sink", "node_id": "sink", "name": "Sink", "capacity_t": 1_000_000.0}],
    )
    assert [emitter.activation_year for emitter in scenario.emitters] == [2026, 2028, 2033]
    assert scenario.emitter_by_id("low").active_in(2032) is False
    assert scenario.emitter_by_id("low").active_in(2033) is True
    assert DEFAULT_ONBOARDING_YEARS[0.5] == 2028


def test_emitter_needs_either_a_year_or_a_probability():
    with pytest.raises(ValueError):
        ScenarioConfig(
            id="bad",
            name="Bad",
            start_year=2025,
            end_year=2030,
            nodes=[
                {"id": "plant", "name": "Plant", "kind": "emitter"},
                {"id": "sink", "name": "Sink", "kind": "storage"},
            ],
            emitters=[
                {
                    "id": "unknown",
                    "name": "Unknown",
                    "node_id": "plant",
                    "gross_emissions": {"kind": "constant", "constant_t_per_year": 10.0},
                }
            ],
            storage_sinks=[{"id": "sink", "node_id": "sink", "name": "Sink", "capacity_t": 10.0}],
        )


def test_commented_json_round_trip():
    scenario = ScenarioConfig(
        id="json",
        name="JSON",
        start_year=2025,
        end_year=2030,
        nodes=[
            {"id": "plant", "name": "Plant", "kind": "emitter"},
            {"id": "sink", "name": "Sink", "kind": "storage"},
        ],
        emitters=[
            {
                "id": "e1",
                "name": "E1",
                "node_id": "plant",
                "activation_year": 2026,
                "gross_emissions": {"kind": "power_law", "e0_t_per_year": 1000.0, "reference_year": 2025, "a": -0.05, "c": 1.5},
            }
        ],
        storage_sinks=[{"id": "sink", "node_id": "sink", "name": "Sink", "capacity_t": 10_000.0}],
        policy=PolicyConfig(),
    )
    text = commented_json.dump(scenario)
    assert '"unit": "t CO2/year"' in text
    assert '"comment":' in text
    reloaded = load(text)
    # E(t) = 1000 - 50 * 2**1.5 = 858.5786...
    assert reloaded.emitter_by_id("e1").gross_emissions.value_at(2027) == pytest.approx(
        1000.0 - 50.0 * (2.0**1.5), rel=1e-9
    )
    assert reloaded.policy is not None


def test_policy_adjusts_the_without_ccs_counterfactual():
    """The counterfactual must pay only for emissions above the free allocation."""

    import pandas as pd

    from ccus_core.finance.cashflow import build_cash_flow_config

    scenario = ScenarioConfig(
        id="ets",
        name="ETS",
        start_year=2025,
        end_year=2032,
        nodes=[
            {"id": "plant", "name": "Plant", "kind": "emitter"},
            {"id": "sink", "name": "Sink", "kind": "storage"},
        ],
        emitters=[
            {
                "id": "e1",
                "name": "E1",
                "node_id": "plant",
                "activation_year": 2025,
                "gross_emissions": {"kind": "constant", "constant_t_per_year": 1_000_000.0},
            }
        ],
        storage_sinks=[{"id": "sink", "node_id": "sink", "name": "Sink", "capacity_t": 100_000_000.0}],
        policy=PolicyConfig(),
        economics={"start_year": 2025, "end_year": 2032, "capex_start_year": 2025},
    )
    ledger = pd.DataFrame(
        {
            "year": list(range(2025, 2033)),
            "co2_chain_t": [1_000_000.0] * 8,
            "orc_gross_mwh": [0.0] * 8,
            "gt_pump_mwh": [0.0] * 8,
            "co2_compressor_mwh": [0.0] * 8,
            "electricity_export_mwh": [0.0] * 8,
            "electricity_import_mwh": [0.0] * 8,
            "injection_active": [True] * 8,
            "geothermal_active": [False] * 8,
            "monitoring_active": [True] * 8,
        }
    )
    config, _notes = build_cash_flow_config(scenario, ledger=ledger)
    emissions = config["emitter_emissions_annual"]
    assert emissions[2028] == pytest.approx(675_000.0)  # 32.5 % free
    assert emissions[2030] == pytest.approx(1_000_000.0)  # 0 % free


def test_workbook_import_reproduces_the_sheet():
    if not WORKBOOK.exists():
        pytest.skip("workbook not present")
    from ccus_core.io.excel_import import build_scenario

    scenario = build_scenario(WORKBOOK)
    assert len(scenario.emitters) == 14
    assert len(scenario.edges) == 14
    assert {sink.name for sink in scenario.storage_sinks} == {"Ivanić", "Stružec", "Boksić"}

    plomin = scenario.emitter_by_id("te-plomin")
    assert plomin.gross_emissions.value_at(2025) == pytest.approx(1_118_203.087, rel=1e-6)
    assert plomin.activation_year == 2028
    assert scenario.emitter_by_id("nexe").activation_year == 2026
    assert scenario.emitter_by_id("rafinerija-nafte-rijeka").activation_year == 2033