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


def _clamp_schedule(
    schedule: dict[int, float], years: list[int], label: str, notes: list[str]
) -> dict[int, float]:
    """Force a CAPEX schedule inside the ledger horizon.

    A cost planned before the first modelled year cannot be discounted from a year
    that does not exist, so it is booked in the first year (and reported) instead of
    silently disappearing.
    """

    if not years:
        return {}
    first, last = int(years[0]), int(years[-1])
    clamped: dict[int, float] = {}
    for year, amount in sorted(schedule.items()):
        amount = float(amount)
        if amount == 0.0:
            continue
        if int(year) < first:
            notes.append(f"{label}: CAPEX of {int(year)} moved to {first} (before the horizon)")
            year = first
        if int(year) > last:
            notes.append(f"{label}: CAPEX of {int(year)} is after the horizon and is ignored")
            continue
        clamped[int(year)] = clamped.get(int(year), 0.0) + amount
    return clamped


def upgrade_capex_by_edge(
    scenario: ScenarioConfig,
    *,
    fired_upgrades: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, dict[int, float]]:
    """Per-edge CAPEX of the upgrades that actually fire (positive EUR).

    An upgrade is booked **once**, in the year its new state comes into force:

    * a ``year``/``both`` trigger is known in advance, so its planned year is used;
    * a ``cumulative_mass`` trigger is only known chronologically, so the year the
      solver recorded in ``fired_upgrades`` is used - and nothing is booked while it
      has not fired.

    ``lead_time_years`` is applied by :meth:`InfrastructureUpgrade.effective_year`.
    """

    fired = {edge_id: dict(mapping) for edge_id, mapping in (fired_upgrades or {}).items()}
    schedule: dict[str, dict[int, float]] = {}
    for edge in scenario.edges:
        per_edge: dict[int, float] = defaultdict(float)
        for upgrade in edge.upgrades:
            trigger = upgrade.trigger
            fired_year: int | None = fired.get(edge.id, {}).get(upgrade.id)
            if fired_year is None and trigger.kind in ("year", "both") and trigger.year is not None:
                fired_year = int(trigger.year)
            if fired_year is None:
                # a mass trigger that never fired: no asset, no CAPEX
                continue
            effective = upgrade.effective_year(current_year=fired_year, fired_year=fired_year)
            if effective is None:  # pragma: no cover - defensive
                continue
            _add_schedule(per_edge, effective, upgrade.new_state.capex_eur)
        if per_edge:
            schedule[edge.id] = dict(per_edge)
    return schedule


