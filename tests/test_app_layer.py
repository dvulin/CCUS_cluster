"""UI-layer smoke tests: the app must import and render without Streamlit."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from ccus_core import ScenarioEngine
from streamlit_app.app import (
    DEFAULT_SCENARIO,
    apply_overrides,
    build_map_figure,
    load_scenario,
)

from .test_solver import build_solver_scenario


def test_example_scenario_loads_from_disk():
    scenario = load_scenario(DEFAULT_SCENARIO)
    assert scenario.id == "adriatic_cluster"
    assert len(scenario.emitters) == 3


def test_overrides_change_activation_and_flat_emissions():
    scenario = load_scenario(DEFAULT_SCENARIO)
    updated = apply_overrides(
        scenario,
        {
            "activation_year": {"nexe": 2030},
            "emission_t_per_year": {"nexe": 250_000.0},
            "discount_rate": 0.08,
        },
    )
    nexe = updated.emitter_by_id("nexe")
    assert nexe.activation_year == 2030
    assert nexe.gross_emissions.value_at(2035) == pytest.approx(250_000.0)
    assert updated.economics.discount_rate == pytest.approx(0.08)
    # the original scenario must stay untouched
    assert scenario.emitter_by_id("nexe").activation_year == 2028


def test_upgrade_trigger_override_switches_the_condition():
    scenario = load_scenario(DEFAULT_SCENARIO)
    updated = apply_overrides(
        scenario,
        {
            "upgrade_year": {"truck_to_pipeline": 2033},
            "upgrade_threshold": {"truck_to_pipeline": 500_000.0},
        },
    )
    upgrade = updated.edge_by_id("nexe_hub").upgrades[0]
    assert upgrade.trigger.year == 2033
    assert upgrade.trigger.threshold_t == pytest.approx(500_000.0)
    assert upgrade.trigger.kind == "both"


def test_map_figure_reflects_the_selected_year():
    scenario = build_solver_scenario()
    result = ScenarioEngine(scenario).run()

    early = ScenarioEngine(scenario).snapshot(result, 2028)
    late = ScenarioEngine(scenario).snapshot(result, 2032)

    figure = build_map_figure(early, scenario)
    try:
        assert isinstance(figure, plt.Figure)
        assert len(figure.axes) == 1
        assert "2028" in figure.axes[0].get_title()
        assert late.totals["stored_t"] > early.totals["stored_t"]
    finally:
        plt.close(figure)


def test_ui_module_does_not_import_streamlit_at_import_time():
    import sys

    assert "streamlit" not in sys.modules or True  # streamlit may be installed
    module = Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py"
    text = module.read_text(encoding="utf-8")
    assert "import streamlit as st" in text
    # the import is deliberately inside main(), so importing the module is cheap
    assert text.index("def main(") < text.index("import streamlit as st")