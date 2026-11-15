"""Named scenario files: default names, round-trip and safe naming."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccus_core.io import (
    ScenarioNotFoundError,
    delete_scenario,
    list_scenarios,
    load_scenario_file,
    next_default_name,
    save_scenario,
    validate_name,
)
from ccus_core.io.excel_import import build_scenario

from .test_solver import build_solver_scenario

WORKBOOK = Path(__file__).resolve().parents[1] / "docs" / "examples" / "CCS TABLICE 2015-2022 example.xlsx"


def test_default_names_start_at_001(tmp_path):
    assert next_default_name(tmp_path) == "scenario_001"
    save_scenario(build_solver_scenario(), None, directory=tmp_path)
    assert next_default_name(tmp_path) == "scenario_002"
    save_scenario(build_solver_scenario(), None, directory=tmp_path)
    assert next_default_name(tmp_path) == "scenario_003"
    assert [record.name for record in list_scenarios(tmp_path)] == [
        "scenario_001",
        "scenario_002",
    ]


def test_save_and_load_round_trip(tmp_path):
    scenario = build_solver_scenario()
    path = save_scenario(scenario, "my_case", directory=tmp_path)
    assert path.name == "my_case.json"

    reloaded = load_scenario_file("my_case", directory=tmp_path)
    assert len(reloaded.emitters) == len(scenario.emitters)
    assert reloaded.emitter_by_id("source").activation_year == 2028


def test_existing_name_is_not_overwritten(tmp_path):
    save_scenario(build_solver_scenario(), "case", directory=tmp_path)
    with pytest.raises(FileExistsError):
        save_scenario(build_solver_scenario(), "case", directory=tmp_path)
    # explicit opt-in works
    path = save_scenario(build_solver_scenario(), "case", directory=tmp_path, overwrite=True)
    assert path.exists()


def test_missing_scenario_raises(tmp_path):
    with pytest.raises(ScenarioNotFoundError):
        load_scenario_file("nope", directory=tmp_path)


def test_names_are_validated():
    assert validate_name(" scenario_01.json ") == "scenario_01"
    for bad in ("../escape", "a/b", "", "   ", ".hidden"):
        with pytest.raises(ValueError):
            validate_name(bad)


def test_delete_scenario(tmp_path):
    save_scenario(build_solver_scenario(), "temp", directory=tmp_path)
    delete_scenario("temp", directory=tmp_path)
    assert list_scenarios(tmp_path) == []


def test_cluster_workbook_round_trip(tmp_path):
    if not WORKBOOK.exists():
        pytest.skip("workbook not present")
    scenario = build_scenario(WORKBOOK)
    save_scenario(scenario, "cluster", directory=tmp_path)
    reloaded = load_scenario_file("cluster", directory=tmp_path)
    assert len(reloaded.emitters) == 14
    assert len(reloaded.connections) == 14
    assert len(reloaded.edges) == 14  # rebuilt from the connections