"""Scenario document validation and the economics bridge."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ccus_core.models import (
    EconomicsConfig,
    EmissionCurve,
    Emitter,
    Node,
    NodeKind,
    PricePath,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
)

from .conftest import pipeline_state


def test_summary_reports_counts_and_capacity(sample_scenario):
    summary = sample_scenario.summary()
    assert summary["counts"] == {
        "nodes": 6,
        "emitters": 2,
        "edges": 3,
        "storage_sinks": 1,
        "geothermal_systems": 0,
    }
    assert summary["years"] == [2027, 2045]
    assert summary["first_onboarding_year"] == 2028
    assert summary["total_capacity_t"] == pytest.approx(9_308_000.0)


def test_staggered_cluster_totals(sample_scenario):
    totals = [sample_scenario.total_captured_t_per_year(year) for year in (2027, 2028, 2031, 2033)]
    assert totals == pytest.approx([0.0, 400_000.0, 500_000.0, 700_000.0])


def test_active_emitters_only(sample_scenario):
    assert [emitter.id for emitter in sample_scenario.emitters_active_in(2027)] == []
    assert [emitter.id for emitter in sample_scenario.emitters_active_in(2028)] == ["nexe"]
    assert [emitter.id for emitter in sample_scenario.emitters_active_in(2033)] == ["nexe", "plomin"]


def test_unknown_node_reference_is_rejected(sample_scenario):
    payload = sample_scenario.model_dump()
    payload["emitters"][0]["node_id"] = "does_not_exist"
    with pytest.raises(ValidationError, match="unknown node"):
        ScenarioConfig.model_validate(payload)


def test_unknown_marine_port_is_rejected(sample_scenario):
    payload = sample_scenario.model_dump()
    payload["edges"][2]["states"][0]["marine"]["port_node_id"] = "ghost_port"
    with pytest.raises(ValidationError, match="unknown port"):
        ScenarioConfig.model_validate(payload)


def test_duplicate_ids_are_rejected(sample_scenario):
    payload = sample_scenario.model_dump()
    payload["nodes"].append(dict(payload["nodes"][0]))
    with pytest.raises(ValidationError, match="duplicate node id"):
        ScenarioConfig.model_validate(payload)


def test_a_scenario_needs_a_sink_and_an_emitter(sample_scenario):
    payload = sample_scenario.model_dump()
    payload["storage_sinks"] = []
    with pytest.raises(ValidationError, match="at least one storage sink"):
        ScenarioConfig.model_validate(payload)

    payload = sample_scenario.model_dump()
    payload["emitters"] = []
    with pytest.raises(ValidationError, match="at least one emitter"):
        ScenarioConfig.model_validate(payload)


def test_economic_horizon_must_fit_the_simulation(sample_scenario):
    payload = sample_scenario.model_dump()
    payload["economics"]["end_year"] = 2060
    with pytest.raises(ValidationError, match="economic horizon"):
        ScenarioConfig.model_validate(payload)


def test_price_path_endpoints_are_held_outside_the_published_range():
    path = PricePath(
        mode="conservative",
        start_year=2025,
        values_eur_per_t=[64.0, 68.0, 71.0],
    )
    assert path.price_at(2024) == pytest.approx(64.0)
    assert path.price_at(2025) == pytest.approx(64.0)
    assert path.price_at(2026) == pytest.approx(68.0)
    assert path.price_at(2040) == pytest.approx(71.0)


def test_custom_price_path_uses_the_documented_functions():
    economics = EconomicsConfig(
        start_year=2027,
        end_year=2035,
        capex_start_year=2028,
        price_path=PricePath(
            mode="custom",
            custom={
                "function": "linear",
                "p0_eur_per_t": 60.0,
                "linear_growth_eur_per_t_per_year": 4.0,
            },
        ),
    )
    prices = economics.prices_by_year()
    assert prices[2027] == pytest.approx(60.0)
    assert prices[2030] == pytest.approx(72.0)
    assert prices[2035] == pytest.approx(92.0)


def test_economics_config_maps_to_the_existing_cash_flow_runner(sample_scenario):
    config = sample_scenario.economics.to_cash_flow_config()
    assert config["economics_interest_rate"] == pytest.approx(0.05)
    assert config["economics_inflation_rate"] == pytest.approx(0.05)
    assert config["economics_ccs_start_year"] == 2028
    assert config["co2_value"]["value_eur_per_t"][2027] == pytest.approx(71.0)
    assert config["electricity"]["sell_price_eur_per_mwh"] == 0.0