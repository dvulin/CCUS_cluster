"""Geothermal doublet coupled to the CO2 storage pressure.

The doublet produces and reinjects the same water mass, so the reservoir sees a
zero net withdrawal and its pressure is governed by CO2 injection alone.  What the
doublet does change is the energy balance: production flow, ORC power and pump
power all follow the storage pressure year by year.

The production temperature is held at the reservoir temperature (no thermal
breakthrough), which is the conservative assumption for the power estimate; the
full transient front model remains available in ``engineering.Geothermal`` for
scenarios that need it.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from ccus_core.models import GeothermalSystem, ReservoirProperties

from .adapters import geothermal_inputs, power_inputs, well_inputs

try:
    from engineering import FluidProperties, Geothermal, Power, VFP
except Exception:  # pragma: no cover
    FluidProperties = Geothermal = Power = VFP = None  # type: ignore[assignment]

SURFACE_FORMATION_TEMPERATURE_C = 20.0
HOURS_PER_YEAR = 8766.0
PUMP_EFFICIENCY = 0.90


class GeothermalCoupling:
    """Annual doublet performance for one storage complex."""

    def __init__(
        self,
        system: GeothermalSystem,
        reservoir: ReservoirProperties,
        *,
        fluid_props=None,
        eta_co2_compressor_isentropic: float = 0.75,
        eta_co2_dense_phase_pump: float = 0.90,
    ):
        if Geothermal is None:  # pragma: no cover
            raise ImportError("CoolProp/engineering are required for geothermal coupling")
        self.system = system
        self.reservoir = reservoir
        self.fluid_props = fluid_props if fluid_props is not None else FluidProperties()
        self._efficiency = {
            "eta_co2_compressor_isentropic": float(eta_co2_compressor_isentropic),
            "eta_co2_dense_phase_pump": float(eta_co2_dense_phase_pump),
        }

    def simulate(self, pressure_by_year: Mapping[int, float]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for year in sorted(int(key) for key in pressure_by_year):
            pressure = float(pressure_by_year[int(year)])
            row: dict[str, object] = {
                "year": int(year),
                "pressure_bar": pressure,
                "production_flow_kg_s": 0.0,
                "production_bhp_bar": float("nan"),
                "injection_bhp_bar": float("nan"),
                "production_whp_bar": float("nan"),
                "orc_power_kw": 0.0,
                "pump_power_kw": 0.0,
                "net_power_kw": 0.0,
                "operating": False,
            }
            if not self.system.active_in(int(year)) or pressure <= 0.0:
                rows.append(row)
                continue

            geothermal = Geothermal(
                geothermal_inputs(self.reservoir, self.system), self.fluid_props
            )
            mass_flow, _reservoir_flow, production_bhp = geothermal.calculate_m_dot_prod(
                p_ref=pressure, bhp_dp=float(self.system.bhp_dp_bar)
            )
            if mass_flow <= 0.0:
                rows.append(row)
                continue
            injection_bhp, _density = geothermal.calculate_bhp_inj(
                p_ref=pressure, m_dot_h2o=mass_flow
            )

            production_well = VFP(
                well_inputs(
                    self.reservoir,
                    radius_m=float(self.system.rw_production_m),
                    depth_m=float(self.system.h_ref_production_m),
                    m_dot_kg_s=mass_flow,
                ),
                self.fluid_props,
            )
            production_whp, _diagnostics = production_well.calculate_dp(
                fluid="H2O",
                bhp=production_bhp,
                m_dot=mass_flow,
                T_C=float(self.reservoir.temperature_c),
                epsilon=float(self.system.roughness_m),
                return_diagnostics=True,
                flow_direction="production",
                formation_surface_temperature_C=SURFACE_FORMATION_TEMPERATURE_C,
                formation_bottomhole_temperature_C=float(self.reservoir.temperature_c),
            )

            power = Power(
                power_inputs(
                    m_dot_kg_s=mass_flow,
                    p_comp_in_bar=float(self.system.p_out_bar),
                    t_comp_in_c=float(self.system.t_out_c),
                    eta_orc=float(self.system.eta_orc),
                    eta_gt_injection_pump=PUMP_EFFICIENCY,
                    **self._efficiency,
                ),
                self.fluid_props,
            )
            pump_power = power.calculate_pump_power(
                fluid="H2O",
                m_dot=mass_flow,
                p_in_bar=float(self.system.p_out_bar),
                p_out_bar=injection_bhp,
                t_C=float(self.system.t_out_c),
                eta=PUMP_EFFICIENCY,
            )

            operating = production_whp > float(self.system.p_out_bar)
            if operating:
                orc_power = power.calculate_ORC_power(
                    m_dot=mass_flow,
                    p_in=production_whp,
                    p_out=float(self.system.p_out_bar),
                    t_in=float(self.reservoir.temperature_c),
                    t_out=float(self.system.t_out_c),
                    fluid="H2O",
                )
            else:
                orc_power = 0.0
                pump_power = 0.0

            row.update(
                {
                    "production_flow_kg_s": float(mass_flow),
                    "production_bhp_bar": float(production_bhp),
                    "injection_bhp_bar": float(injection_bhp),
                    "production_whp_bar": float(production_whp),
                    "orc_power_kw": float(orc_power),
                    "pump_power_kw": float(pump_power),
                    "net_power_kw": float(orc_power - pump_power),
                    "operating": bool(operating),
                }
            )
            rows.append(row)

        frame = pd.DataFrame(rows)
        frame.attrs["system_id"] = self.system.id
        frame.attrs["available_hours_per_year"] = self.system.available_hours_per_year()
        return frame