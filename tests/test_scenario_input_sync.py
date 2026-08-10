import unittest

from inputs.scenario_sync import (
    expand_storage_capacity_for_plan,
    required_storage_capacity_t,
)


class ScenarioInputSyncTests(unittest.TestCase):
    def test_required_capacity_includes_start_and_end_year(self):
        self.assertEqual(
            required_storage_capacity_t(716_000.0, 2028, 2045),
            12_888_000.0,
        )

    def test_plan_expands_but_never_shrinks_capacity(self):
        inputs = {
            "emitter_emissions_annual": [716_000.0],
            "ccs_injection_start_year": [2028],
            "ccs_injection_end_year": [2045],
            "storage_capacity": [9_308_000.0],
        }

        self.assertEqual(
            expand_storage_capacity_for_plan(inputs),
            (9_308_000.0, 12_888_000.0),
        )
        self.assertEqual(inputs["storage_capacity"][0], 12_888_000.0)

        inputs["ccs_injection_end_year"][0] = 2040
        self.assertIsNone(expand_storage_capacity_for_plan(inputs))
        self.assertEqual(inputs["storage_capacity"][0], 12_888_000.0)


if __name__ == "__main__":
    unittest.main()
