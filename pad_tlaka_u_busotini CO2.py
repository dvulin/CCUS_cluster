import numpy as np
import pandas as pd
from ccs_utilities.fluid_properties import FluidProperties
from ccs_utilities.wellbore import WaterInjector as WI
from CoolProp.CoolProp import PropsSI
from ccs_utilities.metadata import ParamMetadata
from numpy.ma.core import log10
from scipy.optimize import fsolve

# Parametri
depth_total = 2000  # m
step = 100  # m
fluid = 'H2O'
T_surface_C = 25  # °C (primjer)

p_surface_bar = 59.807188  # bar (primjer) 
g = 9.81  # m/s²
pipe_diameter = 2 * 0.15  # m 
m_dot = 20  # kg/s (primjer)
epsilon = 0.0005  # hrapavost cijevi

# Konverzije
p_surface_Pa = p_surface_bar * 1e5
T_surface_K = T_surface_C + 273.15

# Inicijalizacija
fluid_props = FluidProperties()
depths = np.arange(0, depth_total + step, step)
pressures = [p_surface_Pa]
densities = []

def colebrook(D, Re, e=0.0005):
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


# Proračun
dp = [0]
for i, depth in enumerate(depths[:-1]):
    z1 = depth
    z2 = depths[i+1]
    delta_z = z2 - z1
    p1 = pressures[-1]

    rho1 = fluid_props.get_density(fluid, p1, T_surface_K)
    rho2 = fluid_props.get_density(fluid, p1, T_surface_K)
    rho_avg = (rho1 + rho2) / 2
    densities.append(rho_avg)

    A = np.pi*(pipe_diameter / 2)**2
    v = m_dot / (rho_avg * A)
    mu = fluid_props.get_viscosity(fluid, p1, T_surface_K)
    Re = (rho_avg * v * pipe_diameter) / mu
    f = colebrook(D = pipe_diameter,
                     Re = Re, 
                     e = epsilon)

    dp_grav = rho_avg * g * delta_z
    dp_fric = f * (delta_z / pipe_diameter) * 0.5 * rho_avg * v ** 2
    dp_total = dp_grav + dp_fric
    dp.append(dp_total)
    p2 = p1 + dp_total
    pressures.append(p2)
    
dp = np.array(dp)/1e5               # list to numpy to bar

# Konverzija i DataFrame
pressures_bar = np.array(pressures) / 1e5
df = pd.DataFrame({
    'Dubina [m]': depths,
    'Tlak [bar]': pressures_bar,
    'dp [bar]' : dp,
    'Gustoća CO2 [kg/m3]': [np.nan] + densities
})

print(df)

