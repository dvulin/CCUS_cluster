"""Annual component cash-flow runner for the integrated GT-CCS scenario.

The runner uses composition: independent cost models consume a canonical
annual technical ledger and return auditable line items.  Costs are escalated
with the configured inflation rate before the nominal cash flow is discounted.
This keeps inflation and discounting explicit and avoids making future costs
artificially cheap.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from .cost_models import (
    CapexCostModel,
    CashFlowInputError,
    Co2ValueModel,
    ElectricityCashFlowModel,
    MonitoringCostModel,
    OperatingCostModel,
    annual_series,
    unwrap_config_value,
)


REQUIRED_LEDGER_COLUMNS = (
    "year",
    "co2_chain_t",
    "orc_gross_mwh",
    "gt_pump_mwh",
    "co2_compressor_mwh",
    "electricity_export_mwh",
    "electricity_import_mwh",
    "injection_active",
    "geothermal_active",
    "monitoring_active",
)

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

REVENUE_LINE_ITEM_COLUMNS = (
    "electricity_revenue",
    "co2_value",
)

BASE_LINE_ITEM_COLUMNS = (
    *COST_LINE_ITEM_COLUMNS,
    *REVENUE_LINE_ITEM_COLUMNS,
)

CASH_FLOW_COLUMNS = (
    "year",
    *COST_LINE_ITEM_COLUMNS,
    *REVENUE_LINE_ITEM_COLUMNS,
    "inflation_adjusted_electricity_purchase",
    "net_electricity_cash_flow",
    "cost_inflation_adjustment",
    "net_cash_flow",
    "cumulative_net_cash_flow",
    "discount_factor",
    "discounted_cash_flow",
    "cumulative_npv",
    "without_ccs_cash_flow",
    "cumulative_without_ccs_cash_flow",
    "discounted_without_ccs_cash_flow",
    "cumulative_discounted_without_ccs_cash_flow",
)


_FLAT_ALIASES = {
    ("capture", "capex_eur"): ("capture_capex_eur", "emitter_capex"),
    ("capture", "variable_opex_eur_per_t"): (
        "capture_opex_eur_per_t",
        "emitter_opex_per_ton",
    ),
    ("transport", "capex_eur"): ("transport_capex_eur", "transport_capex"),
    ("transport", "variable_opex_eur_per_t"): (
        "transport_opex_eur_per_t",
        "transport_opex_per_ton",
    ),
    ("storage", "capex_eur"): ("storage_capex_eur", "storage_capex"),
    ("storage", "variable_opex_eur_per_t"): (
        "storage_opex_eur_per_t",
        "storage_opex_per_ton",
    ),
    ("compressor", "capex_eur"): (
        "compressor_capex",
        "compressor_capex_eur",
    ),
    ("compressor", "fixed_opex_eur_per_year"): (
        "compressor_annual_opex",
    ),
    ("geothermal", "capex_eur"): (
        "geothermal_capex",
        "geothermal_capex_eur",
    ),
    ("geothermal", "fixed_opex_eur_per_year"): (
        "geothermal_annual_opex",
    ),
    ("electricity", "sell_price_eur_per_mwh"): (
        "electricity_sell_price",
        "electricity_sell_price_eur_per_mwh",
    ),
    ("electricity", "buy_price_eur_per_mwh"): (
        "electricity_buy_price",
        "electricity_buy_price_eur_per_mwh",
    ),
    ("co2_value", "value_eur_per_t"): (
        "co2_value_eur_per_t",
        "co2_price_eur_per_t",
    ),
}


def _as_dataframe(ledger: pd.DataFrame | Mapping[str, Any]) -> pd.DataFrame:
    if isinstance(ledger, pd.DataFrame):
        return ledger.copy(deep=True)
    if not isinstance(ledger, Mapping):
        raise CashFlowInputError(
            "Godišnja tehnička tablica mora biti pandas DataFrame ili dict."
        )
    try:
        if ledger and all(np.isscalar(value) for value in ledger.values()):
            return pd.DataFrame([dict(ledger)])
        return pd.DataFrame(dict(ledger))
    except (TypeError, ValueError) as exc:
        raise CashFlowInputError(
            "Godišnju tehničku tablicu nije moguće pretvoriti u DataFrame."
        ) from exc


def _normalise_active(series: pd.Series, *, name: str) -> pd.Series:
    if series.isna().any():
        raise CashFlowInputError(f"{name} ne smije sadržavati prazne vrijednosti.")

    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)

    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any() or not numeric.isin([0, 1]).all():
        raise CashFlowInputError(f"{name} mora sadržavati samo True/False ili 0/1.")
    return numeric.astype(bool)


def _normalise_ledger(ledger: pd.DataFrame | Mapping[str, Any]) -> pd.DataFrame:
    frame = _as_dataframe(ledger)
    missing = [column for column in REQUIRED_LEDGER_COLUMNS if column not in frame]
    if missing:
        raise CashFlowInputError(
            "Godišnjoj tehničkoj tablici nedostaju stupci: " + ", ".join(missing)
        )
    if frame.empty:
        raise CashFlowInputError("Godišnja tehnička tablica ne smije biti prazna.")

    frame = frame.loc[:, REQUIRED_LEDGER_COLUMNS].copy()
    years = pd.to_numeric(frame["year"], errors="coerce")
    if years.isna().any() or not np.equal(years, np.floor(years)).all():
        raise CashFlowInputError("year mora sadržavati cijele kalendarske godine.")
    frame["year"] = years.astype(int)
    if frame["year"].duplicated().any():
        raise CashFlowInputError("Godišnja tehnička tablica sadrži duple godine.")
    if not frame["year"].is_monotonic_increasing:
        raise CashFlowInputError("Godine u tehničkoj tablici moraju biti rastuće.")

    numeric_columns = (
        "co2_chain_t",
        "orc_gross_mwh",
        "gt_pump_mwh",
        "co2_compressor_mwh",
        "electricity_export_mwh",
        "electricity_import_mwh",
    )
    for column in numeric_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy()).all():
            raise CashFlowInputError(
                f"{column} mora sadržavati samo konačne numeričke vrijednosti."
            )
        if (values < 0).any():
            raise CashFlowInputError(f"{column} ne smije sadržavati negativne vrijednosti.")
        frame[column] = values.astype(float)

    for column in ("injection_active", "geothermal_active", "monitoring_active"):
        frame[column] = _normalise_active(frame[column], name=column)

    if ((frame["co2_chain_t"] > 0) & ~frame["injection_active"]).any():
        raise CashFlowInputError(
            "co2_chain_t je veći od nule u godini u kojoj utiskivanje nije aktivno."
        )
    if (
        ((frame["co2_compressor_mwh"] > 0) & ~frame["injection_active"])
    ).any():
        raise CashFlowInputError(
            "Energija CO2 kompresora postoji u godini u kojoj utiskivanje nije aktivno."
        )
    if (
        (
            ((frame["orc_gross_mwh"] > 0) | (frame["gt_pump_mwh"] > 0))
            & ~frame["geothermal_active"]
        )
    ).any():
        raise CashFlowInputError(
            "Geotermalna energija postoji u godini u kojoj geotermalni sustav nije aktivan."
        )
    return frame.reset_index(drop=True)


def _nested_config(config: Mapping[str, Any], section: str) -> Mapping[str, Any]:
    value = config.get(section, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CashFlowInputError(f"Konfiguracijska sekcija '{section}' mora biti dict.")
    return value


def _config_value(
    config: Mapping[str, Any],
    section: str,
    key: str,
    default: Any = 0.0,
) -> Any:
    nested = _nested_config(config, section)
    if key in nested:
        return unwrap_config_value(nested[key])

    for alias in _FLAT_ALIASES.get((section, key), ()):
        if alias in config:
            return unwrap_config_value(config[alias])

    direct_key = f"{section}_{key}"
    if direct_key in config:
        return unwrap_config_value(config[direct_key])
    return default


def _default_capex_year(config: Mapping[str, Any], first_year: int) -> int:
    value = config.get("economics_ccs_start_year", first_year)
    value = unwrap_config_value(value)
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise CashFlowInputError("economics_ccs_start_year mora biti cijela godina.")
    return int(value)


def _economic_rate(
    config: Mapping[str, Any],
    key: str,
    *,
    label: str,
) -> float:
    value = unwrap_config_value(config.get(key, 0.0))
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float, np.integer, np.floating),
    ):
        raise CashFlowInputError(f"{label} mora biti nenegativan broj.")
    value = float(value)
    if not np.isfinite(value) or value < 0.0:
        raise CashFlowInputError(f"{label} mora biti nenegativan konačan broj.")
    return value


def _irr_roots(cash_flows: np.ndarray) -> list[float]:
    """Return all numerically valid annual IRR roots greater than -100%."""
    values = np.asarray(cash_flows, dtype=float)
    if (
        values.size < 2
        or not np.any(values > 0.0)
        or not np.any(values < 0.0)
    ):
        return []

    # With x = 1 / (1 + IRR), NPV = 0 becomes a polynomial in x.
    roots_x = np.polynomial.polynomial.polyroots(values)
    roots: list[float] = []
    scale = max(1.0, float(np.sum(np.abs(values))))
    periods = np.arange(values.size, dtype=float)
    for root_x in roots_x:
        if abs(float(root_x.imag)) > 1e-7 or float(root_x.real) <= 0.0:
            continue
        rate = 1.0 / float(root_x.real) - 1.0
        if not np.isfinite(rate) or rate <= -1.0:
            continue
        residual = float(np.sum(values / (1.0 + rate) ** periods))
        if abs(residual) > scale * 1e-7:
            continue
        if not any(abs(rate - existing) <= 1e-7 for existing in roots):
            roots.append(rate)
    return sorted(roots)


def summarize_cash_flow(cash_flow: pd.DataFrame) -> dict[str, Any]:
    """Return PV, NPV and IRR metrics from a completed annual cash-flow table."""
    missing = [column for column in CASH_FLOW_COLUMNS if column not in cash_flow]
    if missing:
        raise CashFlowInputError(
            "Tablici novčanog toka nedostaju stupci: " + ", ".join(missing)
        )

    discount_factor = cash_flow["discount_factor"].to_numpy(dtype=float)
    base_costs = cash_flow.loc[:, COST_LINE_ITEM_COLUMNS].sum(axis=1).to_numpy(
        dtype=float
    )
    inflation_adjustment = cash_flow[
        "cost_inflation_adjustment"
    ].to_numpy(dtype=float)
    revenues = cash_flow.loc[:, REVENUE_LINE_ITEM_COLUMNS].sum(axis=1).to_numpy(
        dtype=float
    )
    nominal_cash_flow = cash_flow["net_cash_flow"].to_numpy(dtype=float)
    irr_roots = _irr_roots(nominal_cash_flow)
    if irr_roots:
        # A conventional IRR calculator starts from a 10% guess.  If the
        # project has multiple mathematical roots, report the closest one and
        # make that ambiguity explicit in the status.
        irr = min(irr_roots, key=lambda rate: abs(rate - 0.10))
        irr_status = "multiple_roots" if len(irr_roots) > 1 else "defined"
    else:
        irr = None
        irr_status = "not_defined"

    return {
        "discount_rate": float(cash_flow.attrs.get("discount_rate", 0.0)),
        "inflation_rate": float(cash_flow.attrs.get("inflation_rate", 0.0)),
        "discount_base_year": int(cash_flow["year"].iloc[0]),
        "pv_revenues_eur": float(np.sum(revenues * discount_factor)),
        "pv_costs_eur": float(
            np.sum((base_costs + inflation_adjustment) * discount_factor)
        ),
        "npv_eur": float(cash_flow["discounted_cash_flow"].sum()),
        "irr": irr,
        "irr_status": irr_status,
        "irr_roots": irr_roots,
        "without_ccs_npv_eur": float(
            cash_flow["discounted_without_ccs_cash_flow"].sum()
        ),
    }


def _asset_models(
    config: Mapping[str, Any],
    *,
    section: str,
    quantity_column: str,
    active_column: str,
    variable_rate_key: str,
    default_capex_year: int,
    variable_rate_override: Any = None,
) -> tuple[CapexCostModel, OperatingCostModel]:
    capex_year = _config_value(config, section, "capex_year", default_capex_year)
    capex_year = unwrap_config_value(capex_year)
    if isinstance(capex_year, bool) or not isinstance(capex_year, (int, np.integer)):
        raise CashFlowInputError(f"{section}.capex_year mora biti cijela godina.")

    variable_rate = (
        _config_value(
            config,
            section,
            variable_rate_key,
            0.0,
        )
        if variable_rate_override is None
        else variable_rate_override
    )

    return (
        CapexCostModel(
            line_item=f"{section}_capex",
            amount_eur=_config_value(config, section, "capex_eur", 0.0),
            year=int(capex_year),
            schedule_eur=_config_value(config, section, "capex_schedule_eur", None),
        ),
        OperatingCostModel(
            line_item=f"{section}_opex",
            quantity_column=quantity_column,
            active_column=active_column,
            variable_rate_eur_per_unit=variable_rate,
            fixed_opex_eur_per_year=_config_value(
                config,
                section,
                "fixed_opex_eur_per_year",
                0.0,
            ),
        ),
    )


class CashFlowRunner:
    """Calculate auditable annual GT-CCS cash-flow line items.

    Recommended configuration sections are ``capture``, ``transport``,
    ``compressor``, ``storage``, ``geothermal``, ``monitoring``,
    ``electricity`` and ``co2_value``.  Asset sections accept ``capex_eur``,
    ``capex_year`` (or ``capex_schedule_eur``), ``fixed_opex_eur_per_year``
    and a component-specific variable OPEX rate.
    """

    def __init__(self, config: Mapping[str, Any] | None = None):
        if config is None:
            config = {}
        if not isinstance(config, Mapping):
            raise CashFlowInputError("Ekonomska konfiguracija mora biti dict.")
        self.config = dict(config)

    def run(
        self,
        annual_technical_ledger: pd.DataFrame | Mapping[str, Any],
    ) -> pd.DataFrame:
        ledger = _normalise_ledger(annual_technical_ledger)
        years = ledger["year"].to_numpy(dtype=int)
        default_capex_year = _default_capex_year(self.config, int(years[0]))

        output = pd.DataFrame({"year": years})
        asset_specs = (
            ("capture", "co2_chain_t", "injection_active", "variable_opex_eur_per_t"),
            (
                "compressor",
                "co2_compressor_mwh",
                "injection_active",
                "variable_opex_eur_per_mwh",
            ),
            ("storage", "co2_chain_t", "injection_active", "variable_opex_eur_per_t"),
            (
                "geothermal",
                "orc_gross_mwh",
                "geothermal_active",
                "variable_opex_eur_per_mwh",
            ),
        )

        for section, quantity_column, active_column, rate_key in asset_specs:
            capex_model, opex_model = _asset_models(
                self.config,
                section=section,
                quantity_column=quantity_column,
                active_column=active_column,
                variable_rate_key=rate_key,
                default_capex_year=default_capex_year,
            )
            output[capex_model.line_item] = capex_model.calculate(years).to_numpy()
            output[opex_model.line_item] = opex_model.calculate(ledger).to_numpy()

        transport_mode = str(
            _config_value(self.config, "transport", "mode", "pipeline")
        ).strip().lower()
        if transport_mode not in {"pipeline", "truck", "rail"}:
            raise CashFlowInputError(
                "transport_mode mora biti 'pipeline', 'truck' ili 'rail'."
            )

        if transport_mode == "pipeline":
            transport_variable_rate = _config_value(
                self.config,
                "transport",
                "variable_opex_eur_per_t",
                0.0,
            )
        else:
            transport_opex_per_tkm = annual_series(
                _config_value(
                    self.config,
                    "transport",
                    "opex_eur_per_tkm",
                    0.0,
                ),
                years,
                name="transport.opex_eur_per_tkm",
            ).to_numpy()
            transport_distance_km = annual_series(
                _config_value(
                    self.config,
                    "transport",
                    "distance_km",
                    0.0,
                ),
                years,
                name="transport.distance_km",
            ).to_numpy()
            transport_variable_rate = (
                transport_opex_per_tkm * transport_distance_km
            )

        transport_capex_model, transport_opex_model = _asset_models(
            self.config,
            section="transport",
            quantity_column="co2_chain_t",
            active_column="injection_active",
            variable_rate_key="variable_opex_eur_per_t",
            default_capex_year=default_capex_year,
            variable_rate_override=transport_variable_rate,
        )
        output["transport_capex"] = transport_capex_model.calculate(
            years
        ).to_numpy()
        output["transport_opex"] = transport_opex_model.calculate(
            ledger
        ).to_numpy()

        monitoring_capex_model = CapexCostModel(
            line_item="monitoring",
            amount_eur=_config_value(
                self.config,
                "monitoring",
                "capex_eur",
                0.0,
            ),
            year=int(
                _config_value(
                    self.config,
                    "monitoring",
                    "capex_year",
                    default_capex_year,
                )
            ),
            schedule_eur=_config_value(
                self.config,
                "monitoring",
                "capex_schedule_eur",
                None,
            ),
        )
        monitoring_opex_model = MonitoringCostModel(
            annual_cost_during_injection_eur=_config_value(
                self.config,
                "monitoring",
                "annual_cost_during_injection",
                0.0,
            ),
            annual_cost_after_injection_eur=_config_value(
                self.config,
                "monitoring",
                "annual_cost_after_injection",
                0.0,
            ),
        )
        output["monitoring"] = (
            monitoring_capex_model.calculate(years).to_numpy()
            + monitoring_opex_model.calculate(ledger).to_numpy()
        )

        electricity_model = ElectricityCashFlowModel(
            sell_price_eur_per_mwh=_config_value(
                self.config,
                "electricity",
                "sell_price_eur_per_mwh",
                0.0,
            ),
            buy_price_eur_per_mwh=_config_value(
                self.config,
                "electricity",
                "buy_price_eur_per_mwh",
                0.0,
            ),
        )
        electricity = electricity_model.calculate(ledger)
        output["electricity_revenue"] = electricity[
            "electricity_revenue"
        ].to_numpy()
        output["electricity_purchase"] = electricity[
            "electricity_purchase"
        ].to_numpy()

        co2_value_model = Co2ValueModel(
            value_eur_per_t=_config_value(
                self.config,
                "co2_value",
                "value_eur_per_t",
                0.0,
            )
        )
        output["co2_value"] = co2_value_model.calculate(ledger).to_numpy()

        discount_rate = _economic_rate(
            self.config,
            "economics_interest_rate",
            label="economics_interest_rate",
        )
        inflation_rate = _economic_rate(
            self.config,
            "economics_inflation_rate",
            label="economics_inflation_rate",
        )
        periods = years - int(years[0])
        cost_inflation_factor = (1.0 + inflation_rate) ** periods
        output["inflation_adjusted_electricity_purchase"] = (
            output["electricity_purchase"] * cost_inflation_factor
        )
        output["net_electricity_cash_flow"] = (
            output["electricity_revenue"]
            + output["inflation_adjusted_electricity_purchase"]
        )
        base_costs = output.loc[:, COST_LINE_ITEM_COLUMNS].sum(axis=1)
        output["cost_inflation_adjustment"] = base_costs * (
            cost_inflation_factor - 1.0
        )
        output["net_cash_flow"] = (
            output.loc[:, BASE_LINE_ITEM_COLUMNS].sum(axis=1)
            + output["cost_inflation_adjustment"]
        )
        output["cumulative_net_cash_flow"] = output["net_cash_flow"].cumsum()

        output["discount_factor"] = 1.0 / (1.0 + discount_rate) ** periods
        output["discounted_cash_flow"] = (
            output["net_cash_flow"] * output["discount_factor"]
        )
        output["cumulative_npv"] = output["discounted_cash_flow"].cumsum()

        annual_emissions = annual_series(
            self.config.get("emitter_emissions_annual", 0.0),
            years,
            name="emitter_emissions_annual",
        ).to_numpy()
        co2_price = annual_series(
            _config_value(
                self.config,
                "co2_value",
                "value_eur_per_t",
                0.0,
            ),
            years,
            name="co2_value.value_eur_per_t",
        ).to_numpy()
        output["without_ccs_cash_flow"] = -(annual_emissions * co2_price)
        output["cumulative_without_ccs_cash_flow"] = output[
            "without_ccs_cash_flow"
        ].cumsum()
        output["discounted_without_ccs_cash_flow"] = (
            output["without_ccs_cash_flow"] * output["discount_factor"]
        )
        output["cumulative_discounted_without_ccs_cash_flow"] = output[
            "discounted_without_ccs_cash_flow"
        ].cumsum()

        output = output.loc[:, CASH_FLOW_COLUMNS]
        output.attrs["discount_rate"] = discount_rate
        output.attrs["inflation_rate"] = inflation_rate
        output.attrs["discount_base_year"] = int(years[0])
        output.attrs["cost_treatment"] = (
            "base-year costs escalated by inflation before discounting"
        )
        return output


def run_cash_flow(
    annual_technical_ledger: pd.DataFrame | Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Convenience wrapper around :class:`CashFlowRunner`."""

    return CashFlowRunner(config).run(annual_technical_ledger)
