import json
from io import BytesIO
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from outputs import build_results_excel, build_results_json
from services.scenario_runner import ScenarioRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "inputs" / "examples" / "main_inputs.json"


class ResultExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.active_inputs = json.loads(DEFAULT_INPUT_PATH.read_text(encoding="utf-8"))
        cls.results = ScenarioRunner(cls.active_inputs).run()

    def test_json_contains_inputs_tables_summaries_and_strict_values(self):
        exported = build_results_json(self.results, self.active_inputs)
        payload = json.loads(exported)

        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(
            payload["active_inputs"]["emitter_emissions_annual"][0],
            716_000.0,
        )
        annual_ledger = payload["results"]["annual_technical_ledger"]
        self.assertEqual(
            annual_ledger["columns"],
            list(self.results["annual_technical_ledger"].columns),
        )
        self.assertEqual(
            len(annual_ledger["records"]),
            len(self.results["annual_technical_ledger"]),
        )
        self.assertIn("adapter_metadata", annual_ledger["attrs"])
        self.assertIn("operational_kpis", payload["results"])
        self.assertIn("economic_kpis", payload["results"])
        self.assertIn("scenario_notes", payload["results"])
        self.assertIn("transport_configuration", payload["results"])
        well_pressures = payload["results"]["well_pressure_df"]
        self.assertEqual(
            well_pressures["columns"],
            list(self.results["well_pressure_df"].columns),
        )
        co2_well_columns = payload["results"]["vfp_co2_df"]["columns"]
        self.assertIn("CO2 VFP density at BHP [kg/m3]", co2_well_columns)
        self.assertIn("CO2 VFP density at WHP [kg/m3]", co2_well_columns)

    def test_json_replaces_non_finite_numbers_with_null(self):
        exported = build_results_json(
            {
                "frame": pd.DataFrame(
                    {"value": [np.nan, np.inf, -np.inf, np.float64(2.5)]}
                ),
                "summary": {"missing": np.nan},
            }
        )
        payload = json.loads(exported)

        self.assertEqual(
            [row["value"] for row in payload["results"]["frame"]["records"]],
            [None, None, None, 2.5],
        )
        self.assertIsNone(payload["results"]["summary"]["missing"])

    def test_excel_is_readable_and_contains_every_result_table(self):
        exported = build_results_excel(self.results, self.active_inputs)
        self.assertTrue(exported.startswith(b"PK"))

        workbook = pd.ExcelFile(BytesIO(exported), engine="openpyxl")
        expected_sheets = {
            "inputs",
            "summary",
            "annual_technical",
            "annual_cash_flow",
            "storage",
            "co2_well",
            "geothermal",
            "well_pressures",
            "thermal_front",
            "relative_permeability",
            "annual_rel_perm",
            "annual_injection_debug",
            "co2_price",
        }
        self.assertEqual(set(workbook.sheet_names), expected_sheets)

        exported_ledger = pd.read_excel(
            workbook,
            sheet_name="annual_technical",
        )
        self.assertEqual(len(exported_ledger), len(self.results["annual_technical_ledger"]))
        self.assertEqual(
            list(exported_ledger.columns),
            list(self.results["annual_technical_ledger"].columns),
        )

        exported_well_pressures = pd.read_excel(
            workbook,
            sheet_name="well_pressures",
        )
        self.assertEqual(
            len(exported_well_pressures),
            len(self.results["well_pressure_df"]),
        )
        self.assertEqual(
            list(exported_well_pressures.columns),
            list(self.results["well_pressure_df"].columns),
        )

        exported_co2_well = pd.read_excel(workbook, sheet_name="co2_well")
        self.assertIn(
            "CO2 VFP density at BHP [kg/m3]",
            exported_co2_well.columns,
        )
        self.assertIn(
            "CO2 VFP density at WHP [kg/m3]",
            exported_co2_well.columns,
        )

        exported_inputs = pd.read_excel(workbook, sheet_name="inputs")
        emitter_row = exported_inputs.loc[
            exported_inputs["parameter"] == "emitter_emissions_annual"
        ].iloc[0]
        self.assertEqual(float(emitter_row["value"]), 716_000.0)

        exported_summary = pd.read_excel(workbook, sheet_name="summary")
        self.assertIn("operational_kpis", set(exported_summary["section"]))
        self.assertIn("economic_kpis", set(exported_summary["section"]))
        self.assertIn("scenario_notes", set(exported_summary["section"]))

    def test_export_requires_scenario_result_mapping(self):
        with self.assertRaisesRegex(TypeError, "mapiranje"):
            build_results_json(["not", "a", "mapping"])
        with self.assertRaisesRegex(TypeError, "mapiranje"):
            build_results_excel(["not", "a", "mapping"])


if __name__ == "__main__":
    unittest.main()
