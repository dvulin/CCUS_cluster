import json
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np

from engineering.fluid_properties import FluidProperties
from engineering.wellbore import VFP
from inputs.scenario_sync import expand_storage_capacity_for_plan
from services.scenario_runner import ScenarioRunner


DEFAULT_INPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "inputs"
    / "examples"
    / "main_inputs.json"
)


class ScenarioRunnerIntegrationTests(unittest.TestCase):
    def test_default_scenario_connects_engineering_and_cash_flow(self):
        results = ScenarioRunner().run()
        ledger = results["annual_technical_ledger"].set_index("year")
        cash_flow = results["annual_cash_flow_df"].set_index("year")

        self.assertEqual(ledger.index.min(), 2027)
        self.assertEqual(ledger.index.max(), 2050)
        np.testing.assert_allclose(
            ledger.loc[2028:2040, "co2_chain_t"],
            716_000.0,
        )
        self.assertEqual(ledger.loc[2027, "co2_chain_t"], 0.0)
        self.assertTrue((ledger.loc[2041:, "co2_chain_t"] == 0.0).all())
        self.assertAlmostEqual(
            ledger["co2_stored_cumulative_t"].max(),
            9_308_000.0,
        )
        self.assertAlmostEqual(
            results["mbal_df"]["Time, yr"].iloc[-1],
            13.0,
        )
        self.assertAlmostEqual(
            results["vfp_gt_df"]["Time [yr]"].iloc[-1],
            23.0,
        )
        self.assertAlmostEqual(
            cash_flow.loc[2028, "capture_opex"],
            -17_900_000.0,
        )
        self.assertEqual(cash_flow.loc[2041, "capture_opex"], 0.0)
        self.assertIn("discounted_cash_flow", cash_flow.columns)
        self.assertIn("cumulative_npv", cash_flow.columns)
        self.assertIn("without_ccs_cash_flow", cash_flow.columns)
        self.assertAlmostEqual(
            results["economic_kpis"]["npv_eur"],
            cash_flow["discounted_cash_flow"].sum(),
        )
        self.assertLess(
            ledger.loc[2028, "orc_gross_mwh"],
            ledger.loc[2029, "orc_gross_mwh"],
        )
        self.assertTrue((cash_flow.loc[2041:, "electricity_revenue"] > 0.0).all())

        co2_well = results["vfp_co2_df"]
        bhp_density_column = "CO2 VFP density at BHP [kg/m3]"
        whp_density_column = "CO2 VFP density at WHP [kg/m3]"
        for density_column in (bhp_density_column, whp_density_column):
            self.assertIn(density_column, co2_well.columns)
            self.assertTrue(np.isfinite(co2_well[density_column]).all())
            self.assertTrue((co2_well[density_column] > 0.0).all())
        fluid_props = FluidProperties()
        expected_bhp_density = [
            fluid_props.get_density("CO2", pressure_bar * 1e5, 293.15)
            for pressure_bar in co2_well["BHP [bar]"].to_numpy(dtype=float)
        ]
        expected_whp_density = [
            fluid_props.get_density("CO2", pressure_bar * 1e5, 293.15)
            for pressure_bar in co2_well["CO2 WHP [bar]"].to_numpy(dtype=float)
        ]
        np.testing.assert_allclose(
            co2_well[bhp_density_column],
            expected_bhp_density,
            rtol=2e-6,
        )
        np.testing.assert_allclose(
            co2_well[whp_density_column],
            expected_whp_density,
            rtol=2e-6,
        )
        expected_without_ccs_2028 = -(
            716_000.0
            * float(
                results["co2_price_df"].set_index("Godina").loc[
                    2028, "Cijena CO2 (EUR/tCO2)"
                ]
            )
        )
        self.assertAlmostEqual(
            cash_flow.loc[2028, "without_ccs_cash_flow"],
            expected_without_ccs_2028,
        )
        self.assertIsNone(results["scenario_notes"]["injection_stop_note"])
        self.assertIsNotNone(
            results["scenario_notes"]["post_injection_pressure_assumption"]
        )
        post_injection_gt = results["vfp_gt_df"].loc[
            results["vfp_gt_df"]["Time [yr]"] >= 13.0
        ]
        np.testing.assert_allclose(
            post_injection_gt["prod BHP [bar]"],
            post_injection_gt["prod BHP [bar]"].iloc[0],
        )

        gt = results["vfp_gt_df"]
        gt_off = ~gt["geothermal active"]
        self.assertTrue(gt_off.any())
        np.testing.assert_allclose(gt.loc[gt_off, "m_dot, kg/s"], 0.0)
        np.testing.assert_allclose(
            gt.loc[gt_off, "q geothermal [rm3/d]"], 0.0
        )
        np.testing.assert_allclose(gt.loc[gt_off, "pump power, kW"], 0.0)
        np.testing.assert_allclose(gt.loc[gt_off, "ORC power, kW"], 0.0)
        np.testing.assert_allclose(gt.loc[gt_off, "net power GT, kW"], 0.0)
        np.testing.assert_allclose(
            gt.loc[gt_off, "avg prod velocity [m/s]"], 0.0
        )
        np.testing.assert_allclose(
            gt.loc[gt_off, "avg inj velocity [m/s]"], 0.0
        )
        self.assertTrue(gt.loc[gt_off, "inj BHP [bar]"].isna().all())

        gt_active = gt["geothermal active"]
        self.assertTrue(gt_active.any())
        self.assertTrue(
            (gt.loc[gt_active, "avg prod velocity [m/s]"] > 0.0).all()
        )
        self.assertTrue(
            (gt.loc[gt_active, "avg inj velocity [m/s]"] > 0.0).all()
        )

        annual_rel_perm = results["annual_relative_permeability_df"].set_index(
            "year"
        )
        self.assertEqual(
            annual_rel_perm.loc[2027, "effective_co2_saturation (-)"],
            0.0,
        )
        self.assertAlmostEqual(
            annual_rel_perm.loc[2027, "krw (-)"],
            self.default_data_value("krw_max"),
        )
        self.assertAlmostEqual(
            annual_rel_perm.loc[2027, "krg (-)"],
            self.default_data_value("krg_min"),
        )

        diagnostics = results["annual_injection_diagnostics_df"].set_index(
            "year"
        )
        self.assertEqual(diagnostics.loc[2027, "co2_injected_t"], 0.0)
        self.assertTrue(
            np.isnan(diagnostics.loc[2027, "co2_injection_bhp_end_bar"])
        )
        self.assertTrue(
            np.isfinite(diagnostics.loc[2028, "co2_injection_bhp_end_bar"])
        )
        self.assertIn("average_dsa_pressure_bar", diagnostics.columns)
        self.assertTrue(
            np.isfinite(diagnostics["average_dsa_pressure_bar"]).all()
        )
        self.assertAlmostEqual(
            diagnostics.loc[2027, "average_dsa_pressure_bar"],
            200.0,
        )
        self.assertAlmostEqual(
            diagnostics.loc[2028, "average_dsa_pressure_bar"],
            204.147956,
            places=5,
        )
        np.testing.assert_allclose(
            diagnostics.loc[2041:, "average_dsa_pressure_bar"],
            results["mbal_df"]["DSA pressure, bar"].iloc[-1],
        )

        pressure_columns = [
            "Time [yr]",
            "DSA pressure [bar]",
            "CO2 injection BHP [bar]",
            "CO2 injection WHP [bar]",
            "GT production BHP [bar]",
            "GT production WHP [bar]",
            "GT injection BHP [bar]",
            "GT injection WHP [bar]",
        ]
        well_pressure = results["well_pressure_df"]
        self.assertEqual(well_pressure.columns.tolist(), pressure_columns)
        self.assertFalse(well_pressure["Time [yr]"].duplicated().any())
        self.assertAlmostEqual(
            well_pressure["Time [yr]"].iloc[-1],
            results["vfp_gt_df"]["Time [yr]"].iloc[-1],
        )

        expected_dsa_pressure = np.interp(
            well_pressure["Time [yr]"].to_numpy(dtype=float),
            results["mbal_df"]["Time, yr"].to_numpy(dtype=float),
            results["mbal_df"]["DSA pressure, bar"].to_numpy(dtype=float),
        )
        np.testing.assert_allclose(
            well_pressure["DSA pressure [bar]"],
            expected_dsa_pressure,
        )
        after_injection = well_pressure["Time [yr]"] > float(
            results["vfp_co2_df"]["Time [yr]"].iloc[-1]
        )
        self.assertTrue(after_injection.any())
        self.assertTrue(
            well_pressure.loc[
                after_injection,
                [
                    "CO2 injection BHP [bar]",
                    "CO2 injection WHP [bar]",
                ],
            ]
            .isna()
            .all()
            .all()
        )
        np.testing.assert_allclose(
            well_pressure.loc[after_injection, "DSA pressure [bar]"],
            results["mbal_df"]["DSA pressure, bar"].iloc[-1],
        )

        pressure_with_gt_status = well_pressure.merge(
            results["vfp_gt_df"][["Time [yr]", "geothermal active"]],
            on="Time [yr]",
            how="inner",
        )
        inactive_gt_pressure = pressure_with_gt_status.loc[
            ~pressure_with_gt_status["geothermal active"],
            [
                "GT production BHP [bar]",
                "GT production WHP [bar]",
                "GT injection BHP [bar]",
                "GT injection WHP [bar]",
            ],
        ]
        self.assertFalse(inactive_gt_pressure.empty)
        self.assertTrue(inactive_gt_pressure.isna().all().all())
        active_gt_pressure = pressure_with_gt_status.loc[
            pressure_with_gt_status["geothermal active"],
            [
                "GT production BHP [bar]",
                "GT production WHP [bar]",
                "GT injection BHP [bar]",
                "GT injection WHP [bar]",
            ],
        ]
        self.assertFalse(active_gt_pressure.empty)
        self.assertTrue(np.isfinite(active_gt_pressure).all().all())

        log_bytes = (
            DEFAULT_INPUT_PATH.parents[2] / "calculation.log"
        ).read_bytes()
        log_bytes.decode("ascii")
        log_text = log_bytes.decode("ascii")
        log_lines = log_text.splitlines()
        self.assertEqual(
            log_lines[1],
            "year | CO2_inj_t | CO2_BHP_bar | avg_DSA_pressure_bar",
        )
        self.assertIn("2027 | 0 | - | 200.0", log_lines)
        self.assertIn("2028 | 716000 | 281.9 | 204.1", log_lines)
        self.assertIn(
            "result_active_year_CO2_quantity_constant = yes",
            log_lines,
        )
        self.assertNotIn("active_year_quantity_constant = yes", log_lines)
        log_rows = {
            int(parts[0]): parts
            for line in log_lines[2:]
            if len(parts := [part.strip() for part in line.split("|")]) == 4
        }
        for year, row in diagnostics.iterrows():
            logged = log_rows[int(year)]
            self.assertEqual(logged[1], f"{row.co2_injected_t:.0f}")
            expected_bhp = (
                "-"
                if not np.isfinite(row.co2_injection_bhp_end_bar)
                else f"{row.co2_injection_bhp_end_bar:.1f}"
            )
            self.assertEqual(logged[2], expected_bhp)
            self.assertEqual(
                logged[3],
                f"{row.average_dsa_pressure_bar:.1f}",
            )

    @staticmethod
    def default_data_value(key):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            return json.load(input_file)[key][0]

    def test_no_thermal_breakthrough_does_not_abort_scenario(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            scenario = json.load(input_file)
        scenario = deepcopy(scenario)
        scenario["d_doublet"][0] = 5000.0

        results = ScenarioRunner(scenario).run()

        self.assertFalse(results["gt_info"]["breakthrough_reached"])
        self.assertIsNone(results["gt_info"]["t_bt"])

    def test_role_specific_depths_reach_the_matching_vfp_instances(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            scenario = json.load(input_file)
        scenario = deepcopy(scenario)
        expected = {
            "co2": {"fluid": "CO2", "rw": 0.11, "h_ref": 1800.0},
            "gt_production": {
                "fluid": "H2O",
                "rw": 0.13,
                "h_ref": 2100.0,
            },
            "gt_injection": {
                "fluid": "H2O",
                "rw": 0.17,
                "h_ref": 2400.0,
            },
        }
        scenario["rw_co2"][0] = expected["co2"]["rw"]
        scenario["h_ref_co2"][0] = expected["co2"]["h_ref"]
        scenario["rw_geothermal_production"][0] = expected["gt_production"][
            "rw"
        ]
        scenario["h_ref_geothermal_production"][0] = expected[
            "gt_production"
        ]["h_ref"]
        scenario["rw_geothermal_injection"][0] = expected["gt_injection"]["rw"]
        scenario["h_ref_geothermal_injection"][0] = expected["gt_injection"][
            "h_ref"
        ]

        calls = []
        original_calculate_dp = VFP.calculate_dp

        def recording_calculate_dp(well, *args, **kwargs):
            fluid = kwargs.get("fluid", args[0] if args else None)
            calls.append((fluid, float(well.rw), float(well.h_ref)))
            return original_calculate_dp(well, *args, **kwargs)

        with patch.object(VFP, "calculate_dp", new=recording_calculate_dp):
            ScenarioRunner(scenario).run()

        for role, role_expected in expected.items():
            matching_depths = {
                h_ref
                for fluid, rw, h_ref in calls
                if fluid == role_expected["fluid"]
                and np.isclose(rw, role_expected["rw"])
            }
            with self.subTest(role=role):
                self.assertEqual(matching_depths, {role_expected["h_ref"]})

    def test_geomechanical_limit_stops_longer_planned_operation_with_note(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            scenario = json.load(input_file)
        scenario = deepcopy(scenario)
        for key in (
            "ccs_injection_end_year",
            "geothermal_operation_end_year",
            "ccs_monitoring_end_year",
            "economics_end_year",
        ):
            scenario[key][0] = 2100
        scenario["storage_capacity"][0] = 100_000_000.0

        results = ScenarioRunner(scenario).run()
        ledger = results["annual_technical_ledger"].set_index("year")
        note = results["scenario_notes"]["injection_stop_note"]

        self.assertIsNotNone(note)
        self.assertIn("tlak frakturiranja", note)
        self.assertTrue((ledger.loc[2062:, "co2_chain_t"] == 0.0).all())
        self.assertLessEqual(
            results["operational_kpis"]["final_storage_pressure_bar"],
            0.18 * 2000.0,
        )

    def test_nominal_storage_capacity_can_end_injection_early(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            scenario = json.load(input_file)
        scenario = deepcopy(scenario)
        scenario["storage_capacity"][0] = 1_432_000.0

        results = ScenarioRunner(scenario).run()
        ledger = results["annual_technical_ledger"].set_index("year")

        self.assertAlmostEqual(ledger["co2_chain_t"].sum(), 1_432_000.0)
        self.assertIn(
            "nazivni kapacitet skladišta",
            results["scenario_notes"]["injection_stop_note"],
        )

    def test_2045_plan_reports_direct_json_capacity_limit_and_ui_sync_runs(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            scenario = json.load(input_file)
        scenario = deepcopy(scenario)
        scenario["ccs_injection_end_year"][0] = 2045

        limited = ScenarioRunner(scenario).run()
        limited_ledger = limited["annual_technical_ledger"].set_index("year")
        self.assertEqual(limited["scenario_notes"]["planned_injection_end_year"], 2045)
        self.assertEqual(limited["scenario_notes"]["actual_injection_end_year"], 2040)
        self.assertTrue((limited_ledger.loc[2041:, "co2_chain_t"] == 0.0).all())
        self.assertIn(
            "nazivni kapacitet skladišta",
            limited["scenario_notes"]["injection_stop_note"],
        )

        adjustment = expand_storage_capacity_for_plan(scenario)
        self.assertEqual(adjustment, (9_308_000.0, 12_888_000.0))
        self.assertEqual(scenario["storage_capacity"][0], 12_888_000.0)
        extended = ScenarioRunner(scenario).run()
        extended_ledger = extended["annual_technical_ledger"].set_index("year")
        np.testing.assert_allclose(
            extended_ledger.loc[2028:2045, "co2_chain_t"],
            716_000.0,
        )
        self.assertEqual(
            extended["scenario_notes"]["actual_injection_end_year"],
            2045,
        )

    def test_marginal_gt_whp_does_not_oscillate_or_leave_pump_running(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            scenario = json.load(input_file)
        scenario = deepcopy(scenario)
        scenario["d_doublet"][0] = 50.0
        scenario["p_out"][0] = 22.0

        results = ScenarioRunner(scenario).run()
        gt = results["vfp_gt_df"]
        off = ~gt["geothermal active"]

        self.assertTrue(off.any())
        np.testing.assert_allclose(gt.loc[off, "m_dot, kg/s"], 0.0)
        np.testing.assert_allclose(
            gt.loc[off, "q geothermal [rm3/d]"], 0.0
        )
        np.testing.assert_allclose(gt.loc[off, "pump power, kW"], 0.0)
        np.testing.assert_allclose(gt.loc[off, "ORC power, kW"], 0.0)
        np.testing.assert_allclose(gt.loc[off, "net power GT, kW"], 0.0)
        np.testing.assert_allclose(
            gt.loc[off, "avg prod velocity [m/s]"], 0.0
        )
        np.testing.assert_allclose(
            gt.loc[off, "avg inj velocity [m/s]"], 0.0
        )

    def test_initial_pressure_at_geomechanical_limit_returns_zero_injection(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            scenario = json.load(input_file)
        scenario = deepcopy(scenario)
        scenario["fracture_pressure_gradient"][0] = 0.10

        results = ScenarioRunner(scenario).run()

        self.assertAlmostEqual(
            results["annual_technical_ledger"]["co2_chain_t"].sum(),
            0.0,
        )
        self.assertIn(
            "tlak frakturiranja",
            results["scenario_notes"]["injection_stop_note"],
        )


if __name__ == "__main__":
    unittest.main()
