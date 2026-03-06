# -*- coding: utf-8 -*-
"""
Created on Wed Jul  9 20:49:00 2025
@author: domagoj
"""
# GT_CCS_engineering.py
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from ccs_utilities import IOEndpoints
from ccs_utilities import MaterialBalance
from ccs_utilities import VFP
from ccs_utilities import Geothermal
from ccs_utilities import FluidProperties
from ccs_utilities import Visualization
from ccs_utilities import Power
import json

# Load inputs
inputs = IOEndpoints('reservoir_inputs.json')

# Initialize objects
fluid_props = FluidProperties()

# transport power
pipeline = Power(inputs, fluid_props)
P_pipeline = pipeline.calculate_compression_power(p_in_bar=1, p_out_bar= 50, t_in_C=20, m_dot = 700*1e6/(365.25*24*3600), print_p_sat = True)
     

mbalance = MaterialBalance(inputs, fluid_props)
p_initial = mbalance.p_ref      # početni tlak u sloju

# Material balance calculations
mbal_results = mbalance.calculate_material_balance()
mbal_df = pd.DataFrame({
    'Time, yr': np.array(mbal_results['time_s']) / (3600 * 24 * 365.25),
    'm_CO2, Mt': np.array(mbal_results['m_CO2']) / 1e9,
    'DSA pressure, bar': mbal_results['p'],
    'CO2_stored density, kg/m³': mbal_results['rho_CO2_stored'],
    'Vp, rm³': mbal_results['V_p'],
    'Vw, rm³': mbal_results['V_w'],
    'free PV, rm³': mbal_results['free_PV']
})

co2_stored = mbal_df['m_CO2, Mt'].values*1e9
S_CO2_eff = mbalance.calculate_effective_saturation(m_co2 = co2_stored)

well_bhp_results = mbalance.calculate_bhp_properties(S_co2_effective = S_CO2_eff)
vfp_CO2_df = pd.DataFrame({
    'Time [yr]': well_bhp_results['time'] / (3600 * 24 * 365.25),
    'BHP [bar]': well_bhp_results['BHP'],
    'dp [bar]' : well_bhp_results['dp'], 
    'density at BHP': well_bhp_results['density_BHP'],
    'viscosity at BHP [mPas]': well_bhp_results['viscosity_BHP']*1000,
    're': well_bhp_results['re'],
    'S_eff' : well_bhp_results['s_co2_eff'],
    'kr_co2': well_bhp_results['kr_co2']
        })

vis = Visualization()
vis.s_eff_vs_co2_stored_kr_co2(vfp_CO2_df, mbal_df)
# vis.bhp_vs_density_viscosity(bhp_df)

CO2_injection_well = VFP(inputs, fluid_props)
CO2_injection_power = Power(inputs, fluid_props)

gt_ipr = Geothermal(inputs, fluid_props)

BHP = vfp_CO2_df['BHP [bar]'].to_numpy()
whps, co2_power = [], []
for bhp in BHP:
    whps.append(
        CO2_injection_well.calculate_dp(
        fluid = 'CO2', 
        bhp = bhp,
        T_C = 20            # temperatura utiskivanja CO2
        )
    )
    # calculate compression power
    p_comp_out = whps[-1]
    co2_power.append(
        CO2_injection_power.calculate_compression_power(p_out_bar=p_comp_out)
        )
    
vfp_CO2_df['CO2 WHP [bar]']= whps
vfp_CO2_df['CO2 comp. P [kW]'] = co2_power
vis.time_vs_CO2_stored_vs_bhp_vs_whp(mbal_df, vfp_CO2_df)
vis.time_vs_power_vs_bhp_vs_pDSA(mbal_df, vfp_CO2_df)

# proračun protoka geotermalne vode - radi pojednostavljenja ne uzima u obzir 
#       promjenu temperature u ležištu /neznatno povećanje viskoznosti vode)
m_dot_h2o_list, q_rc, rho_h2o_list = [], [], []
gt_bhp_inj_list, gt_bhp_prod_list = [], []
gt_pressures = mbal_results['p']
for p in gt_pressures:
    m_dot_h2o, qr_h2o, bhp_prod = gt_ipr.calculate_m_dot_prod(
                            p_ref = p, 
                            bhp_dp = (p-p*0.9),   # kritično vidjeti koji dp paše
                            rw = 0.15
        )
    
    bhp_inj, rho_h2o = gt_ipr.calculate_bhp_inj(
                            p_ref = p, 
                            m_dot_h2o = m_dot_h2o
        )
    m_dot_h2o_list.append(m_dot_h2o)
    q_rc.append(qr_h2o)
    gt_bhp_prod_list.append(bhp_prod)  
    gt_bhp_inj_list.append(bhp_inj)
    rho_h2o_list.append(rho_h2o)
    
