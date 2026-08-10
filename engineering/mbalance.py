# -*- coding: utf-8 -*-
"""
Created on Wed Jul  9 20:46:00 2025

@author: domagoj
"""

import numpy as np
import math
import pdb
from CoolProp.CoolProp import PropsSI
from inputs.metadata import ParamMetadata

class MaterialBalance(ParamMetadata):
    PARAM_METADATA = {
        'A': ('m^2', 'Površina akvifera'),
        'h_ef': ('m', 'Efektivna debljina akvifera'),
        'poro': ('-', 'Poroznost akvifera'),
        'p_ref': ('bar', 'Referentni početni tlak'),
        'dp': ('bar', 'Korak tlaka za niz tlakova'),
        'c_p': ('1/bar', 'Stlačivost pora'),
        'sal': ('gNaCl/L', 'Salinitet'),
        'k': ('m^2', 'Prosječna propusnost'),
        'rw': ('m', 'Radijus bušotine'),
        't': ('°C', 'Temperatura sloja'),
        'm_dot': ('kg/s', 'Maseni protok CO2'),
        're': ('m', 'Efektivni drenažni radijus'),
        'V_p_ref': ('m^3', 'Početni volumen pora'),
        'V_w_ref': ('m^3', 'Početni volumen vode'),
        'p_max': ('bar', 'Maksimalni tlak'),
        'E_eff' : ('-', 'Učinkovitost skladištenja CO2 u akviferu'),
        'S_plume_core' : ('-','Osnovno zasićenje s CO2 u zoni bušotine'),
        'Sw_i': ('-', 'Minimalno zasićenje vodom'),
        'krw_max': ('-', 'Maksimalna relativna propusnost za vodu'),
        'krg_max': ('-', 'Maksimalno zasićenje za plin (CO2, zakrivljenost kr_CO2 krivulje)'),
        'nw': ('-', 'Corey-ev koeficijent za vodu (zakrivljenost krw krivulje)'),
        'ng': ('-', 'Corey-ev koeficijent za plin (CO2, zakrivljenost kr_CO2 krivulje)'),
        'krw_min': ('-', 'Minimalna relativna propusnost za vodu (da se izbjegne problem kr = 0)'),
        'krg_min': ('-', 'Minimalna relativna propusnost za plin (da se izbjegne problem kr = 0)')
    }

    def __init__(self, inputs, fluid_props):
        super().__init__(**{k: getattr(inputs, k) for k in self.PARAM_METADATA})
        self.inputs = inputs
        self.fluid_props = fluid_props
        self.fluid = 'CO2'
        self.Tr = self.inputs.t + 273.15
    
    def c_w(self, p, T, S):
        """Calculate water compressibility."""
        p = p * 14.503773773  # bar to psi
        T = T * 9/5 + 32  # °C to °F
        cw = 1 / (7.033 * p + 0.5415 * S - 537 * T + 403300)  # 1/psi
        cw = cw * 14.503773773  # 1/bar
        return cw / 1e5  # Convert to 1/Pa
    
    def calculate_total_compressibility(self, p, T):
        """Calculate total compressibility (c_p + c_f for CO2)."""
        # p, bar
        # T, K
        c_p = self.inputs.c_p / 1e5  # Convert 1/bar to 1/Pa
        p_pa = p * 1e5  # bar to Pa
        delta_p = 0.1 * 1e5  # Small pressure increment
        rho1 = self.fluid_props.get_density(self.fluid, p_pa, T)
        rho2 = self.fluid_props.get_density(self.fluid, p_pa + delta_p, T)
        c_f = (1 / rho1) * (rho2 - rho1) / delta_p  # 1/Pa
        return c_p + c_f
    
    def calculate_drainage_radius(self, k, t, phi, mu, ct):
        """
        Parameters
        ----------
        k : double
            permeability, m2.
        t : double
            time, s.
        phi : double
            porosity.
        mu : double
            viscosity, Pas.
        ct : double
            total compressibility, 1/Pa.

        Raises
        ------
        ValueError
            DESCRIPTION.

        Returns
        -------
        drainage_radius : double

        """
        if k <= 0 or t <= 0 or phi <= 0 or phi >= 1 or mu <= 0 or ct <= 0:
            raise ValueError("Invalid input parameters for drainage radius")
        hydraulic_diffusivity = k / (phi * mu * ct)
        drainage_radius = math.sqrt(hydraulic_diffusivity * t)
        return drainage_radius
    
    def kr_Corey(self, s_co2, 
                 s_wi=None, s_gr=0.0, 
                 process='drainage'):
        """
        Calculate gas(CO2)-brine relative permeability using Corey-type correlation
        for deep saline aquifer CO2 storage applications.
        
        Parameters:
        -----------
        s_co2 : float or array-like
            CO2 saturation (fraction) - Volume fraction of pore space occupied by CO2
        
        s_wi : float, optional
            Irreducible water saturation (fraction) - Physical meaning: Minimum water saturation that cannot be displaced
        
        s_gr : float, optional
            Residual CO2 saturation (fraction) - CO2 saturation trapped by capillary forces
        
        krw_max : float, optional (default=1.0)
            Maximum water relative permeability (fraction) - Water relative permeability at s_co2 = s_gr
        
        krg_max : float, optional (default=0.4)
            Maximum CO2 relative permeability (fraction) - CO2 relative permeability at s_w = s_wi
            - Range: 0.18 to 0.67 (literature values)
        
        nw : float, optional (default=3.0)
            Water/brine Corey exponent (dimensionless)
            - Physical meaning: Controls curvature of water relative permeability
            - Range: 1.2 to 6.34 (from literature)

        
        ng : float, optional (default=6.0)
            CO2/gas Corey exponent (dimensionless)
            - Physical meaning: Controls curvature of CO2 relative permeability
            - Range: 2.1 to ... (from literature)
        
        process : str, optional (default='drainage')
            Flow phase type ('drainage' or 'imbibition')
            - 'drainage': CO2 displacing water (injection phase)
            - 'imbibition': Water displacing CO2 (post-injection phase)
        krw_min, krg_min : float (default = 0.02)
                - this parameter prevents calculation of zero rate, to avoid
                    division by zero errors and errors in calculating densities
    
        Returns:
        --------
            - krw, krg: float
                Water and gas relative permeability (dimensionless)
        """
        if s_wi is None:
            s_wi = self.Sw_i

        krw_min = self.krw_min
        krg_min = self.krg_min
        krw_max = self.krw_max
        krg_max = self.krg_max
        nw=self.nw
        ng=self.ng
        
        if (isinstance(s_co2, np.ndarray)):
            mask = s_co2 >(1 - s_wi)
            if np.any(mask):
                raise Warning (f"non-physical CO2 saturation detected. Setting values to {1 - s_wi}.")
                s_co2[mask] = 1 - s_wi
        else:
            if s_co2>(1 - s_wi): s_co2 = (1 - s_wi)
        
        s_w = 1.0 - s_co2  # Water saturation
        
        sw_eff = (s_w - s_wi) / (1 - s_wi - s_gr)
        sg_eff = (s_co2 - s_gr) / (1 - s_wi - s_gr)
        sg_eff = np.clip(sg_eff, 0, 1)
        
        krw = krw_max * (sw_eff ** nw)
        krg = krg_max * (sg_eff ** ng)
        
        if krg<krg_min: krg = krg_min
        if krw<krw_min: krw = krw_min
        
        if krg>krg_max: krg = krg_max
        if krw>krw_max: krw = krw_max

        return krw, krg
    
    def calculate_bhp_from_CO2_mass_flow(self, pr, m_dot, t, ke_ef):
        pass
    
    def solve_BHP_from_CO2_mass_flow(self, pr, m_dot, t, k_ef):
        """Calculate BHP for CO2 injection with time-dependent drainage radius and Corey permeability."""
        Tr = self.Tr   # K
        ct = self.calculate_total_compressibility(pr, Tr)  # Pa⁻¹
        pr = pr * 1e5  # bar to Pa
        mu = self.fluid_props.get_viscosity(self.fluid, pr, Tr)  # Pa·s
        
        guess = 10e5  # Pa
        p_BHP = pr + guess
        tol = 1e-6
        max_iter = 50
                
        # Calculate drainage radius
        re = self.calculate_drainage_radius(self.k, t, self.poro, mu, ct)  # m
        
        for i in range(max_iter):
            rho = self.fluid_props.get_density(self.fluid, p_BHP, Tr)
            mu = self.fluid_props.get_viscosity(self.fluid, p_BHP, Tr)
            dp = p_BHP - pr
            brojnik = 2 * np.pi * k_ef * self.h_ef * rho * dp
            nazivnik = mu * np.log(re / self.rw)
            q_m_calculated = brojnik / nazivnik
            residual = q_m_calculated - m_dot
            if abs(residual) < tol:
                break
            dq_dp = (2 * np.pi * k_ef * self.h_ef * rho) / (mu * np.log(re / self.rw))
            dp_update = residual / dq_dp
            p_BHP -= dp_update
        
        p_wf_bar = p_BHP / 1e5
        return p_wf_bar, rho, mu, re
    
    def calculate_material_balance(self):
        pressures = np.arange(self.p_ref, self.p_max + self.dp, self.dp)
        # ``np.arange(..., p_max + dp, dp)`` can create one point above the
        # existing geomechanical limit when the interval is not divisible by
        # ``dp``. Keep only admissible pressure steps; the pressure-limit
        # equation itself is unchanged.
        pressures = pressures[pressures <= self.p_max + 1e-12]
        self.pressures = pressures
        
        # area and radius of deep saline aquifer, DSA
        A_dsa = self.inputs.A
        r_dsa = np.sqrt(A_dsa / np.pi)

        #pdb.set_trace()  # Uncomment for debugging
        V_p = [self.V_p_ref]
        V_w = [self.V_w_ref]
        
        free_PV = [0]
        m_CO2 = [0]
        rho_CO2_stored = [(self.fluid_props.get_density(
                                self.fluid, pressures[0] * 1e5, self.t + 273.15))
            ]
        times = [1.0]  # Initial time (1 second)
        cw = self.c_w(pressures, self.t, self.inputs.sal)
        
        print("Material balance progress:", end='', flush=True)
        for i, p_i in enumerate(pressures[1:], start=1):
            V_pi = V_p[i-1] * (1 + self.c_p * self.dp)
            V_wi = V_w[i-1] * (1 - cw[i] * self.dp)
            V_p.append(V_pi)
            V_w.append(V_wi)
            free_PVi = (V_pi - V_p[0]) + (V_w[0] - V_wi)
            free_PV.append(free_PVi)
            m_CO2.append(free_PVi * rho_CO2_stored[i-1])
            rho_CO2_stored.append(self.fluid_props.get_density(self.fluid, p_i * 1e5, self.t + 273.15))
       
            # Estimate time from cumulative m_CO2
            t = m_CO2[i] / self.m_dot  # seconds
            times.append(t)
  
            # Progress bar: print dot every 50 iterations
            if i % 50 == 0:
                print('.', end='', flush=True)
        
        print ("|")
        self.storage_capacity = m_CO2[-1]       # kg    | last calculated CO2 stored ~ m_CO2_max
        self.times = np.array(times)
        return {
            'p': pressures,
            'V_p': V_p,
            'V_w': V_w,
            'free_PV': free_PV,
            'm_CO2': m_CO2,
            'rho_CO2_stored': rho_CO2_stored,
            'time_s': times,
        }
    
    def calculate_bhp_properties(self, S_co2_effective = 0.6):
        """
        Parameters
        ----------
        self : object should be populated with input variables in
                calculate_material_balance function
        -------
        None.

        """    
        BHP, density_BHP, viscosity_BHP = [self.pressures[0]], [0], [0]
        re_list, kr_co2_list, k_co2_list = [0], [0], [0]
        S_co2_effective = S_co2_effective*np.ones(len(self.pressures))
        print("Calculating CO2 injection pressures:", end='', flush=True)
        for i, p_i in enumerate(self.pressures[1:], start = 1):
            t = self.times[i]
            s_co2 = S_co2_effective[i]
            kr_w, kr_co2 = self.kr_Corey(s_co2)
            k_CO2 = kr_co2 * self.k         # but in first step kr_CO2 = 0
                                            # check how initial kr_CO2 affects the calculation

            p_bhp, rho, mu, re = self.solve_BHP_from_CO2_mass_flow(
                pr=p_i, m_dot=self.m_dot, t=t, k_ef=k_CO2
                )
            BHP.append(p_bhp)
            density_BHP.append(rho)
            viscosity_BHP.append(mu)
            re_list.append(re)
            kr_co2_list.append(kr_co2)
            k_co2_list.append(k_CO2)
            if i % 50 == 0: print('.', end='', flush=True)
        
        print ("|")
        return {
            'time' : np.array(self.times),                 # s
            'BHP': np.array(BHP),                          # bar
            'dp' : np.array(BHP) - self.pressures,         # bar
            'density_BHP': np.array(density_BHP),          # kg/m3
            'viscosity_BHP': np.array(viscosity_BHP),      # Pas
            're': np.array(re_list),                          # m
            's_co2_eff' : np.array(S_co2_effective),
            'kr_co2': np.array(kr_co2_list),                  # -
        }
    
    def calculate_effective_saturation(self, m_co2):
        """
        Parameters
        ----------
        m_co2: float or numpy array 
            - strored CO2 in all pressure steps
        DESCRIPTION:
            calculates effective CO2 saturation which approximates saturation
            for calculating relative permeabilities.
            Note: this should override too small total CO2 saturations
            which yield to small kr_CO2 values
            CO2 saturation will depend on storage efficiency and S_plume_core:
                - saturation in "transition zone" and "leading edge" is described as
                  mass of stored CO2 devided by effective volume (from E_eff)
                - S_CO2_eff is arithmetic mean of saturation in "plume core"
                    (i.e. near wellbore) and in "transition/leading edge"  
        Returns
        -------
        S_CO2_eff - float or numpy array

        """
        S_CO2_eff = m_co2/self.storage_capacity
        S_CO2_eff = S_CO2_eff + self.S_plume_core       # this is the influence of core plume near wellbore
        
        return S_CO2_eff
    
    def calculate_co2_plume_radius(self, m_co2, t):
        """Calculate CO2 plume radius at time t (years)."""
        rho_co2 = self.fluid_props.get_density(self.fluid, self.p_ref * 1e5, self.t + 273.15)
        V_co2 = m_co2 / rho_co2  # m^3
        r_plume = np.sqrt(V_co2 / (np.pi * self.h_ef))
        return r_plume  # m
