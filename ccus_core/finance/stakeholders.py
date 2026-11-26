"""Per-stakeholder economics: who earns and who pays, year by year.

The consolidated cash-flow model answers "is the cluster worth it".  A cluster
study also has to answer "who carries which cost", because emitters, transport
operators and storage operators are usually different parties.  This module splits
**the same consolidated cash flow** into per-stakeholder statements.

Attribution rules (cost-reflective tariffs, no margin)
------------------------------------------------------
===========================  ==================================================
consolidated line item       attributed to
===========================  ==================================================
``capture_capex``            each emitter, in its capture commissioning year
``capture_opex``             emitters, pro-rata by captured mass
``transport_capex``          each transport operator, in the year its state (or a
                            *fired* upgrade) enters force
``transport_opex``           each transport operator, pro-rata by the tariff of the
                            arcs it carries (= the routed modal cost)
``compressor_*``             the storage operator that runs the injection skid
``storage_capex``            each storage operator, in its commissioning year
``storage_opex``             each storage operator, pro-rata by injected mass
``geothermal_capex/opex``    the geothermal operator of the doublet
``monitoring``               each storage operator, ``rate x years`` per phase
``electricity_purchase``     the storage operator (compressor and pump load)
``electricity_revenue``      the geothermal operator (ORC export)
``co2_value``                the emitters, pro-rata by delivered mass
``cost_inflation_adjustment`` every party, pro-rata by its own base cost
===========================  ==================================================

With these conventions every transfer cancels on consolidation, so

    sum(stakeholder net cash flow) == consolidated net cash flow

holds for every year and for the total (asserted in ``tests``).  Transfers are the
emitter's ``tariff_paid`` against the operator's ``tariff_collected``; they can be
hidden with ``include_transfers=False`` without changing the consolidated total,
because both sides of every transfer are dropped together.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping

import pandas as pd

from ccus_core.models import ScenarioConfig

from .cashflow import (
    edge_capex_schedules,
    upgrade_capex_by_edge,
)

try:  # the audited cash-flow module owns the canonical cost columns
    from economics.cash_flow_runner import COST_LINE_ITEM_COLUMNS
except Exception:  # pragma: no cover - model-only environment
    COST_LINE_ITEM_COLUMNS = (
        "capture_capex",
        "capture_opex",
        "transport_capex",
        "transport_opex",
        "compressor_capex",
        "compressor_opex",
        "storage_capex",
        "storage_opex",
        "geothermal_capex",
        "geothermal_opex",
        "monitoring",
        "electricity_purchase",
    )

STAKEHOLDER_LABELS = {
    "emitter": "Emitter",
    "transport": "Transport operator",
    "storage": "Storage operator",
    "geothermal": "Geothermal operator",
    "system": "Cluster (unallocated)",
}

LINE_ITEMS = (
    "capex",
    "opex",
    "tariff_paid",
    "tariff_collected",
    "revenue",
    "inflation_adjustment",
)

#: consolidated cash-flow columns that are revenues rather than costs
REVENUE_COLUMNS = ("electricity_revenue", "co2_value")


def build_stakeholder_table(
    scenario: ScenarioConfig, result, *, include_transfers: bool = True
) -> pd.DataFrame:
    """Return a tidy ``year x stakeholder x line item`` table in euro.

    The table is a *decomposition* of ``result.cash_flow``: every consolidated cost
    and revenue line is assigned to exactly one party, so the per-stakeholder net
    cash flows add back up to the consolidated net cash flow.
    """

    columns = ["year", "stakeholder", "stakeholder_id", "line_item", "amount_eur"]
    cash_flow = getattr(result, "cash_flow", None)
    ledger = result.ledger
    if cash_flow is None or cash_flow.empty:
        return pd.DataFrame(columns=columns)

    # the scenario of the *run* is authoritative: the engine may have added the
    # default doublet of a coupled sink, and the consolidated cash flow already
    # includes its CAPEX and OPEX
    scenario = getattr(result, "scenario", None) or scenario
    years = [int(year) for year in ledger["year"]]
    cash = cash_flow.set_index("year")
    rows: list[dict[str, object]] = []

    def add(year: int, stakeholder: str, stakeholder_id: str, item: str, amount: float) -> None:
        rows.append(
            {
                "year": int(year),
                "stakeholder": stakeholder,
                "stakeholder_id": stakeholder_id,
                "line_item": item,
                "amount_eur": float(amount),
            }
        )

    def consolidated(column: str, year: int) -> float:
        if column not in cash.columns or year not in cash.index:
            return 0.0
        value = float(cash.loc[year, column])
        return 0.0 if value != value else value  # NaN -> 0

    fired = dict(getattr(result, "fired_upgrades", {}) or {})
    edge_capex = edge_capex_schedules(scenario, fired_upgrades=fired)
    injections = _sink_injections(result)

    # ------------------------------------------------------------- emitters
    # capture CAPEX: each emitter owns its capture plant
    capture_capex: dict[str, dict[int, float]] = {}
    for emitter in scenario.emitters:
        unit = emitter.capture
        if unit is None or not unit.capex_eur:
            continue
        start = int(unit.commissioning_year)
        # the consolidated schedule is clamped to the ledger horizon: mirror that
        start = max(start, years[0])
        if start <= years[-1]:
            capture_capex[emitter.id] = {start: float(unit.capex_eur)}
    for emitter_id, schedule in capture_capex.items():
        for year, amount in schedule.items():
            add(year, "emitter", emitter_id, "capex", -amount)

    captured_by_year = {
        int(year): {
            emitter.id: float(emitter.captured_emissions(year))
            for emitter in scenario.emitters
        }
        for year in years
    }
    # capture OPEX: one consolidated number, split by captured mass
    for year in years:
        total = -consolidated("capture_opex", year)
        if total <= 0.0:
            continue
        captured = captured_by_year[year]
        mass = sum(captured.values())
        for emitter_id, value in captured.items():
            if value <= 0.0 or mass <= 0.0:
                continue
            add(year, "emitter", emitter_id, "opex", -total * value / mass)

    # CO2 value: the emitters own the CO2 that is delivered
    for routing in result.routing:
        year = int(routing.year)
        total = consolidated("co2_value", year)
        if total <= 0.0:
            continue
        chain = sum(item.quantity_t for item in routing.allocations)
        if chain <= 0.0:
            continue
        for allocation in routing.allocations:
            add(
                year,
                "emitter",
                allocation.emitter_id,
                "revenue",
                total * allocation.quantity_t / chain,
            )

    # ------------------------------------------------------------- transport
    for edge in scenario.edges:
        per_edge = edge_capex.get(edge.id, {})
        for year, amount in per_edge.items():
            start = max(int(year), years[0])
            if start <= years[-1]:
                add(start, "transport", edge.id, "capex", -float(amount))

    for year in years:
        total = -consolidated("transport_opex", year)
        if total <= 0.0:
            continue
        # the routed modal cost of every arc is its tariff times its flow
        shares = _transport_shares(scenario, result, year, fired)
        mass = sum(shares.values())
        if mass <= 0.0:
            continue
        for edge_id, value in shares.items():
            add(year, "transport", edge_id, "opex", -total * value / mass)

    if include_transfers:
        for routing in result.routing:
            year = int(routing.year)
            shares = _transport_shares(scenario, result, year, fired)
            mass = sum(shares.values())
            if mass <= 0.0:
                continue
            collected_total = -consolidated("transport_opex", year)
            for edge_id, value in shares.items():
                add(
                    year,
                    "transport",
                    edge_id,
                    "tariff_collected",
                    collected_total * value / mass,
                )
            for allocation in routing.allocations:
                add(
                    year,
                    "emitter",
                    allocation.emitter_id,
                    "tariff_paid",
                    -float(allocation.cost_eur),
                )

    # -------------------------------------------------------------- storage
    for sink in scenario.storage_sinks:
        start = sink.commissioning_year or years[0]
        start = max(int(start), years[0])
        if sink.capex_eur and start <= years[-1]:
            add(start, "storage", sink.id, "capex", -float(sink.capex_eur))

    storage_opex_by_year = _storage_opex_by_year(scenario, result, injections)
    for year in years:
        total = -consolidated("storage_opex", year)
        if total <= 0.0:
            continue
        shares = storage_opex_by_year.get(year, {})
        mass = sum(shares.values())
        if mass <= 0.0:
            continue
        for sink_id, value in shares.items():
            add(year, "storage", sink_id, "opex", -total * value / mass)

    for year in years:
        # compressor CAPEX and OPEX belong to the sink that runs the skid
        split = _storage_split(scenario, injections.get(year, {}))
        for column in ("compressor_capex", "compressor_opex"):
            total = -consolidated(column, year)
            if total <= 0.0 or not split:
                continue
            item = "capex" if column.endswith("capex") else "opex"
            for sink_id, share in split.items():
                add(year, "storage", sink_id, item, -total * share)

        # electricity: the compressor/pump load is an operating cost of storage
        purchase = consolidated("electricity_purchase", year)
        if purchase and split:
            for sink_id, share in split.items():
                add(year, "storage", sink_id, "opex", purchase * share)

    monitoring_by_year = _monitoring_by_year(scenario, years, injections)
    for sink_id, per_year in monitoring_by_year.items():
        for year, amount in per_year.items():
            if amount:
                add(year, "storage", sink_id, "opex", -amount)

    if include_transfers:
        for routing in result.routing:
            year = int(routing.year)
            for allocation in routing.allocations:
                sink = scenario.sink_by_id(allocation.sink_id)
                if sink is None:
                    continue
                add(
                    year,
                    "emitter",
                    allocation.emitter_id,
                    "tariff_paid",
                    -float(sink.opex_eur_per_t) * float(allocation.quantity_t),
                )
        for year in years:
            for sink in scenario.storage_sinks:
                mass = injections.get(sink.id, {}).get(year, 0.0)
                if mass > 0.0:
                    add(
                        year,
                        "storage",
                        sink.id,
                        "tariff_collected",
                        float(sink.opex_eur_per_t) * float(mass),
                    )

    # ------------------------------------------------------------ geothermal
    geothermal_rate = _geothermal_variable_rate(scenario)
    for system in scenario.geothermal_systems:
        start = system.operation_start_year or years[0]
        start = max(int(start), years[0])
        if system.capex_eur and start <= years[-1]:
            add(start, "geothermal", system.id, "capex", -float(system.capex_eur))

    orc_by_year = _orc_by_year(result)
    geothermal_active = _ledger_flags(result, "geothermal_active")
    for year in years:
        total = -consolidated("geothermal_opex", year)
        # the consolidated model charges the fixed OPEX only in the years the
        # doublet is actually on stream, so the split uses the same activation
        keys: dict[str, float] = {}
        for system in scenario.geothermal_systems:
            fixed = (
                float(system.fixed_opex_eur_per_year)
                if system.active_in(year) and geothermal_active.get(year, False)
                else 0.0
            )
            variable = geothermal_rate * float(orc_by_year.get(year, {}).get(system.id, 0.0))
            keys[system.id] = fixed + variable
        mass = sum(keys.values())
        for system_id, key in keys.items():
            if key <= 0.0:
                continue
            share = key / mass if mass > 0.0 else 0.0
            add(year, "geothermal", system_id, "opex", -total * share)
        if total > 0.0 and mass <= 0.0:
            # defensive: never drop a consolidated cost because no key matched
            systems = [system.id for system in scenario.geothermal_systems]
            for system_id in systems:
                add(year, "geothermal", system_id, "opex", -total / len(systems))

        revenue = consolidated("electricity_revenue", year)
        mwh_total = sum(orc_by_year.get(year, {}).values())
        if revenue and mwh_total > 0.0:
            for system_id, mwh in orc_by_year.get(year, {}).items():
                add(
                    year,
                    "geothermal",
                    system_id,
                    "revenue",
                    revenue * mwh / mwh_total,
                )

    # --------------------------------------------- inflation and reconciliation
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        return frame
    frame = _allocate_inflation(frame, cash, years)

    frame.attrs["stakeholder_labels"] = STAKEHOLDER_LABELS
    frame.attrs["consolidated_net_eur"] = float(
        sum(consolidated_net_by_year(cash_flow).values())
    )
    return frame.sort_values(["year", "stakeholder", "stakeholder_id", "line_item"]).reset_index(
        drop=True
    )


# --------------------------------------------------------------------- helpers
def stakeholder_summary(table: pd.DataFrame) -> pd.DataFrame:
    """Net cash flow per stakeholder and year (transfers included)."""

    if table.empty:
        return table
    return (
        table.groupby(["year", "stakeholder"], as_index=False)["amount_eur"]
        .sum()
        .rename(columns={"amount_eur": "net_cash_flow_eur"})
        .sort_values(["year", "stakeholder"])
        .reset_index(drop=True)
    )


def entity_index(scenario: ScenarioConfig) -> list[dict[str, str]]:
    """List every stakeholder entity that can be inspected on its own."""

    entities: list[dict[str, str]] = []
    for emitter in scenario.emitters:
        entities.append(
            {
                "stakeholder": "emitter",
                "id": emitter.id,
                "label": f"{emitter.name} (emitter)",
            }
        )
    for edge in scenario.edges:
        entities.append(
            {
                "stakeholder": "transport",
                "id": edge.id,
                "label": f"{edge.name} (transport operator)",
            }
        )
    for sink in scenario.storage_sinks:
        entities.append(
            {
                "stakeholder": "storage",
                "id": sink.id,
                "label": f"{sink.name} (storage operator)",
            }
        )
    for system in scenario.geothermal_systems:
        entities.append(
            {
                "stakeholder": "geothermal",
                "id": system.id,
                "label": f"{system.name} (geothermal operator)",
            }
        )
    return entities


def entity_statement(
    table: pd.DataFrame,
    stakeholder: str,
    stakeholder_id: str,
    *,
    discount_rate: float | None = None,
) -> dict[str, object]:
    """Year-by-year statement for one entity.

    Returns a dict with ``years``, ``items`` (``line item -> [values]``),
    ``net_by_year`` and the totals (CAPEX, OPEX, tariffs, revenue, net and - when
    a discount rate is given - the entity's NPV).
    """

    if table.empty:
        return {"years": [], "items": {}, "net_by_year": [], "totals": {}}

    subset = table[
        (table["stakeholder"] == stakeholder) & (table["stakeholder_id"] == stakeholder_id)
    ]
    years = sorted(int(year) for year in subset["year"].unique())
    items: dict[str, list[float]] = {}
    for year in years:
        rows = subset[subset["year"] == year]
        for line_item in LINE_ITEMS:
            values = rows.loc[rows["line_item"] == line_item, "amount_eur"]
            items.setdefault(line_item, []).append(float(values.sum()) if not values.empty else 0.0)

    net_by_year = [
        float(sum(items[line][index] for line in LINE_ITEMS if line in items))
        for index in range(len(years))
    ]
    totals = {
        line: float(sum(values)) for line, values in items.items() if line in LINE_ITEMS
    }
    totals["net"] = float(sum(net_by_year))

    npv: float | None = None
    if discount_rate is not None and years:
        npv = float(
            sum(
                amount / ((1.0 + float(discount_rate)) ** (year - years[0]))
                for year, amount in zip(years, net_by_year)
            )
        )
    return {
        "years": years,
        "items": items,
        "net_by_year": net_by_year,
        "totals": totals,
        "npv": npv,
    }


def consolidated_net_by_year(cash_flow: pd.DataFrame) -> dict[int, float]:
    """Net cash flow of the whole cluster per year (the reconciliation target)."""

    if "net_cash_flow" in cash_flow.columns:
        return {
            int(row.year): float(row.net_cash_flow)
            for row in cash_flow.itertuples(index=False)
        }
    return {
        int(row.year): float(
            sum(float(getattr(row, column)) for column in _all_columns(cash_flow))
        )
        for row in cash_flow.itertuples(index=False)
    }


def stakeholder_net_by_year(table: pd.DataFrame) -> dict[int, float]:
    """Net cash flow of every stakeholder added together, per year."""

    if table.empty:
        return {}
    grouped = table.groupby("year")["amount_eur"].sum()
    return {int(year): float(value) for year, value in grouped.items()}


def cumulative_costs(cash_flow: pd.DataFrame) -> pd.DataFrame:
    """Cumulative cost per category (positive numbers, for charting)."""

    columns = [column for column in COST_LINE_ITEM_COLUMNS if column in cash_flow.columns]
    if not columns:
        return pd.DataFrame({"year": cash_flow.get("year", [])})
    costs = cash_flow[["year"] + columns].copy()
    costs[columns] = costs[columns].abs().cumsum()
    costs["total"] = costs[columns].sum(axis=1)
    return costs


def cost_breakdown_for_year(cash_flow: pd.DataFrame, year: int) -> dict[str, float]:
    """Absolute cost per category in one year (for a pie chart)."""

    row = cash_flow.loc[cash_flow["year"] == int(year)]
    if row.empty:
        return {}
    values = row.iloc[0]
    return {
        column: abs(float(values[column]))
        for column in COST_LINE_ITEM_COLUMNS
        if column in cash_flow.columns and abs(float(values[column])) > 0.0
    }


def _all_columns(cash: pd.DataFrame) -> list[str]:
    columns = [column for column in COST_LINE_ITEM_COLUMNS if column in cash.columns]
    columns += [column for column in REVENUE_COLUMNS if column in cash.columns]
    return columns


def _sink_injections(result) -> dict[str, dict[int, float]]:
    injections: dict[str, dict[int, float]] = {}
    for sink_id, frame in result.reservoir.items():
        if "co2_injected_t" not in frame:
            continue
        injections[sink_id] = {
            int(row.year): float(row.co2_injected_t)
            for row in frame.itertuples(index=False)
        }
    return injections


def _storage_split(
    scenario: ScenarioConfig, injected: Mapping[str, float]
) -> dict[str, float]:
    """Shares (summing to 1) that split a cluster-level storage cost per sink.

    Injection-weighted while a sink is taking CO2; an equal split when nothing is
    injected, because the compressors and the injection skids still stand ready (and
    still cost money) in a year without injection.
    """

    mass = sum(max(0.0, float(value)) for value in injected.values())
    if mass > 0.0:
        return {
            sink_id: max(0.0, float(value)) / mass
            for sink_id, value in injected.items()
            if float(value) > 0.0
        }
    sinks = [sink.id for sink in scenario.storage_sinks]
    if not sinks:
        return {}
    return {sink_id: 1.0 / len(sinks) for sink_id in sinks}


def _transport_shares(scenario, result, year: int, fired: Mapping) -> dict[str, float]:
    """Tariff-weighted transport cost per edge in ``year`` (positive EUR)."""

    routing = next((item for item in result.routing if int(item.year) == year), None)
    shares: dict[str, float] = defaultdict(float)
    if routing is None:
        return {}
    for edge_id, flow in routing.edge_flows.items():
        edge = scenario.edge_by_id(edge_id)
        if edge is None or flow <= 0.0:
            continue
        state = edge.resolve_state(
            year,
            fired_upgrades=dict((fired or {}).get(edge_id, {})),
        )
        if state is None:
            continue
        shares[edge_id] += float(state.variable_opex_eur_per_t()) * float(flow)
    return dict(shares)


def _storage_opex_by_year(scenario, result, injections) -> dict[int, dict[str, float]]:
    """Storage OPEX per sink and year (positive EUR), the consolidated cost key."""

    shares: dict[int, dict[str, float]] = {}
    for sink in scenario.storage_sinks:
        for year, mass in injections.get(sink.id, {}).items():
            if mass <= 0.0:
                continue
            shares.setdefault(int(year), {})[sink.id] = float(sink.opex_eur_per_t) * float(mass)
    return shares


def _monitoring_by_year(
    scenario: ScenarioConfig,
    years: list[int],
    injections: Mapping[str, Mapping[int, float]],
) -> dict[str, dict[int, float]]:
    """Monitoring cost per sink and year (``rate x years``, positive EUR)."""

    from .cashflow import monitoring_cost_by_sink

    return monitoring_cost_by_sink(scenario, years, injections)


def _orc_by_year(result) -> dict[int, dict[str, float]]:
    """ORC generation per geothermal system and year (MWh)."""

    per_year: dict[int, dict[str, float]] = {}
    for system_id, frame in result.geothermal.items():
        if "orc_power_kw" not in frame:
            continue
        for row in frame.itertuples(index=False):
            if not bool(row.operating):
                continue
            mwh = float(row.orc_power_kw) * 8766.0 / 1000.0
            if mwh > 0.0:
                per_year.setdefault(int(row.year), {})[system_id] = mwh
    return per_year


def _geothermal_variable_rate(scenario: ScenarioConfig) -> float:
    return float(
        scenario.geothermal_systems[0].variable_opex_eur_per_mwh
        if scenario.geothermal_systems
        else 0.0
    )


def _ledger_flags(result, column: str) -> dict[int, bool]:
    """Per-year boolean column of the technical ledger (default: False)."""

    ledger = result.ledger
    if ledger is None or column not in ledger.columns:
        return {}
    return {int(row.year): bool(getattr(row, column)) for row in ledger.itertuples(index=False)}


def _allocate_inflation(frame: pd.DataFrame, cash: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Spread the consolidated cost-escalation adjustment over the parties.

    ``cost_inflation_adjustment`` escalates the *cost* side of the cash flow, so it
    is shared pro-rata by each party's own base cost in that year.  This is the last
    step that makes the stakeholder nets add up to the consolidated net.
    """

    if "cost_inflation_adjustment" not in cash.columns:
        return frame
    extra: list[dict[str, object]] = []
    for year in years:
        adjustment = float(cash.loc[year, "cost_inflation_adjustment"])
        if not adjustment:
            continue
        subset = frame[frame["year"] == year]
        base = (
            subset[subset["amount_eur"] < 0.0]
            .groupby(["stakeholder", "stakeholder_id"])["amount_eur"]
            .sum()
        )
        total = float(-base.sum())
        if total <= 0.0:
            continue
        for (stakeholder, stakeholder_id), amount in base.items():
            extra.append(
                {
                    "year": int(year),
                    "stakeholder": stakeholder,
                    "stakeholder_id": stakeholder_id,
                    "line_item": "inflation_adjustment",
                    "amount_eur": adjustment * (float(-amount) / total),
                }
            )
    if not extra:
        return frame
    return pd.concat([frame, pd.DataFrame(extra, columns=list(frame.columns))], ignore_index=True)


__all__ = [
    "LINE_ITEMS",
    "REVENUE_COLUMNS",
    "STAKEHOLDER_LABELS",
    "build_stakeholder_table",
    "consolidated_net_by_year",
    "cost_breakdown_for_year",
    "cumulative_costs",
    "entity_index",
    "entity_statement",
    "stakeholder_net_by_year",
    "stakeholder_summary",
]