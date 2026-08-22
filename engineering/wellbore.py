# engineering/wellbore.py

import numpy as np
import pandas as pd
from scipy.optimize import fsolve
from inputs.metadata import ParamMetadata
from engineering.fluid_properties import FluidProperties  # Assuming it's in the package

class VFP(ParamMetadata):
    """
    Vertical Flow Performance (VFP) class for calculating pressure profiles in wells 
    """
    PARAM_METADATA = {
        'rw': ('m', 'Radijus bušotine'),
        're': ('m', 'Efektivni drenazni radijus'),
        'h_ef': ('m', 'Efektivna debljina akvifera'),
        'h_ref': ('m', 'Referentna dubina sloja'),
        'k': ('m^2', 'Prosječna propusnost'),
        'm_dot': ('kg/s', 'Maseni protok CO2')
    }

    def __init__(self, inputs, fluid_props):
        super().__init__(**{k: getattr(inputs, k) for k in self.PARAM_METADATA})
        self.inputs = inputs
        self.fluid_props = fluid_props

    def colebrook(self, D, Re, e=0.0005):
        """
        Solves the Colebrook-White equation for the friction factor using fsolve.

        Parameters:
            D (float): Pipe diameter, m
            Re (float): Reynolds number
            e (float): Pipe roughness, m

        Returns:
            float: Friction factor
        """
        def f_eq(f):
            return 1 / np.sqrt(f) + 2 * np.log10(e / (3.7 * D) + 2.51 / (Re * np.sqrt(f)))
        f0 = 0.01
        return fsolve(f_eq, f0)[0]

    def _calculate_temperature_profile(
        self,
        fluid,
        m_dot,
        reference_pressure_pa,
        inlet_temperature_C,
        depth_total,
        nsteps,
        pipe_diameter,
        flow_direction,
        formation_surface_temperature_C,
        formation_bottomhole_temperature_C,
        heat_transfer_coefficient_W_m2_K,
        specific_heat_capacity_J_kg_K,
    ):
        """Return fluid and formation temperatures on a surface-to-bottom grid."""
        depth_profile = np.linspace(0.0, depth_total, nsteps + 1)
        formation_temperature_profile = np.linspace(
            formation_surface_temperature_C,
            formation_bottomhole_temperature_C,
            nsteps + 1,
        )

        if abs(m_dot) <= 0.0:
            return depth_profile, formation_temperature_profile.copy(), (
                formation_temperature_profile
            )

        if (
            heat_transfer_coefficient_W_m2_K <= 0.0
            or np.allclose(
                formation_temperature_profile,
                inlet_temperature_C,
            )
        ):
            return depth_profile, np.full(
                nsteps + 1,
                inlet_temperature_C,
                dtype=float,
            ), formation_temperature_profile

        if specific_heat_capacity_J_kg_K is None:
            specific_heat_capacity_J_kg_K = self.fluid_props.get_specific_heat(
                fluid,
                reference_pressure_pa,
                inlet_temperature_C + 273.15,
                param="CPMASS",
            )
        specific_heat_capacity_J_kg_K = float(
            specific_heat_capacity_J_kg_K
        )
        if (
            not np.isfinite(specific_heat_capacity_J_kg_K)
            or specific_heat_capacity_J_kg_K <= 0.0
        ):
            raise ValueError(
                "specific_heat_capacity_J_kg_K must be finite and greater "
                "than zero"
            )

        segment_length = depth_total / nsteps
        thermal_exponent = (
            heat_transfer_coefficient_W_m2_K
            * np.pi
            * pipe_diameter
            * segment_length
            / (abs(m_dot) * specific_heat_capacity_J_kg_K)
        )
        relaxation = np.exp(-thermal_exponent)
        linear_formation_response = (
            -np.expm1(-thermal_exponent) / thermal_exponent
        )

        def advance_temperature(
            inlet_temperature,
            formation_inlet_temperature,
            formation_outlet_temperature,
        ):
            return (
                formation_outlet_temperature
                + (
                    inlet_temperature - formation_inlet_temperature
                )
                * relaxation
                - (
                    formation_outlet_temperature
                    - formation_inlet_temperature
                )
                * linear_formation_response
            )

        temperature_profile = np.empty(nsteps + 1, dtype=float)
        if flow_direction == "injection":
            temperature_profile[0] = inlet_temperature_C
            for index in range(nsteps):
                temperature_profile[index + 1] = advance_temperature(
                    temperature_profile[index],
                    formation_temperature_profile[index],
                    formation_temperature_profile[index + 1],
                )
        else:
            temperature_profile[-1] = inlet_temperature_C
            for index in range(nsteps - 1, -1, -1):
                temperature_profile[index] = advance_temperature(
                    temperature_profile[index + 1],
                    formation_temperature_profile[index + 1],
                    formation_temperature_profile[index],
                )

        return (
            depth_profile,
            temperature_profile,
            formation_temperature_profile,
        )

    def calculate_dp(
        self,
        fluid,
        m_dot=None,
        bhp=None,
        whp=None,
        T_C=None,
        depth_total=None,
        nsteps=10,
        pipe_diameter=None,
        epsilon=0.0005,
        return_diagnostics=False,
        flow_direction=None,
        formation_surface_temperature_C=None,
        formation_bottomhole_temperature_C=None,
        heat_transfer_coefficient_W_m2_K=20.0,
        specific_heat_capacity_J_kg_K=None,
    ):
        """
        Compute the pressure profile between the wellhead and bottomhole.

        The physical flow direction must be explicit because friction opposes
        downward injection and upward production, independently of the chosen
        pressure-profile integration direction.
    
        Parameters:
            fluid (str): 'Water', 'CO2', etc.
            m_dot (float): Mass flow rate (kg/s), positive for flow.
            bhp, whp (float): Bottomhole and wellhead pressure (bar) - should set only one
            T_C (float): Fluid inlet temperature in the physical flow
                direction (°C): wellhead for injection, bottomhole for
                production.
            depth_total (float): Total depth (m)
            nsteps (int): Number of steps
            pipe_diameter (float): Inner diameter (m)
            epsilon (float): Pipe roughness (m)
            return_diagnostics (bool): When True, also return length-averaged
                and maximum axial fluid velocity across the VFP segments.
            flow_direction (str): Physical flow direction; either
                ``"production"`` (upward) or ``"injection"`` (downward).
            formation_surface_temperature_C (float): Formation temperature at
                the wellhead depth (°C). Defaults to ``T_C`` for an isothermal
                backward-compatible profile.
            formation_bottomhole_temperature_C (float): Formation temperature
                at total depth (°C). Defaults to ``T_C``.
            heat_transfer_coefficient_W_m2_K (float): Effective wellbore-fluid
                heat-transfer coefficient (W/m²/K).
            specific_heat_capacity_J_kg_K (float): Optional constant fluid
                specific heat. When omitted, it is evaluated at the scenario
                reference pressure ``p_ref`` and inlet temperature, avoiding
                dependence on the pressure integration direction.
    
        Returns:
            float: Wellhead or bottomhole pressure (WHP / BHP) in bar.
            tuple: When ``return_diagnostics`` is True, the pressure and a
                dictionary containing velocity, temperature, density and
                viscosity diagnostics.
        """
        if depth_total is None:
            depth_total = self.h_ref
        if pipe_diameter is None:
            pipe_diameter = 2 * self.rw
        if m_dot is None:
            m_dot = self.m_dot
        if not np.isfinite(m_dot):
            raise ValueError("m_dot must be finite")
        if flow_direction not in {"production", "injection"}:
            raise ValueError(
                "flow_direction must be explicitly set to 'production' or "
                "'injection'"
            )
        if T_C is None or not np.isfinite(T_C) or T_C <= -273.15:
            raise ValueError(
                "T_C must be a finite inlet temperature above absolute zero"
            )
        if isinstance(nsteps, bool) or int(nsteps) != nsteps or nsteps <= 0:
            raise ValueError("nsteps must be a positive integer")
        nsteps = int(nsteps)
        if not np.isfinite(depth_total) or depth_total <= 0.0:
            raise ValueError("depth_total must be finite and greater than zero")
        if not np.isfinite(pipe_diameter) or pipe_diameter <= 0.0:
            raise ValueError("pipe_diameter must be finite and greater than zero")
        if (
            not np.isfinite(heat_transfer_coefficient_W_m2_K)
            or heat_transfer_coefficient_W_m2_K < 0.0
        ):
            raise ValueError(
                "heat_transfer_coefficient_W_m2_K must be finite and "
                "non-negative"
            )

        if formation_surface_temperature_C is None:
            formation_surface_temperature_C = T_C
        if formation_bottomhole_temperature_C is None:
            formation_bottomhole_temperature_C = T_C
        for name, temperature in (
            (
                "formation_surface_temperature_C",
                formation_surface_temperature_C,
            ),
            (
                "formation_bottomhole_temperature_C",
                formation_bottomhole_temperature_C,
            ),
        ):
            if (
                not np.isfinite(temperature)
                or temperature <= -273.15
            ):
                raise ValueError(
                    f"{name} must be finite and above absolute zero"
                )

        flow_sign = 1 if flow_direction == "injection" else -1

        if (bhp is None) and (whp is None):
            raise Exception("BHP or WHP must be set")
        if bhp is None:
            p_start = whp
            integration_direction = 1      # from wellhead to bottomhole
            z_vals = np.linspace(0, depth_total, nsteps + 1) 
        else:
            p_start = bhp
            integration_direction = -1     # from bottomhole to wellhead
            z_vals = np.linspace(depth_total, 0, nsteps + 1)  

        if not np.isfinite(p_start) or p_start <= 0.0:
            raise ValueError("Known pressure boundary must be finite and positive")

        A = np.pi * (pipe_diameter / 2)**2
        g = 9.80665
        p = p_start * 1e5  # Pa
        specific_heat_reference_pressure_pa = p
        temperature_profile_requires_specific_heat = (
            abs(m_dot) > 0.0
            and heat_transfer_coefficient_W_m2_K > 0.0
            and not np.allclose(
                (
                    formation_surface_temperature_C,
                    formation_bottomhole_temperature_C,
                ),
                T_C,
            )
        )
        if (
            specific_heat_capacity_J_kg_K is None
            and temperature_profile_requires_specific_heat
        ):
            specific_heat_reference_pressure_bar = getattr(
                self.inputs,
                "p_ref",
                None,
            )
            if (
                specific_heat_reference_pressure_bar is None
                or not np.isfinite(specific_heat_reference_pressure_bar)
                or specific_heat_reference_pressure_bar <= 0.0
            ):
                raise ValueError(
                    "A positive inputs.p_ref or explicit "
                    "specific_heat_capacity_J_kg_K is required for a "
                    "non-isothermal temperature profile"
                )
            specific_heat_reference_pressure_pa = (
                float(specific_heat_reference_pressure_bar) * 1e5
            )
        (
            depth_profile,
            temperature_profile_C,
            formation_temperature_profile_C,
        ) = self._calculate_temperature_profile(
            fluid=fluid,
            m_dot=m_dot,
            reference_pressure_pa=specific_heat_reference_pressure_pa,
            inlet_temperature_C=T_C,
            depth_total=depth_total,
            nsteps=nsteps,
            pipe_diameter=pipe_diameter,
            flow_direction=flow_direction,
            formation_surface_temperature_C=(
                formation_surface_temperature_C
            ),
            formation_bottomhole_temperature_C=(
                formation_bottomhole_temperature_C
            ),
            heat_transfer_coefficient_W_m2_K=(
                heat_transfer_coefficient_W_m2_K
            ),
            specific_heat_capacity_J_kg_K=(
                specific_heat_capacity_J_kg_K
            ),
        )
        physical_segment_temperature_C = 0.5 * (
            temperature_profile_C[:-1] + temperature_profile_C[1:]
        )
    
        segment_velocities = []
        segment_temperatures_C = []
        segment_densities = []
        segment_viscosities = []
        for i in range(nsteps):
            z_current = z_vals[i]
            z_next = z_vals[i + 1]
            delta_z = abs(z_current - z_next)
            segment_depth = 0.5 * (z_current + z_next)
            local_temperature_C = float(
                np.interp(
                    segment_depth,
                    0.5 * (depth_profile[:-1] + depth_profile[1:]),
                    physical_segment_temperature_C,
                )
            )
            local_temperature_K = local_temperature_C + 273.15
            segment_temperatures_C.append(local_temperature_C)
            if p > 0:
                rho = self.fluid_props.get_density(
                    fluid,
                    p,
                    local_temperature_K,
                )
                mu = self.fluid_props.get_viscosity(
                    fluid,
                    p,
                    local_temperature_K,
                )
                segment_densities.append(float(rho))
                segment_viscosities.append(float(mu))
                v = m_dot / (rho * A)
                segment_velocities.append(abs(float(v)))
                dp_grav = rho * g * delta_z
                if abs(m_dot) <= 0.0:
                    dp_fric = 0.0
                else:
                    Re = (rho * abs(v) * pipe_diameter) / mu
                    f = self.colebrook(pipe_diameter, Re, epsilon)
                    dp_fric = f * (delta_z / pipe_diameter) * 0.5 * rho * v**2
                dp_total = dp_grav - flow_sign * dp_fric
                p = p + dp_total * integration_direction
            else:
                p = 0
                segment_velocities.append(0.0)
                segment_densities.append(np.nan)
                segment_viscosities.append(np.nan)
        p_end = p / 1e5
        if p_end<0: p_end = 1.01325
        if return_diagnostics:
            velocities = np.asarray(segment_velocities, dtype=float)
            segment_temperatures = np.asarray(
                segment_temperatures_C,
                dtype=float,
            )
            densities = np.asarray(segment_densities, dtype=float)
            viscosities = np.asarray(segment_viscosities, dtype=float)
            if integration_direction < 0:
                velocities = velocities[::-1]
                segment_temperatures = segment_temperatures[::-1]
                densities = densities[::-1]
                viscosities = viscosities[::-1]
            if bhp is None:
                wellhead_pressure_bar = float(whp)
                bottomhole_pressure_bar = float(p_end)
            else:
                wellhead_pressure_bar = float(p_end)
                bottomhole_pressure_bar = float(bhp)
            wellhead_temperature_K = temperature_profile_C[0] + 273.15
            bottomhole_temperature_K = temperature_profile_C[-1] + 273.15
            return p_end, {
                "average_velocity_m_s": float(np.mean(velocities)),
                "maximum_velocity_m_s": float(np.max(velocities)),
                "segment_velocity_m_s": velocities,
                "depth_profile_m": depth_profile,
                "segment_depth_m": 0.5 * (
                    depth_profile[:-1] + depth_profile[1:]
                ),
                "temperature_profile_c": temperature_profile_C,
                "formation_temperature_profile_c": (
                    formation_temperature_profile_C
                ),
                "segment_temperature_c": segment_temperatures,
                "average_temperature_c": float(
                    np.mean(physical_segment_temperature_C)
                ),
                "wellhead_temperature_c": float(temperature_profile_C[0]),
                "bottomhole_temperature_c": float(
                    temperature_profile_C[-1]
                ),
                "segment_density_kg_m3": densities,
                "segment_viscosity_pa_s": viscosities,
                "wellhead_density_kg_m3": float(
                    self.fluid_props.get_density(
                        fluid,
                        wellhead_pressure_bar * 1e5,
                        wellhead_temperature_K,
                    )
                ),
                "bottomhole_density_kg_m3": float(
                    self.fluid_props.get_density(
                        fluid,
                        bottomhole_pressure_bar * 1e5,
                        bottomhole_temperature_K,
                    )
                ),
                "wellhead_viscosity_pa_s": float(
                    self.fluid_props.get_viscosity(
                        fluid,
                        wellhead_pressure_bar * 1e5,
                        wellhead_temperature_K,
                    )
                ),
                "bottomhole_viscosity_pa_s": float(
                    self.fluid_props.get_viscosity(
                        fluid,
                        bottomhole_pressure_bar * 1e5,
                        bottomhole_temperature_K,
                    )
                ),
            }
        return p_end
