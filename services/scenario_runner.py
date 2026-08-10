"""Application service that orchestrates the existing engineering models."""

from pathlib import Path
import unicodedata

import numpy as np
import pandas as pd

from economics import CashFlowRunner, generate_co2_price_path, summarize_cash_flow
from engineering import (
    FluidProperties,
    Geothermal,
    MaterialBalance,
    Power,
    Transport,
    VFP,
)
from inputs import IOEndpoints
from .engineering_economics_adapter import build_annual_engineering_ledger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "inputs" / "examples" / "main_inputs.json"
CALCULATION_LOG_PATH = PROJECT_ROOT / "calculation.log"


def _clip_time_series(frame, time_column, end_elapsed_year):
    """Clip a numeric engineering table and interpolate its final boundary."""
    end_elapsed_year = float(end_elapsed_year)
    times = frame[time_column].to_numpy(dtype=float)
    clipped = frame.loc[times <= end_elapsed_year].copy()
    if end_elapsed_year < times[0]:
        clipped = frame.iloc[[0]].copy()
    if end_elapsed_year < times[-1] and not np.any(
        np.isclose(times, end_elapsed_year, rtol=0.0, atol=1e-12)
    ):
        boundary = {}
        for column in frame.columns:
            if column == time_column:
                boundary[column] = end_elapsed_year
            elif pd.api.types.is_numeric_dtype(frame[column]):
                boundary[column] = float(
                    np.interp(
                        end_elapsed_year,
                        times,
                        frame[column].to_numpy(dtype=float),
                    )
                )
            else:
                boundary[column] = frame[column].iloc[-1]
        clipped = pd.concat(
            [clipped, pd.DataFrame([boundary], columns=frame.columns)],
            ignore_index=True,
        )
    return clipped.reset_index(drop=True)


def _extend_constant_state(frame, time_column, end_elapsed_year):
    """Extend a clipped state table while holding its final state constant.

    This is used only after CO2 injection has stopped. The geothermal doublet
    produces and reinjects the same water mass, so the current non-spatial
    material-balance model applies a zero-net-withdrawal boundary and keeps the
    final storage pressure constant. No existing physical equation is changed.
    """
    end_elapsed_year = float(end_elapsed_year)
    extended = frame.copy().reset_index(drop=True)
    current_end = float(extended[time_column].iloc[-1])
    if end_elapsed_year <= current_end:
        return _clip_time_series(extended, time_column, end_elapsed_year)

    additional_times = list(
        np.arange(np.floor(current_end) + 1.0, end_elapsed_year, 1.0)
    )
    additional_times.append(end_elapsed_year)
    additional_times = [
        value
        for value in additional_times
        if value > current_end and not np.isclose(value, current_end)
    ]
    if not additional_times:
        return extended

    final_row = extended.iloc[-1].to_dict()
    rows = []
    for elapsed_year in additional_times:
        row = dict(final_row)
        row[time_column] = float(elapsed_year)
        rows.append(row)
    return pd.concat(
        [extended, pd.DataFrame(rows, columns=extended.columns)],
        ignore_index=True,
    )


def _annual_injection_diagnostics(
    annual_ledger,
    vfp_co2_df,
    dsa_pressure_df,
    *,
    injection_start_year,
    injection_active_elapsed_years,
):
    """Build annual CO2/BHP and time-weighted aquifer-pressure diagnostics."""
    years = annual_ledger["year"].to_numpy(dtype=int)
    quantities = annual_ledger["co2_chain_t"].to_numpy(dtype=float)
    time = vfp_co2_df["Time [yr]"].to_numpy(dtype=float)
    bhp = vfp_co2_df["BHP [bar]"].to_numpy(dtype=float)
    dsa_time = dsa_pressure_df["Time, yr"].to_numpy(dtype=float)
    dsa_pressure = dsa_pressure_df["DSA pressure, bar"].to_numpy(dtype=float)
    bhp_at_year_end = np.full(years.size, np.nan, dtype=float)
    average_dsa_pressure = np.empty(years.size, dtype=float)

    for index, (year, quantity) in enumerate(zip(years, quantities)):
        elapsed_start = float(year - injection_start_year)
        elapsed_end = elapsed_start + 1.0
        interior_time = dsa_time[
            (dsa_time > elapsed_start) & (dsa_time < elapsed_end)
        ]
        integration_time = np.unique(
            np.concatenate(
                ([elapsed_start], interior_time, [elapsed_end])
            )
        )
        integration_pressure = np.interp(
            integration_time,
            dsa_time,
            dsa_pressure,
            left=float(dsa_pressure[0]),
            right=float(dsa_pressure[-1]),
        )
        average_dsa_pressure[index] = float(
            np.sum(
                0.5
                * (integration_pressure[:-1] + integration_pressure[1:])
                * np.diff(integration_time)
            )
            / (elapsed_end - elapsed_start)
        )
        if quantity <= 0.0:
            continue
        elapsed_end = min(
            float(year - injection_start_year + 1),
            float(injection_active_elapsed_years),
        )
        bhp_at_year_end[index] = float(np.interp(elapsed_end, time, bhp))

    return pd.DataFrame(
        {
            "year": years,
            "co2_injected_t": quantities,
            "co2_injection_bhp_end_bar": bhp_at_year_end,
            "average_dsa_pressure_bar": average_dsa_pressure,
        }
    )


