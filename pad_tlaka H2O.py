import numpy as np
import pandas as pd
from ccs_utilities.fluid_properties import FluidProperties
from CoolProp.CoolProp import PropsSI
from ccs_utilities.metadata import ParamMetadata
from numpy.ma.core import log10
from scipy.optimize import fsolve

# Parametri
depth_total = 2000  # m
step = 100  # m
fluid = 'Water'
T_surface_C = 35  # °C ORC izlaz (pitati)
geothermal_gradient_C_per_m = 0.03  # °C/m (primjer)
BHP_bar = 250  # Zadan tlak na dnu bušotine (bar)
g = 9.81  # m/s²
pipe_diameter = 0.3  # m
m_dot = 20  # kg/s (primjer)
epsilon = 0.0005  # hrapavost cijevi
T_sloja = T_surface_C+geothermal_gradient_C_per_m*depth_total
T_sloja_K = T_sloja+273.15

# Konverzije
p_bottom_Pa = BHP_bar * 1e5
T_surface_K = T_surface_C + 273.15

# Inicijalizacija
fluid_props = FluidProperties()
depths = np.arange(depth_total, -step, -step)  # Od dna prema vrhu
pressures = [p_bottom_Pa]
densities = []



def f_Colebrook_White(D, Re, e):
    """
    Solves the Colebrook-White equation using the fsolve function from scipy.optimize.

    Parameters:
        Re (float): Reynolds number
        e (float): Absolute roughness of the pipe, m
        D (float): Diameter of the pipe, m

    Returns:
        f[0] (float): Friction factor
    """
    def f(f):
        return 1 / (f ** 0.5) + 2 * log10(e / (3.7 * D) + 2.51 / (Re * f ** 0.5))
    f0 = 0.01
    f = fsolve(f, f0)
    return f[0]

dp = [0]

#
#       PROIZVODNA BUŠOTINA
#

for i in range(len(depths) - 1):
    z1 = depths[i]
    z2 = depths[i + 1]
    delta_z = z1 - z2
    
    # TODO: in future - temperature loss...
    # T1 = T_surface_K + geothermal_gradient_C_per_m * z1
    # T2 = T_surface_K + geothermal_gradient_C_per_m * z2
    p1 = pressures[-1]

    rho1 = fluid_props.get_density(fluid, p1, T_sloja_K)
    rho2 = fluid_props.get_density(fluid, p1, T_sloja_K)
    rho_avg = (rho1 + rho2) / 2
    densities.append(rho_avg)

    A = np.pi * (pipe_diameter / 2) ** 2
    v = m_dot / (rho_avg * A)
    mu = fluid_props.get_viscosity(fluid, p1, T_sloja_K)
    Re = (rho_avg * v * pipe_diameter) / mu
    f = f_Colebrook_White(D = pipe_diameter, 
                  Re=Re, 
                  e = epsilon)

    dp_grav = rho_avg * g * delta_z
    dp_fric = f * (delta_z / pipe_diameter) * 0.5 * rho_avg * v ** 2
    dp_total = dp_grav + dp_fric
    dp.append(dp_total)
    p2 = p1 - dp_total
    pressures.append(p2)

# Konverzija i DataFrame
pressures_bar = np.array(pressures) / 1e5
depths_sorted = np.flip(depths)  # za vizualno od površine prema dnu
df = pd.DataFrame({
    'Dubina [m]': depths_sorted,
    'Tlak [bar]': np.flip(pressures_bar),
    'dp [bar]' : dp,
    'Gustoća vode [kg/m3]': [np.nan] + list(np.flip(densities))
})

print(df)


#
#       UTISNA BUŠOTINA
#
