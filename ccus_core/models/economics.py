"""Economic configuration for the dynamic cash-flow model.

The Pydantic model is the *input* contract of the engine.  ``to_cash_flow_config``
translates it into the flat mapping already understood by
``economics.cash_flow_runner.CashFlowRunner``, so the existing, auditable cash-flow
code is reused instead of being rewritten.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import CoreModel, fraction


class CustomPricePath(CoreModel):
    """Parametric CO2 price path (legacy custom modes)."""

    function: Literal["linear", "logarithmic", "power_law"] = "linear"
    p0_eur_per_t: float = Field(default=64.0, ge=0.0)
    linear_growth_eur_per_t_per_year: float = Field(default=3.0)
    log_amplitude_eur_per_t: float = Field(default=30.0, ge=0.0)
    log_rate_per_year: float = Field(default=0.1, gt=0.0)
    power_coefficient_eur_per_t: float = Field(default=1.0, ge=0.0)
    power_exponent: float = Field(default=1.5, gt=0.0)

    def value_at(self, elapsed_years: float) -> float:
        tau = float(elapsed_years)
        if self.function == "linear":
            return self.p0_eur_per_t + self.linear_growth_eur_per_t_per_year * tau
        if self.function == "logarithmic":
            import math

            return self.p0_eur_per_t + self.log_amplitude_eur_per_t * math.log1p(self.log_rate_per_year * tau)
        return self.p0_eur_per_t + self.power_coefficient_eur_per_t * (tau**self.power_exponent)


class PricePath(CoreModel):
    """CO2 price path: one of the three presets or a custom parametric curve."""

    mode: Literal["pessimistic", "conservative", "optimistic", "custom"] = "conservative"
    start_year: int = 2025
    values_eur_per_t: list[float] | None = Field(
        default=None,
        description="Preset values starting at start_year; required for preset modes.",
    )
    custom: CustomPricePath | None = None

    @model_validator(mode="after")
    def _check(self) -> "PricePath":
        if self.mode == "custom":
            if self.custom is None:
                raise ValueError("custom price path requires a CustomPricePath")
        else:
            if not self.values_eur_per_t:
                raise ValueError("a preset price path requires values_eur_per_t")
            if any(value < 0.0 for value in self.values_eur_per_t):
                raise ValueError("CO2 prices must be non-negative")
        return self

    def price_at(self, year: int, reference_year: int | None = None) -> float:
        """Price in ``year``; outside the published range the endpoint is held.

        A custom path is anchored at ``reference_year`` (the economic start year
        by default), which reproduces the legacy ``tau = year - start_year``
        convention.
        """

        if self.mode == "custom":
            assert self.custom is not None
            anchor = int(self.start_year if reference_year is None else reference_year)
            return max(0.0, self.custom.value_at(float(year - anchor)))
        assert self.values_eur_per_t
        index = min(max(int(year) - int(self.start_year), 0), len(self.values_eur_per_t) - 1)
        return float(self.values_eur_per_t[index])

    def to_frame(self, start_year: int, end_year: int):
        """Return the same ``Godina``/``Cijena CO2`` frame used by the app."""

        import pandas as pd

        years = list(range(int(start_year), int(end_year) + 1))
        return pd.DataFrame(
            {
                "Godina": years,
                "Cijena CO2 (EUR/tCO2)": [self.price_at(year) for year in years],
            }
        )


class EconomicsConfig(CoreModel):
    """Discounting, cost escalation and CO2 price assumptions."""

    start_year: int
    end_year: int
    capex_start_year: int
    discount_rate: float = Field(default=0.05, ge=0.0, lt=1.0)
    inflation_rate: float = Field(default=0.05, ge=0.0, lt=1.0)
    electricity_sell_price_eur_per_mwh: float = Field(default=0.0, ge=0.0)
    electricity_buy_price_eur_per_mwh: float = Field(default=0.0, ge=0.0)
    co2_value_eur_per_t: float | None = Field(
        default=None,
        ge=0.0,
        description="Flat CO2 value; when omitted the price path is used year by year.",
    )
    price_path: PricePath = Field(
        default_factory=lambda: PricePath(mode="custom", custom=CustomPricePath()),
        description="CO2 price path; defaults to the legacy linear custom path.",
    )
    cost_treatment: Literal[
        "base_year_escalated_then_discounted",
        "real_terms",
    ] = "base_year_escalated_then_discounted"
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "EconomicsConfig":
        if self.end_year < self.start_year:
            raise ValueError("end_year must not precede start_year")
        if not (self.start_year <= self.capex_start_year <= self.end_year):
            raise ValueError("capex_start_year must lie inside the economic horizon")
        return self

    def years(self) -> list[int]:
        return list(range(int(self.start_year), int(self.end_year) + 1))

    def prices_by_year(self) -> dict[int, float]:
        if self.co2_value_eur_per_t is not None:
            return {year: float(self.co2_value_eur_per_t) for year in self.years()}
        return {year: self.price_path.price_at(year, reference_year=self.start_year) for year in self.years()}

    def to_cash_flow_config(self) -> dict[str, object]:
        """Flat mapping consumed by :class:`economics.cash_flow_runner.CashFlowRunner`."""

        prices = self.prices_by_year()
        return {
            "economics_interest_rate": float(self.discount_rate),
            "economics_inflation_rate": float(self.inflation_rate),
            "economics_start_year": int(self.start_year),
            "economics_end_year": int(self.end_year),
            "economics_ccs_start_year": int(self.capex_start_year),
            "co2_value": {"value_eur_per_t": prices},
            "electricity": {
                "sell_price_eur_per_mwh": float(self.electricity_sell_price_eur_per_mwh),
                "buy_price_eur_per_mwh": float(self.electricity_buy_price_eur_per_mwh),
            },
        }