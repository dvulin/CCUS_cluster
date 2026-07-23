"""Runnable Matplotlib client for the existing engineering scenario."""

import matplotlib.pyplot as plt

from outputs import Visualization
from services import ScenarioRunner


def main():
    """Run the engineering scenario and render the existing visualizations."""
    results = ScenarioRunner().run()
    mbal_df = results["mbal_df"]
    vfp_co2_df = results["vfp_co2_df"]
    doublet_df = results["doublet_df"]
    vfp_gt_df = results["vfp_gt_df"]

    visualization = Visualization()
    visualization.s_eff_vs_co2_stored_kr_co2(vfp_co2_df, mbal_df)
    visualization.time_vs_CO2_stored_vs_bhp_vs_whp(mbal_df, vfp_co2_df)
    visualization.time_vs_power_vs_bhp_vs_pDSA(mbal_df, vfp_co2_df)

    doublet_df.plot(
        x="time, years",
        xlabel="vrijeme, godine",
        y="temperature, °C",
        ylabel="proizvodna temperatura, °C",
        ylim=(0, 200),
    )
    plt.show()

    visualization.time_vs_geothermal_flow_temperature(mbal_df, vfp_gt_df)
    visualization.time_vs_geothermal_co2_bhp_whp_comparison(
        vfp_gt_df, vfp_co2_df
    )
    visualization.time_vs_power(vfp_gt_df, vfp_co2_df)


if __name__ == "__main__":
    main()
