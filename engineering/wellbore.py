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
    

    def calculate_dp(self, fluid, m_dot=None, bhp = None, whp = None, T_C=None, depth_total=None, nsteps=10,
           pipe_diameter=None, epsilon=0.0005, return_diagnostics=False):
        """
        Compute pressure profile from BHP to WHP by integrating upward.
        Works for both production and injection (friction always adds loss when moving up).
        Returns WHP.
    
        Parameters:
            fluid (str): 'Water', 'CO2', etc.
            m_dot (float): Mass flow rate (kg/s), positive for flow.
            bhp, whp (float): Bottomhole and wellhead pressure (bar) - should set only one
            T_C (float): Temperature at bottom (°C)
            depth_total (float): Total depth (m)
            nsteps (int): Number of steps
            pipe_diameter (float): Inner diameter (m)
            epsilon (float): Pipe roughness (m)
            return_diagnostics (bool): When True, also return length-averaged
                and maximum axial fluid velocity across the VFP segments.
    
        Returns:
            float: Wellhead or bottomhole pressure (WHP / BHP) in bar.
            tuple: When ``return_diagnostics`` is True, the pressure and a
                dictionary containing average, maximum, and segment axial
                velocity magnitudes in m/s.
        """
        if depth_total is None:
            depth_total = self.h_ref
        if pipe_diameter is None:
            pipe_diameter = 2 * self.rw
        if m_dot is None:
            m_dot = self.m_dot
            
        dz = depth_total / nsteps
            
        if (bhp is None) and (whp is None):
            raise Exception("BHP or WHP must be set")
        if bhp is None:
            p_start = whp
            direction = 1      # from wellhead to bottomhole
            z_vals = np.linspace(0, depth_total, nsteps + 1) 
        else:
            p_start = bhp
            direction = -1     # from bottomhole to wellhead
            z_vals = np.linspace(depth_total, 0, nsteps + 1)  

        A = np.pi * (pipe_diameter / 2)**2
        g = 9.80665
        p = p_start * 1e5  # Pa
        T_K = T_C + 273.15
    
        segment_velocities = []
        for i in range(nsteps):
            z_current = z_vals[i]
            z_next = z_vals[i + 1]
            delta_z = abs(z_current - z_next)
            if p > 0:
                rho = self.fluid_props.get_density(fluid, p, T_K)
                mu = self.fluid_props.get_viscosity(fluid, p, T_K)
                v = m_dot / (rho * A)
                segment_velocities.append(abs(float(v)))
                dp_grav = rho * g * delta_z
                if abs(m_dot) <= 0.0:
                    dp_fric = 0.0
                else:
                    Re = (rho * abs(v) * pipe_diameter) / mu
                    f = self.colebrook(pipe_diameter, Re, epsilon)
                    dp_fric = f * (delta_z / pipe_diameter) * 0.5 * rho * v**2
                dp_total = dp_grav + dp_fric
                p = p + dp_total*direction
            else:
                p = 0
                segment_velocities.append(0.0)
        p_end = p / 1e5
        if p_end<0: p_end = 1.01325
        if return_diagnostics:
            velocities = np.asarray(segment_velocities, dtype=float)
            return p_end, {
                "average_velocity_m_s": float(np.mean(velocities)),
                "maximum_velocity_m_s": float(np.max(velocities)),
                "segment_velocity_m_s": velocities,
            }
        return p_end
