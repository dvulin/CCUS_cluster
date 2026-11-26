"""Map geometry for the links: which source is used, and the fallbacks.

Every link must be drawable from the table alone.  The line follows the surveyed
route when the reference study has one, the road when the mode is road, and the
direct line otherwise - and it never fails because the network is down.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccus_core.io import commented_json
from streamlit_app.map_layers import (
    _line_for,
    build_hub_map,
    hub_coordinates,
    road_polyline,
)

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = "inputs/examples/cluster_three_emitters.json"


@pytest.fixture
def scenario():
    return commented_json.load_file(str((REPO / EXAMPLE)))


def _routes(scenario, modes):
    """One link per (mode) between the first two placed hubs."""

    placed = list(hub_coordinates(scenario))[:2]
    return [
        {
            "from_node": placed[0],
            "to_node": placed[1],
            "mode": mode,
            "on": True,
        }
        for mode in modes
    ]


# ------------------------------------------------------------------ the sources
def test_a_surveyed_route_wins_over_everything(scenario, monkeypatch):
    from streamlit_app import map_layers

    monkeypatch.setattr(map_layers, "route_geometries", lambda: {("a", "b"): [[1.0, 2.0], [3.0, 4.0]]})
    coordinates = {"a": (1.0, 2.0), "b": (3.0, 4.0)}

    line, source = _line_for("a", "b", coordinates, {("a", "b"): [[1.0, 2.0], [3.0, 4.0]]}, mode="truck")

    assert source == "route"
    assert line == [[1.0, 2.0], [3.0, 4.0]]


def test_a_road_link_follows_the_road(scenario, monkeypatch):
    from streamlit_app import map_layers

    monkeypatch.setattr(
        map_layers, "road_polyline", lambda start, end: [[1.0, 2.0], [2.5, 3.5], [3.0, 4.0]]
    )
    coordinates = {"a": (1.0, 2.0), "b": (3.0, 4.0)}

    line, source = _line_for("a", "b", coordinates, {}, mode="truck")

    assert source == "road"
    assert len(line) == 3


def test_a_rail_link_is_not_sent_to_a_road_router(monkeypatch):
    from streamlit_app import map_layers

    called = []
    monkeypatch.setattr(
        map_layers,
        "road_polyline",
        lambda start, end: called.append((start, end)) or [[1.0, 2.0], [3.0, 4.0]],
    )
    coordinates = {"a": (1.0, 2.0), "b": (3.0, 4.0)}

    line, source = _line_for("a", "b", coordinates, {}, mode="rail")

    assert source == "straight"
    assert line == [[1.0, 2.0], [3.0, 4.0]]
    assert called == [], "a railway must not be drawn along a car road"


def test_road_geometry_is_optional(monkeypatch):
    from streamlit_app import map_layers

    monkeypatch.setattr(
        map_layers, "road_polyline", lambda start, end: [[1.0, 2.0], [3.0, 4.0]]
    )
    coordinates = {"a": (1.0, 2.0), "b": (3.0, 4.0)}

    line, source = _line_for("a", "b", coordinates, {}, mode="truck", road=False)

    assert source == "straight"


def test_a_hub_without_coordinates_is_not_drawn(monkeypatch):
    from streamlit_app import map_layers

    monkeypatch.setattr(map_layers, "road_polyline", lambda start, end: None)

    line, source = _line_for("a", "ghost", {"a": (1.0, 2.0)}, {}, mode="truck")

    assert line is None
    assert source == "straight"


# ------------------------------------------------------------- the road lookup
def test_an_unreachable_router_falls_back(monkeypatch):
    import urllib.request

    from streamlit_app import map_layers

    def boom(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    map_layers._ROAD_CACHE.clear()

    assert road_polyline((15.0, 45.0), (16.0, 46.0), timeout=0.1) is None


def test_a_router_error_code_is_not_geometry(monkeypatch):
    from streamlit_app import map_layers

    class FakeResponse:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: FakeResponse({"code": "NotOk", "message": "no route"}),
    )
    map_layers._ROAD_CACHE.clear()

    assert road_polyline((15.0, 45.0), (16.0, 46.0), timeout=0.1) is None


def test_the_road_lookup_is_cached(monkeypatch):
    from streamlit_app import map_layers

    calls = []

    def fake(start, end, timeout=6.0):
        calls.append((start, end))
        return [[1.0, 2.0], [3.0, 4.0]]

    monkeypatch.setattr(map_layers, "_fetch_osrm", fake)
    map_layers._ROAD_CACHE.clear()

    first = road_polyline((15.0, 45.0), (16.0, 46.0))
    second = road_polyline((15.0, 45.0), (16.0, 46.0))

    assert first == second
    assert len(calls) == 1, "a rerun must not ask the router again"


# ------------------------------------------------------------- every link drawn
def test_every_link_of_the_table_is_drawn(scenario, monkeypatch):
    from streamlit_app import map_layers

    monkeypatch.setattr(map_layers, "road_polyline", lambda start, end: None)
    routes = _routes(scenario, ["pipeline", "truck", "rail", "marine"])
    # a second leg so the table holds more than one link
    placed = list(hub_coordinates(scenario))
    routes.append(
        {"from_node": placed[2], "to_node": placed[3], "mode": "pipeline", "on": True}
    )

    deck = build_hub_map(scenario, routes=routes)
    links = [layer for layer in deck.layers if layer.id == "links"]
    drawn = links[0].data["features"] if links else []

    assert len(drawn) == len(routes)
    assert {feature["properties"]["mode"] for feature in drawn} == {
        "pipeline",
        "truck",
        "rail",
        "marine",
    }


def test_the_selection_does_not_hide_a_link(scenario, monkeypatch):
    """Ticking a row is a selection, not a filter: the map draws it all the same."""

    from streamlit_app import map_layers

    monkeypatch.setattr(map_layers, "road_polyline", lambda start, end: None)
    routes = _routes(scenario, ["pipeline"])
    routes.append({**routes[0], "id": "second", "sel": True})

    deck = build_hub_map(scenario, routes=routes)
    links = [layer for layer in deck.layers if layer.id == "links"]
    drawn = links[0].data["features"] if links else []

    assert len(drawn) == 2


def test_a_link_to_a_placeless_hub_is_left_out(scenario, monkeypatch):
    from streamlit_app import map_layers

    monkeypatch.setattr(map_layers, "road_polyline", lambda start, end: None)
    routes = _routes(scenario, ["pipeline"])
    routes[0]["to_node"] = "nowhere"

    deck = build_hub_map(scenario, routes=routes)
    links = [layer for layer in deck.layers if layer.id == "links"]

    assert not links or links[0].data["features"] == []


# ------------------------------------------------------------- focus / zoom
def test_a_short_link_is_framed_not_lost(scenario):
    """Two hubs 2 km apart are invisible nationally - the map must zoom to them."""

    deck = build_hub_map(
        scenario,
        routes=[{"from_node": "plomin", "to_node": "hub_plomin", "mode": "pipeline"}],
        focus={"from_node": "plomin", "to_node": "hub_plomin"},
    )

    view = deck.initial_view_state
    assert view.zoom >= 11.0
    assert abs(view.longitude - 14.19) < 0.05
    assert abs(view.latitude - 45.14) < 0.05


def test_a_long_link_keeps_the_overview(scenario):
    deck = build_hub_map(
        scenario,
        routes=[{"from_node": "holcim", "to_node": "nexe", "mode": "pipeline"}],
        focus={"from_node": "holcim", "to_node": "nexe"},
    )

    assert deck.initial_view_state.zoom == 6.4


def test_an_unknown_focus_falls_back_to_the_overview(scenario):
    deck = build_hub_map(
        scenario,
        routes=[],
        focus={"from_node": "nope", "to_node": "also_nope"},
    )

    assert deck.initial_view_state.zoom == 6.4


def test_line_width_units_must_be_a_literal_string():
    """pydeck turns a plain string into a JS expression, silently restoring metres."""

    import pydeck
    from pydeck.types import String

    literal = pydeck.Layer("GeoJsonLayer", data={}, id="a", line_width_units=String("pixels"))
    expression = pydeck.Layer("GeoJsonLayer", data={}, id="b", line_width_units="pixels")

    assert literal.line_width_units == "pixels"
    assert expression.line_width_units != "pixels"