mbal_df['m_dot geothermal [kg/s]'] = m_dot_h2o_list
mbal_df['q geothermal [rm3/d]'] = q_rc
mbal_df['rho geoth. [kg/m3]'] = rho_h2o_list
mbal_df['gt bhp_inj [bar]'] = gt_bhp_inj_list

###
geothermal = Geothermal (inputs, fluid_props)
time_yr = mbal_df['Time, yr'].values
m_dot_geothermal = mbal_df['m_dot geothermal [kg/s]'].values
p_ref =  mbal_df['DSA pressure, bar'].values

# racuna pad temperature na proizvodnoj busotini
doublet, gt_info = geothermal.calculate_unsteady_production(mbal_df = mbal_df)
t_prod = doublet['temperature, °C'].values

# VFP geothermal
gt_power = Power(inputs, fluid_props)
gt_production_well = VFP(inputs, fluid_props)
gt_injection_well = VFP(inputs, fluid_props)
gt_prod_whps, gt_inj_whps, ORC_power, pump_power = [], [], [], []

for i, bhp_inj in enumerate(gt_bhp_inj_list):
    gt_prod_whps.append(
        gt_production_well.calculate_dp(fluid = 'H2O', bhp = gt_bhp_prod_list[i], 
                                        m_dot = m_dot_geothermal[i], 
                                        T_C = t_prod[i])   # T_C: temperatura proizvodnje vode
                        )
    gt_inj_whps.append(
        gt_production_well.calculate_dp(fluid = 'H2O', bhp = bhp_inj, 
                                        m_dot = m_dot_geothermal[i],
                                        T_C = 40)   # T_C: temperatura utiskivanja vode
                        )
    
    # calculate pump power
    p_pump_out = gt_inj_whps[-1]
    p_pump_in =  gt_prod_whps[-1]
    pump_power.append(gt_power.calculate_pump_power(fluid = 'H2O', 
                                                   m_dot = m_dot_geothermal[i],
                                                   p_in_bar= p_pump_in,
                                                   p_out_bar=p_pump_out,
                                                   t_C = 35 
                                                   ))
    ORC_power.append(gt_power.calculate_ORC_power(
                                                m_dot = m_dot_geothermal[i],
                                                p_in = gt_prod_whps[-1],
                                                p_out = gt_prod_whps[-1]-0.1,  # preciznije bi bilo s padom tlaka u cijevi do utisne busotine
                                                t_in = t_prod[i], 
                                                t_out = 40, 
                                                fluid = 'H2O'
                                                  ))


vfp_gt_df = pd.DataFrame({
    'Time [yr]': well_bhp_results['time'] / (3600 * 24 * 365.25),
    'm_dot, kg/s' : m_dot_geothermal,
    'prod t, °C' : t_prod,
    'prod BHP [bar]': gt_bhp_prod_list,
    'inj BHP [bar]': gt_bhp_inj_list,
    'prod WHP [bar]': gt_prod_whps,
    'inj WHP [bar]': gt_inj_whps,
    'pump power, kW' : pump_power, 
    'ORC power, kW' : ORC_power
        })
vfp_gt_df['net power GT, kW'] = vfp_gt_df['ORC power, kW'] - vfp_gt_df['pump power, kW']

doublet.plot(x = 'time, years', xlabel = 'vrijeme, godine',
             y = 'temperature, °C', ylabel = 'proizvodna temperatura, °C', ylim = (0, 200))
plt.show()




vis.time_vs_geothermal_flow_temperature(mbal_df, vfp_gt_df)
vis.time_vs_geothermal_co2_bhp_whp_comparison(vfp_gt_df, vfp_CO2_df)
vis.time_vs_power(vfp_gt_df, vfp_CO2_df)