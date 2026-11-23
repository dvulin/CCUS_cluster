"""D1 + the distance column: the designer wires a study up without JSON.

Two things are pinned here:

* the **Connections** grid moved into the Scenario tab and still carries the
  many-to-many semantics (emitter -> first leg -> sink, with its own start year);
* ``total_distance_km`` is calculated from the leg lengths, written on save, and a
  value the user types becomes an override that survives the next calculation.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ccus_core.models import (
    EdgeState,
    EmissionCurve,
    Emitter,
    EmitterSinkConnection,
    Node,
    NodeKind,
    PipelineDesign,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
    TransportMode,
)
from streamlit_app.app import (
    CONNECTION_COLUMNS,
    DEFAULT_CLUSTER,
    ROUTE_COLUMNS,
    _follow_distance_column,
    _merge_edited_routes,
    frames_to_scenario,
    load_scenario,
    scenario_to_frames,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = "inputs/examples/ccus_cluster_v1.json"


# --------------------------------------------------------------------- helpers
def pipeline_state(km: float) -> EdgeState:
    return EdgeState(
        mode=TransportMode.PIPELINE,
        valid_from_year=2026,
        distance_km=km,
        capacity_t_per_year=1_000_000.0,
        pipeline=PipelineDesign(
            inner_diameter_m=0.30, inlet_pressure_bar=150.0, inlet_temperature_c=20.0
        ),
    )


def leg(edge_id: str, start: str, end: str, km: float) -> TransportEdge:
    return TransportEdge(
        id=edge_id, name=edge_id, from_node=start, to_node=end, states=[pipeline_state(km)]
    )


def sink(sink_id: str, node_id: str) -> StorageSink:
    return StorageSink(
        id=sink_id,
        node_id=node_id,
        name=sink_id,
        storage_type=StorageType.DSA,
        capacity_t=1_000_000.0,
    )


def connected_scenario() -> ScenarioConfig:
    """Two emitters sharing one leg, each with its own sink and start year."""

    nodes = [
        Node(id="plant", name="Plant", kind=NodeKind.EMITTER),
        Node(id="hub", name="Hub", kind=NodeKind.HUB),
        Node(id="sink_a", name="Sink A", kind=NodeKind.STORAGE),
        Node(id="sink_b", name="Sink B", kind=NodeKind.STORAGE),
    ]
    edges = [
        leg("L1", "plant", "hub", 10.0),
        leg("L2", "hub", "sink_a", 20.0),
        leg("L3", "hub", "sink_b", 30.0),
    ]
    emitters = [
        Emitter(
            id="e1",
            name="E1",
            node_id="plant",
            activation_year=2026,
            gross_emissions=EmissionCurve.constant(100_000.0),
        ),
        Emitter(
            id="e2",
            name="E2",
            node_id="plant",
            activation_year=2026,
            gross_emissions=EmissionCurve.constant(50_000.0),
        ),
    ]
    connections = [
        EmitterSinkConnection(
            emitter_id="e1", sink_id="SA", route_edge_id="L1", start_year=2028
        ),
        EmitterSinkConnection(
            emitter_id="e2", sink_id="SB", route_edge_id="L1", start_year=2029
        ),
    ]
    return ScenarioConfig(
        id="connected",
        name="Connected",
        start_year=2026,
        end_year=2030,
        nodes=nodes,
        emitters=emitters,
        edges=edges,
        connections=connections,
        storage_sinks=[sink("SA", "sink_a"), sink("SB", "sink_b")],
    )


def rows(frame) -> list[dict]:
    return frame.to_dict("records")


# ------------------------------------------------------------------- D1 grid
def test_the_connections_grid_carries_a_selection_tick():
    frames = scenario_to_frames(connected_scenario())

    assert list(frames["connections"].columns) == CONNECTION_COLUMNS
    assert CONNECTION_COLUMNS[0] == "sel"
    assert not any(row["sel"] for row in rows(frames["connections"]))


def test_connections_round_trip_keeps_the_many_to_many_semantics():
    """Two emitters on one leg, two sinks, two start years - all preserved."""

    scenario = connected_scenario()
    updated = frames_to_scenario(scenario, scenario_to_frames(scenario))

    assert len(updated.connections) == 2
    assert {(item.emitter_id, item.sink_id) for item in updated.connections} == {
        ("e1", "SA"),
        ("e2", "SB"),
    }
    assert all(item.route_edge_id == "L1" for item in updated.connections)
    assert sorted(item.start_year for item in updated.connections) == [2028, 2029]


def test_ticking_a_connection_row_changes_nothing():
    """``sel`` is a UI tick, not data: Apply must ignore it."""

    scenario = connected_scenario()
    frames = scenario_to_frames(scenario)
    frames["connections"].loc[0, "sel"] = True

    updated = frames_to_scenario(scenario, frames)

    assert [item.model_dump() for item in updated.connections] == [
        item.model_dump() for item in scenario.connections
    ]


def test_a_new_connection_row_is_accepted_by_apply():
    scenario = connected_scenario()
    frames = scenario_to_frames(scenario)
    appended = pd.concat(
        [frames["connections"], pd.DataFrame([dict.fromkeys(CONNECTION_COLUMNS)])],
        ignore_index=True,
    )
    appended.loc[len(appended) - 1] = {
        "sel": False,
        "emitter_id": "e2",
        "route_edge_id": "L2",
        "sink_id": "SA",
        "start_year": 2030,
    }

    updated = frames_to_scenario(scenario, {**frames, "connections": appended})

    assert len(updated.connections) == 3
    assert (updated.connections[-1].emitter_id, updated.connections[-1].start_year) == (
        "e2",
        2030,
    )


# ---------------------------------------------------------- the distance column
def test_the_routes_table_carries_the_total_distance():
    frames = scenario_to_frames(connected_scenario())

    assert "total_distance_km" in ROUTE_COLUMNS
    assert "total_distance_km" in frames["routes"].columns


def test_a_calculated_distance_is_written_to_the_scenario_on_save():
    scenario = connected_scenario()
    frames = scenario_to_frames(scenario)
    index = list(frames["routes"]["id"]).index("L1")
    frames["routes"].loc[index, "total_distance_km"] = 60.0

    updated = frames_to_scenario(scenario, frames)

    assert updated.edge_by_id("L1").total_distance_km == pytest.approx(60.0)
    # and it comes back when the saved scenario is opened again
    again = scenario_to_frames(updated)
    assert again["routes"].loc[index, "total_distance_km"] == pytest.approx(60.0)


def test_the_distance_column_never_moves_the_physics():
    """It is an annotation: the solver must not see it."""

    from ccus_core import ScenarioEngine

    scenario = load_scenario(DEFAULT_CLUSTER)
    frames = scenario_to_frames(scenario)
    frames["routes"]["total_distance_km"] = 999.0
    annotated = frames_to_scenario(scenario, frames)

    before = ScenarioEngine(scenario).run()
    after = ScenarioEngine(annotated).run()

    assert after.kpis["stored_co2_t"] == pytest.approx(before.kpis["stored_co2_t"])
    assert after.kpis["npv_eur"] == pytest.approx(before.kpis["npv_eur"])


def test_a_locked_route_can_carry_a_distance_without_being_flattened():
    """A route with a state timeline is refused when edited - a distance is not an edit."""

    scenario = load_scenario(EXAMPLE)
    frames = scenario_to_frames(scenario)
    index = list(frames["routes"]["id"]).index("nexe_hub")
    frames["routes"].loc[index, "total_distance_km"] = 12.5

    updated = frames_to_scenario(scenario, frames)
    edge = updated.edge_by_id("nexe_hub")

    assert edge.total_distance_km == pytest.approx(12.5)
    assert len(edge.states) == len(scenario.edge_by_id("nexe_hub").states)
    assert edge.upgrades == scenario.edge_by_id("nexe_hub").upgrades


# ------------------------------------------------- calculated vs typed override
def test_the_calculated_distance_fills_blank_cells_and_follows_edits():
    state = SimpleNamespace(session_state={})
    base = pd.DataFrame(
        {
            "id": ["L1", "L2"],
            "distance_km": [10.0, 20.0],
            "total_distance_km": [None, None],
        }
    )

    shown = _follow_distance_column(state, base, {"L1": 60.0, "L2": 20.0})
    assert list(shown["total_distance_km"]) == [60.0, 20.0]

    # a longer leg moves every total above it, because those values are ours
    moved = _follow_distance_column(state, base, {"L1": 80.0, "L2": 20.0})
    assert list(moved["total_distance_km"]) == [80.0, 20.0]


def test_a_typed_distance_is_an_override_and_survives():
    state = SimpleNamespace(session_state={})
    base = pd.DataFrame(
        {
            "id": ["L1", "L2"],
            "distance_km": [10.0, 20.0],
            "total_distance_km": [None, None],
        }
    )
    shown = _follow_distance_column(state, base, {"L1": 60.0, "L2": 20.0})

    edited = shown.copy()
    edited.loc[0, "total_distance_km"] = 123.0
    merged = _merge_edited_routes(state, base, shown, edited)
    assert list(merged["total_distance_km"]) == [123.0, 20.0]

    # the override is kept even though the calculation still says 60
    again = _follow_distance_column(state, merged, {"L1": 60.0, "L2": 20.0})
    assert list(again["total_distance_km"]) == [123.0, 20.0]


def test_clearing_a_distance_puts_it_back_under_calculation():
    state = SimpleNamespace(session_state={})
    base = pd.DataFrame(
        {
            "id": ["L1", "L2"],
            "distance_km": [10.0, 20.0],
            "total_distance_km": [None, None],
        }
    )
    shown = _follow_distance_column(state, base, {"L1": 60.0, "L2": 20.0})
    edited = shown.copy()
    edited.loc[0, "total_distance_km"] = 123.0
    merged = _merge_edited_routes(state, base, shown, edited)

    cleared = merged.copy()
    cleared.loc[0, "total_distance_km"] = None
    back = _merge_edited_routes(state, merged, merged, cleared)

    assert _follow_distance_column(state, back, {"L1": 60.0, "L2": 20.0}).loc[
        0, "total_distance_km"
    ] == pytest.approx(60.0)


def test_a_distance_is_forgotten_when_its_leg_is_deleted():
    state = SimpleNamespace(session_state={})
    base = pd.DataFrame(
        {"id": ["L1", "L2"], "distance_km": [10.0, 20.0], "total_distance_km": [None, None]}
    )
    _follow_distance_column(state, base, {"L1": 60.0, "L2": 20.0})

    shorter = base.iloc[:1].copy()
    shown = _follow_distance_column(state, shorter, {"L1": 60.0})

    assert list(shown["total_distance_km"]) == [60.0]
    assert set(state.session_state["links_auto_distance"]) == {"L1"}


# ------------------------------------------------------------------ AppTest
def test_the_scenario_tab_renders_the_distance_target_and_the_connections_grid():
    """The designer wires hubs -> links -> connections without an exception."""

    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "streamlit_app" / "app.py"), default_timeout=600)
    app.run()

    assert not [item.value for item in app.exception]
    assert not [item.value for item in app.error]
    # the distance is measured against a chosen storage site
    assert "links_distance_sink" in {box.key for box in app.selectbox}
    # and the connections grid is one of the designer's editable tables
    editors = {
        editor.key: list(editor.value.columns)
        for editor in app.data_editor
        if getattr(editor, "value", None) is not None
    }
    assert "total_distance_km" in editors["editor_routes"]
    assert editors["editor_connections"][0] == "sel"