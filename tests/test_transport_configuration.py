import unittest
from pathlib import Path

from engineering.pipeline import Pipeline
from engineering.transport import Transport
from inputs import IOEndpoints


DEFAULT_INPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "inputs"
    / "examples"
    / "main_inputs.json"
)


class TransportConfigurationTests(unittest.TestCase):
    def test_default_pipeline_configuration_is_exposed(self):
        transport = Transport(IOEndpoints(DEFAULT_INPUT_PATH))
        configuration = transport.as_dict()

        self.assertEqual(configuration["mode"], "pipeline")
        self.assertEqual(configuration["annual_co2_t"], 716_000.0)
        self.assertEqual(configuration["distance_km"], 50.0)
        self.assertEqual(configuration["pipeline_inner_diameter_m"], 0.30)
        self.assertEqual(configuration["pipeline_elbows_90_count"], 0)

    def test_pressure_drop_waits_for_equation_approval(self):
        transport = Transport(IOEndpoints(DEFAULT_INPUT_PATH))

        with self.assertRaisesRegex(NotImplementedError, "potrebno je posebno"):
            transport.calculate_pipeline_pressure_drop()

        pipeline = Pipeline(IOEndpoints(DEFAULT_INPUT_PATH))
        with self.assertRaises(NotImplementedError):
            pipeline.calculate_pressure_drop()


if __name__ == "__main__":
    unittest.main()
