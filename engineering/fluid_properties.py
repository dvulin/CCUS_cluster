# -*- coding: utf-8 -*-
"""
Created on Wed Jul  9 23:36:01 2025

@author: domagoj
"""

from CoolProp.CoolProp import PropsSI

class FluidProperties:
    def __init__(self):
        """Initialize fluid properties."""
        pass
    
    def get_density(self, fluid, p, T):
        return PropsSI('D', 'P', p, 'T', T, fluid)  # kg/m³
    
    def get_viscosity(self, fluid, p, T):
        return PropsSI('V', 'P', p, 'T', T, fluid)  # Pa·s
    
    def get_enthalpy(self, fluid, T, p):
        return PropsSI('H', 'T', T, 'P', p, fluid)  # J/kg
    
    def get_molar_mass(self, fluid):
        return PropsSI('MOLAR_MASS', fluid)  # kg/mol
    
    def get_saturation_pressure(self, fluid, T):
        return PropsSI('P', 'Q', 0, 'T', T, fluid)  # Pa
    
    def get_compressibility_factor(self, fluid, p, T):
        return PropsSI('Z', 'P', p, 'T', T, fluid)
    
    def get_specific_heat(self, fluid, p, T, param='CP0MASS'):
        return PropsSI(param, 'P', p, 'T', T, fluid)  # J/kg/K
    
    def get_Tc(self, fluid):
        return PropsSI('TCRIT', fluid)  # critical temperature, K

    def get_pc(self, fluid):
        return PropsSI('PCRIT', fluid)  # critical pressure, Pa