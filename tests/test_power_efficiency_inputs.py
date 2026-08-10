import unittest
from types import SimpleNamespace

from engineering.power import Power


class ConstantFluidProperties:
    def get_enthalpy(self, fluid, p, T):
        return T * 1000.0

    def get_density(self, fluid, p, T):
        return 1000.0

    def get_Tc(self, fluid):
        return 250.0

    def get_molar_mass(self, fluid):
        return 0.044

    def get_specific_heat(self, fluid, p, T, parameter):
        return 1000.0 if parameter == "CP0MASS" else 750.0

    def get_compressibility_factor(self, fluid, p, T):
        return 1.0


def _inputs(**overrides):
    values = {
        "m_dot": 10.0,
        "t_comp_in": 20.0,
        "p_comp_in": 25.0,
        "eta_orc": 0.20,
        "eta_gt_injection_pump": 0.90,
        "eta_co2_compressor_isentropic": 0.75,
        "eta_co2_dense_phase_pump": 0.90,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class PowerEfficiencyInputTests(unittest.TestCase):
    def test_orc_is_off_until_inlet_pressure_exceeds_outlet_pressure(self):
        power = Power(_inputs(), ConstantFluidProperties())

        self.assertEqual(
            power.calculate_ORC_power(
                m_dot=10.0,
                p_in=5.0,
                p_out=5.0,
                t_in=100.0,
                t_out=40.0,
            ),
            0.0,
        )
        self.assertEqual(
            power.calculate_ORC_power(
                m_dot=10.0,
                p_in=4.0,
                p_out=5.0,
                t_in=100.0,
                t_out=40.0,
            ),
            0.0,
        )

    def test_device_efficiencies_are_read_from_inputs(self):
        fluid_properties = ConstantFluidProperties()
        reference = Power(_inputs(), fluid_properties)
        changed = Power(
            _inputs(
                eta_orc=0.10,
                eta_gt_injection_pump=0.45,
                eta_co2_compressor_isentropic=0.50,
            ),
            fluid_properties,
        )

        reference_orc = reference.calculate_ORC_power(
            m_dot=10.0,
            p_in=10.0,
            p_out=5.0,
            t_in=100.0,
            t_out=40.0,
        )
        changed_orc = changed.calculate_ORC_power(
            m_dot=10.0,
            p_in=10.0,
            p_out=5.0,
            t_in=100.0,
            t_out=40.0,
        )
        self.assertAlmostEqual(changed_orc, reference_orc / 2.0)

        reference_pump = reference.calculate_pump_power(
            fluid="H2O",
            m_dot=10.0,
            p_in_bar=10.0,
            p_out_bar=20.0,
            t_C=40.0,
        )
        changed_pump = changed.calculate_pump_power(
            fluid="H2O",
            m_dot=10.0,
            p_in_bar=10.0,
            p_out_bar=20.0,
            t_C=40.0,
        )
        self.assertAlmostEqual(changed_pump, reference_pump * 2.0)

        reference_compressor = reference.calculate_compression_power(
            p_out_bar=50.0
        )
        changed_compressor = changed.calculate_compression_power(
            p_out_bar=50.0
        )
        self.assertGreater(changed_compressor, reference_compressor)


if __name__ == "__main__":
    unittest.main()
