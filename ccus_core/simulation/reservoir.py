"""Storage physics driven by a scheduled CO2 mass instead of a constant rate.

The legacy :class:`engineering.MaterialBalance` marches the reservoir pressure from
``p_ref`` to ``p_max`` and derives the elapsed time from a *constant* injection
rate.  Because the cumulative-mass curve ``m_CO2(p)`` is monotonic, the same
equations can be evaluated for any mass schedule by inverting that curve:

    p(t) = interp(cumulative_mass(t), m_CO2(p), p)

The injection BHP is then recomputed with the *local* annual rate through
``solve_BHP_from_CO2_mass_flow``, which was already rate-parameterised.  No
physical equation is changed or duplicated: the constant-rate case reproduces the
legacy model exactly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ccus_core.models import StorageSink

from .adapters import SECONDS_PER_YEAR, reservoir_inputs

try:  # the engineering package is optional for pure-model tests
    from engineering import FluidProperties, MaterialBalance
except Exception:  # pragma: no cover - exercised only without CoolProp
    FluidProperties = None  # type: ignore[assignment]
    MaterialBalance = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CapacityCurve:
    """Monotone cumulative-mass / pressure relationship of one reservoir."""

    mass_kg: np.ndarray
    pressure_bar: np.ndarray

    @property
    def maximum_mass_kg(self) -> float:
        return float(self.mass_kg[-1])

    @property
    def maximum_pressure_bar(self) -> float:
        return float(self.pressure_bar[-1])


class VariableRateReservoir:
    """Run the existing material balance for an arbitrary annual mass schedule."""

    def __init__(self, sink: StorageSink, fluid_props=None):
        if MaterialBalance is None:  # pragma: no cover
            raise ImportError("CoolProp/engineering are required for reservoir simulation")
        self.sink = sink
        self.reservoir = sink.reservoir
        self.fluid_props = fluid_props if fluid_props is not None else FluidProperties()
        self._curve: CapacityCurve | None = None
        self._model_instance = None

    @property
    def has_pressure_model(self) -> bool:
        """False for capacity-only sinks (e.g. an offshore site without a model)."""

        return self.reservoir is not None

    # ------------------------------------------------------------------ internals
    def _model(self, m_dot_kg_s: float):
        inputs = reservoir_inputs(self.reservoir, m_dot_kg_s=m_dot_kg_s, well=self.sink.injection_well)
        model = MaterialBalance(inputs, self.fluid_props)
        if self.sink.injection_well is not None:
            model.rw = float(self.sink.injection_well.radius_m)
        return model

    def capacity_curve(self) -> CapacityCurve:
        """Cumulative mass versus pressure, computed once per reservoir."""

        if self.reservoir is None:
            raise ValueError(
                f"storage sink '{self.sink.id}' has no reservoir properties: "
                "no pressure model can be built for it"
            )
        if self._curve is None:
            model = self._model(m_dot_kg_s=1.0)
            result = model.calculate_material_balance()
            self._model_instance = model
            self._curve = CapacityCurve(
                mass_kg=np.asarray(result["m_CO2"], dtype=float),
                pressure_bar=np.asarray(result["p"], dtype=float),
            )
        return self._curve

    # ------------------------------------------------------------------ public API
    def simulate(self, annual_mass_t: Mapping[int, float]) -> pd.DataFrame:
        """Return the annual reservoir state for a scheduled injection profile."""

        if self.reservoir is None:
            return self._simulate_capacity_only(annual_mass_t)
        curve = self.capacity_curve()
        model = self._model_instance or self._model(m_dot_kg_s=1.0)
        years = sorted(int(year) for year in annual_mass_t)
        rates_t = np.asarray([float(annual_mass_t[year]) for year in years], dtype=float)
        rates_kg_s = rates_t * 1000.0 / SECONDS_PER_YEAR
        cumulative_kg = np.cumsum(rates_t) * 1000.0

        pressures = np.interp(cumulative_kg, curve.mass_kg, curve.pressure_bar)
        capacity_limited = cumulative_kg > curve.maximum_mass_kg
        pressures = np.where(capacity_limited, curve.pressure_bar[-1], pressures)

        saturations = model.calculate_effective_saturation(m_co2=cumulative_kg)
        saturations = np.asarray(saturations, dtype=float)

        rows: list[dict[str, object]] = []
        last_bhp = float("nan")
        for index, year in enumerate(years):
            rate_kg_s = float(rates_kg_s[index])
            active = rate_kg_s > 0.0 and not bool(capacity_limited[index])
            bhp = float("nan")
            kr_co2 = float("nan")
            if active:
                _, kr_co2 = model.kr_Corey(float(saturations[index]))
                elapsed_s = cumulative_kg[index] / rate_kg_s
                bhp, _, _, _ = model.solve_BHP_from_CO2_mass_flow(
                    pr=float(pressures[index]),
                    m_dot=rate_kg_s,
                    t=float(elapsed_s),
                    k_ef=float(kr_co2) * float(self.reservoir.permeability_m2),
                )
                last_bhp = float(bhp)
            elif not capacity_limited[index] and cumulative_kg[index] > 0.0:
                # injection finished earlier: keep the last computed BHP for reference
                bhp = last_bhp
            limit = float(self.reservoir.maximum_pressure_bar)
            rows.append(
                {
                    "year": year,
                    "co2_injected_t": float(rates_t[index]),
                    "co2_cumulative_t": float(cumulative_kg[index] / 1000.0),
                    "pressure_bar": float(pressures[index]),
                    "pressure_limit_bar": limit,
                    "injection_rate_kg_s": rate_kg_s,
                    "effective_saturation": float(saturations[index]),
                    "kr_co2": kr_co2,
                    "bhp_bar": bhp,
                    "bhp_above_limit": bool(bhp == bhp and bhp > limit),
                    "active": bool(active),
                    "capacity_limited": bool(capacity_limited[index]),
                }
            )

        frame = pd.DataFrame(rows)
        frame.attrs["sink_id"] = self.sink.id
        frame.attrs["curve_maximum_mass_t"] = curve.maximum_mass_kg / 1000.0
        return frame

    def _simulate_capacity_only(self, annual_mass_t: Mapping[int, float]) -> pd.DataFrame:
        """Track cumulative mass for a sink without a reservoir model."""

        years = sorted(int(year) for year in annual_mass_t)
        rates = np.asarray([float(annual_mass_t[year]) for year in years], dtype=float)
        cumulative = np.cumsum(rates)
        capacity = float(self.sink.capacity_t)
        rows = [
            {
                "year": year,
                "co2_injected_t": float(rate),
                "co2_cumulative_t": float(total),
                "pressure_bar": float("nan"),
                "pressure_limit_bar": float("nan"),
                "injection_rate_kg_s": float(rate) * 1000.0 / SECONDS_PER_YEAR,
                "effective_saturation": float("nan"),
                "kr_co2": float("nan"),
                "bhp_bar": float("nan"),
                "bhp_above_limit": False,
                "active": bool(rate > 0.0),
                "capacity_limited": bool(total > capacity),
            }
            for year, rate, total in zip(years, rates, cumulative)
        ]
        frame = pd.DataFrame(rows)
        frame.attrs["sink_id"] = self.sink.id
        frame.attrs["pressure_model"] = False
        return frame

    def maximum_injectable_rate_t_per_year(self) -> float | None:
        """Explicit per-year cap, if the sink declares one."""

        return self.sink.max_injection_rate_t_per_year