def _build_well_pressure_table(gt_support_df, vfp_co2_df, vfp_gt_df):
    """Outer-merge all reservoir and flowing well pressures on elapsed time."""
    dsa_pressure = gt_support_df[["Time, yr", "DSA pressure, bar"]].rename(
        columns={
            "Time, yr": "Time [yr]",
            "DSA pressure, bar": "DSA pressure [bar]",
        }
    )
    co2_pressure = vfp_co2_df[
        ["Time [yr]", "BHP [bar]", "CO2 WHP [bar]"]
    ].rename(
        columns={
            "BHP [bar]": "CO2 injection BHP [bar]",
            "CO2 WHP [bar]": "CO2 injection WHP [bar]",
        }
    )

    geothermal_active = vfp_gt_df["geothermal active"].to_numpy(dtype=bool)
    gt_pressure = pd.DataFrame(
        {
            "Time [yr]": vfp_gt_df["Time [yr]"].to_numpy(dtype=float),
            "GT production BHP [bar]": vfp_gt_df["prod BHP [bar]"].where(
                geothermal_active,
                np.nan,
            ),
            "GT production WHP [bar]": vfp_gt_df["prod WHP [bar]"].where(
                geothermal_active,
                np.nan,
            ),
            "GT injection BHP [bar]": vfp_gt_df["inj BHP [bar]"].where(
                geothermal_active,
                np.nan,
            ),
            "GT injection WHP [bar]": vfp_gt_df["inj WHP [bar]"].where(
                geothermal_active,
                np.nan,
            ),
        }
    )

    combined = dsa_pressure.merge(
        co2_pressure,
        on="Time [yr]",
        how="outer",
    ).merge(
        gt_pressure,
        on="Time [yr]",
        how="outer",
    )
    combined = combined.sort_values("Time [yr]").reset_index(drop=True)
    combined["DSA pressure [bar]"] = np.interp(
        combined["Time [yr]"].to_numpy(dtype=float),
        dsa_pressure["Time [yr]"].to_numpy(dtype=float),
        dsa_pressure["DSA pressure [bar]"].to_numpy(dtype=float),
        left=float(dsa_pressure["DSA pressure [bar]"].iloc[0]),
        right=float(dsa_pressure["DSA pressure [bar]"].iloc[-1]),
    )
    return combined[
        [
            "Time [yr]",
            "DSA pressure [bar]",
            "CO2 injection BHP [bar]",
            "CO2 injection WHP [bar]",
            "GT production BHP [bar]",
            "GT production WHP [bar]",
            "GT injection BHP [bar]",
            "GT injection WHP [bar]",
        ]
    ]


