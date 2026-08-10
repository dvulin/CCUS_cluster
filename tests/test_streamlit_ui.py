import ast
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _source_function(function_name):
    """Load one pure helper from app.py without executing the Streamlit app."""
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(APP_PATH))
    function_node = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    isolated_module = ast.Module(body=[function_node], type_ignores=[])
    ast.fix_missing_locations(isolated_module)
    namespace = {}
    exec(compile(isolated_module, str(APP_PATH), "exec"), namespace)
    return namespace[function_name]


class StreamlitInputRangeTests(unittest.TestCase):
    def test_role_specific_depth_controls_round_trip_and_tab_name(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertIn("Ekonomika i energija", [tab.label for tab in app.tabs])
        self.assertNotIn("Ekonomika", [tab.label for tab in app.tabs])

        depth_controls = (
            (
                "Dubina utisne CO₂ bušotine (m)",
                "h_ref_co2",
                2101.0,
            ),
            (
                "Dubina proizvodne geotermalne bušotine (m)",
                "h_ref_geothermal_production",
                2202.0,
            ),
            (
                "Dubina utisne geotermalne bušotine (m)",
                "h_ref_geothermal_injection",
                2303.0,
            ),
        )
        for label, parameter, new_value in depth_controls:
            number_input = next(
                item for item in app.number_input if item.label == label
            )
            self.assertAlmostEqual(number_input.value, 2075.0)
            number_input.set_value(new_value)
            app.run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(
                app.session_state["active_scenario_inputs"][parameter][0],
                new_value,
            )

    def test_requested_vega_specs_are_interactive_and_not_matplotlib(self):
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("from matplotlib", source)
        self.assertNotIn("st.pyplot(", source)

        line_spec = _source_function("_zoomable_line_chart_spec")(
            x_title="Godina",
            y_title="Vrijednost",
            zoom_name="test_x_zoom",
            y_zoom_name="test_y_zoom",
            integer_x=True,
            interpolate="step-after",
        )
        self.assertEqual(line_spec["mark"]["type"], "line")
        self.assertEqual(line_spec["mark"]["interpolate"], "step-after")
        self.assertEqual(
            line_spec["encoding"]["x"]["type"],
            "quantitative",
        )
        self.assertEqual(line_spec["encoding"]["x"]["axis"]["format"], "d")
        self.assertEqual(line_spec["params"][0]["bind"], "scales")
        self.assertEqual(
            line_spec["params"][0]["select"]["encodings"],
            ["x"],
        )
        self.assertEqual(
            line_spec["params"][0]["select"]["zoom"],
            "wheel![!event.shiftKey]",
        )
        self.assertEqual(
            line_spec["params"][1]["select"]["encodings"],
            ["y"],
        )
        self.assertEqual(
            line_spec["params"][1]["select"]["zoom"],
            "wheel![event.shiftKey]",
        )

        compressor_spec = _source_function(
            "_compressor_density_chart_spec"
        )()
        self.assertEqual(len(compressor_spec["layer"]), 2)
        self.assertEqual(
            compressor_spec["resolve"]["scale"]["y"],
            "independent",
        )
        self.assertEqual(
            compressor_spec["layer"][0]["encoding"]["y"]["axis"]["orient"],
            "left",
        )
        self.assertEqual(
            compressor_spec["layer"][1]["encoding"]["y"]["axis"]["orient"],
            "right",
        )
        self.assertEqual(
            compressor_spec["layer"][0]["encoding"]["color"]["scale"]["domain"],
            ["P komp.", "ρ BHP", "ρ WHP"],
        )
        compressor_zoom = compressor_spec["layer"][0]["params"][0]
        self.assertEqual(compressor_zoom["bind"], "scales")
        self.assertEqual(
            compressor_zoom["select"]["encodings"],
            ["x"],
        )

    def test_requested_ranges_formats_and_storage_mt_round_trip(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
        self.assertEqual(list(app.exception), [])

        sliders = {slider.label: slider for slider in app.slider}
        expected_maximums = {
            "CAPEX kompresora CO₂ (mil. EUR)": 100.0,
            "Godišnji OPEX kompresora CO₂ (EUR/god)": 10_000_000.0,
            "CAPEX geotermalnog sustava (mil. EUR)": 1_000.0,
            "Godišnji OPEX geotermalnog sustava (EUR/god)": 100_000_000.0,
            "Godišnji monitoring tijekom utiskivanja (EUR/god)": 10_000_000.0,
            "Godišnji monitoring nakon utiskivanja (EUR/god)": 10_000_000.0,
            "CAPEX hvatanja (mil. EUR)": 10_000.0,
            "CAPEX transporta (mil. EUR)": 1_000.0,
            "CAPEX skladišta (mil. EUR)": 2_000.0,
            "Nazivni kapacitet skladišta (MtCO₂)": 10_000.0,
        }
        for label, expected_maximum in expected_maximums.items():
            self.assertIn(label, sliders)
            self.assertEqual(sliders[label].min, 0.0)
            self.assertEqual(sliders[label].max, expected_maximum)

        roughness = sliders["Apsolutna hrapavost cjevovoda (m)"]
        self.assertEqual(roughness.format, "%.7f")
        self.assertAlmostEqual(roughness.value, 0.000045)

        storage = sliders["Nazivni kapacitet skladišta (MtCO₂)"]
        self.assertEqual(storage.format, "%.2f")
        self.assertAlmostEqual(storage.value, 9.308)
        storage.set_value(12.34)
        app.run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.session_state["active_scenario_inputs"]["storage_capacity"][0],
            12_340_000.0,
        )
        storage_number = next(
            number
            for number in app.number_input
            if number.label == "Nazivni kapacitet skladišta (MtCO₂)"
        )
        self.assertAlmostEqual(storage_number.value, 12.34)

        capex_labels = (
            "CAPEX kompresora CO₂ (mil. EUR)",
            "CAPEX geotermalnog sustava (mil. EUR)",
            "CAPEX hvatanja (mil. EUR)",
            "CAPEX transporta (mil. EUR)",
            "CAPEX skladišta (mil. EUR)",
        )
        for capex_label in capex_labels:
            capex_slider = next(
                slider for slider in app.slider if slider.label == capex_label
            )
            self.assertEqual(capex_slider.format, "%.2f")

        compressor_capex = next(
            slider
            for slider in app.slider
            if slider.label == "CAPEX kompresora CO₂ (mil. EUR)"
        )
        compressor_capex.set_value(12.34)
        app.run()
        self.assertEqual(
            app.session_state["active_scenario_inputs"]["compressor_capex"][0],
            12_340_000.0,
        )

    def test_pipeline_elbow_controls_persist_only_integers(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
        self.assertEqual(list(app.exception), [])

        elbow_controls = (
            ("Broj koljena od 90°", "pipeline_elbows_90_count", 3),
            ("Broj koljena od 45°", "pipeline_elbows_45_count", 4),
            ("Broj koljena od 30°", "pipeline_elbows_30_count", 5),
        )
        for label, parameter, new_value in elbow_controls:
            slider = next(item for item in app.slider if item.label == label)
            self.assertEqual(slider.format, "%d")
            slider.set_value(new_value)
            app.run()
            stored_value = app.session_state["active_scenario_inputs"][parameter][0]
            self.assertIs(type(stored_value), int)
            self.assertEqual(stored_value, new_value)

    def test_default_run_renders_requested_energy_economics_ui_without_error(self):
        app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
        next(
            button for button in app.button if button.label == "Pokreni proračun"
        ).click()
        app.run(timeout=60)

        self.assertEqual(list(app.exception), [])
        co2_well = app.session_state["engineering_demo_results"]["vfp_co2_df"]
        self.assertIn("CO2 VFP density at BHP [kg/m3]", co2_well.columns)
        self.assertIn("CO2 VFP density at WHP [kg/m3]", co2_well.columns)
        tab_labels = [tab.label for tab in app.tabs]
        self.assertEqual(tab_labels.count("Ekonomika i energija"), 2)
        markdown_values = [element.value for element in app.markdown]
        self.assertIn("#### Prosječna godišnja snaga komponenti", markdown_values)
        self.assertIn(
            "#### Godišnji troškovi po komponentama i prihod od električne energije",
            markdown_values,
        )
        self.assertTrue(
            any(
                "obje gustoće izračunate su" in caption.value
                for caption in app.caption
            )
        )
        self.assertTrue(
            any("8766 sati" in caption.value for caption in app.caption)
        )

        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertIn("Izbjegnuti CO₂ rashod", metrics)
        self.assertIn("PV koristi i prihoda s CCS-om", metrics)
        total_labels = (
            "Ukupni trošak CCS-a",
            "Ukupni trošak geotermalnog sustava",
            "Ukupni trošak kupnje električne energije",
            "Sveukupni troškovi",
            "Prihod od električne energije",
        )
        for label in total_labels:
            self.assertIn(label, metrics)
            self.assertFalse(str(metrics[label]).startswith("-"))


if __name__ == "__main__":
    unittest.main()
