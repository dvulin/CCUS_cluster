"""Financial coupling: CAPEX/OPEX, NPV/IRR and per-stakeholder statements."""

from __future__ import annotations

from .cashflow import (
    build_cash_flow_config,
    capex_schedules,
    edge_capex_schedules,
    monitoring_cost_by_sink,
    monitoring_total_by_year,
    upgrade_capex_by_edge,
    upgrade_capex_schedule,
)
from .stakeholders import (
    build_stakeholder_table,
    consolidated_net_by_year,
    cost_breakdown_for_year,
    cumulative_costs,
    entity_index,
    entity_statement,
    stakeholder_net_by_year,
    stakeholder_summary,
)

__all__ = [
    "build_cash_flow_config",
    "build_stakeholder_table",
    "capex_schedules",
    "consolidated_net_by_year",
    "cost_breakdown_for_year",
    "cumulative_costs",
    "edge_capex_schedules",
    "entity_index",
    "entity_statement",
    "monitoring_cost_by_sink",
    "monitoring_total_by_year",
    "stakeholder_net_by_year",
    "stakeholder_summary",
    "upgrade_capex_by_edge",
    "upgrade_capex_schedule",
]