def _annual_relative_permeability(
    annual_ledger,
    vfp_co2_df,
    *,
    injection_start_year,
    initial_krw,
    initial_krg,
):
    """Sample effective Corey permeabilities at each calendar-year end."""
    years = annual_ledger["year"].to_numpy(dtype=int)
    time = vfp_co2_df["Time [yr]"].to_numpy(dtype=float)
    sample_time = np.clip(
        years.astype(float) - float(injection_start_year) + 1.0,
        0.0,
        float(time[-1]),
    )
    krw = np.interp(
        sample_time,
        time,
        vfp_co2_df["krw (-)"].to_numpy(dtype=float),
    )
    krg = np.interp(
        sample_time,
        time,
        vfp_co2_df["krg (-)"].to_numpy(dtype=float),
    )
    effective_saturation = np.interp(
        sample_time,
        time,
        vfp_co2_df["S_eff"].to_numpy(dtype=float),
    )
    before_injection = years < int(injection_start_year)
    krw[before_injection] = float(initial_krw)
    krg[before_injection] = float(initial_krg)
    effective_saturation[before_injection] = 0.0
    return pd.DataFrame(
        {
            "year": years,
            "krw (-)": krw,
            "krg (-)": krg,
            "effective_co2_saturation (-)": effective_saturation,
        }
    )


