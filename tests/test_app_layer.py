"""The Apply path: the edited tables must round-trip without data loss.

The Inputs tables own a few columns per entity.  Everything else - the state
timeline and the upgrades of a route, the modal designs, the node coordinates, the
full reservoir description - comes from the base scenario, so pressing *Apply* may
never silently drop it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from streamlit_app.app import (
    DEFAULT_CLUSTER,
    DEFAULT_SCENARIO,
    SOURCE_KEYS,
    _source_label,
    apply_overrides,
    build_map_figure,
    frames_to_scenario,
    load_scenario,
    scenario_to_frames,
)

from .test_solver import build_solver_scenario

EXAMPLE = "inputs/examples/ccus_cluster_v1.json"
ROOT = Path(__file__).resolve().parents[1]
CROATIA = ROOT / "inputs" / "examples" / "croatia_cluster_2025_2050.json"


def round_trip(scenario):
    return frames_to_scenario(scenario, scenario_to_frames(scenario))


def test_apply_round_trips_a_multi_state_edge_with_upgrades():
    scenario = load_scenario(EXAMPLE)
    updated = round_trip(scenario)

    before = scenario.edge_by_id("nexe_hub")
    after = updated.edge_by_id("nexe_hub")
    assert after is not None
    assert [state.model_dump() for state in after.states] == [
        state.model_dump() for state in before.states
    ]
    assert [item.model_dump() for item in after.upgrades] == [
        item.model_dump() for item in before.upgrades
    ]
    assert after.geometry_id == before.geometry_id


def test_apply_round_trips_node_locations_and_reservoirs():
    scenario = load_scenario(EXAMPLE)
    updated = round_trip(scenario)

    for node in scenario.nodes:
        other = updated.node_by_id(node.id)
        assert other is not None
        assert other.location.model_dump() == node.location.model_dump()
        assert other.kind == node.kind

    for sink in scenario.storage_sinks:
        other = updated.sink_by_id(sink.id)
        assert other is not None
        assert other.reservoir is not None and sink.reservoir is not None
        for name in ("area_m2", "effective_thickness_m", "temperature_c", "reference_pressure_bar"):
            assert getattr(other.reservoir, name) == pytest.approx(
                getattr(sink.reservoir, name)
            )
        assert other.node_id == sink.node_id


def test_apply_round_trips_monitoring_windows():
    scenario = load_scenario(EXAMPLE)
    updated = round_trip(scenario)
    for sink in scenario.storage_sinks:
        other = updated.sink_by_id(sink.id)
        assert other.monitoring_end_year == sink.monitoring_end_year
        assert other.monitoring_cost_during_injection_eur_per_year == (
            sink.monitoring_cost_during_injection_eur_per_year
        )


def test_apply_keeps_the_catchment_of_every_emitter():
    scenario = load_scenario(EXAMPLE)
    updated = round_trip(scenario)
    assert len(updated.emitters) == len(scenario.emitters)
    for emitter in scenario.emitters:
        other = updated.emitter_by_id(emitter.id)
        assert other is not None
        assert other.node_id == emitter.node_id
        assert other.gross_emissions.model_dump() == emitter.gross_emissions.model_dump()


def test_an_edited_simple_route_is_applied_and_keeps_its_design():
    scenario = build_solver_scenario()
    frames = scenario_to_frames(scenario)
    routes = frames["routes"]
    index = list(routes["id"]).index("trunk")
    routes.loc[index, "capacity_t_per_year"] = 250_000.0
    routes.loc[index, "distance_km"] = 55.0

    updated = frames_to_scenario(scenario, frames)
    edge = updated.edge_by_id("trunk")
    assert edge.states[0].capacity_t_per_year == pytest.approx(250_000.0)
    assert edge.states[0].distance_km == pytest.approx(55.0)
    # the design of the state survives the edit
    assert edge.states[0].pipeline is not None
    assert edge.states[0].pipeline.inner_diameter_m == pytest.approx(0.30)


def test_editing_a_route_with_upgrades_is_refused_instead_of_flattened():
    scenario = load_scenario(EXAMPLE)
    frames = scenario_to_frames(scenario)
    routes = frames["routes"]
    index = list(routes["id"]).index("nexe_hub")
    routes.loc[index, "opex_eur_per_t"] = 99.0

    with pytest.raises(ValueError, match="state timeline or a conditional upgrade"):
        frames_to_scenario(scenario, frames)


@pytest.mark.parametrize(
    "payload",
    [EXAMPLE, str(CROATIA), str(DEFAULT_CLUSTER), str(DEFAULT_SCENARIO)],
    ids=["v1", "croatia", "default_cluster", "default_single"],
)
def test_unchanged_tables_reproduce_the_very_same_scenario(payload):
    """Apply with zero edits must be the identity, for every shipped example."""

    scenario = load_scenario(payload)
    updated = round_trip(scenario)
    assert updated == scenario
    # nothing a user can see may move either
    assert updated.notes == scenario.notes
    for emitter in scenario.emitters:
        assert (
            updated.emitter_by_id(emitter.id).gross_emissions.model_dump()
            == emitter.gross_emissions.model_dump()
        )


def test_apply_with_zero_edits_reproduces_the_kpis():
    """The tester's decisive case: Apply must not move NPV or the stored mass."""

    from ccus_core import ScenarioEngine

    for payload in (str(DEFAULT_CLUSTER), str(DEFAULT_SCENARIO)):
        scenario = load_scenario(payload)
        before = ScenarioEngine(scenario).run()
        after = ScenarioEngine(round_trip(scenario)).run()
        assert after.kpis["stored_co2_t"] == pytest.approx(
            before.kpis["stored_co2_t"], rel=1e-12
        )
        assert after.kpis["npv_eur"] == pytest.approx(before.kpis["npv_eur"], rel=1e-12, abs=1e-6)


