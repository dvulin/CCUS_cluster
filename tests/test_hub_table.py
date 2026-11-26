"""The hub table: filter, map tick, add/remove, and the links drawn on the map.

The table is the scenario's "who exists" list, so it is editable - but a filter must
never look like a deletion, and a hub a link still uses cannot be removed.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from streamlit_app.app import (
    ROUTE_COLUMNS,
    SCENARIO_NODE_COLUMNS,
    _apply_node_table,
    _filter_rows,
    _merge_filtered,
    _node_rows,
    _set_column,
    frames_to_scenario,
    load_scenario,
    route_row_from_candidate,
    scenario_to_frames,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "inputs" / "examples" / "cluster_three_emitters.json"


def _frame(rows):
    return pd.DataFrame(rows, columns=SCENARIO_NODE_COLUMNS)


# ----------------------------------------------------------------- the filtering
def test_the_filter_matches_any_case():
    rows = [{"map": True, "id": "HR.CH.001", "name": "Zagreb", "kind": "hub"}]

    assert _filter_rows(rows, "id", "hr.ch") == rows
    assert _filter_rows(rows, "name", "ZAG") == rows


def test_an_empty_filter_keeps_every_row():
    rows = [{"map": True, "id": "a", "name": "A", "kind": "hub"}]

    assert _filter_rows(rows, "name", "") == rows
    assert _filter_rows(rows, "name", "   ") == rows


def test_an_unknown_column_is_not_a_filter():
    rows = [{"map": True, "id": "a", "name": "A", "kind": "hub"}]

    assert _filter_rows(rows, "nope", "a") == rows


def test_the_filter_does_not_hide_rows_with_a_blank_cell():
    rows = [
        {"map": True, "id": "a", "name": "A", "kind": "hub"},
        {"map": True, "id": "b", "name": None, "kind": "hub"},
    ]

    # searching for "a" must not drop the row whose name is empty
    assert {row["id"] for row in _filter_rows(rows, "name", "a")} == {"a"}


# ------------------------------------------------------------- merging the edits
def test_a_filtered_edit_keeps_the_hidden_rows():
    full = _frame(
        [
            {"map": True, "id": "a", "name": "A", "kind": "hub", "links": 1},
            {"map": True, "id": "b", "name": "B", "kind": "hub", "links": 1},
        ]
    )
    shown = _frame([full.to_dict("records")[0]])  # the filter hid "b"
    edited = _frame([{**full.to_dict("records")[0], "name": "A2"}])

    merged = _merge_filtered(full, shown, edited)

    assert [row["id"] for row in merged] == ["a", "b"]
    assert merged[0]["name"] == "A2"
    assert merged[1]["name"] == "B"


def test_a_deleted_row_is_really_deleted():
    full = _frame([{"map": True, "id": "a", "name": "A", "kind": "hub", "links": 0}])
    shown = _frame(full.to_dict("records"))

    merged = _merge_filtered(full, shown, _frame([]))

    assert merged == []


def test_an_added_row_survives_the_merge():
    full = _frame([{"map": True, "id": "a", "name": "A", "kind": "hub", "links": 0}])
    shown = _frame(full.to_dict("records"))
    edited = _frame(
        full.to_dict("records")
        + [{"map": True, "id": "new", "name": "New", "kind": "hub", "links": 0}]
    )

    merged = _merge_filtered(full, shown, edited)

    assert [row["id"] for row in merged] == ["a", "new"]


# ------------------------------------------------------------- the node table
def test_the_hub_table_is_part_of_the_frames():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)

    assert list(frames["nodes"].columns) == SCENARIO_NODE_COLUMNS
    assert len(frames["nodes"]) == len(scenario.nodes)
    # a hub with coordinates starts on; one without cannot be ticked at all
    placed = {node.id for node in scenario.nodes
              if node.location.latitude is not None and node.location.longitude is not None}
    for row in frames["nodes"].to_dict("records"):
        assert bool(row["map"]) is (row["id"] in placed), row["id"]


def test_a_hub_the_table_hides_is_reported_not_deleted():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    rows = _node_rows(scenario, frames["routes"], hidden=["holcim"])

    hidden = {row["id"] for row in rows if not row["map"]}

    # the explicit tick-off is honoured ...
    assert "holcim" in hidden
    # ... and so is the "no coordinates" rule, on top of it
    assert {"sink_ivanic", "sink_poljana", "sink_drava"} <= hidden
    # hiding is a view concern: the scenario still has the node
    updated = frames_to_scenario(scenario, frames)
    assert updated.node_by_id("holcim") is not None


def test_a_new_hub_is_added_to_the_scenario():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    frames["nodes"] = _frame(
        frames["nodes"].to_dict("records")
        + [
            {
                "map": True,
                "id": "nb",
                "name": "New booster",
                "kind": "hub",
                "latitude": 45.5,
                "longitude": 15.5,
                "links": 0,
            }
        ]
    )

    updated = frames_to_scenario(scenario, frames)

    node = updated.node_by_id("nb")
    assert node is not None
    assert node.name == "New booster"
    assert node.kind.value == "hub"
    assert node.location.latitude == 45.5


def test_moving_a_hub_updates_its_position():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    rows = frames["nodes"].to_dict("records")
    for row in rows:
        if row["id"] == "hub_plomin":
            row["latitude"] = 46.0
            row["longitude"] = 16.0
    frames["nodes"] = _frame(rows)

    updated = frames_to_scenario(scenario, frames)

    assert updated.node_by_id("hub_plomin").location.latitude == 46.0


def test_a_hub_a_link_still_uses_cannot_be_removed():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    used = _text = {row["from_node"] for row in frames["routes"].to_dict("records")}
    keep = _frame(
        [row for row in frames["nodes"].to_dict("records") if row["id"] not in used]
    )
    frames["nodes"] = keep

    try:
        frames_to_scenario(scenario, frames)
    except ValueError as error:
        assert "still uses" in str(error)
    else:  # pragma: no cover - the check must fire
        raise AssertionError("removing a used hub was accepted")


def test_an_unused_hub_can_be_removed():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    # an extra hub that nothing links to, then dropped again
    frames["nodes"] = _frame(
        frames["nodes"].to_dict("records")
        + [
            {
                "map": True,
                "id": "spare",
                "name": "Spare",
                "kind": "hub",
                "latitude": 45.0,
                "longitude": 15.0,
                "links": 0,
            }
        ]
    )
    scenario = frames_to_scenario(scenario, frames)
    assert scenario.node_by_id("spare") is not None

    frames = scenario_to_frames(scenario)
    frames["nodes"] = _frame(
        [row for row in frames["nodes"].to_dict("records") if row["id"] != "spare"]
    )

    updated = frames_to_scenario(scenario, frames)

    assert updated.node_by_id("spare") is None


def test_the_node_table_keeps_the_node_order():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    before = [node.id for node in scenario.nodes]

    updated = frames_to_scenario(scenario, frames)

    assert [node.id for node in updated.nodes] == before


# ------------------------------------------------------------------- the map data
def test_the_map_links_are_read_from_the_rows():
    from streamlit_app.map_layers import _line_for, route_geometries

    geometries = route_geometries()
    assert geometries, "the reference study ships route geometries"

    (start, end), line = next(iter(geometries.items()))

    # a link the study has is drawn along the real route, not as a straight line
    drawn, source = _line_for(start, end, {}, geometries, mode="pipeline")

    assert source == "route"
    assert drawn == line


def test_an_unknown_pair_falls_back_to_a_straight_line():
    from streamlit_app.map_layers import _line_for

    coordinates = {"a": (15.0, 45.0), "b": (16.0, 46.0)}

    line, source = _line_for("a", "b", coordinates, {})

    assert source == "straight"
    assert line == [[15.0, 45.0], [16.0, 46.0]]


def test_a_hub_without_coordinates_is_not_drawn():
    from streamlit_app.map_layers import _line_for

    assert _line_for("a", "ghost", {"a": (15.0, 45.0)}, {}) == (None, "straight")


# ------------------------------------------------------- the include ticks
def test_the_links_table_carries_a_selection_column():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)

    assert "sel" in frames["routes"].columns
    # nothing is selected until the user ticks something
    assert not bool(frames["routes"]["sel"].any())

    row = route_row_from_candidate(
        {"source_hub": "a", "destination_hub": "b", "mode": "pipeline", "length_km": 1.0},
        set(),
        2027,
        1000.0,
    )
    assert row["sel"] is False


def test_the_selection_does_not_remove_a_link():
    """Ticking a row selects it; the link stays in the scenario until deleted."""

    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    rows = frames["routes"].to_dict("records")
    rows[0]["sel"] = True
    frames["routes"] = pd.DataFrame(rows, columns=ROUTE_COLUMNS)

    updated = frames_to_scenario(scenario, frames)

    assert len(updated.edges) == len(scenario.edges)
    assert updated.edge_by_id(rows[0]["id"]) is not None


def test_the_selection_can_be_set_for_every_row():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)

    _set_column(frames["routes"], "sel", True)
    assert frames["routes"]["sel"].all()

    updated = frames_to_scenario(scenario, frames)
    assert len(updated.edges) == len(scenario.edges)

    _set_column(frames["routes"], "sel", False)
    assert not frames["routes"]["sel"].any()


def test_the_hub_tick_can_be_set_for_every_row():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)

    _set_column(frames["nodes"], "map", False)
    assert not frames["nodes"]["map"].any()

    _set_column(frames["nodes"], "map", True)
    assert frames["nodes"]["map"].all()


def test_the_name_callback_strips_the_json_suffix():
    """The callback closes over ``st``: it must not need a module-level import."""

    from streamlit_app.app import _name_normaliser

    class FakeSt:
        def __init__(self):
            self.session_state = {"scenario_name": "  My case.JSON  "}

    fake = FakeSt()
    _name_normaliser(fake)()

    assert fake.session_state["scenario_name"] == "My case"


# ------------------------------------------------- hubs need coordinates
def test_a_hub_without_coordinates_cannot_be_a_link_end():
    from ccus_core.models import ScenarioConfig

    from streamlit_app.app import _hub_options

    payload = load_scenario(str(EXAMPLE)).model_dump()
    scenario = ScenarioConfig.model_validate(
        {
            **payload,
            "nodes": [
                *payload["nodes"],
                {
                    "id": "placeless",
                    "name": "Placeless",
                    "kind": "hub",
                    "location": {"latitude": None, "longitude": None},
                },
            ],
        }
    )
    frames = scenario_to_frames(scenario)

    options = _hub_options(scenario, frames["routes"])

    assert "holcim" in options
    assert "placeless" not in options, "a hub with no position is not linkable"


def test_a_link_already_using_a_placeless_hub_keeps_its_value():
    """Opening the table must not invalidate a stored value."""

    from streamlit_app.app import _hub_options

    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    rows = frames["routes"].to_dict("records")
    rows[0]["to_node"] = "sink_poljana"
    frames["routes"] = pd.DataFrame(rows, columns=ROUTE_COLUMNS)

    assert "sink_poljana" in _hub_options(scenario, frames["routes"])


def test_a_new_hub_without_coordinates_is_refused():
    scenario = load_scenario(str(EXAMPLE))
    frames = scenario_to_frames(scenario)
    frames["nodes"] = _frame(
        frames["nodes"].to_dict("records")
        + [
            {
                "map": True,
                "id": "pin",
                "name": "Pinned",
                "kind": "hub",
                "latitude": None,
                "longitude": None,
                "links": 0,
            }
        ]
    )

    try:
        frames_to_scenario(scenario, frames)
    except ValueError as error:
        assert "latitude and longitude" in str(error)
    else:  # pragma: no cover - the check must fire
        raise AssertionError("a hub without coordinates was accepted")


def test_the_tick_is_off_for_a_hub_without_coordinates():
    from streamlit_app.app import _force_ticks

    rows = _force_ticks(
        [
            {"map": True, "id": "ok", "latitude": 45.0, "longitude": 15.0},
            {"map": True, "id": "sink", "latitude": None, "longitude": None},
            {"map": False, "id": "hidden", "latitude": 45.0, "longitude": 15.0},
        ]
    )

    assert [row["id"] for row in rows if row["map"]] == ["ok"]
    assert [row["id"] for row in rows if not row["map"]] == ["sink", "hidden"]