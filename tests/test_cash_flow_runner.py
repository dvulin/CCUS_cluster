import unittest

import pandas as pd

from economics.cash_flow_runner import (
    COST_LINE_ITEM_COLUMNS,
    CASH_FLOW_COLUMNS,
    CashFlowInputError,
    CashFlowRunner,
    run_cash_flow,
    summarize_cash_flow,
)


def _ledger():
    return pd.DataFrame(
        {
            "year": [2028, 2029, 2030],
            "co2_chain_t": [100.0, 120.0, 0.0],
            "orc_gross_mwh": [50.0, 60.0, 40.0],
            "gt_pump_mwh": [10.0, 12.0, 8.0],
            "co2_compressor_mwh": [20.0, 24.0, 0.0],
            "electricity_export_mwh": [25.0, 30.0, 32.0],
            "electricity_import_mwh": [5.0, 6.0, 0.0],
            "injection_active": [True, True, False],
            "geothermal_active": [True, True, True],
            "monitoring_active": [True, True, True],
        }
    )


def _config():
    return {
        "capture": {
            "capex_eur": 1_000.0,
            "capex_year": 2028,
            "variable_opex_eur_per_t": 2.0,
            "fixed_opex_eur_per_year": 10.0,
        },
        "transport": {
            "capex_eur": 500.0,
            "capex_year": 2028,
            "variable_opex_eur_per_t": 1.0,
        },
        "compressor": {
            "capex_eur": 300.0,
            "capex_year": 2028,
            "variable_opex_eur_per_mwh": 2.0,
            "fixed_opex_eur_per_year": 5.0,
        },
        "storage": {
            "capex_eur": 400.0,
            "capex_year": 2028,
            "variable_opex_eur_per_t": 0.5,
            "fixed_opex_eur_per_year": 20.0,
        },
        "geothermal": {
            "capex_eur": 600.0,
            "capex_year": 2028,
            "variable_opex_eur_per_mwh": 3.0,
            "fixed_opex_eur_per_year": 30.0,
        },
        "monitoring_annual_cost_during_injection": 7.0,
        "monitoring_annual_cost_after_injection": 9.0,
        "electricity": {
            "sell_price_eur_per_mwh": 80.0,
            "buy_price_eur_per_mwh": 100.0,
        },
        "co2_value": {"value_eur_per_t": 50.0},
    }


