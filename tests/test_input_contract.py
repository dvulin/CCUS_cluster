import json
import unittest
from copy import deepcopy
from pathlib import Path

from inputs import IOEndpoints


DEFAULT_INPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "inputs"
    / "examples"
    / "main_inputs.json"
)


class InputContractTests(unittest.TestCase):
    def setUp(self):
        with DEFAULT_INPUT_PATH.open(encoding="utf-8") as input_file:
            self.default_data = json.load(input_file)

    def data(self):
        return deepcopy(self.default_data)

    def test_default_input_obeys_integrated_contract(self):
        inputs = IOEndpoints(self.data())

        self.assertEqual(inputs.emitter_emissions_annual, 716_000.0)
        self.assertEqual(inputs.m_dot_annual, 716.0)
        self.assertEqual(inputs.transport_flow_rate, 716_000.0)
        self.assertEqual(inputs.storage_capacity, 9_308_000.0)
        self.assertEqual(inputs.eta, inputs.eta_orc)
        self.assertEqual(
            inputs.component_available_hours_per_year["co2_compressor"],
            8766.0,
        )
        self.assertEqual(
            inputs.p_max,
            inputs.fracture_pressure_gradient * inputs.h_top,
        )
        self.assertEqual(inputs.h_ref_co2, 2075.0)
        self.assertEqual(inputs.h_ref_geothermal_production, 2075.0)
        self.assertEqual(inputs.h_ref_geothermal_injection, 2075.0)
        self.assertEqual(inputs.h_ref, inputs.h_ref_co2)

    def test_annual_quantity_aliases_are_derived_when_omitted(self):
        data = self.data()
        del data["m_dot_annual"]
        del data["transport_flow_rate"]

        inputs = IOEndpoints(data)

        self.assertEqual(inputs.m_dot_annual, 716.0)
        self.assertEqual(inputs.transport_flow_rate, 716_000.0)

    def test_inconsistent_annual_quantities_are_rejected(self):
        for key, inconsistent_value in (
            ("m_dot_annual", 700.0),
            ("transport_flow_rate", 700_000.0),
        ):
            with self.subTest(key=key):
                data = self.data()
                data[key][0] = inconsistent_value
                with self.assertRaisesRegex(
                    ValueError,
                    "Nekonzistentna godišnja količina CO2",
                ):
                    IOEndpoints(data)

    def test_eta_orc_and_legacy_eta_are_compatible_aliases(self):
        without_legacy_eta = self.data()
        del without_legacy_eta["eta"]
        inputs = IOEndpoints(without_legacy_eta)
        self.assertEqual(inputs.eta, inputs.eta_orc)

        legacy_only = self.data()
        del legacy_only["eta_orc"]
        inputs = IOEndpoints(legacy_only)
        self.assertEqual(inputs.eta_orc, inputs.eta)

        inconsistent = self.data()
        inconsistent["eta"][0] = 0.19
        with self.assertRaisesRegex(ValueError, "Nekonzistentna ORC"):
            IOEndpoints(inconsistent)

    def test_role_specific_well_depths_survive_json_round_trip(self):
        data = self.data()
        expected_depths = {
            "h_ref_co2": 1800.0,
            "h_ref_geothermal_production": 2100.0,
            "h_ref_geothermal_injection": 2400.0,
        }
        for key, value in expected_depths.items():
            data[key][0] = value

        reloaded_inputs = IOEndpoints(
            json.loads(json.dumps(data, ensure_ascii=False))
        )

        for key, expected_value in expected_depths.items():
            self.assertEqual(getattr(reloaded_inputs, key), expected_value)
        self.assertEqual(reloaded_inputs.h_ref, expected_depths["h_ref_co2"])

    def test_legacy_shared_well_depth_populates_all_role_specific_depths(self):
        data = self.data()
        for key in (
            "h_ref_co2",
            "h_ref_geothermal_production",
            "h_ref_geothermal_injection",
        ):
            del data[key]
        data["h_ref"] = [2250.0, "m", "Legacy shared VFP depth"]

        inputs = IOEndpoints(data)

        self.assertEqual(inputs.h_ref_co2, 2250.0)
        self.assertEqual(inputs.h_ref_geothermal_production, 2250.0)
        self.assertEqual(inputs.h_ref_geothermal_injection, 2250.0)
        self.assertEqual(inputs.h_ref, 2250.0)

    def test_role_specific_well_depths_must_be_positive(self):
        for key in (
            "h_ref_co2",
            "h_ref_geothermal_production",
            "h_ref_geothermal_injection",
        ):
            with self.subTest(key=key):
                data = self.data()
                data[key][0] = 0.0
                with self.assertRaisesRegex(
                    ValueError,
                    rf"{key} mora biti veći od nule",
                ):
                    IOEndpoints(data)

    def test_orc_outlet_pressure_is_required_and_survives_json_round_trip(self):
        data = self.data()
        data["p_out"][0] = 17.25

        exported_active_inputs = json.dumps(data, ensure_ascii=False)
        reloaded_inputs = IOEndpoints(json.loads(exported_active_inputs))

        self.assertEqual(reloaded_inputs.p_out, 17.25)

        missing_p_out = self.data()
        del missing_p_out["p_out"]
        with self.assertRaisesRegex(ValueError, "Nedostaje p_out"):
            IOEndpoints(missing_p_out)

    def test_timeline_allows_equal_years(self):
        data = self.data()
        for key in (
            "economics_start_year",
            "economics_ccs_start_year",
            "ccs_injection_start_year",
            "ccs_injection_end_year",
            "geothermal_operation_end_year",
            "ccs_monitoring_end_year",
            "economics_end_year",
        ):
            data[key][0] = 2030

        inputs = IOEndpoints(data)

        self.assertEqual(inputs.ccs_injection_end_year, 2030)

    def test_invalid_timeline_is_rejected(self):
        invalid_updates = (
            {"economics_ccs_start_year": 2026},
            {"ccs_injection_end_year": 2027},
            {"geothermal_operation_end_year": 2039},
            {"ccs_monitoring_end_year": 2051},
        )
        for updates in invalid_updates:
            with self.subTest(updates=updates):
                data = self.data()
                for key, value in updates.items():
                    data[key][0] = value
                with self.assertRaisesRegex(ValueError, "Neispravna kronologija"):
                    IOEndpoints(data)

    def test_efficiencies_must_be_in_physical_range(self):
        for key, invalid_value in (
            ("eta_orc", 0.0),
            ("eta_gt_injection_pump", 1.01),
            ("eta_co2_compressor_isentropic", -0.1),
            ("eta_co2_dense_phase_pump", 2.0),
        ):
            with self.subTest(key=key):
                data = self.data()
                data[key][0] = invalid_value
                if key == "eta_orc":
                    data["eta"][0] = invalid_value
                with self.assertRaisesRegex(ValueError, "mora biti veći od 0"):
                    IOEndpoints(data)

    def test_availabilities_must_be_in_physical_range(self):
        for key, invalid_value in (
            ("co2_compressor_availability", 0.0),
            ("co2_injection_well_availability", 1.01),
            ("orc_availability", -0.1),
            ("geothermal_production_well_availability", 2.0),
            ("geothermal_injection_well_availability", 0.0),
        ):
            with self.subTest(key=key):
                data = self.data()
                data[key][0] = invalid_value
                with self.assertRaisesRegex(ValueError, "mora biti veći od 0"):
                    IOEndpoints(data)

    def test_cost_transport_and_geometry_constraints(self):
        invalid_updates = (
            ("compressor_capex", -1.0),
            ("geothermal_annual_opex", -1.0),
            ("monitoring_annual_cost_after_injection", -1.0),
            ("transport_distance_km", -1.0),
            ("pipeline_elbows_90_count", -1),
            ("pipeline_inner_diameter_m", 0.0),
            ("pipeline_roughness_m", 0.30),
            ("economics_interest_rate", -0.01),
            ("economics_inflation_rate", -0.01),
        )
        for key, value in invalid_updates:
            with self.subTest(key=key):
                data = self.data()
                data[key][0] = value
                with self.assertRaises(ValueError):
                    IOEndpoints(data)

        invalid_mode = self.data()
        invalid_mode["transport_mode"][0] = "ship"
        with self.assertRaisesRegex(ValueError, "transport_mode"):
            IOEndpoints(invalid_mode)

        for required_cost in (
            "emitter_capex",
            "emitter_opex_per_ton",
            "storage_capex",
            "storage_opex_per_ton",
        ):
            with self.subTest(required_cost=required_cost):
                data = self.data()
                del data[required_cost]
                with self.assertRaisesRegex(ValueError, "Nedostaje"):
                    IOEndpoints(data)

    def test_initial_pressure_cannot_exceed_geomechanical_limit(self):
        data = self.data()
        data["p_ref"][0] = 400.0

        with self.assertRaisesRegex(ValueError, "Početni tlak ležišta"):
            IOEndpoints(data)

    def test_pressure_step_uses_json_default_and_enforces_minimum(self):
        inputs = IOEndpoints(self.data())
        self.assertEqual(inputs.dp, self.default_data["dp"][0])

        minimum = self.data()
        minimum["dp"][0] = 0.5
        self.assertEqual(IOEndpoints(minimum).dp, 0.5)

        below_minimum = self.data()
        below_minimum["dp"][0] = 0.49
        with self.assertRaisesRegex(ValueError, "najmanje 0,5 bar"):
            IOEndpoints(below_minimum)

    def test_pipeline_does_not_require_road_or_rail_opex(self):
        data = self.data()
        del data["transport_opex_eur_per_tkm"]

        inputs = IOEndpoints(data)

        self.assertIsNone(inputs.transport_opex_eur_per_tkm)

    def test_road_and_rail_transport_do_not_require_pipeline_geometry(self):
        for mode in ("truck", "rail"):
            with self.subTest(mode=mode):
                data = self.data()
                data["transport_mode"][0] = mode
                for key in (
                    "pipeline_inner_diameter_m",
                    "pipeline_roughness_m",
                    "pipeline_elbows_90_count",
                    "pipeline_elbows_45_count",
                    "pipeline_elbows_30_count",
                    "transport_opex_per_ton",
                ):
                    del data[key]

                inputs = IOEndpoints(data)

                self.assertEqual(inputs.transport_mode, mode)


if __name__ == "__main__":
    unittest.main()
