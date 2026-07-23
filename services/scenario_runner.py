"""Application service that orchestrates the existing engineering models."""

from pathlib import Path

import numpy as np
import pandas as pd

from engineering import FluidProperties, Geothermal, MaterialBalance, Power, VFP
from inputs import IOEndpoints


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "inputs" / "examples" / "main_inputs.json"


class ScenarioRunner:
    """Run the existing storage, wellbore, geothermal and power calculations.

    This class only coordinates the current engineering classes and prepares
    their results as DataFrames. Physical equations remain in ``engineering``.
    """

    def __init__(self, input_source=None):
        self.input_source = (
            Path(input_source)
            if input_source is not None and not isinstance(input_source, dict)
            else input_source
        )
        if self.input_source is None:
            self.input_source = DEFAULT_INPUT_PATH

    def run(self):
        """Execute the active engineering scenario and return its results."""
        inputs = IOEndpoints(self.input_source)
        fluid_props = FluidProperties()

        mbalance = MaterialBalance(inputs, fluid_props)
        mbalance.rw = inputs.rw_co2
        mbal_results = mbalance.calculate_material_balance()
        mbal_df = pd.DataFrame(
            {
                "Time, yr": np.array(mbal_results["time_s"]) / (3600 * 24 * 365.25),
                "m_CO2, Mt": np.array(mbal_results["m_CO2"]) / 1e9,
                "DSA pressure, bar": mbal_results["p"],
                "CO2_stored density, kg/m³": mbal_results["rho_CO2_stored"],
                "Vp, rm³": mbal_results["V_p"],
                "Vw, rm³": mbal_results["V_w"],
                "free PV, rm³": mbal_results["free_PV"],
            }
        )

        co2_stored = mbal_df["m_CO2, Mt"].values * 1e9
        effective_co2_saturation = mbalance.calculate_effective_saturation(
            m_co2=co2_stored
        )
        well_bhp_results = mbalance.calculate_bhp_properties(
            S_co2_effective=effective_co2_saturation
        )
        vfp_co2_df = pd.DataFrame(
            {
                "Time [yr]": well_bhp_results["time"] / (3600 * 24 * 365.25),
                "BHP [bar]": well_bhp_results["BHP"],
                "dp [bar]": well_bhp_results["dp"],
                "density at BHP": well_bhp_results["density_BHP"],
                "viscosity at BHP [mPas]": well_bhp_results["viscosity_BHP"] * 1000,
                "re": well_bhp_results["re"],
                "S_eff": well_bhp_results["s_co2_eff"],
                "kr_co2": well_bhp_results["kr_co2"],
            }
        )

        co2_injection_well = VFP(inputs, fluid_props)
        co2_injection_well.rw = inputs.rw_co2
        co2_injection_power = Power(inputs, fluid_props)
        co2_whp_values = []
        co2_power_values = []

        for bhp in vfp_co2_df["BHP [bar]"].to_numpy():
            co2_whp_values.append(
                co2_injection_well.calculate_dp(
                    fluid="CO2",
                    bhp=bhp,
                    T_C=20,
                )
            )
            co2_power_values.append(
                co2_injection_power.calculate_compression_power(
                    p_out_bar=co2_whp_values[-1]
                )
            )

        vfp_co2_df["CO2 WHP [bar]"] = co2_whp_values
        vfp_co2_df["CO2 comp. P [kW]"] = co2_power_values

        geothermal_production_ipr = Geothermal(inputs, fluid_props)
        geothermal_production_ipr.rw = inputs.rw_geothermal_production
        geothermal_injection_ipr = Geothermal(inputs, fluid_props)
        geothermal_injection_ipr.rw = inputs.rw_geothermal_injection
        geothermal_mass_flow = []
        geothermal_reservoir_flow = []
        geothermal_density = []
        geothermal_injection_bhp = []
        geothermal_production_bhp = []

        for pressure in mbal_results["p"]:
            mass_flow, reservoir_flow, production_bhp = (
                geothermal_production_ipr.calculate_m_dot_prod(
                    p_ref=pressure,
                    bhp_dp=inputs.bhp_dp,
                )
            )
            injection_bhp, density = geothermal_injection_ipr.calculate_bhp_inj(
                p_ref=pressure,
                m_dot_h2o=mass_flow,
            )
            geothermal_mass_flow.append(mass_flow)
            geothermal_reservoir_flow.append(reservoir_flow)
            geothermal_production_bhp.append(production_bhp)
            geothermal_injection_bhp.append(injection_bhp)
            geothermal_density.append(density)

        mbal_df["m_dot geothermal [kg/s]"] = geothermal_mass_flow
        mbal_df["q geothermal [rm3/d]"] = geothermal_reservoir_flow
        mbal_df["rho geoth. [kg/m3]"] = geothermal_density
        mbal_df["gt bhp_inj [bar]"] = geothermal_injection_bhp

        geothermal = Geothermal(inputs, fluid_props)
        doublet_df, gt_info = geothermal.calculate_unsteady_production(
            mbal_df=mbal_df
        )
        production_temperature = doublet_df["temperature, °C"].values

        geothermal_power = Power(inputs, fluid_props)
        geothermal_production_well = VFP(inputs, fluid_props)
        geothermal_production_well.rw = inputs.rw_geothermal_production
        geothermal_injection_well = VFP(inputs, fluid_props)
        geothermal_injection_well.rw = inputs.rw_geothermal_injection
        production_whp = []
        injection_whp = []
        orc_power = []
        pump_power = []

        for index, injection_bhp in enumerate(geothermal_injection_bhp):
            production_whp.append(
                geothermal_production_well.calculate_dp(
                    fluid="H2O",
                    bhp=geothermal_production_bhp[index],
                    m_dot=geothermal_mass_flow[index],
                    T_C=production_temperature[index],
                )
            )
            injection_whp.append(
                geothermal_injection_well.calculate_dp(
                    fluid="H2O",
                    bhp=injection_bhp,
                    m_dot=geothermal_mass_flow[index],
                    T_C=inputs.t_out,
                )
            )
            pump_power.append(
                geothermal_power.calculate_pump_power(
                    fluid="H2O",
                    m_dot=geothermal_mass_flow[index],
                    p_in_bar=production_whp[-1],
                    p_out_bar=injection_whp[-1],
                    t_C=inputs.t_out,
                )
            )
            orc_power.append(
                geothermal_power.calculate_ORC_power(
                    m_dot=geothermal_mass_flow[index],
                    p_in=production_whp[-1],
                    p_out=inputs.p_out,
                    t_in=production_temperature[index],
                    t_out=inputs.t_out,
                    fluid="H2O",
                )
            )

        vfp_gt_df = pd.DataFrame(
            {
                "Time [yr]": well_bhp_results["time"] / (3600 * 24 * 365.25),
                "m_dot, kg/s": geothermal_mass_flow,
                "prod t, °C": production_temperature,
                "prod BHP [bar]": geothermal_production_bhp,
                "inj BHP [bar]": geothermal_injection_bhp,
                "prod WHP [bar]": production_whp,
                "inj WHP [bar]": injection_whp,
                "pump power, kW": pump_power,
                "ORC power, kW": orc_power,
            }
        )
        vfp_gt_df["net power GT, kW"] = (
            vfp_gt_df["ORC power, kW"] - vfp_gt_df["pump power, kW"]
        )

        water_saturation = np.linspace(inputs.Sw_i, 1.0, 101)
        relative_permeability = [
            mbalance.kr_Corey(s_co2=float(1.0 - sw))
            for sw in water_saturation
        ]
        relative_permeability_df = pd.DataFrame(
            {
                "Sw (-)": water_saturation,
                "krw (-)": [values[0] for values in relative_permeability],
                "krg (-)": [values[1] for values in relative_permeability],
            }
        )

        return {
            "mbal_df": mbal_df,
            "vfp_co2_df": vfp_co2_df,
            "doublet_df": doublet_df,
            "vfp_gt_df": vfp_gt_df,
            "gt_info": gt_info,
            "relative_permeability_df": relative_permeability_df,
        }
