"""Per-stakeholder economics: transfers cancel, each party keeps its own statement.

The hard invariant of this module is the reconciliation

    sum(stakeholder net cash flow) == consolidated net cash flow

for every single year *and* for the total.  The tests below assert it, together with
the CAPEX-once rule that the per-stakeholder view shares with the consolidated one.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ccus_core import ScenarioEngine
from ccus_core.finance import build_stakeholder_table, stakeholder_summary
from ccus_core.finance.stakeholders import (
    consolidated_net_by_year,
    stakeholder_net_by_year,
)

from .test_solver import build_solver_scenario


def run(scenario=None):
    scenario = scenario or build_solver_scenario()
    return scenario, ScenarioEngine(scenario).run()


def test_stakeholder_table_covers_every_party():
    scenario, result = run()

    table = build_stakeholder_table(scenario, result)
    assert set(table["stakeholder"]) >= {"emitter", "storage", "geothermal", "transport"}

    summary = stakeholder_summary(table)
    assert set(summary["year"]) == set(range(2028, 2033))
    # every year and party must be present
    assert len(summary) >= 5 * 4 - 1


def test_stakeholder_nets_reconcile_with_the_consolidated_cash_flow():
    scenario, result = run()

    table = build_stakeholder_table(scenario, result)
    consolidated = consolidated_net_by_year(result.cash_flow)
    stakeholder = stakeholder_net_by_year(table)

    assert set(stakeholder) == set(consolidated)
    for year, expected in consolidated.items():
        assert stakeholder[year] == pytest.approx(expected, rel=1e-9, abs=1e-6)
    # and the total over the horizon
    assert sum(stakeholder.values()) == pytest.approx(
        sum(consolidated.values()), rel=1e-9, abs=1e-2
    )


def test_reconciliation_holds_without_transfers_too():
    """Dropping the tariff rows must not change the total (both sides go)."""

    scenario, result = run()
    with_transfers = build_stakeholder_table(scenario, result)
    without = build_stakeholder_table(scenario, result, include_transfers=False)

    assert stakeholder_net_by_year(without) == pytest.approx(
        stakeholder_net_by_year(with_transfers), rel=1e-9, abs=1e-6
    )


def test_entity_statements_and_charts_helpers():
    scenario, result = run()

    table = build_stakeholder_table(scenario, result)

    from ccus_core.finance import (
        cost_breakdown_for_year,
        cumulative_costs,
        entity_index,
        entity_statement,
    )

    entities = entity_index(scenario)
    labels = {(item["stakeholder"], item["id"]) for item in entities}
    assert ("emitter", "source") in labels
    assert any(key[0] == "storage" for key in labels)

    statement = entity_statement(table, "emitter", "source", discount_rate=0.05)
    assert statement["years"]
    assert statement["totals"]["tariff_paid"] < 0.0
    assert statement["totals"]["revenue"] > 0.0
    assert statement["npv"] is not None

    cumulative = cumulative_costs(result.cash_flow)
    assert cumulative["total"].iloc[-1] >= cumulative["total"].iloc[0]

    breakdown = cost_breakdown_for_year(result.cash_flow, int(result.cash_flow["year"].iloc[-1]))
    assert isinstance(breakdown, dict)


def test_emitter_pays_transport_and_injection_tariffs():
    scenario, result = run()

    table = build_stakeholder_table(scenario, result)
    emitter = table[(table["stakeholder"] == "emitter") & (table["line_item"] == "tariff_paid")]
    assert not emitter.empty
    assert (emitter["amount_eur"] < 0.0).all()

    transport = table[
        (table["stakeholder"] == "transport") & (table["line_item"] == "tariff_collected")
    ]
    storage = table[
        (table["stakeholder"] == "storage") & (table["line_item"] == "tariff_collected")
    ]
    paid = -float(emitter["amount_eur"].sum())
    collected = float(transport["amount_eur"].sum()) + float(storage["amount_eur"].sum())
    assert paid == pytest.approx(collected, rel=1e-9)


def test_transport_capex_is_booked_once_per_state_not_every_year():
    """A state is an asset built once: its CAPEX must not repeat every year."""

    scenario, result = run()
    table = build_stakeholder_table(scenario, result)

    capex = table[(table["line_item"] == "capex") & (table["amount_eur"] < 0.0)]
    for (stakeholder, entity), group in capex.groupby(["stakeholder", "stakeholder_id"]):
        years = sorted(int(year) for year in group["year"])
        assert len(years) == len(set(years)), (
            f"{stakeholder}/{entity} books CAPEX in {years}"
        )

    transport_capex = table[
        (table["stakeholder"] == "transport") & (table["line_item"] == "capex")
    ]
    # the trunk edge is the only route in this scenario and is built in 2028
    trunk = transport_capex[transport_capex["stakeholder_id"] == "trunk"]
    assert list(int(year) for year in trunk["year"]) == [2028]

    # the stakeholder CAPEX must equal the consolidated CAPEX block by block
    consolidated = result.cash_flow.set_index("year")
    for stakeholder, column in (
        ("emitter", "capture_capex"),
        ("storage", "storage_capex"),
        ("geothermal", "geothermal_capex"),
        ("transport", "transport_capex"),
    ):
        booked = -float(
            table[(table["stakeholder"] == stakeholder) & (table["line_item"] == "capex")][
                "amount_eur"
            ].sum()
        )
        expected = -float(consolidated[column].sum())
        assert booked == pytest.approx(expected, abs=1.0), column


def test_upgrade_capex_reaches_the_transport_operator_once():
    from ccus_core.models import InfrastructureUpgrade, TransportEdge, UpgradeTrigger

    from .conftest import pipeline_state

    scenario = build_solver_scenario()
    trunk = scenario.edge_by_id("trunk")
    upgraded = trunk.model_copy(
        update={
            "upgrades": [
                InfrastructureUpgrade(
                    id="trunk_expansion",
                    trigger=UpgradeTrigger(kind="year", year=2030),
                    new_state=pipeline_state(
                        valid_from_year=2030, capacity_t_per_year=2_000_000.0, capex_eur=12_000_000.0
                    ),
                )
            ]
        }
    )
    scenario = scenario.model_copy(
        update={"edges": [upgraded if edge.id == "trunk" else edge for edge in scenario.edges]}
    )
    result = ScenarioEngine(scenario).run()
    table = build_stakeholder_table(scenario, result)

    transport_capex = table[
        (table["stakeholder"] == "transport")
        & (table["stakeholder_id"] == "trunk")
        & (table["line_item"] == "capex")
    ]
    paid = {int(row.year): float(-row.amount_eur) for row in transport_capex.itertuples(index=False)}
    assert paid == {2028: pytest.approx(25_000_000.0), 2030: pytest.approx(12_000_000.0)}
    assert sum(paid.values()) == pytest.approx(
        -float(result.cash_flow["transport_capex"].sum()), abs=1.0
    )
    # the stakeholder sum still reconciles after the upgrade
    assert stakeholder_net_by_year(table) == pytest.approx(
        consolidated_net_by_year(result.cash_flow), rel=1e-9, abs=1e-6
    )


def test_stakeholder_table_is_empty_without_a_cash_flow():
    from dataclasses import replace

    scenario, result = run()
    without_cash_flow = replace(result, cash_flow=None)
    empty = build_stakeholder_table(scenario, without_cash_flow)
    assert isinstance(empty, pd.DataFrame)
    assert empty.empty


@pytest.mark.parametrize(
    "example",
    [
        "ccus_cluster_v1.json",
        "croatia_cluster_2025_2050.json",
        "cluster_three_emitters.json",
    ],
)
def test_reference_scenarios_reconcile_year_by_year(example):
    """The shipped example scenarios must reconcile too (14 emitters, hubs, ESRT)."""

    from ccus_core.io import commented_json

    path = Path(__file__).resolve().parents[1] / "inputs" / "examples" / example
    scenario = commented_json.load_file(path)
    result = ScenarioEngine(scenario).run()
    table = build_stakeholder_table(scenario, result)

    consolidated = consolidated_net_by_year(result.cash_flow)
    stakeholder = stakeholder_net_by_year(table)
    for year, expected in consolidated.items():
        # a year without any cash flow has no stakeholder rows at all
        assert stakeholder.get(year, 0.0) == pytest.approx(expected, rel=1e-9, abs=1e-3), example