class CashFlowRunnerTests(unittest.TestCase):
    def test_component_line_items_and_sign_convention(self):
        result = CashFlowRunner(_config()).run(_ledger())

        self.assertEqual(tuple(result.columns), CASH_FLOW_COLUMNS)
        first = result.iloc[0]
        expected = {
            "capture_capex": -1_000.0,
            "capture_opex": -210.0,
            "transport_capex": -500.0,
            "transport_opex": -100.0,
            "compressor_capex": -300.0,
            "compressor_opex": -45.0,
            "storage_capex": -400.0,
            "storage_opex": -70.0,
            "geothermal_capex": -600.0,
            "geothermal_opex": -180.0,
            "monitoring": -7.0,
            "electricity_revenue": 2_000.0,
            "electricity_purchase": -500.0,
            "co2_value": 5_000.0,
            "net_cash_flow": 3_088.0,
        }
        for line_item, expected_value in expected.items():
            with self.subTest(line_item=line_item):
                self.assertAlmostEqual(first[line_item], expected_value)

    def test_active_flags_control_fixed_opex_and_monitoring_continues(self):
        result = run_cash_flow(_ledger(), _config()).set_index("year")

        self.assertEqual(result.loc[2030, "capture_opex"], 0.0)
        self.assertEqual(result.loc[2030, "transport_opex"], 0.0)
        self.assertEqual(result.loc[2030, "compressor_opex"], 0.0)
        self.assertEqual(result.loc[2030, "storage_opex"], 0.0)
        self.assertEqual(result.loc[2030, "geothermal_opex"], -(40.0 * 3.0 + 30.0))
        self.assertEqual(result.loc[2030, "monitoring"], -9.0)

    def test_year_keyed_prices_and_capex_schedule(self):
        config = _config()
        config["capture"] = {
            "capex_schedule_eur": {2028: 400.0, 2029: 600.0},
            "variable_opex_eur_per_t": 0.0,
        }
        config["electricity"] = {
            "sell_price_eur_per_mwh": {2028: 80.0, 2029: 90.0, 2030: 100.0},
            "buy_price_eur_per_mwh": [100.0, 110.0, 120.0],
        }

        result = run_cash_flow(
            _ledger().to_dict(orient="list"), config
        ).set_index("year")

        self.assertEqual(result.loc[2028, "capture_capex"], -400.0)
        self.assertEqual(result.loc[2029, "capture_capex"], -600.0)
        self.assertEqual(result.loc[2030, "capture_capex"], 0.0)
        self.assertEqual(result.loc[2029, "electricity_revenue"], 30.0 * 90.0)
        self.assertEqual(result.loc[2029, "electricity_purchase"], -(6.0 * 110.0))

    def test_inflates_costs_before_discounting_and_builds_no_ccs_case(self):
        config = _config()
        config.update(
            {
                "economics_interest_rate": 0.10,
                "economics_inflation_rate": 0.05,
                "emitter_emissions_annual": 200.0,
            }
        )

        result = run_cash_flow(_ledger(), config).set_index("year")
        second_year = result.loc[2029]
        base_costs = second_year.loc[list(COST_LINE_ITEM_COLUMNS)].sum()
        base_cash_flow = second_year.loc[
            [
                column
                for column in CASH_FLOW_COLUMNS
                if column
                in {
                    *COST_LINE_ITEM_COLUMNS,
                    "electricity_revenue",
                    "co2_value",
                }
            ]
        ].sum()

        self.assertAlmostEqual(
            second_year["cost_inflation_adjustment"],
            base_costs * 0.05,
        )
        self.assertAlmostEqual(
            second_year["net_cash_flow"],
            base_cash_flow + base_costs * 0.05,
        )
        self.assertAlmostEqual(second_year["discount_factor"], 1.0 / 1.10)
        self.assertAlmostEqual(
            second_year["discounted_cash_flow"],
            second_year["net_cash_flow"] / 1.10,
        )
        self.assertEqual(second_year["without_ccs_cash_flow"], -10_000.0)
        self.assertAlmostEqual(
            second_year["discounted_without_ccs_cash_flow"],
            -10_000.0 / 1.10,
        )
        self.assertAlmostEqual(
            result.loc[2030, "cumulative_net_cash_flow"],
            result["net_cash_flow"].sum(),
        )
        self.assertAlmostEqual(
            result.loc[2030, "cumulative_npv"],
            result["discounted_cash_flow"].sum(),
        )
        self.assertAlmostEqual(
            second_year["net_electricity_cash_flow"],
            second_year["electricity_revenue"]
            + second_year["electricity_purchase"] * 1.05,
        )

        summary = summarize_cash_flow(result.reset_index())
        self.assertAlmostEqual(
            summary["npv_eur"],
            result["discounted_cash_flow"].sum(),
        )
        self.assertAlmostEqual(
            summary["npv_eur"],
            summary["pv_revenues_eur"] + summary["pv_costs_eur"],
        )

    def test_monitoring_capex_and_opex_share_one_auditable_line_item(self):
        config = _config()
        config["monitoring"] = {
            "capex_eur": 50.0,
            "capex_year": 2028,
            "fixed_opex_eur_per_year": 7.0,
        }

        result = run_cash_flow(_ledger(), config).set_index("year")

        self.assertEqual(result.loc[2028, "monitoring"], -57.0)
        self.assertEqual(result.loc[2029, "monitoring"], -7.0)
        self.assertEqual(result.loc[2030, "monitoring"], -9.0)

    def test_existing_flat_json_style_cost_keys_are_supported(self):
        config = {
            "economics_ccs_start_year": [2028, "year", "Početak rada"],
            "emitter_capex": [1_000.0, "EUR", "CAPEX hvatanja"],
            "emitter_opex_per_ton": [2.0, "EUR/tCO2", "OPEX hvatanja"],
            "transport_capex": [500.0, "EUR", "CAPEX transporta"],
            "transport_mode": ["pipeline", "-", "Način transporta"],
            "transport_opex_per_ton": [1.0, "EUR/tCO2", "OPEX transporta"],
            "transport_opex_eur_per_tkm": [10.0, "EUR/tCO2/km", "Ne koristi se"],
            "transport_distance_km": [100.0, "km", "Udaljenost"],
            "compressor_capex": [300.0, "EUR", "CAPEX kompresora"],
            "compressor_annual_opex": [5.0, "EUR/year", "OPEX kompresora"],
            "storage_capex": [400.0, "EUR", "CAPEX ležišta"],
            "storage_opex_per_ton": [0.5, "EUR/tCO2", "OPEX utiskivanja"],
            "geothermal_capex": [600.0, "EUR", "CAPEX geotermalnog sustava"],
            "geothermal_annual_opex": [30.0, "EUR/year", "OPEX geotermije"],
            "electricity_buy_price": [100.0, "EUR/MWh", "Kupovna cijena"],
            "electricity_sell_price": [80.0, "EUR/MWh", "Prodajna cijena"],
            "monitoring_annual_cost_during_injection": [
                7.0,
                "EUR/year",
                "Monitoring tijekom utiskivanja",
            ],
            "monitoring_annual_cost_after_injection": [
                9.0,
                "EUR/year",
                "Monitoring nakon utiskivanja",
            ],
        }

        result = run_cash_flow(_ledger(), config).iloc[0]

        self.assertEqual(result["capture_capex"], -1_000.0)
        self.assertEqual(result["capture_opex"], -200.0)
        self.assertEqual(result["transport_capex"], -500.0)
        self.assertEqual(result["transport_opex"], -100.0)
        self.assertEqual(result["compressor_capex"], -300.0)
        self.assertEqual(result["compressor_opex"], -5.0)
        self.assertEqual(result["storage_capex"], -400.0)
        self.assertEqual(result["storage_opex"], -50.0)
        self.assertEqual(result["geothermal_capex"], -600.0)
        self.assertEqual(result["geothermal_opex"], -30.0)
        self.assertEqual(result["electricity_revenue"], 2_000.0)
        self.assertEqual(result["electricity_purchase"], -500.0)
        self.assertEqual(result["monitoring"], -7.0)

    def test_truck_and_rail_use_tonne_kilometre_opex_only(self):
        for transport_mode in ("truck", "rail"):
            with self.subTest(transport_mode=transport_mode):
                config = {
                    "transport_mode": transport_mode,
                    "transport_opex_per_ton": 999.0,
                    "transport_opex_eur_per_tkm": 0.02,
                    "transport_distance_km": 150.0,
                }

                result = run_cash_flow(_ledger(), config).set_index("year")

                self.assertEqual(result.loc[2028, "transport_opex"], -300.0)
                self.assertEqual(result.loc[2029, "transport_opex"], -360.0)
                self.assertEqual(result.loc[2030, "transport_opex"], 0.0)

    def test_monitoring_uses_lifecycle_specific_annual_cost(self):
        ledger = _ledger()
        ledger.loc[2029 - 2028, "monitoring_active"] = False
        config = {
            "monitoring_annual_cost_during_injection": 7.0,
            "monitoring_annual_cost_after_injection": 9.0,
        }

        result = run_cash_flow(ledger, config).set_index("year")

        self.assertEqual(result.loc[2028, "monitoring"], -7.0)
        self.assertEqual(result.loc[2029, "monitoring"], 0.0)
        self.assertEqual(result.loc[2030, "monitoring"], -9.0)

    def test_invalid_ledger_values_are_rejected(self):
        cases = (
            ("co2_chain_t", -1.0, "ne smije sadržavati negativne"),
            ("injection_active", 2, "True/False ili 0/1"),
        )
        for column, value, message in cases:
            with self.subTest(column=column):
                ledger = _ledger()
                ledger[column] = ledger[column].astype(object)
                ledger.loc[0, column] = value
                with self.assertRaisesRegex(CashFlowInputError, message):
                    run_cash_flow(ledger, {})

    def test_nonzero_chain_quantity_requires_active_injection(self):
        ledger = _ledger()
        ledger.loc[0, "injection_active"] = False

        with self.assertRaisesRegex(CashFlowInputError, "utiskivanje nije aktivno"):
            run_cash_flow(ledger, {})

    def test_missing_required_column_is_rejected(self):
        ledger = _ledger().drop(columns="monitoring_active")

        with self.assertRaisesRegex(CashFlowInputError, "monitoring_active"):
            run_cash_flow(ledger, {})


if __name__ == "__main__":
    unittest.main()
