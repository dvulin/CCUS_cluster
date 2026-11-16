"""Per-stakeholder economics: who earns and who pays, year by year.

The consolidated cash-flow model answers "is the cluster worth it".  A cluster
study also has to answer "who carries which cost", because emitters, transport
operators and storage operators are usually different parties.  This module
splits the same physical flows into per-stakeholder statements.

Convention (cost-reflective tariffs, no margin)
-----------------------------------------------
* the emitter pays the transport tariff of every arc it uses and the injection
  tariff of the sink it feeds;
* the transport operator collects those transport tariffs;
* the storage operator collects the injection tariffs;
* the geothermal operator sells the net electricity.

With these conventions every transfer cancels on consolidation, so the sum of
the stakeholder net cash flows equals the consolidated net cash flow of the
scenario.  Tariffs are explicit data (``EdgeState.opex_eur_per_t`` /
``StorageSink.opex_eur_per_t``); a study that wants a margin can raise them.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from ccus_core.models import ScenarioConfig

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
}

LINE_ITEMS = ("capex", "opex", "tariff_paid", "tariff_collected", "revenue")


def build_stakeholder_table(
    scenario: ScenarioConfig, result, *, include_transfers: bool = True
) -> pd.DataFrame:
    """Return a tidy ``year × stakeholder × line item`` table in euro."""

    ledger = result.ledger
    years = [int(year) for year in ledger["year"]]
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

    # ------------------------------------------------------------- emitters
    capture_capex = _schedule_from_capture(scenario, years)
    for emitter in scenario.emitters:
        capture = emitter.capture
        if capture is None:
            continue
        for year in years:
            captured = emitter.captured_emissions(year)
            if captured <= 0.0:
                continue
            add(year, "emitter", emitter.id, "opex", -capture.opex_eur_per_t * captured)
        for year, amount in capture_capex.get(emitter.id, {}).items():
            add(int(year), "emitter", emitter.id, "capex", -float(amount))

    # ------------------------------------------------------------- transport
    for edge in scenario.edges:
        state_by_year = {}
        for year in years:
            state = edge.resolve_state(year)
            if state is not None:
                state_by_year[int(year)] = state
        for year, state in state_by_year.items():
            if state.capex_eur:
                add(year, "transport", edge.id, "capex", -float(state.capex_eur))
        for routing in result.routing:
            year = int(routing.year)
            flow = float(routing.edge_flows.get(edge.id, 0.0))
            state = state_by_year.get(year)
            if flow <= 0.0 or state is None:
                continue
            tariff = state.variable_opex_eur_per_t() * flow
            add(year, "transport", edge.id, "opex", -float(state.opex_eur_per_t) * flow)
            if include_transfers:
                add(year, "transport", edge.id, "tariff_collected", +tariff)

    # emitter side of the transport tariff
    if include_transfers:
        for routing in result.routing:
            for allocation in routing.allocations:
                add(
                    int(routing.year),
                    "emitter",
                    allocation.emitter_id,
                    "tariff_paid",
                    -float(allocation.cost_eur),
                )

    # -------------------------------------------------------------- storage
    for sink in scenario.storage_sinks:
        start = sink.commissioning_year or min(years)
        for year, amount in _sink_capex_schedule(sink, start).items():
            add(int(year), "storage", sink.id, "capex", -float(amount))
        for year in years:
            injected = 0.0
            frame = result.reservoir.get(sink.id)
            if frame is not None:
                row = frame.loc[frame["year"] == year]
                if not row.empty:
                    injected = float(row["co2_injected_t"].iloc[0])
            if injected <= 0.0:
                continue
            add(year, "storage", sink.id, "opex", -sink.opex_eur_per_t * injected)
            if include_transfers:
                add(year, "storage", sink.id, "tariff_collected", sink.opex_eur_per_t * injected)
        # monitoring
        for year in years:
            frame = result.reservoir.get(sink.id)
            if frame is None:
                continue
            row = frame.loc[frame["year"] == year]
            if row.empty or not bool(row["active"].iloc[0]):
                continue
            cost = (
                sink.monitoring_cost_during_injection_eur_per_year
                if sink.commissioning_year is not None and year >= sink.commissioning_year
                else sink.monitoring_cost_after_injection_eur_per_year
            )
            if cost:
                add(year, "storage", sink.id, "opex", -float(cost))

    # emitters pay the injection tariff
    if include_transfers:
        for routing in result.routing:
            for sink_id, injected in routing.sink_injections.items():
                sink = scenario.sink_by_id(sink_id)
                if sink is None or injected <= 0.0:
                    continue
                for allocation in routing.allocations:
                    if allocation.sink_id != sink_id:
                        continue
                    add(
                        int(routing.year),
                        "emitter",
                        allocation.emitter_id,
                        "tariff_paid",
                        -sink.opex_eur_per_t * allocation.quantity_t,
                    )

    # ------------------------------------------------------------ geothermal
    if result.cash_flow is not None:
        electricity = _electricity_cash_flow(result.cash_flow)
    else:
        electricity = {}
    for system in scenario.geothermal_systems:
        for year, amount in _geothermal_capex_schedule(system, years).items():
            add(int(year), "geothermal", system.id, "capex", -float(amount))
        for year in years:
            opex = system.fixed_opex_eur_per_year if system.active_in(year) else 0.0
            if opex:
                add(year, "geothermal", system.id, "opex", -float(opex))
            revenue = electricity.get(year, 0.0)
            if revenue:
                add(year, "geothermal", system.id, "revenue", float(revenue))

    frame = pd.DataFrame(rows, columns=["year", "stakeholder", "stakeholder_id", "line_item", "amount_eur"])
    if frame.empty:
        return frame
    frame.attrs["stakeholder_labels"] = STAKEHOLDER_LABELS
    return frame


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


# --------------------------------------------------------------------- helpers
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
                "label": f"{edge.name} (operater prijevoza)",
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
                "label": f"{system.name} (operater geotermalne)",
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
    ``net_by_year`` and the totals (CAPEX, OPEX, tariffs, revenue, net and – when
    a discount rate is given – the entity's NPV).
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


def _schedule_from_capture(scenario: ScenarioConfig, years: list[int]) -> dict[str, dict[int, float]]:
    schedule: dict[str, dict[int, float]] = {}
    for emitter in scenario.emitters:
        capture = emitter.capture
        if capture is None or not capture.capex_eur:
            continue
        schedule.setdefault(emitter.id, {})[int(capture.commissioning_year)] = float(capture.capex_eur)
    return schedule


def _sink_capex_schedule(sink, start_year: int) -> dict[int, float]:
    return {int(start_year): float(sink.capex_eur)} if sink.capex_eur else {}


def _geothermal_capex_schedule(system, years: list[int]) -> dict[int, float]:
    start = system.operation_start_year or (min(years) if years else 0)
    return {int(start): float(system.capex_eur)} if system.capex_eur else {}


def _electricity_cash_flow(cash_flow: pd.DataFrame) -> dict[int, float]:
    """Net electricity revenue per year (export revenue minus purchase cost)."""

    if "net_electricity_cash_flow" not in cash_flow.columns:
        return {}
    return {
        int(row.year): float(row.net_electricity_cash_flow)
        for row in cash_flow.itertuples(index=False)
    }


__all__ = [
    "STAKEHOLDER_LABELS",
    "LINE_ITEMS",
    "build_stakeholder_table",
    "stakeholder_summary",
    "entity_index",
    "entity_statement",
    "cumulative_costs",
    "cost_breakdown_for_year",
]