def _write_calculation_log(
    diagnostics,
    *,
    planned_injection_end_year,
    actual_injection_end_year,
    stop_reason,
):
    """Print and persist an ASCII annual CO2 injection/BHP diagnostic table."""
    active_quantities = diagnostics.loc[
        diagnostics["co2_injected_t"] > 0.0,
        "co2_injected_t",
    ].to_numpy(dtype=float)
    quantities_constant = bool(
        active_quantities.size > 0
        and np.allclose(
            active_quantities,
            active_quantities[0],
            rtol=1e-9,
            atol=1e-6,
        )
    )
    lines = [
        "ANNUAL CO2 INJECTION DEBUG",
        "year | CO2_inj_t | CO2_BHP_bar | avg_DSA_pressure_bar",
    ]
    for row in diagnostics.itertuples(index=False):
        bhp_text = (
            "-"
            if not np.isfinite(row.co2_injection_bhp_end_bar)
            else f"{row.co2_injection_bhp_end_bar:.1f}"
        )
        lines.append(
            f"{int(row.year):04d} | {row.co2_injected_t:.0f} | {bhp_text} | "
            f"{row.average_dsa_pressure_bar:.1f}"
        )
    lines.extend(
        [
            "",
            "result_active_year_CO2_quantity_constant = "
            f"{'yes' if quantities_constant else 'no'}",
            f"planned_injection_end_year = {int(planned_injection_end_year)}",
            "actual_injection_end_year = "
            + (
                "none"
                if actual_injection_end_year is None
                else str(int(actual_injection_end_year))
            ),
            f"injection_stop_reason = {stop_reason or 'planned end'}",
        ]
    )
    report = "\n".join(lines) + "\n"
    report = unicodedata.normalize("NFKD", report).encode(
        "ascii", errors="ignore"
    ).decode("ascii")
    print("\n" + report, end="", flush=True)
    try:
        CALCULATION_LOG_PATH.write_text(report, encoding="ascii")
    except OSError as exc:
        print(
            f"WARNING: calculation.log could not be written: {exc}",
            flush=True,
        )


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
        transport = Transport(inputs)

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
        if np.allclose(co2_stored, 0.0):
            effective_co2_saturation = np.zeros_like(co2_stored)
        else:
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
        co2_relative_permeability = [
            mbalance.kr_Corey(s_co2=float(saturation))
            for saturation in vfp_co2_df["S_eff"].to_numpy(dtype=float)
        ]
        vfp_co2_df["krw (-)"] = [
            permeability[0] for permeability in co2_relative_permeability
        ]
        vfp_co2_df["krg (-)"] = [
            permeability[1] for permeability in co2_relative_permeability
        ]
        # Keep the legacy name numerically consistent with the explicit krg
        # column used by annual results.
        vfp_co2_df["kr_co2"] = vfp_co2_df["krg (-)"]

        co2_injection_well = VFP(inputs, fluid_props)
        co2_injection_well.rw = inputs.rw_co2
        co2_injection_well.h_ref = inputs.h_ref_co2
        co2_injection_power = Power(inputs, fluid_props)
        co2_vfp_temperature_c = 20.0
        co2_whp_values = []
        co2_power_values = []
        co2_bhp_density_values = []
        co2_whp_density_values = []

        for bhp in vfp_co2_df["BHP [bar]"].to_numpy():
            co2_whp_values.append(
                co2_injection_well.calculate_dp(
                    fluid="CO2",
                    bhp=bhp,
                    T_C=co2_vfp_temperature_c,
                )
            )
            co2_bhp_density_values.append(
                fluid_props.get_density(
                    "CO2",
                    float(bhp) * 1e5,
                    co2_vfp_temperature_c + 273.15,
                )
            )
            co2_whp_density_values.append(
                fluid_props.get_density(
                    "CO2",
                    float(co2_whp_values[-1]) * 1e5,
                    co2_vfp_temperature_c + 273.15,
                )
            )
            co2_power_values.append(
                co2_injection_power.calculate_compression_power(
                    p_out_bar=co2_whp_values[-1]
                )
            )

        vfp_co2_df["CO2 WHP [bar]"] = co2_whp_values
        vfp_co2_df["CO2 comp. P [kW]"] = co2_power_values
        vfp_co2_df["CO2 VFP density at BHP [kg/m3]"] = co2_bhp_density_values
        vfp_co2_df["CO2 VFP density at WHP [kg/m3]"] = co2_whp_density_values

        planned_injection_duration = float(
            inputs.ccs_injection_end_year
            - inputs.ccs_injection_start_year
            + 1
        )
        geomechanical_injection_duration = min(
            float(mbal_df["Time, yr"].iloc[-1]),
            float(vfp_co2_df["Time [yr]"].iloc[-1]),
        )
        maximum_engineering_mass_t = float(
            mbal_df["m_CO2, Mt"].iloc[-1] * 1_000_000.0
        )
        if inputs.storage_capacity <= maximum_engineering_mass_t:
            capacity_injection_duration = float(
                np.interp(
                    inputs.storage_capacity / 1_000_000.0,
                    mbal_df["m_CO2, Mt"].to_numpy(dtype=float),
                    mbal_df["Time, yr"].to_numpy(dtype=float),
                )
            )
        else:
            capacity_injection_duration = float("inf")
        engineering_injection_duration = min(
            geomechanical_injection_duration,
            capacity_injection_duration,
        )
        injection_stop_reason = None
        injection_stop_note = None
        if engineering_injection_duration < planned_injection_duration:
            if capacity_injection_duration <= geomechanical_injection_duration:
                injection_stop_reason = "dosegnut nazivni kapacitet skladišta"
                injection_stop_note = (
                    "Utiskivanje je završilo prije planirane godine jer je "
                    "dosegnut nazivni kapacitet skladišta od "
                    f"{inputs.storage_capacity:,.0f} t CO2."
                )
            else:
                injection_stop_reason = "dosegnuta geomehanička granica tlaka"
                injection_stop_note = (
                    "Utiskivanje je završilo prije planirane godine jer bi sljedeći "
                    "tlačni korak prešao dopušteni tlak frakturiranja pokrovnih "
                    f"naslaga od {inputs.p_max:.2f} bar."
                )

        injection_active_elapsed_years = min(
            planned_injection_duration,
            engineering_injection_duration,
        )
        operational_mbal_df = _clip_time_series(
            mbal_df,
            "Time, yr",
            injection_active_elapsed_years,
        )
        operational_vfp_co2_df = _clip_time_series(
            vfp_co2_df,
            "Time [yr]",
            injection_active_elapsed_years,
        )

        planned_geothermal_duration = float(
            inputs.geothermal_operation_end_year
            - inputs.ccs_injection_start_year
            + 1
        )
        post_injection_pressure_assumption = None
        if planned_geothermal_duration > injection_active_elapsed_years:
            post_injection_pressure_assumption = (
                "Nakon prestanka utiskivanja CO2 tlak ležišta drži se "
                "konstantnim jer model pretpostavlja jednaku proizvodnju i "
                "ponovno utiskivanje geotermalne vode."
            )
        gt_support_df = _extend_constant_state(
            operational_mbal_df,
            "Time, yr",
            planned_geothermal_duration,
        )

        geothermal_production_ipr = Geothermal(inputs, fluid_props)
        geothermal_production_ipr.rw = inputs.rw_geothermal_production
        geothermal_injection_ipr = Geothermal(inputs, fluid_props)
        geothermal_injection_ipr.rw = inputs.rw_geothermal_injection
        geothermal_mass_flow = []
        geothermal_reservoir_flow = []
        geothermal_density = []
        geothermal_injection_bhp = []
        geothermal_production_bhp = []

        for pressure in gt_support_df["DSA pressure, bar"].to_numpy():
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

        # Determine whether the candidate geothermal flow can reach the ORC
        # inlet. If its calculated flowing WHP is not above the configured
        # ORC outlet pressure, the complete GT loop is off: no production, no
        # reinjection and no pump/ORC power. Re-evaluate after the thermal
        # profile changes so a later temperature decline cannot leave a pump
        # running while ORC power is zero.
        geothermal_operability_well = VFP(inputs, fluid_props)
        geothermal_operability_well.rw = inputs.rw_geothermal_production
        geothermal_operability_well.h_ref = inputs.h_ref_geothermal_production
        potential_geothermal_mass_flow = np.asarray(
            geothermal_mass_flow, dtype=float
        )
        potential_geothermal_reservoir_flow = np.asarray(
            geothermal_reservoir_flow, dtype=float
        )
        potential_geothermal_injection_bhp = np.asarray(
            geothermal_injection_bhp, dtype=float
        )
        geothermal_operating = np.ones(
            potential_geothermal_mass_flow.size, dtype=bool
        )
        geothermal = Geothermal(inputs, fluid_props)
        for _ in range(10):
            geothermal_mass_flow = np.where(
                geothermal_operating,
                potential_geothermal_mass_flow,
                0.0,
            ).tolist()
            geothermal_reservoir_flow = np.where(
                geothermal_operating,
                potential_geothermal_reservoir_flow,
                0.0,
            ).tolist()
            geothermal_injection_bhp = np.where(
                geothermal_operating,
                potential_geothermal_injection_bhp,
                np.nan,
            ).tolist()

            gt_support_df["m_dot geothermal [kg/s]"] = geothermal_mass_flow
            gt_support_df["q geothermal [rm3/d]"] = geothermal_reservoir_flow
            gt_support_df["rho geoth. [kg/m3]"] = geothermal_density
            gt_support_df["gt bhp_inj [bar]"] = geothermal_injection_bhp

            doublet_df, gt_info = geothermal.calculate_unsteady_production(
                mbal_df=gt_support_df
            )
            production_temperature = doublet_df["temperature, °C"].values
            potential_production_whp = np.asarray(
                [
                    geothermal_operability_well.calculate_dp(
                        fluid="H2O",
                        bhp=geothermal_production_bhp[index],
                        m_dot=potential_geothermal_mass_flow[index],
                        T_C=production_temperature[index],
                    )
                    for index in range(
                        potential_geothermal_mass_flow.size
                    )
                ],
                dtype=float,
            )
            # Conservative latch prevents an ON/OFF thermal oscillation at a
            # marginal WHP: once a time point fails the flowing-WHP check, it
            # remains off for this scenario evaluation. Later time points are
            # still evaluated independently and may operate as pressure rises.
            next_operating = geothermal_operating & (
                potential_production_whp > float(inputs.p_out)
            )
            if np.array_equal(next_operating, geothermal_operating):
                break
            geothermal_operating = next_operating
        else:
            raise RuntimeError(
                "GT status rada nije konvergirao nakon provjere proizvodnog WHP-a."
            )

        geothermal_power = Power(inputs, fluid_props)
        geothermal_production_well = VFP(inputs, fluid_props)
        geothermal_production_well.rw = inputs.rw_geothermal_production
        geothermal_production_well.h_ref = inputs.h_ref_geothermal_production
        geothermal_injection_well = VFP(inputs, fluid_props)
        geothermal_injection_well.rw = inputs.rw_geothermal_injection
        geothermal_injection_well.h_ref = inputs.h_ref_geothermal_injection
        production_whp = []
        injection_whp = []
        production_average_velocity = []
        injection_average_velocity = []
        orc_power = []
        pump_power = []

        for index, injection_bhp in enumerate(geothermal_injection_bhp):
            if not geothermal_operating[index]:
                production_whp.append(np.nan)
                injection_whp.append(np.nan)
                production_average_velocity.append(0.0)
                injection_average_velocity.append(0.0)
                pump_power.append(0.0)
                orc_power.append(0.0)
                continue

            production_pressure, production_diagnostics = (
                geothermal_production_well.calculate_dp(
                    fluid="H2O",
                    bhp=geothermal_production_bhp[index],
                    m_dot=geothermal_mass_flow[index],
                    T_C=production_temperature[index],
                    return_diagnostics=True,
                )
            )
            injection_pressure, injection_diagnostics = (
                geothermal_injection_well.calculate_dp(
                    fluid="H2O",
                    bhp=injection_bhp,
                    m_dot=geothermal_mass_flow[index],
                    T_C=inputs.t_out,
                    return_diagnostics=True,
                )
            )
            production_whp.append(production_pressure)
            injection_whp.append(injection_pressure)
            production_average_velocity.append(
                production_diagnostics["average_velocity_m_s"]
            )
            injection_average_velocity.append(
                injection_diagnostics["average_velocity_m_s"]
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
                "Time [yr]": gt_support_df["Time, yr"].to_numpy(),
                "m_dot, kg/s": geothermal_mass_flow,
                "q geothermal [rm3/d]": geothermal_reservoir_flow,
                "prod t, °C": production_temperature,
                "prod BHP [bar]": geothermal_production_bhp,
                "inj BHP [bar]": geothermal_injection_bhp,
                "potential prod WHP [bar]": potential_production_whp,
                "prod WHP [bar]": production_whp,
                "inj WHP [bar]": injection_whp,
                "avg prod velocity [m/s]": production_average_velocity,
                "avg inj velocity [m/s]": injection_average_velocity,
                "pump power, kW": pump_power,
                "ORC power, kW": orc_power,
                "geothermal active": geothermal_operating,
            }
        )
        vfp_gt_df["net power GT, kW"] = (
            vfp_gt_df["ORC power, kW"] - vfp_gt_df["pump power, kW"]
        )
        well_pressure_df = _build_well_pressure_table(
            gt_support_df,
            operational_vfp_co2_df,
            vfp_gt_df,
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

        annual_technical_ledger = build_annual_engineering_ledger(
            operational_mbal_df,
            operational_vfp_co2_df,
            vfp_gt_df,
            economics_start_year=inputs.economics_start_year,
            economics_end_year=inputs.economics_end_year,
            ccs_injection_start_year=inputs.ccs_injection_start_year,
            ccs_injection_end_year=inputs.ccs_injection_end_year,
            geothermal_operation_end_year=inputs.geothermal_operation_end_year,
            ccs_monitoring_end_year=inputs.ccs_monitoring_end_year,
            injection_stop_reason=injection_stop_reason,
            injection_stop_note=injection_stop_note,
        )
        active_injection_years = annual_technical_ledger.loc[
            annual_technical_ledger["co2_chain_t"] > 0.0,
            "year",
        ]
        actual_injection_end_year = (
            None
            if active_injection_years.empty
            else int(active_injection_years.max())
        )
        annual_injection_diagnostics_df = _annual_injection_diagnostics(
            annual_technical_ledger,
            operational_vfp_co2_df,
            operational_mbal_df,
            injection_start_year=inputs.ccs_injection_start_year,
            injection_active_elapsed_years=injection_active_elapsed_years,
        )
        annual_technical_ledger["co2_injection_bhp_end_bar"] = (
            annual_injection_diagnostics_df[
                "co2_injection_bhp_end_bar"
            ].to_numpy()
        )
        annual_relative_permeability_df = _annual_relative_permeability(
            annual_technical_ledger,
            operational_vfp_co2_df,
            injection_start_year=inputs.ccs_injection_start_year,
            initial_krw=mbalance.kr_Corey(s_co2=0.0)[0],
            initial_krg=mbalance.kr_Corey(s_co2=0.0)[1],
        )
        _write_calculation_log(
            annual_injection_diagnostics_df,
            planned_injection_end_year=inputs.ccs_injection_end_year,
            actual_injection_end_year=actual_injection_end_year,
            stop_reason=injection_stop_reason,
        )

        co2_price_df = generate_co2_price_path(inputs)
        co2_price_by_year = dict(
            zip(
                co2_price_df["Godina"].astype(int),
                co2_price_df["Cijena CO2 (EUR/tCO2)"].astype(float),
            )
        )
        economic_config = {
            key: value
            for key, value in inputs.params.items()
            if value is not None
        }
        economic_config["co2_price_eur_per_t"] = co2_price_by_year
        annual_cash_flow_df = CashFlowRunner(economic_config).run(
            annual_technical_ledger
        )
        economic_kpis = summarize_cash_flow(annual_cash_flow_df)

        engineering_geothermal_duration = min(
            float(vfp_gt_df["Time [yr]"].iloc[-1]),
            float(doublet_df["time, years"].iloc[-1]),
        )
        geothermal_active_elapsed_years = min(
            planned_geothermal_duration,
            engineering_geothermal_duration,
        )

        operational_mbal_df = _clip_time_series(
            gt_support_df,
            "Time, yr",
            injection_active_elapsed_years,
        )
        operational_vfp_gt_df = _clip_time_series(
            vfp_gt_df,
            "Time [yr]",
            geothermal_active_elapsed_years,
        )
        operational_doublet_df = _clip_time_series(
            doublet_df,
            "time, years",
            geothermal_active_elapsed_years,
        )

        operational_gt_info = dict(gt_info)
        if (
            gt_info.get("t_bt") is not None
            and float(gt_info["t_bt"]) > geothermal_active_elapsed_years
        ):
            operational_gt_info["breakthrough_reached"] = False

        operational_kpis = {
            "stored_co2_mt": float(
                annual_technical_ledger["co2_stored_cumulative_t"].max()
                / 1_000_000.0
            ),
            "final_storage_pressure_bar": float(
                operational_mbal_df["DSA pressure, bar"].iloc[-1]
            ),
            "max_co2_bhp_bar": float(
                operational_vfp_co2_df["BHP [bar]"].max()
            ),
            "compressor_nameplate_power_kw": float(
                annual_technical_ledger["compressor_peak_kw"].max()
            ),
            "final_geothermal_temperature_c": float(
                operational_vfp_gt_df["prod t, °C"].iloc[-1]
            ),
            "max_net_geothermal_power_kw": float(
                operational_vfp_gt_df["net power GT, kW"].max()
            ),
        }

        return {
            "mbal_df": operational_mbal_df,
            "vfp_co2_df": operational_vfp_co2_df,
            "doublet_df": operational_doublet_df,
            "vfp_gt_df": operational_vfp_gt_df,
            "gt_info": operational_gt_info,
            "relative_permeability_df": relative_permeability_df,
            "annual_relative_permeability_df": (
                annual_relative_permeability_df
            ),
            "annual_technical_ledger": annual_technical_ledger,
            "annual_injection_diagnostics_df": (
                annual_injection_diagnostics_df
            ),
            "well_pressure_df": well_pressure_df,
            "annual_cash_flow_df": annual_cash_flow_df,
            "economic_kpis": economic_kpis,
            "co2_price_df": co2_price_df,
            "operational_kpis": operational_kpis,
            "scenario_notes": {
                "injection_stop_reason": injection_stop_reason,
                "injection_stop_note": injection_stop_note,
                "injection_active_elapsed_years": (
                    injection_active_elapsed_years
                ),
                "planned_injection_end_year": inputs.ccs_injection_end_year,
                "actual_injection_end_year": actual_injection_end_year,
                "geomechanical_injection_coverage_years": (
                    geomechanical_injection_duration
                ),
                "capacity_injection_limit_years": (
                    capacity_injection_duration
                    if np.isfinite(capacity_injection_duration)
                    else None
                ),
                "geothermal_active_elapsed_years": (
                    geothermal_active_elapsed_years
                ),
                "post_injection_pressure_assumption": (
                    post_injection_pressure_assumption
                ),
                "component_availability": {
                    "co2_compressor": inputs.co2_compressor_availability,
                    "co2_injection_well": (
                        inputs.co2_injection_well_availability
                    ),
                    "orc": inputs.orc_availability,
                    "geothermal_production_well": (
                        inputs.geothermal_production_well_availability
                    ),
                    "geothermal_injection_well": (
                        inputs.geothermal_injection_well_availability
                    ),
                },
                "component_available_hours_per_year": (
                    inputs.component_available_hours_per_year
                ),
                "annualization": annual_technical_ledger.attrs.get(
                    "adapter_metadata",
                    {},
                ),
            },
            "transport_configuration": transport.as_dict(),
        }
