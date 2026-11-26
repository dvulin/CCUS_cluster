"""Geothermal doublet coupled to the CO2 storage pressure.

The doublet produces and reinjects the same water mass, so the reservoir sees a
zero net withdrawal and its pressure is governed by CO2 injection alone.  What the
doublet does change is the energy balance: production flow, ORC power and pump
power all follow the storage pressure year by year.

The production temperature is held at the reservoir temperature (no thermal
breakthrough), which is the conservative assumption for the power estimate; the
full transient front model remains available in ``engineering.Geothermal`` for
scenarios that need it.

Energy bookkeeping (one credit per kWh)
---------------------------------------
* ``orc_power_kw`` is the **gross** electrical output of the ORC, already derated
  by the ORC availability;
* ``pump_power_kw`` is the **electricity the reinjection pump needs** to lift the
  produced water from the surface facility pressure (``p_out_bar``) to the
  injection bottomhole pressure, using the real pump efficiency of the sink and
  derated by the pump availability;
* ``net_power_kw = orc - pump`` is what the ledger turns into export/import, so the
  same kilowatt-hour is never counted twice.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from ccus_core.models import GeothermalSystem, ReservoirProperties, ScenarioConfig, StorageSink

from .adapters import geothermal_inputs, power_inputs, well_inputs

try:
    from engineering import FluidProperties, Geothermal, Power, VFP
except Exception:  # pragma: no cover
    FluidProperties = Geothermal = Power = VFP = None  # type: ignore[assignment]

SURFACE_FORMATION_TEMPERATURE_C = 20.0
HOURS_PER_YEAR = 8766.0
#: fallback pump efficiency when the sink does not declare one
DEFAULT_PUMP_EFFICIENCY = 0.90

#: Reference doublet built by the engine when a sink is flagged
#: ``geothermal_coupled`` but carries no explicit :class:`GeothermalSystem`.
DEFAULT_DOUBLET_CAPEX_EUR = 50_000_000.0
DEFAULT_DOUBLET_FIXED_OPEX_EUR_PER_YEAR = 1_500_000.0
DEFAULT_DOUBLET_SPACING_M = 1500.0
DEFAULT_DOUBLET_ETA_ORC = 0.20
DEFAULT_DOUBLET_P_OUT_BAR = 10.0
DEFAULT_DOUBLET_T_OUT_C = 35.0
DEFAULT_DOUBLET_WELL_RADIUS_M = 0.15


def default_doublet_for_sink(
    sink: StorageSink,
    *,
    start_year: int,
    end_year: int,
    doublet_id: str | None = None,
) -> GeothermalSystem:
    """Build the reference doublet of a coupled sink (engine-side default).

    The UI must not invent this object: one place (here) owns the default doublet
    of a sink, so a coupled site always gets exactly one system - and its CAPEX is
    counted exactly once.
    """

    reservoir = sink.reservoir
    depth = float(reservoir.top_depth_m) if reservoir is not None else 1500.0
    temperature = float(reservoir.temperature_c) if reservoir is not None else 150.0
    return GeothermalSystem(
        id=doublet_id or f"{sink.id}-doublet",
        node_id=sink.node_id,
        name=f"{sink.name} doublet",
        d_doublet_m=DEFAULT_DOUBLET_SPACING_M,
        reservoir_temperature_c=temperature,
        bhp_dp_bar=10.0,
        eta_orc=DEFAULT_DOUBLET_ETA_ORC,
        p_out_bar=DEFAULT_DOUBLET_P_OUT_BAR,
        t_out_c=DEFAULT_DOUBLET_T_OUT_C,
        rw_production_m=DEFAULT_DOUBLET_WELL_RADIUS_M,
        rw_injection_m=DEFAULT_DOUBLET_WELL_RADIUS_M,
        h_ref_production_m=depth,
        h_ref_injection_m=depth,
        operation_start_year=int(
            sink.geothermal_start_year or sink.commissioning_year or start_year
        ),
        operation_end_year=int(end_year),
        capex_eur=DEFAULT_DOUBLET_CAPEX_EUR,
        fixed_opex_eur_per_year=DEFAULT_DOUBLET_FIXED_OPEX_EUR_PER_YEAR,
    )


def ensure_coupled_doublets(scenario: ScenarioConfig) -> ScenarioConfig:
    """Return ``scenario`` with one doublet per coupled storage sink.

    Idempotent: a node that already hosts a :class:`GeothermalSystem` is left
    alone, so an explicit system always wins over the default.  The engine calls
    this so that ``StorageSink.geothermal_coupled`` is enough to switch a site to
    doublet operation.
    """

    covered = {system.node_id for system in scenario.geothermal_systems}
    missing = [
        default_doublet_for_sink(
            sink,
            start_year=int(scenario.start_year),
            end_year=int(scenario.end_year),
        )
        for sink in scenario.storage_sinks
        if sink.geothermal_coupled and sink.node_id not in covered
    ]
    if not missing:
        return scenario
    return scenario.model_copy(
        update={"geothermal_systems": [*scenario.geothermal_systems, *missing]}
    )


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
        eta_pump: float = DEFAULT_PUMP_EFFICIENCY,
    ):
        if Geothermal is None:  # pragma: no cover
            raise ImportError("CoolProp/engineering are required for geothermal coupling")
        self.system = system
        self.reservoir = reservoir
        self.fluid_props = fluid_props if fluid_props is not None else FluidProperties()
        self.eta_pump = float(eta_pump)
        self._efficiency = {
            "eta_co2_compressor_isentropic": float(eta_co2_compressor_isentropic),
            "eta_co2_dense_phase_pump": float(eta_co2_dense_phase_pump),
        }

    # ------------------------------------------------------------------ helpers
    def availability_factors(self) -> dict[str, float]:
        """Derating factors of the doublet (all in 0..1)."""

        system = self.system
        flow = min(
            float(system.production_well_availability),
            float(system.injection_well_availability),
        )
        return {
            "flow_availability": flow,
            "orc_availability": float(system.orc_availability),
            "pump_availability": float(system.pump_availability),
            # the combined figure is what the ledger uses for the annual energy
            "combined": min(
                flow,
                float(system.orc_availability),
                float(system.pump_availability),
            ),
        }

    # ------------------------------------------------------------------ main
    def simulate(self, pressure_by_year: Mapping[int, float]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        factors = self.availability_factors()
        flow_factor = factors["flow_availability"]
        orc_factor = factors["orc_availability"]
        pump_factor = factors["pump_availability"]
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
                "flow_availability": flow_factor,
                "orc_availability": orc_factor,
                "pump_availability": pump_factor,
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
            # the wells are not available 100 % of the year: the annual energy is
            # the on-stream power times the well availability
            mass_flow = float(mass_flow) * flow_factor
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
                    eta_gt_injection_pump=self.eta_pump,
                    **self._efficiency,
                ),
                self.fluid_props,
            )
            # electricity needed to re-inject the produced water: from the surface
            # facility pressure up to the injection bottomhole pressure
            pump_power = power.calculate_pump_power(
                fluid="H2O",
                m_dot=mass_flow,
                p_in_bar=float(self.system.p_out_bar),
                p_out_bar=injection_bhp,
                t_C=float(self.system.t_out_c),
                eta=self.eta_pump,
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
                # ORC and pump do not run at the same time: each one is derated by
                # its own availability, the flow by the wells
                orc_power *= orc_factor
                pump_power *= pump_factor
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
        frame.attrs["pump_efficiency"] = self.eta_pump
        return frame