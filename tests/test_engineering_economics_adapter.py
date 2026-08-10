import unittest

import numpy as np
import pandas as pd

from services.engineering_economics_adapter import (
    LEDGER_COLUMNS,
    build_annual_engineering_ledger,
)


MWH_PER_KW_YEAR = 365.25 * 24 / 1000


def _engineering_frames(time, stored_mt, compressor_kw, orc_kw, pump_kw):
    return (
        pd.DataFrame({"Time, yr": time, "m_CO2, Mt": stored_mt}),
        pd.DataFrame(
            {"Time [yr]": time, "CO2 comp. P [kW]": compressor_kw}
        ),
        pd.DataFrame(
            {
                "Time [yr]": time,
                "ORC power, kW": orc_kw,
                "pump power, kW": pump_kw,
            }
        ),
    )


class EngineeringEconomicsAdapterTests(unittest.TestCase):
    def test_builds_confirmed_annual_ledger_and_lifecycle_flags(self):
        frames = _engineering_frames(
            time=[0.0, 1.0, 2.0, 3.0],
            stored_mt=[0.0, 1.0, 2.0, 3.0],
            compressor_kw=[100.0] * 4,
            orc_kw=[300.0] * 4,
            pump_kw=[50.0] * 4,
        )

        ledger = build_annual_engineering_ledger(
            *frames,
            economics_start_year=2028,
            economics_end_year=2033,
            ccs_injection_start_year=2030,
            ccs_injection_end_year=2031,
            geothermal_operation_end_year=2032,
            ccs_monitoring_end_year=2033,
            injection_stop_reason="planirani kraj",
            injection_stop_note="dosegnut ugovoreni rok",
        )

        self.assertEqual(list(ledger.columns), LEDGER_COLUMNS)
        self.assertEqual(
            ledger["year"].tolist(), [2028, 2029, 2030, 2031, 2032, 2033]
        )
        np.testing.assert_allclose(
            ledger["co2_chain_t"], [0.0, 0.0, 1e6, 1e6, 0.0, 0.0]
        )
        np.testing.assert_allclose(
            ledger["co2_stored_cumulative_t"],
            [0.0, 0.0, 1e6, 2e6, 2e6, 2e6],
        )
        np.testing.assert_allclose(
            ledger["orc_gross_mwh"],
            [0.0, 0.0] + [300 * MWH_PER_KW_YEAR] * 3 + [0.0],
        )
        np.testing.assert_allclose(
            ledger["gt_pump_mwh"],
            [0.0, 0.0] + [50 * MWH_PER_KW_YEAR] * 3 + [0.0],
        )
        np.testing.assert_allclose(
            ledger["co2_compressor_mwh"],
            [0.0, 0.0] + [100 * MWH_PER_KW_YEAR] * 2 + [0.0, 0.0],
        )
        np.testing.assert_allclose(
            ledger["electricity_export_mwh"],
            np.array([0, 0, 150, 150, 250, 0]) * MWH_PER_KW_YEAR,
        )
        np.testing.assert_allclose(ledger["electricity_import_mwh"], 0.0)
        np.testing.assert_allclose(
            ledger["compressor_peak_kw"], [0, 0, 100, 100, 0, 0]
        )
        self.assertEqual(
            ledger["injection_active"].tolist(),
            [False, False, True, True, False, False],
        )
        self.assertEqual(
            ledger["geothermal_active"].tolist(),
            [False, False, True, True, True, False],
        )
        self.assertEqual(
            ledger["monitoring_active"].tolist(),
            [False, False, True, True, True, True],
        )
        self.assertEqual(
            ledger.loc[3, "injection_stop_note"],
            "planirani kraj: dosegnut ugovoreni rok",
        )

    def test_integrates_export_and_import_on_each_side_of_zero_crossing(self):
        frames = _engineering_frames(
            time=[0.0, 1.0],
            stored_mt=[0.0, 1.0],
            compressor_kw=[100.0, 100.0],
            orc_kw=[0.0, 200.0],
            pump_kw=[0.0, 0.0],
        )

        ledger = build_annual_engineering_ledger(
            *frames,
            economics_start_year=2040,
            economics_end_year=2040,
            ccs_injection_start_year=2040,
            ccs_injection_end_year=2040,
            geothermal_operation_end_year=2040,
            ccs_monitoring_end_year=2040,
        )

        expected_triangle_mwh = 25.0 * MWH_PER_KW_YEAR
        self.assertAlmostEqual(
            ledger.loc[0, "electricity_export_mwh"], expected_triangle_mwh
        )
        self.assertAlmostEqual(
            ledger.loc[0, "electricity_import_mwh"], expected_triangle_mwh
        )
        self.assertAlmostEqual(
            ledger.loc[0, "orc_gross_mwh"], 100.0 * MWH_PER_KW_YEAR
        )

    def test_full_coverage_keeps_ledger_monitoring_and_gt_through_2100(self):
        frames = _engineering_frames(
            time=[0.0, 1.0, 19.0, 73.0],
            stored_mt=[0.0, 1.0, 19.0, 19.0],
            compressor_kw=[100.0] * 4,
            orc_kw=[300.0] * 4,
            pump_kw=[50.0] * 4,
        )

        ledger = build_annual_engineering_ledger(
            *frames,
            economics_start_year=2027,
            economics_end_year=2100,
            ccs_injection_start_year=2028,
            ccs_injection_end_year=2046,
            geothermal_operation_end_year=2100,
            ccs_monitoring_end_year=2100,
        ).set_index("year")

        self.assertEqual((ledger.index.min(), ledger.index.max()), (2027, 2100))
        self.assertEqual(len(ledger), 74)
        self.assertFalse(ledger.loc[2047:, "injection_active"].any())
        self.assertTrue(ledger.loc[2028:2100, "monitoring_active"].all())
        self.assertTrue(ledger.loc[2028:2100, "geothermal_active"].all())
        np.testing.assert_allclose(
            ledger.loc[2047:2100, "orc_gross_mwh"],
            300.0 * MWH_PER_KW_YEAR,
        )
        np.testing.assert_allclose(
            ledger.loc[2047:2100, "gt_pump_mwh"],
            50.0 * MWH_PER_KW_YEAR,
        )
        np.testing.assert_allclose(
            ledger.loc[2047:2100, "electricity_export_mwh"],
            250.0 * MWH_PER_KW_YEAR,
        )
        self.assertTrue(
            ledger.attrs["adapter_metadata"]["geothermal_coverage_complete"]
        )

    def test_annualizes_all_irregular_engineering_points(self):
        frames = _engineering_frames(
            time=[0.0, 0.25, 0.75, 1.25, 1.75, 2.0],
            stored_mt=[0.0, 0.2, 0.7, 1.5, 1.9, 2.2],
            compressor_kw=[0.0, 400.0, 0.0, 200.0, 0.0, 0.0],
            orc_kw=[0.0] * 6,
            pump_kw=[0.0] * 6,
        )

        ledger = build_annual_engineering_ledger(
            *frames,
            economics_start_year=2030,
            economics_end_year=2031,
            ccs_injection_start_year=2030,
            ccs_injection_end_year=2031,
            geothermal_operation_end_year=2031,
            ccs_monitoring_end_year=2031,
        )

        np.testing.assert_allclose(
            ledger["co2_chain_t"], [1_100_000.0, 1_100_000.0]
        )
        np.testing.assert_allclose(
            ledger["co2_compressor_mwh"],
            np.array([162.5, 87.5]) * MWH_PER_KW_YEAR,
        )
        np.testing.assert_allclose(
            ledger["electricity_import_mwh"],
            ledger["co2_compressor_mwh"],
        )
        np.testing.assert_allclose(
            ledger["compressor_peak_kw"], [400.0, 200.0]
        )

    def test_truncates_gt_at_engineering_coverage_and_records_note(self):
        frames = _engineering_frames(
            time=[0.0, 1.0, 1.5],
            stored_mt=[0.0, 1.0, 1.5],
            compressor_kw=[100.0, 100.0, 100.0],
            orc_kw=[300.0, 300.0, 300.0],
            pump_kw=[50.0, 50.0, 50.0],
        )

        ledger = build_annual_engineering_ledger(
            *frames,
            economics_start_year=2050,
            economics_end_year=2052,
            ccs_injection_start_year=2050,
            ccs_injection_end_year=2050,
            geothermal_operation_end_year=2052,
            ccs_monitoring_end_year=2052,
            geothermal_stop_reason="planirani kraj GT rada",
        )

        np.testing.assert_allclose(
            ledger["orc_gross_mwh"],
            np.array([300.0, 150.0, 0.0]) * MWH_PER_KW_YEAR,
        )
        self.assertEqual(
            ledger["geothermal_active"].tolist(), [True, True, False]
        )
        metadata = ledger.attrs["adapter_metadata"]
        self.assertFalse(metadata["geothermal_coverage_complete"])
        self.assertEqual(
            metadata["geothermal_stop_reason"], "planirani kraj GT rada"
        )
        self.assertTrue(
            any("nije ekstrapolirana" in note for note in metadata["coverage_notes"])
        )

    def test_rejects_invalid_lifecycle_and_missing_columns(self):
        frames = _engineering_frames(
            time=[0.0, 1.0],
            stored_mt=[0.0, 1.0],
            compressor_kw=[100.0, 100.0],
            orc_kw=[300.0, 300.0],
            pump_kw=[50.0, 50.0],
        )

        with self.assertRaisesRegex(ValueError, "Kraj utiskivanja"):
            build_annual_engineering_ledger(
                *frames,
                economics_start_year=2029,
                economics_end_year=2030,
                ccs_injection_start_year=2030,
                ccs_injection_end_year=2029,
                geothermal_operation_end_year=2030,
                ccs_monitoring_end_year=2030,
            )

        with self.assertRaisesRegex(ValueError, "geotermalnog sustava"):
            build_annual_engineering_ledger(
                *frames,
                economics_start_year=2030,
                economics_end_year=2031,
                ccs_injection_start_year=2030,
                ccs_injection_end_year=2031,
                geothermal_operation_end_year=2030,
                ccs_monitoring_end_year=2031,
            )

        with self.assertRaisesRegex(ValueError, "CCS monitoringa"):
            build_annual_engineering_ledger(
                *frames,
                economics_start_year=2030,
                economics_end_year=2031,
                ccs_injection_start_year=2030,
                ccs_injection_end_year=2031,
                geothermal_operation_end_year=2031,
                ccs_monitoring_end_year=2030,
            )

        bad_gt = frames[2].drop(columns="ORC power, kW")
        with self.assertRaisesRegex(ValueError, "ORC power, kW"):
            build_annual_engineering_ledger(
                frames[0],
                frames[1],
                bad_gt,
                economics_start_year=2030,
                economics_end_year=2030,
                ccs_injection_start_year=2030,
                ccs_injection_end_year=2030,
                geothermal_operation_end_year=2030,
                ccs_monitoring_end_year=2030,
            )


if __name__ == "__main__":
    unittest.main()
