# -*- coding: utf-8 -*-
"""
Created on Sat Aug 23 18:54:20 2025

@author: domag
"""

import numpy as np
from inputs.metadata import ParamMetadata
from engineering.fluid_properties import FluidProperties


class Power(ParamMetadata):
    """
    Class for calculating pump and compressor power.
    Moved from previous CO2Injector and water classes.
    """
    PARAM_METADATA = {
        'm_dot': ('kg/s', 'Maseni protok CO2'),
        't_comp_in': ('°C', 'Ulazna temperatura u kompresiju CO2'),
        'p_comp_in': ('bar',      'Ulazni tlak u kompresiju CO2'),
        'eta': ('-', 'ORC učinkovitost (bezdimenzionalna)')

    }

    def __init__(self, inputs, fluid_props):
        super().__init__(**{k: getattr(inputs, k) for k in self.PARAM_METADATA})
        self.inputs = inputs
        self.fluid_props = fluid_props
        
    def calculate_ORC_power(self, m_dot, p_in, p_out, t_in, t_out = 40, fluid = 'H2O', eta = None):
        """
        Simple theoretical estimate of ORC power plant

        Parameters
        ----------
        m_dot : double
            mass flow rate, kg/s.
        p_in : double
            inlet pressure (production wellhead pressure), bar.
        p_out : double
            outlet pressure, bar.
        t_in : double
            inlet temperature (production wellhead temp), °C.
        t_out : double, optional
            outlet temperature, °C. The default is 40.
        fluid : string, optional
            fluid type ('H2O' or 'CO2'...). The default is 'H2O'.
        eta : double, optional
            ORC efficiency (common values from 0.07 to 0.2). Can be defaulted by .json input

        Returns
        -------
        P : double
            output power, kW.

        """
        if eta is None: eta = self.eta
        h_in = self.fluid_props.get_enthalpy(fluid, p = p_in*1e5, T = t_in+273.15)
        h_out = self.fluid_props.get_enthalpy(fluid, p = p_out*1e5, T = t_out+273.15)
        P = (h_in - h_out) * m_dot * eta * 0.001    # kW
        if P<0: P=0
        return P

    def calculate_pump_power(self, fluid, m_dot, p_in_bar, p_out_bar, t_C, eta=0.9):
        """
        Calculates pump power for liquids.

        Parameters:
            fluid (str): Fluid name
            m_dot (float): Mass flow rate, kg/s
            p_in_bar (float): Inlet pressure, bar
            p_out_bar (float): Outlet pressure, bar
            T_C (float): Temperature, °C
            eta (float, optional): Pump efficiency

        Returns:
            float: Pump power, W
        """
        if p_in_bar>p_out_bar:
            return 0
        T_K = t_C + 273.15
        p_avg_pa = ((p_in_bar + p_out_bar) / 2) * 1e5
        delta_p_pa = (p_out_bar - p_in_bar) * 1e5
        rho = self.fluid_props.get_density(fluid, p_avg_pa, T_K)
        q_m3_s = m_dot / rho       
        power_w = q_m3_s * delta_p_pa / eta    # Power = Q * ΔP / η
        return power_w * 0.001  #  kW

    def calculate_compression_power(self, fluid='CO2', p_in_bar=None, p_out_bar=None, t_in_C=None, m_dot=None,
                                    N_stages=5, eta_is=0.75, eta_p=0.9, print_p_sat = False):
        """
        Calculates compressor power, handling compression and optional pumping if above saturation pressure.
        Adapted from CO2Injector.compress.

        Parameters:
            fluid (str): Fluid name
            p_in_bar (float): Inlet pressure, bar
            p_out_bar (float): Outlet pressure, bar
            t_in_C (float): Inlet temperature, °C
            m_dot (float): Mass flow rate, kg/s
            N_stages (int, optional): Number of compression stages
            eta_is (float, optional): Isentropic efficiency
            eta_p (float, optional): Pump efficiency (if pumping required)

        Returns:
            total_power (float): Total power, kW (compression and pumping if it went through liquid region)
        """
        if p_in_bar is None:
            p_in_bar = self.p_comp_in
        if t_in_C is None:
            t_in_C = self.t_comp_in
        if m_dot is None:
            m_dot = self.m_dot
        
        if p_in_bar>p_out_bar:
                return 0
            
        Tc = self.fluid_props.get_Tc(fluid)
            
        R = 8.3144598
        M = self.fluid_props.get_molar_mass(fluid)
        T_in = t_in_C + 273.15
        P_pocetni = p_in_bar * 1e5
        P_zavrsni = p_out_bar * 1e5
        
        if Tc > T_in:         # provjera da li je moguće prijeći u modus pumpanja
            psat = self.fluid_props.get_saturation_pressure(fluid, T_in)
            Pp = psat - 1e5
            i_pumpanje = P_zavrsni > Pp
        else:
            i_pumpanje = False

        P_zavrsni_orig = P_zavrsni
        if i_pumpanje:
            P_zavrsni = Pp

        CR = (P_zavrsni / P_pocetni) ** (1 / N_stages)
        P_in_list = [P_pocetni]
        W_s = 0

        for i in range(N_stages):
            P_out = P_in_list[-1] * CR
            cp = self.fluid_props.get_specific_heat(fluid, P_in_list[-1], T_in, 'CP0MASS')
            cv = self.fluid_props.get_specific_heat(fluid, P_in_list[-1], T_in, 'CVMASS')
            k_s = cp / cv
            Z_s = self.fluid_props.get_compressibility_factor(fluid, P_in_list[-1], T_in)
            Ws = (m_dot * Z_s * R * T_in) / (M * eta_is) * (k_s / (k_s - 1)) * (CR ** ((k_s - 1) / k_s) - 1)
            W_s += Ws
            P_in_list.append(P_out)

        pump_power = 0
        if i_pumpanje:
            # Pump from Pp to original P_zavrsni
            pump_power = self.calculate_pump_power(fluid, m_dot, Pp / 1e5, P_zavrsni_orig / 1e5, t_in_C, eta=eta_p)

        total_power = W_s + pump_power*1000
        if print_p_sat: print(f'Switched to pump at {psat/1e5} bar')
        return total_power/1e3 # in kW