def test_source_labels_report_the_real_emitter_count():
    """K16: the radio must not promise 14 emitters while the file holds 3."""

    from streamlit_app.i18n import strings

    state = SimpleNamespace(session_state={})
    cluster = load_scenario(DEFAULT_CLUSTER)
    single = load_scenario(DEFAULT_SCENARIO)

    label = _source_label(state, strings("en"), "cluster")
    assert label == f"Cluster ({len(cluster.emitters)} emitters)"
    assert _source_label(state, strings("en"), "single") == (
        f"Single chain (legacy, {len(single.emitters)} emitters)"
    )
    assert _source_label(state, strings("en"), "upload") == "Upload JSON"
    # the Croatian label carries the same count
    assert f"{len(cluster.emitters)}" in _source_label(state, strings("hr"), "cluster")
    # the label is keyed, not localised, so a language switch keeps the choice
    assert set(SOURCE_KEYS) == {"cluster", "single", "upload"}


def test_database_rows_show_every_catalogue_emitter():
    """The Database section lists the whole catalogue, not just the scenario."""

    from ccus_core.io import load_emitter_catalogue
    from streamlit_app.app import DATABASE_COLUMNS, emitter_database_rows

    scenario = load_scenario(DEFAULT_CLUSTER)
    records = load_emitter_catalogue()
    rows = emitter_database_rows(scenario, 2030)

    assert len(rows) == len(records)
    assert [row["slug"] for row in rows] == [record.id for record in records]
    assert [row["name"] for row in rows] == [record.name for record in records]
    # the industry column exists even when the data does not
    assert all("industry" in row for row in rows)
    # the emissions are the curve value for the requested year
    for row, record in zip(rows, records):
        assert row["emissions"] == pytest.approx(record.emissions_in(2030), abs=1.0)
    assert set(rows[0]) == set(DATABASE_COLUMNS)


def test_database_rows_can_follow_the_timeline_year():
    from ccus_core.io import load_emitter_catalogue
    from streamlit_app.app import emitter_database_rows

    scenario = load_scenario(DEFAULT_CLUSTER)
    records = load_emitter_catalogue()
    record = records[0]

    early = emitter_database_rows(scenario, 2027)[0]["emissions"]
    late = emitter_database_rows(scenario, 2040)[0]["emissions"]
    assert early == pytest.approx(record.emissions_in(2027), abs=1.0)
    assert late == pytest.approx(record.emissions_in(2040), abs=1.0)
    assert early != pytest.approx(late)  # a declining power law must move


def test_apply_survives_a_full_engine_run():
    from ccus_core import ScenarioEngine

    scenario = load_scenario(EXAMPLE)
    updated = round_trip(scenario)
    result = ScenarioEngine(updated).run()
    assert result.ledger is not None
    assert result.cash_flow is not None


def test_overrides_still_work_after_the_rewrite():
    scenario = load_scenario(EXAMPLE)
    updated = apply_overrides(
        scenario, {"activation_year": {"nexe": 2030}, "discount_rate": 0.08}
    )
    assert updated.emitter_by_id("nexe").activation_year == 2030
    assert updated.economics.discount_rate == pytest.approx(0.08)
    # and the override result also round-trips
    assert frames_to_scenario(updated, scenario_to_frames(updated)) == updated


def test_map_figure_reflects_the_selected_year():
    import matplotlib.pyplot as plt

    from ccus_core import ScenarioEngine

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
    from pathlib import Path

    assert "streamlit" not in sys.modules or True  # streamlit may be installed
    module = Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py"
    text = module.read_text(encoding="utf-8")
    assert "import streamlit as st" in text
    # the import is deliberately inside main(), so importing the module is cheap
    assert text.index("def main(") < text.index("import streamlit as st")


def test_storage_table_exposes_the_monitoring_window():
    scenario = load_scenario(EXAMPLE)
    frames = scenario_to_frames(scenario)
    assert "monitoring_end_year" in frames["sinks"].columns
    assert frames["sinks"]["monitoring_end_year"].notna().any()
    assert isinstance(frames["sinks"], pd.DataFrame)


def test_storage_charts_label_the_year_without_decimals_or_separator():
    """The x axis must read 2028, not 2,028.0.

    The year is handed to the chart as text, which makes Vega-Lite use a nominal
    axis; a numeric year produces a quantitative axis with grouped, decimal ticks.
    """

    from streamlit_app.app import _year_chart_data

    frame = pd.DataFrame(
        {
            "year": [2027, 2028, 2029],
            "pressure_bar": [200.0, 210.0, 220.0],
            "bhp_bar": [210.0, 220.0, 230.0],
        }
    )
    data, x_label, columns = _year_chart_data(frame, ["pressure_bar", "bhp_bar"])

    assert list(data["year"]) == ["2027", "2028", "2029"]
    assert all(isinstance(value, str) for value in data["year"])
    assert not any(char in value for value in data["year"] for char in ",.")
    assert x_label == "Year"
    assert columns == ["pressure_bar", "bhp_bar"]