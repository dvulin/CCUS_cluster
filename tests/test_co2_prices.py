"""``json/CO2_prices.json``: the three CO2 price scenarios as reviewed yearly data.

The file must (a) reproduce the workbook values exactly, (b) be editable without
touching Python, and (c) never be silently ignored - a malformed file has to stop
the run rather than price a cluster with numbers nobody reviewed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccus_core.io import commented_json
from ccus_core.io.co2_prices import (
    CO2_PRICES_PATH,
    PRICE_SCENARIO_NAMES,
    Co2PriceFileError,
    load_price_scenarios,
    price_series,
    price_file_path,
    read_price_scenarios,
    save_price_scenarios,
    scenarios_from_document,
)
from ccus_core.models.policy import DEFAULT_PRICE_SCENARIOS, default_price_scenarios

REPO = Path(__file__).resolve().parents[1]
CLUSTER_JSON = REPO / "inputs" / "examples" / "croatia_cluster_2025_2050.json"
THREE_EMITTERS = REPO / "inputs" / "examples" / "cluster_three_emitters.json"


def _prices(**overrides) -> dict[str, list[float]]:
    """A minimal but valid price document (the three presets)."""

    series = {name: [60.0 + index for index in range(3)] for name in PRICE_SCENARIO_NAMES}
    series.update(overrides)
    return {"years": [2025, 2026, 2027], "scenarios": series}


#: the smallest scenario the model accepts (a sink, and the node it injects into)
MINIMAL_NODE = {"id": "SINK", "name": "Sink", "kind": "storage"}
MINIMAL_SINK = {
    "id": "sink",
    "name": "Sink",
    "node_id": "SINK",
    "capacity_t": 1_000_000.0,
}


def _base_document() -> dict:
    """The reference cluster as a plain payload (nodes, emitters, sinks and all)."""

    return json.loads(CLUSTER_JSON.read_text(encoding="utf-8"))["scenario"]


def _economics(**overrides) -> dict:
    """The economics block of the reference cluster, 2025-2050."""

    block = {
        "start_year": 2025,
        "end_year": 2050,
        "capex_start_year": 2026,
        "discount_rate": 0.06,
        "inflation_rate": 0.06,
    }
    block.update(overrides)
    return block


# ------------------------------------------------------------------ the shipped file
def test_the_shipped_file_exists_and_is_valid():
    assert CO2_PRICES_PATH.is_file(), "json/CO2_prices.json must be versioned with the repo"

    scenarios = read_price_scenarios()

    assert set(scenarios) == set(PRICE_SCENARIO_NAMES)
    for name, values in DEFAULT_PRICE_SCENARIOS.items():
        assert list(scenarios[name].values_eur_per_t) == list(values), name
        assert scenarios[name].start_year == 2025
        assert len(scenarios[name].values_eur_per_t) == 26  # 2025-2050


def test_the_file_matches_the_policy_defaults_exactly():
    """The file is the data source; the constants stay as the offline fallback."""

    assert load_price_scenarios() == default_price_scenarios()


def test_the_year_axis_is_read_from_the_file_not_from_the_values():
    document = json.loads(CO2_PRICES_PATH.read_text(encoding="utf-8"))
    years = document["years"]

    assert years[0] == 2025 and years[-1] == 2050
    assert len(years) == len(document["scenarios"]["conservative"])

    # the first value is the 2025 price, the last one the 2050 price
    conservative = load_price_scenarios()["conservative"]
    assert conservative.price_at(2025) == document["scenarios"]["conservative"][0]
    assert conservative.price_at(2050) == document["scenarios"]["conservative"][-1]


# ------------------------------------------------------------------------ fallback
def test_a_missing_file_falls_back_to_the_workbook_defaults(tmp_path):
    missing = tmp_path / "nope.json"

    assert load_price_scenarios(missing) == default_price_scenarios()


def test_an_empty_environment_falls_back_too(tmp_path, monkeypatch):
    monkeypatch.setenv("GT_CCS_CO2_PRICES", str(tmp_path / "absent.json"))

    assert price_file_path().name == "absent.json"
    assert load_price_scenarios() == default_price_scenarios()


# ---------------------------------------------------------------------- validation
@pytest.mark.parametrize(
    "document",
    [
        {"years": [2025, 2026], "scenarios": {"conservative": [1.0]}},  # missing presets
        {"years": [2025, 2026], "scenarios": {"optimistic": [1.0, 2.0], "conservative": [1.0], "pessimistic": [1.0, 2.0]}},
        {"years": [2025, 2026, 2026], "scenarios": {"optimistic": [1.0, 2.0, 3.0], "conservative": [1.0, 2.0, 3.0], "pessimistic": [1.0, 2.0, 3.0]}},
        {"years": [2026, 2025], "scenarios": {"optimistic": [1.0, 2.0], "conservative": [1.0, 2.0], "pessimistic": [1.0, 2.0]}},
        {"years": [2025, 2026], "scenarios": {"optimistic": [1.0, -2.0], "conservative": [1.0, 2.0], "pessimistic": [1.0, 2.0]}},
        {"years": [2025, 2026], "scenarios": {"optimistic": [1.0, "x"], "conservative": [1.0, 2.0], "pessimistic": [1.0, 2.0]}},
    ],
)
def test_malformed_documents_are_refused(document):
    with pytest.raises(Co2PriceFileError):
        scenarios_from_document(document)


def test_a_malformed_file_stops_the_load_instead_of_pricing_silently(tmp_path):
    broken = tmp_path / "CO2_prices.json"
    broken.write_text("{ not json", encoding="utf-8")

    with pytest.raises(Co2PriceFileError):
        load_price_scenarios(broken)


def test_a_file_without_the_three_presets_is_refused(tmp_path):
    partial = tmp_path / "CO2_prices.json"
    partial.write_text(
        json.dumps({"years": [2025], "scenarios": {"optimistic": [1.0]}}), encoding="utf-8"
    )

    with pytest.raises(Co2PriceFileError) as error:
        load_price_scenarios(partial)
    assert "conservative" in str(error.value) and "pessimistic" in str(error.value)


# --------------------------------------------------------------------------- edits
def test_editing_the_file_changes_the_loaded_series(tmp_path):
    edited = _prices()
    edited["scenarios"]["conservative"][1] = 999.0
    target = tmp_path / "CO2_prices.json"
    target.write_text(json.dumps(edited), encoding="utf-8")

    scenarios = load_price_scenarios(target)

    assert scenarios["conservative"].price_at(2026) == 999.0
    assert price_series("conservative", target)[1] == 999.0
    # the other presets are untouched by the edit
    assert scenarios["optimistic"].price_at(2026) == 61.0


def test_a_preset_price_path_reads_its_series_from_the_file(tmp_path, monkeypatch):
    """``price_path: {mode: conservative}`` used to be invalid without inline values."""

    edited = _prices()
    edited["scenarios"]["conservative"] = [70.0 + index for index in range(3)]
    target = tmp_path / "CO2_prices.json"
    target.write_text(json.dumps(edited), encoding="utf-8")
    monkeypatch.setenv("GT_CCS_CO2_PRICES", str(target))

    document = _base_document()
    document["economics"] = _economics(price_path={"mode": "conservative"})
    document["policy"] = {}

    scenario = commented_json.from_payload(document)

    assert scenario.economics is not None
    assert scenario.economics.price_path.mode == "conservative"
    # the 2025-2027 values come from the file, not from the model defaults
    prices = scenario.economics.prices_by_year()
    assert [prices[year] for year in (2025, 2026, 2027)] == [70.0, 71.0, 72.0]
    # outside the file's range the endpoints are held (2050 -> the last value)
    assert prices[2050] == 72.0
    # the same series is visible through the policy block
    assert scenario.policy is not None
    assert scenario.policy.price_in(2026) == 71.0


def test_a_custom_price_path_is_left_alone(tmp_path, monkeypatch):
    target = tmp_path / "CO2_prices.json"
    target.write_text(json.dumps(_prices()), encoding="utf-8")
    monkeypatch.setenv("GT_CCS_CO2_PRICES", str(target))

    document = _base_document()
    document["economics"] = _economics(
        price_path={"mode": "custom", "custom": {"p0_eur_per_t": 10.0}}
    )
    document["policy"] = {}

    scenario = commented_json.from_payload(document)

    assert scenario.economics is not None
    assert scenario.economics.price_path.mode == "custom"
    # the legacy linear path is untouched: 10 EUR/t in 2025, +3 EUR/t per year
    assert scenario.economics.price_path.price_at(2025, reference_year=2025) == 10.0
    assert scenario.economics.price_path.price_at(2026, reference_year=2025) == 13.0


def test_the_shipped_file_leaves_the_existing_scenarios_unchanged():
    """The file must not silently re-price the reference scenarios."""

    scenario = commented_json.load_file(CLUSTER_JSON)
    dumped = commented_json.dump(scenario)

    # `policy: {}` stays empty because the file equals the model defaults
    assert '"policy": {}' in dumped
    assert scenario.economics is not None
    assert scenario.economics.price_path.mode == "custom"


def test_a_representative_scenario_round_trips_with_the_price_file():
    scenario = commented_json.load_file(CLUSTER_JSON)

    once = commented_json.dump(scenario)
    twice = commented_json.dump(commented_json.load(once))

    assert twice == once


# -------------------------------------------------------------------------- writer
def test_save_then_load_round_trips(tmp_path):
    target = tmp_path / "out.json"

    saved = save_price_scenarios(default_price_scenarios(), target)
    reloaded = read_price_scenarios(saved)

    assert saved == target
    assert reloaded == default_price_scenarios()

    meta = json.loads(target.read_text(encoding="utf-8"))["_meta"]
    assert meta["schema"] == "gt-ccus-co2-prices/1.0"
    assert meta["unit"] == "EUR/t CO2"
    assert meta["years"] == 26


def test_the_writer_refuses_series_of_different_lengths(tmp_path):
    broken = {
        "optimistic": default_price_scenarios()["optimistic"],
        "conservative": default_price_scenarios()["conservative"].model_copy(
            update={"values_eur_per_t": [1.0, 2.0]}
        ),
        "pessimistic": default_price_scenarios()["pessimistic"],
    }

    with pytest.raises(Co2PriceFileError):
        save_price_scenarios(broken, tmp_path / "bad.json")


# ------------------------------------------------------------------ the cash flow
@pytest.mark.slow
def test_the_price_file_reaches_the_cash_flow(tmp_path, monkeypatch):
    """The point of the file: editing a price has to move the NPV of a real run."""

    from ccus_core.engine import ScenarioEngine

    document = json.loads(THREE_EMITTERS.read_text(encoding="utf-8"))
    scenario = document.get("scenario", document)
    scenario["economics"]["price_path"] = {"mode": "conservative"}
    scenario["policy"] = {}
    payload = json.loads(json.dumps(scenario))

    monkeypatch.delenv("GT_CCS_CO2_PRICES", raising=False)
    reference = ScenarioEngine(commented_json.from_payload(payload)).run()

    doubled = default_price_scenarios()
    doubled["conservative"] = doubled["conservative"].model_copy(
        update={
            "values_eur_per_t": [
                2.0 * value for value in doubled["conservative"].values_eur_per_t
            ]
        }
    )
    monkeypatch.setenv(
        "GT_CCS_CO2_PRICES", str(save_price_scenarios(doubled, tmp_path / "prices.json"))
    )
    changed = ScenarioEngine(commented_json.from_payload(payload)).run()

    assert reference.kpis["npv_eur"] is not None
    assert changed.kpis["npv_eur"] != reference.kpis["npv_eur"]