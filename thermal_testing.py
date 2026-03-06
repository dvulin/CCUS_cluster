# -*- coding: utf-8 -*-
"""
Created on Tue Aug 26 06:20:27 2025

@author: domagoj
"""
import numpy as np
from scipy.special import erf
import pandas as pd
import CoolProp.CoolProp as CP
import pprint

#eta_ORC = 0.35
# eta_bus = 1
depth = 2000
m_w = 10_000_000                            # kg/day, mass flow rate

T_inj = 40                                  # °C, temperature of injection at wellhead, after ORC (reinjection)
T_inj_rc = T_inj + T_inj    #*(1-eta_bus)        # °C, temperature of injection at bottomhole ~ reservoir depth
k = 100/(1.01324997e+15)                    # koeficijent propusnosti m2
phi = 0.15									# porosity
h = 100			                            # effective layer thickness, m
d_doublet = 700      								# well distance
p = 150*1e5               					# reservoir pressure
T = 150+273.15           					# reservoir temperature
fluid = 'H2O'
Ti = T-273.15                   # initial temperature, °C
re = d_doublet
rw = 0.15						# well radius
t_sim = 30                      # time of calculation, years
dt = 1/12                       # one-step of calculation, years
dt = dt*365.25*24*3600
t = np.arange(0, (t_sim*365.25*24*3600+dt), dt)  # time-steps of calculation, years
t_god = t/(365.25*24*3600)
    
properties = {
			  'fluid': fluid,
			  'L' : d_doublet,              # well distance, m
			  'T': Ti,  # K
			  'poro' : phi, 
			  'p': p,  # Pa
			  'rho': CP.PropsSI('D', 'P', p, 'T', T, fluid),
			  'mu': CP.PropsSI('viscosity', 'P', p, 'T', T, fluid),
			  'h': CP.PropsSI('H', 'P', p, 'T', T, fluid),            # enthalpy, J/kg
			  'c': CP.PropsSI('Cpmass', 'P', p, 'T', T, fluid),       # specific heat capacity, J/kg K
			  'phase': CP.PhaseSI('P', p, 'T', T, fluid),
			  'P' : None,          # power, MW
			  'E' : None,          # energy produced, MJ
			  'stored' : None,     # stored (prior to breakthrough), Mt
			  't_bt' : 0,          # breaktrough moment, years              
			  'q' : None           # volumetric flow rate at reservoir conditions m3/s
		  }
    
rho_sc = CP.PropsSI('D', 'P', 101325, 'T', 288.15, fluid)         # density at standard conditions
Ea = 0.85                       # Areal sweep efficiency
Ar = np.pi*re**2                 # drainage radius area, m2
A = Ar*Ea                       # effective drainage area, m2
c_r = 950                       # J/kg∙K, matrix heat capacity
rho_r = 2700                    # kg/m3, matrix density
lambda_r = 3.5                  # W/m∙K, matrix thermal conductivity

c_w = properties['c']                 # J/kg∙K, geofluid heat capacity
rho_w = properties['rho']             # kg/m3, geofluid density (reservoir condition)
FVF = rho_sc/rho_w                    # geofluid formation volume factor (rm3/sm3)
q_w = m_w/(24*3600*rho_w)             # m3/s, (flow rate - reservoir conditions)
rho_f = rho_r*(1-phi)+rho_w*phi       # kg/m3, formation density (fluid in pores + matrix)
c_f = (rho_r*c_r*(1-phi)+rho_w*c_w*phi)/rho_f    # J/kg, formation heat capacity (fluid in pores + matrix)
t_bt = A*h*c_f*rho_f/(q_w*c_w*rho_w)  # time of cold front breakthrough, s
W = t_bt*q_w                          # injected until breakthrough, m3 WRONG ESTIMATE SINCE NO PERMEABILITY INCLUDED!!!
t_bt_y = t_bt/(365.25*24*3600)        # time of breakthrough, years.
properties['t_bt'] = t_bt_y
properties['stored'] = W*rho_w*1e-9   # stored (until breakthrough, if geothermal geofluid is CO2 or similar), Mt
properties['q'] = q_w                    
    
# after breakthrough
C1 = A*np.sqrt(lambda_r*c_r*rho_r)
C3 = q_w*c_w*rho_w
C2 = (A*h*c_f*rho_f)/C3

T_prod, E_prod, P_prod = [], [], []
for tn in t:
    try:
        if tn-C2<0:
            T_prod.append(Ti)
        else:
            erf_arg = (C1/(C3*np.sqrt(tn-C2)))
            T_prod.append(T_inj_rc+(Ti-T_inj_rc)*erf(erf_arg))
    except:
        print (f'something went wrong at tstep {tn}')
        T_prod.append(Ti)
T_prod = np.array(T_prod)
E_prod = np.array(E_prod)
properties['T'] = T_prod
properties['t'] = t_god
a = pd.DataFrame(properties)