# -*- coding: utf-8 -*-
"""
Created on Wed Jul  9 23:38:59 2025

@author: domagoj
"""

from inputs.metadata import ParamMetadata
import numpy as np
import pandas as pd
from scipy.special import erf
try:
    from scipy.integrate import cumtrapz
except:
    from scipy.integrate import cumulative_trapezoid as cumtrapz
import CoolProp.CoolProp as CP

class Geothermal(ParamMetadata):
    PARAM_METADATA = {
        'd_doublet': ('m', 'udaljenost proizvodne i utisne geotermalne bušotine'),
        't': ('°C', 'temperatura sloja'),
        'h_ef' : ('m', 'Efektivna debljina akvifera'),
        'k' : ('m2', 'Prosječna propusnost'),
        'bhp_dp': ('bar', 'Pad tlaka na dnu geotermalne proizvodne bušotine'),
        'eta': ('-', 'ORC učinkovitost'),
        't_out': ('°C', 'ORC izlazna temperatura'),
        'p_out': ('bar', 'ORC izlazni tlak'),
        'rw': ('bar', 'ORC izlazni tlak'),
        'poro': ('-', 'Poroznost akvifera (bezdimenzionalna)'),
    }

    def __init__(self, inputs, fluid_props):
        super().__init__(**{k: getattr(inputs, k) for k in self.PARAM_METADATA})
        self.inputs = inputs
        self.fluid_props = fluid_props
        self.max_iter = 50
        self.tolerance = 1e-6
        self.re = self.d_doublet
        self.fluid = 'H2O'
        self.Ea = 0.85              # geothermal reinjection sweep efficiency
        self.c_r = 950              # J/kg∙K, matrix heat capacity
        self.rho_r = 2700           # kg/m3, matrix density
        self.lambda_r = 3.5         # W/m∙K, matrix thermal conductivity
    
    def calculate_m_dot_prod(self, p_ref, 
                         bhp_dp = None, 
                         t_C = None,
                         d_doublet = None,
                         h_ef = None,    # CO2 bi mogao proći iznad
                         k_ef = None, 
                         re = None,      # drenažni radijus pogodno procijeniti u odnosu na udaljenost od CO2 bušotine
                         rw = None
                         ):
        
        if d_doublet is None: d_doublet = self.d_doublet
        if (self.re is None) and (re is None): self.re = self.d_doublet
        if re is None: re = self.re          # ne bi smjelo biti veće od te udaljenosti
        if bhp_dp is None: bhp_dp = self.bhp_dp
        if t_C is None: t_C = self.t
        if h_ef is None: h_ef = self.h_ef
        if k_ef is None: k_ef = self.k

            
        T_K = t_C + 273.15
        bhp_dp = bhp_dp * 1e5         # production well depression, Pa
        p_ref = p_ref * 1e5           # geothermal reservoir pressure, Pa
        p_BHP = p_ref - bhp_dp        # bottom-hole pressure in production well, Pa
    
        rho = self.fluid_props.get_density(self.fluid, p_BHP, T_K)
        mu = self.fluid_props.get_viscosity(self.fluid, p_BHP, T_K)
        brojnik = 2 * np.pi * k_ef * self.h_ef * bhp_dp
        nazivnik = mu * np.log(re / self.rw)
        q_m_calculated = brojnik / nazivnik                 # m3/s
        m_dot = rho*q_m_calculated                          # kg/s
        if m_dot<0: m_dot = 0
        return (m_dot, q_m_calculated * (3600*24), p_BHP/1E5)          # kg/s, rm3/dan
    
    
    
    def calculate_bhp_inj(self, p_ref, 
                         m_dot_h2o, 
                         t_C = None,
                         d_doublet = None,
                         h_ef = None,   # pretpostaviti manji produktivni interval kako bi CO2 mogao proći iznad
                         k_ef = None, 
                         re = None      # drenažni radijus pogodno procijeniti u odnosu na udaljenost od CO2 bušotine        
                         ):
        
        if d_doublet is None: d_doublet = self.d_doublet
        if (self.re is None) and (re is None): self.re = self.d_doublet  # ne bi smjelo biti veće od te udaljenosti
        if re is None: re = self.re          # ne bi smjelo biti veće od te udaljenosti
        if t_C is None: t_C = self.t_out            # temperatura ohlađene vode na utisnoj
        if h_ef is None: h_ef = self.h_ef
        if k_ef is None: k_ef = self.k     
        if self.bhp_dp is None:
            guess = 10e5  # Pa
        else:
            guess = self.bhp_dp*1e5
            
        T_K = t_C + 273.15
        p_ref = p_ref * 1e5           # geothermal reservoir pressure, Pa
        
        p_BHP = p_ref + guess
        tol = self.tolerance
        max_iter = self.max_iter
    
        for i in range(max_iter):
            rho = self.fluid_props.get_density(self.fluid, p_BHP, T_K)
            mu = self.fluid_props.get_viscosity(self.fluid, p_BHP, T_K)
            dp = p_BHP - p_ref
            brojnik = 2 * np.pi * k_ef * self.h_ef * rho * dp
            nazivnik = mu * np.log(re / self.rw)
            q_m_calculated = brojnik / nazivnik
            residual = q_m_calculated - m_dot_h2o
            if abs(residual) < tol:
                break
            dq_dp = (2 * np.pi * k_ef * self.h_ef * rho) / (mu * np.log(re / self.rw))
            dp_update = residual / dq_dp
            p_BHP -= dp_update
        
        bhp_h2o_inj_bar = p_BHP / 1e5
        return bhp_h2o_inj_bar, rho

