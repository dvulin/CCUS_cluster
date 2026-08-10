"""Composable annual cost and revenue models for an integrated GT-CCS case.

The models in this module consume an already annualised technical ledger.  They
do not call engineering classes and do not introduce physical equations.  All
cost inputs are stated as positive amounts, while calculated cash-flow costs
are returned with a negative sign.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

import numpy as np
import pandas as pd


AnnualValue = (
    Real
    | Sequence[Real]
    | np.ndarray
    | Mapping[int | str, Real]
    | pd.Series
)


class CashFlowInputError(ValueError):
    """Raised when a technical-ledger or economic input is inconsistent."""


def unwrap_config_value(value: Any) -> Any:
    """Unwrap the project's ``[value, unit, description]`` JSON convention.

    Normal Python scalars, yearly mappings and numeric arrays pass through
    unchanged.  Supporting both forms lets the cash-flow layer receive either
    a compact economic configuration or selected values from ``main_inputs``.
    """

    if (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and isinstance(value[1], str)
    ):
        return value[0]
    return value


def annual_series(
    value: Any,
    years: pd.Series | np.ndarray | Sequence[int],
    *,
    name: str,
    default: float = 0.0,
    mapping_default: float | None = None,
) -> pd.Series:
    """Return a finite, non-negative value for every ledger year.

    ``value`` may be a scalar, a sequence matching the number of years, a
    year-keyed mapping or a :class:`pandas.Series`.  A year-keyed mapping must
    cover every year unless ``mapping_default`` is supplied.  This prevents a
    partially specified market price path from silently becoming zero.
    """

    year_array = np.asarray(years, dtype=int)
    value = unwrap_config_value(value)
    if value is None:
        value = default

    if isinstance(value, bool):
        raise CashFlowInputError(f"{name} mora biti broj, a ne bool vrijednost.")

    if isinstance(value, Real):
        result = np.full(year_array.size, float(value), dtype=float)
    elif isinstance(value, pd.Series):
        if all(year in value.index or str(year) in value.index for year in year_array):
            result = np.asarray(
                [
                    value.loc[year]
                    if year in value.index
                    else value.loc[str(year)]
                    for year in year_array
                ],
                dtype=float,
            )
        elif len(value) == year_array.size:
            result = value.to_numpy(dtype=float)
        else:
            raise CashFlowInputError(
                f"{name} mora imati jednu vrijednost za svaku godinu tehničke tablice."
            )
    elif isinstance(value, Mapping):
        resolved: list[float] = []
        missing: list[int] = []
        for year in year_array:
            if year in value:
                resolved.append(value[year])
            elif str(year) in value:
                resolved.append(value[str(year)])
            elif mapping_default is not None:
                resolved.append(mapping_default)
            else:
                missing.append(int(year))
        if missing:
            raise CashFlowInputError(
                f"{name} nema vrijednost za godine: {', '.join(map(str, missing))}."
            )
        result = np.asarray(resolved, dtype=float)
    elif (
        isinstance(value, (Sequence, np.ndarray))
        and not isinstance(value, (str, bytes))
    ):
        result = np.asarray(value, dtype=float)
        if result.ndim != 1 or result.size != year_array.size:
            raise CashFlowInputError(
                f"{name} mora imati točno {year_array.size} godišnjih vrijednosti."
            )
    else:
        raise CashFlowInputError(
            f"{name} mora biti skalar, godišnji niz ili mapa po godinama."
        )

    if not np.all(np.isfinite(result)):
        raise CashFlowInputError(f"{name} mora sadržavati samo konačne vrijednosti.")
    if np.any(result < 0):
        raise CashFlowInputError(f"{name} ne smije sadržavati negativne vrijednosti.")
    return pd.Series(result, index=year_array, dtype=float, name=name)


class CapexCostModel:
    """Place a positive CAPEX input into the ledger as a negative cash flow."""

    def __init__(
        self,
        line_item: str,
        amount_eur: Any = 0.0,
        year: int | None = None,
        schedule_eur: Any = None,
    ):
        self.line_item = line_item
        self.amount_eur = amount_eur
        self.year = year
        self.schedule_eur = schedule_eur

    def calculate(self, years: Sequence[int] | pd.Series) -> pd.Series:
        year_array = np.asarray(years, dtype=int)
        amount = unwrap_config_value(self.amount_eur)
        amount = 0.0 if amount is None else amount

        if self.schedule_eur is not None:
            if not isinstance(amount, Real) or float(amount) != 0.0:
                raise CashFlowInputError(
                    f"{self.line_item}: ne mogu se istodobno zadati ukupni CAPEX "
                    "i CAPEX raspored."
                )
            schedule = annual_series(
                self.schedule_eur,
                year_array,
                name=f"{self.line_item}.schedule_eur",
                mapping_default=0.0,
            )
            return (-schedule).rename(self.line_item)

        if isinstance(amount, bool) or not isinstance(amount, Real):
            raise CashFlowInputError(
                f"{self.line_item}.amount_eur mora biti nenegativan broj."
            )
        amount = float(amount)
        if not np.isfinite(amount) or amount < 0:
            raise CashFlowInputError(
                f"{self.line_item}.amount_eur mora biti nenegativan konačan broj."
            )

        result = pd.Series(0.0, index=year_array, name=self.line_item)
        if amount == 0.0:
            return result

        capex_year = int(year_array[0] if self.year is None else self.year)
        if capex_year not in result.index:
            raise CashFlowInputError(
                f"{self.line_item}: CAPEX godina {capex_year} nije unutar tehničke tablice."
            )
        result.loc[capex_year] = -amount
        return result


class OperatingCostModel:
    """Calculate fixed and quantity-driven OPEX for one component."""

    def __init__(
        self,
        line_item: str,
        quantity_column: str,
        active_column: str,
        variable_rate_eur_per_unit: Any = 0.0,
        fixed_opex_eur_per_year: Any = 0.0,
    ):
        self.line_item = line_item
        self.quantity_column = quantity_column
        self.active_column = active_column
        self.variable_rate_eur_per_unit = variable_rate_eur_per_unit
        self.fixed_opex_eur_per_year = fixed_opex_eur_per_year

    def calculate(self, ledger: pd.DataFrame) -> pd.Series:
        years = ledger["year"].to_numpy(dtype=int)
        quantity = ledger[self.quantity_column].to_numpy(dtype=float)
        active = ledger[self.active_column].to_numpy(dtype=bool)
        variable_rate = annual_series(
            self.variable_rate_eur_per_unit,
            years,
            name=f"{self.line_item}.variable_rate_eur_per_unit",
        ).to_numpy()
        fixed_opex = annual_series(
            self.fixed_opex_eur_per_year,
            years,
            name=f"{self.line_item}.fixed_opex_eur_per_year",
        ).to_numpy()

        total_cost = quantity * variable_rate + active.astype(float) * fixed_opex
        return pd.Series(-total_cost, index=years, name=self.line_item)


class MonitoringCostModel:
    """Apply separate annual monitoring costs during and after injection."""

    def __init__(
        self,
        annual_cost_during_injection_eur: Any = 0.0,
        annual_cost_after_injection_eur: Any = 0.0,
    ):
        self.annual_cost_during_injection_eur = annual_cost_during_injection_eur
        self.annual_cost_after_injection_eur = annual_cost_after_injection_eur

    def calculate(self, ledger: pd.DataFrame) -> pd.Series:
        years = ledger["year"].to_numpy(dtype=int)
        monitoring_active = ledger["monitoring_active"].to_numpy(dtype=bool)
        injection_active = ledger["injection_active"].to_numpy(dtype=bool)
        during_cost = annual_series(
            self.annual_cost_during_injection_eur,
            years,
            name="monitoring.annual_cost_during_injection_eur",
        ).to_numpy()
        after_cost = annual_series(
            self.annual_cost_after_injection_eur,
            years,
            name="monitoring.annual_cost_after_injection_eur",
        ).to_numpy()

        selected_cost = np.where(injection_active, during_cost, after_cost)
        return pd.Series(
            -(monitoring_active.astype(float) * selected_cost),
            index=years,
            name="monitoring",
        )


class ElectricityCashFlowModel:
    """Value annual electricity export and purchase already present in ledger."""

    def __init__(
        self,
        sell_price_eur_per_mwh: Any = 0.0,
        buy_price_eur_per_mwh: Any = 0.0,
    ):
        self.sell_price_eur_per_mwh = sell_price_eur_per_mwh
        self.buy_price_eur_per_mwh = buy_price_eur_per_mwh

    def calculate(self, ledger: pd.DataFrame) -> pd.DataFrame:
        years = ledger["year"].to_numpy(dtype=int)
        sell_price = annual_series(
            self.sell_price_eur_per_mwh,
            years,
            name="electricity.sell_price_eur_per_mwh",
        ).to_numpy()
        buy_price = annual_series(
            self.buy_price_eur_per_mwh,
            years,
            name="electricity.buy_price_eur_per_mwh",
        ).to_numpy()

        export = ledger["electricity_export_mwh"].to_numpy(dtype=float)
        purchase = ledger["electricity_import_mwh"].to_numpy(dtype=float)
        return pd.DataFrame(
            {
                "electricity_revenue": export * sell_price,
                "electricity_purchase": -(purchase * buy_price),
            },
            index=years,
        )


class Co2ValueModel:
    """Value the authoritative annual CO2-chain quantity as positive income."""

    def __init__(self, value_eur_per_t: Any = 0.0):
        self.value_eur_per_t = value_eur_per_t

    def calculate(self, ledger: pd.DataFrame) -> pd.Series:
        years = ledger["year"].to_numpy(dtype=int)
        unit_value = annual_series(
            self.value_eur_per_t,
            years,
            name="co2_value.value_eur_per_t",
        ).to_numpy()
        quantity = ledger["co2_chain_t"].to_numpy(dtype=float)
        return pd.Series(
            quantity * unit_value,
            index=years,
            name="co2_value",
        )
