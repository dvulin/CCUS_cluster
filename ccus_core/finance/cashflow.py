"""Couple the routed mass and the infrastructure schedule to the cash-flow model.

The existing :class:`economics.cash_flow_runner.CashFlowRunner` already implements
CAPEX placement (lump sum or per-year schedule), fixed/variable OPEX, inflation
escalation, discounting, cumulative NPV and IRR.  This module only *builds its
configuration* from a :class:`ScenarioConfig` plus the solver's annual results, so
the audited financial code is reused rather than duplicated.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

import pandas as pd

from ccus_core.models import ScenarioConfig


def _weighted_average(pairs: list[tuple[float, float]], default: float = 0.0) -> float:
    """Mass-weighted mean of ``(mass, rate)`` pairs."""

    total_mass = sum(mass for mass, _ in pairs)
    if total_mass <= 0.0:
        return float(default)
    return float(sum(mass * rate for mass, rate in pairs) / total_mass)


def _add_schedule(target: dict[int, float], year: int, amount: float) -> None:
    if amount:
        target[int(year)] = target.get(int(year), 0.0) + float(amount)


def _counterfactual_emissions(scenario: ScenarioConfig, years: list[int]) -> dict[int, float]:
    """Emissions that would be paid for without CCS.

    With a policy block the EU ETS free-allocation phase-out is applied, so the
    counterfactual follows the thesis rule (50 % free in 2025, 0 % from 2030).
    """

    gross = {
        year: sum(emitter.available_emissions(year) for emitter in scenario.emitters)
        for year in years
    }
    if scenario.policy is None:
        return gross
    ets = scenario.policy.ets
    return {year: ets.taxable_emissions(year, value) for year, value in gross.items()}


def build_cash_flow_config(
    scenario: ScenarioConfig,
    *,
    ledger: pd.DataFrame,
    transport_cost_by_year: Mapping[int, float] | None = None,
) -> tuple[dict[str, object], list[str]]:
    """Return ``(config, notes)`` for :class:`CashFlowRunner`."""

    notes: list[str] = []
    years = [int(year) for year in ledger["year"]]
    chain_by_year = {
        int(row.year): float(row.co2_chain_t) for row in ledger.itertuples(index=False)
    }
    injected_by_year = {
        int(row.year): float(row.co2_chain_t) for row in ledger.itertuples(index=False)
    }
    compressor_mwh_by_year = {
        int(row.year): float(row.co2_compressor_mwh) for row in ledger.itertuples(index=False)
    }
    orc_mwh_by_year = {
        int(row.year): float(row.orc_gross_mwh) for row in ledger.itertuples(index=False)
    }

    # ---------------------------------------------------------------- capture
    capture_capex: dict[int, float] = defaultdict(float)
    capture_rate_pairs: list[tuple[float, float]] = []
    for emitter in scenario.emitters:
        capture = emitter.capture
        if capture is None:
            continue
        _add_schedule(capture_capex, capture.commissioning_year, capture.capex_eur)
        for year in years:
            mass = emitter.captured_emissions(year)
            if mass > 0.0 and capture.active_in(year):
                capture_rate_pairs.append((mass, capture.opex_eur_per_t))

    # ---------------------------------------------------------------- transport
    transport_capex: dict[int, float] = defaultdict(float)
    for edge in scenario.edges:
        for state in edge.states:
            _add_schedule(transport_capex, state.valid_from_year, state.capex_eur)
        for upgrade in edge.upgrades:
            _add_schedule(
                transport_capex,
                upgrade.new_state.valid_from_year,
                upgrade.new_state.capex_eur,
            )

    transport_costs = dict(transport_cost_by_year or {})
    transport_rate: object
    if transport_costs:
        rate_by_year = {}
        for year in years:
            chain = chain_by_year.get(year, 0.0)
            rate_by_year[year] = (transport_costs.get(year, 0.0) / chain) if chain > 0.0 else 0.0
        transport_rate = rate_by_year
        notes.append("transport OPEX follows the routed modal cost of each year")
    else:
        transport_rate = 0.0

    # ---------------------------------------------------------------- storage
    storage_capex: dict[int, float] = defaultdict(float)
    storage_rate_pairs: list[tuple[float, float]] = []
    monitoring_during = 0.0
    monitoring_after = 0.0
    for sink in scenario.storage_sinks:
        start = sink.commissioning_year or (min(years) if years else 0)
        _add_schedule(storage_capex, start, sink.capex_eur)
        for year in years:
            mass = injected_by_year.get(year, 0.0)
            if mass > 0.0:
                storage_rate_pairs.append((mass, sink.opex_eur_per_t))
        if sink.monitoring_end_year is not None:
            for year in years:
                if start <= year <= sink.monitoring_end_year:
                    if year <= max((y for y, m in injected_by_year.items() if m > 0.0), default=start):
                        monitoring_during += sink.monitoring_cost_during_injection_eur_per_year
                    else:
                        monitoring_after += sink.monitoring_cost_after_injection_eur_per_year

    # ---------------------------------------------------------------- compressor / geothermal
    compressor_capex: dict[int, float] = defaultdict(float)
    geothermal_capex: dict[int, float] = defaultdict(float)
    geothermal_fixed: dict[int, float] = defaultdict(float)
    for system in scenario.geothermal_systems:
        _add_schedule(geothermal_capex, system.operation_start_year or min(years), system.capex_eur)
        for year in years:
            if system.active_in(year):
                _add_schedule(geothermal_fixed, year, system.fixed_opex_eur_per_year)

    economics = scenario.economics
    if economics is None:
        raise ValueError("the scenario has no economics configuration")
    config: dict[str, object] = dict(economics.to_cash_flow_config())
    config.update(
        {
            "capture": {
                "capex_schedule_eur": dict(capture_capex),
                "variable_opex_eur_per_t": _weighted_average(capture_rate_pairs),
            },
            "transport": {
                "mode": "pipeline",
                "capex_schedule_eur": dict(transport_capex),
                "variable_opex_eur_per_t": transport_rate,
            },
            "storage": {
                "capex_schedule_eur": dict(storage_capex),
                "variable_opex_eur_per_t": _weighted_average(storage_rate_pairs),
            },
            "compressor": {
                "capex_schedule_eur": dict(compressor_capex),
                "variable_opex_eur_per_mwh": 0.0,
            },
            "geothermal": {
                "capex_schedule_eur": dict(geothermal_capex),
                "fixed_opex_eur_per_year": {year: float(geothermal_fixed.get(year, 0.0)) for year in years},
                "variable_opex_eur_per_mwh": (
                    scenario.geothermal_systems[0].variable_opex_eur_per_mwh
                    if scenario.geothermal_systems
                    else 0.0
                ),
            },
            "monitoring": {
                "annual_cost_during_injection": monitoring_during,
                "annual_cost_after_injection": monitoring_after,
            },
            "emitter_emissions_annual": _counterfactual_emissions(scenario, years),
        }
    )
    return config, notes