##################################################################################################################

    def calculate_production_temperature(self, m_dot_h2o, p_bar, t_C, t_inj_C=40,
                                       t_sim=None, dt=None, h_ef=None, 
                                       re=None, poro=None, c_r=None, rho_r=None, 
                                       lambda_r=None, fluid=None, Ea=0.85):
        """
        Calculate production temperature profile for a geothermal doublet system.
        
        Based on the Lauwerier model and Gringarten-Sauty analytical solution.
        
        Parameters
        ----------
        m_dot_h2o : double
            Mass flow rate, kg/s
        p_bar : double
            Reservoir pressure, bar
        t_C : double
            Initial reservoir temperature, °C
        t_inj_C : double, optional
            Injection temperature after ORC, °C. The default is 40.
        t_sim : double, optional
            Simulation time, years. Uses self.t_sim if None.
        dt : double, optional
            Time step, years. Uses self.dt if None.
        h_ef : double, optional
            Effective layer thickness, m. Uses self.h_ef if None.
        re : double, optional
            Effective drainage radius, m. Uses self.re if None.
        poro : double, optional
            Porosity. Uses self.poro if None.
        c_r : double, optional
            Matrix heat capacity, J/kg∙K. The default is 950.
        rho_r : double, optional
            Matrix density, kg/m3. The default is 2700.
        lambda_r : double, optional
            Matrix thermal conductivity, W/m∙K. The default is 3.5.
        fluid : str, optional
            Fluid type. Uses self.fluid if None.
        Ea : double, optional
            Areal sweep efficiency. The default is 0.85.
        
        Returns
        -------
        dict
            Dictionary containing:
            - 'time_years': time array in years
            - 'temperature': production temperature array in °C
            - 't_bt': thermal breakthrough time in years
            - 'properties': dictionary of calculated properties
        """
        # Use defaults from self if not provided
        if t_sim is None: t_sim = getattr(self, 't_sim', 30)
        if dt is None: dt = getattr(self, 'dt', 1/12)
        if h_ef is None: h_ef = self.h_ef
        if re is None: re = self.re
        if poro is None: poro = self.poro
        if c_r is None: c_r = self.c_r
        if rho_r is None: rho_r = self.rho_r
        if lambda_r is None: lambda_r = self.lambda_r
        if fluid is None: fluid = self.fluid
        
        # Convert units
        p = p_bar * 1e5  # Pa
        T = t_C + 273.15  # K
        T_inj = t_inj_C + 273.15  # K
        
        # Time arrays
        dt_seconds = dt * 365.25 * 24 * 3600
        t_seconds = np.arange(0, (t_sim * 365.25 * 24 * 3600 + dt_seconds), dt_seconds)
        t_years = t_seconds / (365.25 * 24 * 3600)
        
        # Fluid properties at reservoir conditions
        rho_w = CP.PropsSI('D', 'P', p, 'T', T, fluid)  # kg/m3
        c_w = CP.PropsSI('Cpmass', 'P', p, 'T', T, fluid)  # J/kg∙K
        
        # Reservoir properties
        Ar = np.pi * re**2  # drainage area
        A = Ar * Ea  # effective drainage area
        rho_f = rho_r * (1 - poro) + rho_w * poro  # formation density
        c_f = (rho_r * c_r * (1 - poro) + rho_w * c_w * poro) / rho_f  # formation heat capacity
        
        # Calculate breakthrough time
        q_w = m_dot_h2o / rho_w  # m3/s
        t_bt = A * h_ef * c_f * rho_f / (q_w * c_w * rho_w)  # seconds
        t_bt_years = t_bt / (365.25 * 24 * 3600)
        
        # Calculate temperature profile
        T_prod = []
        C1 = A * np.sqrt(lambda_r * c_r * rho_r)
        C2 = (A * h_ef * c_f * rho_f) / (q_w * c_w * rho_w)
        C3 = q_w * c_w * rho_w
        
        for t_sec in t_seconds:
            if t_sec < C2:
                T_prod.append(t_C)  # Before breakthrough
            else:
                # After breakthrough - Lauwerier model with error function
                erf_arg = C1 / (C3 * np.sqrt(t_sec - C2))
                T_current = t_inj_C + (t_C - t_inj_C) * erf(erf_arg)
                T_prod.append(T_current)
        
        T_prod = np.array(T_prod)
        
        properties = {
            'rho_w': rho_w,
            'c_w': c_w,
            'rho_f': rho_f,
            'c_f': c_f,
            'q_w': q_w,
            'A': A,
            'C1': C1,
            'C2': C2,
            'C3': C3
        }
        
        return {
            'time_years': t_years,
            'temperature': T_prod,
            't_bt': t_bt_years,
            'properties': properties
        }


    def calculate_unsteady_production(self, mbal_df, target_distance=None, 
                                    t_inj_C=40, h_ef=None, poro=None, 
                                    c_r=None, rho_r=None, lambda_r=None, 
                                    fluid=None, Ea=0.85):
        """
        Calculate production temperature at a specific distance considering 
        variable mass flow rates over time.
        
        This method integrates thermal front propagation for each time step
        to determine breakthrough time, then calculates temperature evolution
        after breakthrough using superposition principle.
        
        Parameters
        ----------
        mbal_df : pandas.DataFrame
            DataFrame with columns:
            - 'Time, yr': time in years
            - 'DSA pressure, bar': pressure in bar
            - 'm_dot geothermal [kg/s]': mass flow rate in kg/s
            - Additional columns for reservoir properties
        target_distance : double, optional
            Distance from injection well, m. Uses self.d_doublet if None.
        t_inj_C : double, optional
            Injection temperature, °C. The default is 40.
        h_ef : double, optional
            Effective thickness, m. Uses self.h_ef if None.
        poro : double, optional
            Porosity. Uses self.poro if None.
        c_r : double, optional
            Matrix heat capacity, J/kg∙K. The default is 950.
        rho_r : double, optional
            Matrix density, kg/m3. The default is 2700.
        lambda_r : double, optional
            Matrix thermal conductivity, W/m∙K. The default is 3.5.
        fluid : str, optional
            Fluid type. Uses self.fluid if None.
        Ea : double, optional
            Areal sweep efficiency. The default is 0.85.
            
        Returns
        -------
        dict
            Dictionary containing:
            - 'time_years': time array
            - 'temperature': temperature at target distance
            - 't_bt': breakthrough time
            - 'cumulative_radius': cumulative thermal front radius
            - 'front_velocities': thermal front velocities for each step
        """
        # Use defaults
        if target_distance is None: target_distance = self.d_doublet
        if h_ef is None: h_ef = self.h_ef  
        if poro is None: poro = self.poro
        if c_r is None: c_r = self.c_r
        if rho_r is None: rho_r = self.rho_r
        if lambda_r is None: lambda_r = self.lambda_r
        if fluid is None: fluid = self.fluid
        
        # Initialize arrays
        time_years = mbal_df['Time, yr'].values
        pressures = mbal_df['DSA pressure, bar'].values  
        flow_rates = mbal_df['m_dot geothermal [kg/s]'].values
        temperatures = mbal_df.get('reservoir_temp', [self.t] * len(time_years))
        
        cumulative_radius = np.zeros(len(time_years))
        front_velocities = np.zeros(len(time_years))
        production_temp = np.zeros(len(time_years))
        breakthrough_reached = False
        t_bt = None
        
        # Step 1: Calculate breakthrough time by integrating front radii
        for i, (t, p_bar, m_dot, t_res) in enumerate(zip(time_years, pressures, flow_rates, temperatures)):
            if i == 0:
                dt_years = t
            else:
                dt_years = t - time_years[i-1]
                
            # Calculate front radius for this time step
            r_f = self.calculate_front_radius(
                t=dt_years, 
                m_dot_h2o=m_dot, 
                p_bar=p_bar, 
                t_C=t_res,
                h_ef=h_ef, 
                poro=poro, 
                c_r=c_r, 
                rho_r=rho_r, 
                lambda_r=lambda_r,
                fluid=fluid, 
                Ea=Ea
            )
            
            # Accumulate radius
            if i == 0:
                cumulative_radius[i] = r_f
            else:
                cumulative_radius[i] = cumulative_radius[i-1] + r_f
                
            # Check for breakthrough
            if not breakthrough_reached and cumulative_radius[i] >= target_distance:
                breakthrough_reached = True
                t_bt = t
                breakthrough_index = i
                
            # Set temperature before breakthrough
            if not breakthrough_reached:
                production_temp[i] = t_res
                
        # Step 2: Calculate temperature after breakthrough
        if breakthrough_reached:
            for i in range(breakthrough_index, len(time_years)):
                t_after_bt = time_years[i] - t_bt  # time since breakthrough
                
                if t_after_bt <= 0:
                    production_temp[i] = temperatures[i]
                    continue
                    
                # Use superposition of all previous flow rate changes
                # This is a simplified approach - for more accuracy, you would need
                # to track the contribution of each time step's thermal front
                
                # Get average properties for the period
                avg_pressure = np.mean(pressures[breakthrough_index:i+1])
                avg_flow = np.mean(flow_rates[breakthrough_index:i+1])
                avg_temp = np.mean(temperatures[breakthrough_index:i+1])
                
                p = avg_pressure * 1e5
                T = avg_temp + 273.15
                
                # Fluid properties
                rho_w = CP.PropsSI('D', 'P', p, 'T', T, fluid)
                c_w = CP.PropsSI('Cpmass', 'P', p, 'T', T, fluid)
                
                # Calculate effective parameters
                q_w = avg_flow / rho_w
                A_eff = np.pi * target_distance**2 * Ea
                
                # Temperature calculation after breakthrough using error function
                # Based on Lauwerier model
                C1 = A_eff * np.sqrt(lambda_r * c_r * rho_r)  
                C3 = q_w * c_w * rho_w
                t_seconds = t_after_bt * 365.25 * 24 * 3600
                
                if t_seconds > 0 and C3 > 0:
                    erf_arg = C1 / (C3 * np.sqrt(t_seconds))
                    production_temp[i] = t_inj_C + (avg_temp - t_inj_C) * erf(erf_arg)
                else:
                    production_temp[i] = avg_temp
                    
        info = {'t_bt': t_bt, 'breakthrough_reached': breakthrough_reached}
        results = pd.DataFrame({
            'time, years': time_years,
            'temperature, °C': production_temp,
            'front radius, m': cumulative_radius
            })
                
        return results, info

    