def upgrade_capex_schedule(
    scenario: ScenarioConfig,
    *,
    fired_upgrades: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[int, float]:
    """CAPEX of the infrastructure upgrades that actually fire, summed per year."""

    total: dict[int, float] = defaultdict(float)
    for per_edge in upgrade_capex_by_edge(scenario, fired_upgrades=fired_upgrades).values():
        for year, amount in per_edge.items():
            total[int(year)] += float(amount)
    return dict(total)


def edge_capex_schedules(
    scenario: ScenarioConfig,
    *,
    fired_upgrades: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, dict[int, float]]:
    """CAPEX of every transport edge, per year (planned states + fired upgrades).

    A planned state is a separate asset: its CAPEX belongs to the year the state
    enters force.  A conditional upgrade is added only when it fires.
    """

    upgrades = upgrade_capex_by_edge(scenario, fired_upgrades=fired_upgrades)
    schedule: dict[str, dict[int, float]] = {}
    for edge in scenario.edges:
        per_edge: dict[int, float] = defaultdict(float)
        for state in edge.states:
            _add_schedule(per_edge, state.valid_from_year, state.capex_eur)
        for year, amount in upgrades.get(edge.id, {}).items():
            _add_schedule(per_edge, year, amount)
        schedule[edge.id] = dict(per_edge)
    return schedule


def capex_schedules(
    scenario: ScenarioConfig,
    *,
    ledger_years: Sequence[int],
    fired_upgrades: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, dict[int, float]]:
    """CAPEX per block and year (positive EUR), clamped to the ledger horizon.

    This is the single source of truth for CAPEX placement: the consolidated
    cash-flow configuration and the per-stakeholder statements both call it, so a
    tonne of CO2 and a euro of CAPEX can never be counted in two different years.
    """

    years = [int(year) for year in ledger_years]
    notes: list[str] = []
    capture: dict[int, float] = defaultdict(float)
    for emitter in scenario.emitters:
        capture_unit = emitter.capture
        if capture_unit is None:
            continue
        _add_schedule(capture, capture_unit.commissioning_year, capture_unit.capex_eur)

    storage: dict[int, float] = defaultdict(float)
    for sink in scenario.storage_sinks:
        start = sink.commissioning_year or (years[0] if years else 0)
        _add_schedule(storage, start, sink.capex_eur)

    geothermal: dict[int, float] = defaultdict(float)
    for system in scenario.geothermal_systems:
        _add_schedule(
            geothermal, system.operation_start_year or (years[0] if years else 0), system.capex_eur
        )

    # per-edge schedules are summed (several edges can be built in the same year)
    transport: dict[int, float] = defaultdict(float)
    for per_edge in edge_capex_schedules(scenario, fired_upgrades=fired_upgrades).values():
        for year, amount in per_edge.items():
            _add_schedule(transport, year, amount)

    return {
        "capture": _clamp_schedule(dict(capture), years, "capture", notes),
        "transport": _clamp_schedule(dict(transport), years, "transport", notes),
        "storage": _clamp_schedule(dict(storage), years, "storage", notes),
        "compressor": {},
        "geothermal": _clamp_schedule(dict(geothermal), years, "geothermal", notes),
    }


def monitoring_cost_by_sink(
    scenario: ScenarioConfig,
    years: Sequence[int],
    sink_injections: Mapping[str, Mapping[int, float]],
) -> dict[str, dict[int, float]]:
    """Monitoring cost per sink and year (positive EUR), charged ``rate x years``.

    Each sink is charged its own annual rate once per year: while it injects
    (``..._during_injection_eur_per_year``) and after its last injection year up to
    ``monitoring_end_year`` (``..._after_injection_eur_per_year``).  A pre-summed
    cluster total is never handed to the cash-flow model: the runner multiplies the
    annual rate by every year of the ledger.
    """

    result: dict[str, dict[int, float]] = {}
    year_list = [int(year) for year in years]
    if not year_list:
        return result

    first = year_list[0]
    last_year = year_list[-1]
    for sink in scenario.storage_sinks:
        rate_during = float(sink.monitoring_cost_during_injection_eur_per_year)
        rate_after = float(sink.monitoring_cost_after_injection_eur_per_year)
        if rate_during <= 0.0 and rate_after <= 0.0:
            continue
        if sink.monitoring_end_year is None:
            raise ValueError(
                f"storage sink '{sink.id}' charges monitoring costs but declares no "
                "monitoring_end_year: the post-injection window must be explicit"
            )
        injected_years = [
            int(year)
            for year, mass in sink_injections.get(sink.id, {}).items()
            if float(mass) > 0.0
        ]
        commissioning = (
            int(sink.commissioning_year) if sink.commissioning_year is not None else first
        )
        last_injection = max(injected_years) if injected_years else commissioning
        start = min(commissioning, last_injection)
        end = int(sink.monitoring_end_year)
        per_year: dict[int, float] = {}
        for year in year_list:
            if year < start or year > min(end, last_year):
                continue
            per_year[year] = rate_during if year <= last_injection else rate_after
        if per_year:
            result[sink.id] = per_year
    return result


def monitoring_total_by_year(
    scenario: ScenarioConfig,
    years: Sequence[int],
    sink_injections: Mapping[str, Mapping[int, float]],
) -> dict[int, float]:
    """Cluster-wide monitoring cost per year (positive EUR), phases already resolved.

    The "during" and "after" phases are a *per-sink* property (each site stops
    injecting in its own year), so the phase is resolved here and the cash-flow model
    receives one annual amount per year.  Handing it a pre-summed total instead would
    charge ``rate x years`` in a single year.
    """

    per_sink = monitoring_cost_by_sink(scenario, years, sink_injections)
    # every ledger year must be present: the cash-flow model rejects a partial path
    total: dict[int, float] = {int(year): 0.0 for year in years}
    for amounts in per_sink.values():
        for year, amount in amounts.items():
            total[int(year)] = total.get(int(year), 0.0) + float(amount)
    return total


def build_cash_flow_config(
    scenario: ScenarioConfig,
    *,
    ledger: pd.DataFrame,
    transport_cost_by_year: Mapping[int, float] | None = None,
    sink_injections: Mapping[str, Mapping[int, float]] | None = None,
    fired_upgrades: Mapping[str, Mapping[str, int]] | None = None,
) -> tuple[dict[str, object], list[str]]:
    """Return ``(config, notes)`` for :class:`CashFlowRunner`."""

    notes: list[str] = []
    years = [int(year) for year in ledger["year"]]
    chain_by_year = {
        int(row.year): float(row.co2_chain_t) for row in ledger.itertuples(index=False)
    }
    injections = {
        sink_id: {int(year): float(mass) for year, mass in mapping.items()}
        for sink_id, mapping in (sink_injections or {}).items()
    }
    if injections:
        injected_by_year = {
            year: sum(mapping.get(year, 0.0) for mapping in injections.values())
            for year in years
        }
    else:
        # no per-sink detail available: the chain total is the best proxy
        injected_by_year = dict(chain_by_year)
    compressor_mwh_by_year = {
        int(row.year): float(row.co2_compressor_mwh) for row in ledger.itertuples(index=False)
    }
    orc_mwh_by_year = {
        int(row.year): float(row.orc_gross_mwh) for row in ledger.itertuples(index=False)
    }

    # ---------------------------------------------------------------- capex
    # one shared schedule for the consolidated view and the stakeholder split
    schedules = capex_schedules(
        scenario, ledger_years=years, fired_upgrades=fired_upgrades
    )
    capture_capex = schedules["capture"]
    transport_capex = schedules["transport"]
    storage_capex = schedules["storage"]
    compressor_capex = schedules["compressor"]
    geothermal_capex = schedules["geothermal"]

    # ---------------------------------------------------------------- capture
    capture_rate_pairs: list[tuple[float, float]] = []
    for emitter in scenario.emitters:
        capture = emitter.capture
        if capture is None:
            continue
        for year in years:
            mass = emitter.captured_emissions(year)
            if mass > 0.0 and capture.active_in(year):
                capture_rate_pairs.append((mass, capture.opex_eur_per_t))

    # ---------------------------------------------------------------- transport
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
    storage_rate_pairs: list[tuple[float, float]] = []
    for sink in scenario.storage_sinks:
        for year in years:
            mass = injections.get(sink.id, {}).get(year, injected_by_year.get(year, 0.0))
            if mass > 0.0:
                storage_rate_pairs.append((mass, sink.opex_eur_per_t))

    monitoring_total = monitoring_total_by_year(scenario, years, injections)

    # ---------------------------------------------------------------- geothermal
    geothermal_fixed: dict[int, float] = defaultdict(float)
    for system in scenario.geothermal_systems:
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
                # the phase (during / after injection) is resolved per sink in
                # `monitoring_total_by_year`; both keys carry the same annual amount
                # so the runner's cluster-wide injection flag cannot drop a year
                "annual_cost_during_injection": monitoring_total,
                "annual_cost_after_injection": monitoring_total,
            },
            "emitter_emissions_annual": _counterfactual_emissions(scenario, years),
        }
    )
    return config, notes