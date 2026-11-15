"""Policy, price and unit-cost assumptions taken from the cluster study.

The numbers encoded here are the ones documented in the accompanying workbook
(``emissions-change``, ``razrada scenarija``, ``cash-flow``) and the thesis text:

* emission curve ``E(t) = E0 + b * x**c`` with ``b = a * E0``, ``a`` in
  ``[-0.05, -0.02]`` and ``c = 1.5``;
* CCS implementation probability -> onboarding year (1.0 -> 2026, 0.5 -> 2028,
  0.1 -> 2033);
* capture CAPEX/OPEX by technology, transport CAPEX per t·km, transport OPEX as a
  logarithmic function of distance above 45 km, injection CAPEX/OPEX per tonne;
* EU ETS free-allocation phase-out (50 % in 2025 down to 0 % in 2030);
* three CO2 price scenarios (optimistic, conservative, pessimistic), 2025-2050;
* Fisher relation with a real rate and an inflation rate.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, model_validator

from .base import CoreModel


class EtsAllowanceStep(CoreModel):
    """Free-allocation share of verified emissions in one year."""

    year: int
    free_allowance_share: float = Field(ge=0.0, le=1.0)


class EtsAllowanceSchedule(CoreModel):
    """EU ETS free-allocation phase-out.

    Before the first step and after the last step the nearest step is held
    constant, which reproduces the "50 % until 2025, 0 % from 2030" rule.
    """

    steps: list[EtsAllowanceStep] = Field(
        default_factory=lambda: [
            EtsAllowanceStep(year=2025, free_allowance_share=0.50),
            EtsAllowanceStep(year=2026, free_allowance_share=0.475),
            EtsAllowanceStep(year=2027, free_allowance_share=0.425),
            EtsAllowanceStep(year=2028, free_allowance_share=0.325),
            EtsAllowanceStep(year=2029, free_allowance_share=0.175),
            EtsAllowanceStep(year=2030, free_allowance_share=0.0),
        ],
        min_length=1,
    )

    @model_validator(mode="after")
    def _sorted(self) -> "EtsAllowanceSchedule":
        if [step.year for step in self.steps] != sorted(step.year for step in self.steps):
            raise ValueError("ETS allowance steps must be sorted by year")
        return self

    def share_in(self, year: int) -> float:
        year = int(year)
        eligible = [step for step in self.steps if step.year <= year]
        if not eligible:
            return float(self.steps[0].free_allowance_share)
        return float(eligible[-1].free_allowance_share)

    def taxable_emissions(self, year: int, emissions_t: float) -> float:
        """Emissions that actually have to be paid for in ``year``."""

        return float(emissions_t) * (1.0 - self.share_in(year))


class Co2PriceScenario(CoreModel):
    """One CO2 price path (EUR/t) starting at ``start_year``."""

    name: str = Field(min_length=1)
    start_year: int
    values_eur_per_t: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> "Co2PriceScenario":
        if any(value < 0.0 for value in self.values_eur_per_t):
            raise ValueError("CO2 prices must be non-negative")
        return self

    def price_at(self, year: int) -> float:
        index = min(max(int(year) - int(self.start_year), 0), len(self.values_eur_per_t) - 1)
        return float(self.values_eur_per_t[index])


# workbook ``cash-flow``!F25:AE27 (2025-2050)
DEFAULT_PRICE_SCENARIOS: dict[str, list[float]] = {
    "optimistic": [
        63.64125, 93.9989389639, 104.5330178819, 114.7252192969, 121.8575041324,
        128.8701257457, 131.4420849198, 135.2770703217, 139.5674992013, 143.5154598031,
        143.8802745846, 145.4765368955, 145.8286805579, 148.7786672176, 150.3842612788,
        151.3829339417, 153.0747719889, 154.3161703381, 157.2202312381, 156.9866612705,
        160.2513312822, 162.9810068616, 166.0418107222, 169.8703824812, 173.3818774629,
        183.6171867123,
    ],
    "conservative": [
        63.64125, 68.0799844366, 71.0221120429, 74.8772202337, 78.6593594661,
        81.5764253094, 83.4879060918, 86.9188945306, 89.3276842646, 91.6411585650,
        93.3246865461, 95.1836144885, 96.5695555426, 98.8017618951, 100.2582639075,
        103.3552666886, 105.4016800043, 107.3412987849, 110.9172515922, 113.8398068496,
        118.1648943260, 121.9698448297, 125.2849336901, 130.0779628804, 135.6697911905,
        143.5425492336,
    ],
    "pessimistic": [
        63.64125, 42.5929744459, 39.6550949199, 38.5337419996, 40.4280396868,
        41.5174722122, 42.7922895782, 43.7667235317, 44.9863720163, 46.5039525677,
        45.8905973719, 48.3380841987, 50.1629217792, 51.9976024655, 53.2469070731,
        55.2670276039, 59.2080385316, 59.3206653386, 58.0416829189, 62.3662428829,
        66.7897478691, 67.5430470143, 70.3499097126, 75.7168497702, 78.0843158606,
        82.4954618056,
    ],
}


def default_price_scenarios() -> dict[str, Co2PriceScenario]:
    return {
        name: Co2PriceScenario(name=name, start_year=2025, values_eur_per_t=values)
        for name, values in DEFAULT_PRICE_SCENARIOS.items()
    }


class CaptureCostParameters(CoreModel):
    """Capture CAPEX/OPEX per tonne by technology code."""

    capex_eur_per_t: dict[str, float] = Field(
        default_factory=lambda: {"PI": 100.0, "NI": 75.0, "OXY": 90.0}
    )
    opex_eur_per_t: dict[str, float] = Field(
        default_factory=lambda: {"PI": 30.0, "NI": 40.0, "OXY": 25.0, "DEFAULT": 20.0}
    )
    oxygen_plant_capex_eur: float = Field(default=15_000_000.0, ge=0.0)

    def capex_eur(self, technology: str) -> float:
        return float(self.capex_eur_per_t.get(technology, self.capex_eur_per_t["NI"]))

    def opex_eur(self, technology: str) -> float:
        return float(self.opex_eur_per_t.get(technology, self.opex_eur_per_t.get("DEFAULT", 20.0)))


class TransportCostParameters(CoreModel):
    """Transport CAPEX per t·km and the distance-dependent OPEX rule."""

    capex_eur_per_t_km: float = Field(default=0.7, ge=0.0)
    opex_eur_per_t_short: float = Field(default=15.0, ge=0.0)
    opex_short_length_threshold_km: float = Field(default=45.0, gt=0.0)
    opex_log_a: float = 22.0
    opex_log_b: float = -80.0

    def opex_eur_per_t(self, distance_km: float) -> float:
        """``15 EUR/t`` up to 45 km, ``22*ln(L) - 80 EUR/t`` above it."""

        if distance_km <= self.opex_short_length_threshold_km:
            return float(self.opex_eur_per_t_short)
        return float(self.opex_log_a) * math.log(float(distance_km)) + float(self.opex_log_b)


class StorageCostParameters(CoreModel):
    """Injection CAPEX/OPEX per tonne of stored CO2."""

    capex_eur_per_t: float = Field(default=20.0, ge=0.0)
    opex_eur_per_t: float = Field(default=10.0, ge=0.0)


class FinancialParameters(CoreModel):
    """Real rate, inflation and the Fisher-derived nominal rate."""

    real_rate: float = Field(default=0.06, ge=0.0, lt=1.0)
    inflation_rate: float = Field(default=0.06, ge=0.0, lt=1.0)
    discount_base_year: int | None = None

    @property
    def nominal_rate(self) -> float:
        """``(1+i) = (1+r)(1+pi)`` – 12.36 % for the thesis values."""

        return (1.0 + float(self.real_rate)) * (1.0 + float(self.inflation_rate)) - 1.0

    def discount_factor(self, year: int, base_year: int) -> float:
        return 1.0 / ((1.0 + float(self.real_rate)) ** (int(year) - int(base_year)))


class PolicyConfig(CoreModel):
    """All policy/cost assumptions of one scenario in one object."""

    ets: EtsAllowanceSchedule = EtsAllowanceSchedule()
    prices: dict[str, Co2PriceScenario] = Field(default_factory=default_price_scenarios)
    capture: CaptureCostParameters = CaptureCostParameters()
    transport: TransportCostParameters = TransportCostParameters()
    storage: StorageCostParameters = StorageCostParameters()
    financial: FinancialParameters = FinancialParameters()
    selected_price_scenario: Literal["optimistic", "conservative", "pessimistic"] = "conservative"

    def price_scenario(self) -> Co2PriceScenario:
        return self.prices[self.selected_price_scenario]

    def price_in(self, year: int) -> float:
        return self.price_scenario().price_at(year)