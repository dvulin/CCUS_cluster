"""Financial coupling: CAPEX/OPEX, NPV/IRR and per-stakeholder statements."""

from __future__ import annotations

from .cashflow import build_cash_flow_config
from .stakeholders import (
    build_stakeholder_table,
    cost_breakdown_for_year,
    cumulative_costs,
    entity_index,
    entity_statement,
    stakeholder_summary,
)

__all__ = [
    "build_cash_flow_config",
    "build_stakeholder_table",
    "cost_breakdown_for_year",
    "cumulative_costs",
    "entity_index",
    "entity_statement",
    "stakeholder_summary",
]