################################################################################################################
    
    def calculate_front_radius(self, t, m_dot_h2o, p_bar, t_C, 
                               h_ef = None, re = None,
                               poro = None, 
                               c_r=None, rho_r = None, lambda_r = None,
                               fluid = None, Ea = 0.85):
        """
        Parameters
        ----------
        t : double
            time, years
        m_dot_h2o : double
            mass flow rate, kg/s.
        p_bar : double
            pressure, bar.
        t_C : temperature
            DESCRIPTION.
        h_ef : double
            effective layer thickness.
        re : double
            effective drainage radius (recommended to be less than well distance).
        c_r : double, optional
            matrix heat capacity, J/kg∙K. The default is 950.
        rho_r : double, optional
            matrix density, kg/m3. The default is 2700.
        lambda_r : double, optional
            matrix thermal conductivity, W/m∙K, The default is 3.5 
        Ea : TYPE, optional
            DESCRIPTION. The default is 0.85.

        Returns
        -------
        None.

        """
        if poro is None: poro = self.poro
        if fluid is None: fluid = self.fluid
        if h_ef is None: h_ef = self.h_ef
        if re is None: re = self.re
        if c_r is None: c_r = self.c_r
        if rho_r is None: rho_r = self.rho_r
        if lambda_r is None: lambda_r = self.lambda_r
        
        p = p_bar * 1e5
        T = t_C + 273.15
        
        rho_w = CP.PropsSI('D', 'P', p, 'T', T, fluid)   # kg/m3, geofluid density (reservoir condition)
        rho_f = rho_r*(1-poro)+rho_w*poro            # kg/m3, formation density (fluid in pores + matrix)
        c_w = CP.PropsSI('Cpmass', 'P', p, 'T', T, fluid)       # specific heat capacity, J/kg K
        c_f = (rho_r*c_r*(1-poro)+rho_w*c_w*poro)/rho_f  # J/kg K, formation heat capacity (fluid + matrix)
        t = 365.25*24*3600*t                # time, s
         
        try:
            r_f = np.sqrt(t * m_dot_h2o *c_w / (np.pi*Ea*h_ef*c_f*rho_f))
        except:
            print ('non-physical inputs (probably some negative value')
            r_f = 0
        
        return r_f
    
    
