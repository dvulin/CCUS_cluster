"""Build a pydeck map (OpenStreetMap-based basemap) for the scenario network.

Tier 1 of the GIS work: the extracted STRATEGY CCUS routes (``data/gis``) give
context, and the scenario's own edges are drawn on top using the node
coordinates.  No new dependency is required – pydeck ships with Streamlit.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydeck.types import String

from ccus_core.geo.distance import path_length_km

HERE = Path(__file__).resolve().parents[1]
GIS_DIR = HERE / "data" / "gis"
BASEMAP = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"

MODE_COLOURS = {
    "pipeline": [31, 119, 180],
    "truck": [230, 126, 34],
    "rail": [44, 160, 44],
    "marine": [148, 103, 189],
}

#: the hub marker's radius in PIXELS; a marker is twice that across
HUB_RADIUS_PX = 9

#: link width in PIXELS (`line_width_units="pixels"`).  A hub marker is 18 px
#: across, so the thickest link is half a marker, and the others step down.
MODE_LINE_WIDTH = {
    "pipeline": HUB_RADIUS_PX,
    "truck": 6,
    "rail": 8,
    "marine": 8,
}

#: the pale casing drawn under a link.  There is deliberately no dark border: an
#: outline that wide read as a grey shadow on the basemap, not as depth.
CASING_EXTRA_WIDTH = 3
CASING_COLOUR = [255, 255, 255, 170]

#: the selected link and its two hubs
HIGHLIGHT_COLOUR = [214, 39, 40]


def _load(name: str) -> dict | None:
    path = GIS_DIR / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


#: public OSRM demo server: a car/road profile, no key, good enough for a map
OSRM_BASE = "https://router.project-osrm.org/route/v1/driving"

#: the driving geometry and length of a pair, so a rerun (and every map click) is free
_ROAD_CACHE: dict[tuple, tuple[list[list[float]] | None, float | None]] = {}

#: how many pairs to remember before the cache is dropped
ROAD_CACHE_LIMIT = 512


def _fetch_osrm(start, end, timeout: float = 6.0):
    """The road geometry between two WGS84 points, or ``None`` when unavailable.

    Only a map refinement: when the network is down, slow or blocked the caller
    falls back to the straight line, so the analysis never depends on it.
    """

    import urllib.request

    url = (
        f"{OSRM_BASE}/{float(start[0])},{float(start[1])};"
        f"{float(end[0])},{float(end[1])}?overview=full&geometries=geojson"
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - offline is a normal state, not an error
        return None

    if not isinstance(payload, dict) or payload.get("code") != "Ok":
        return None
    routes = payload.get("routes") or []
    if not routes:
        return None
    coordinates = (routes[0].get("geometry") or {}).get("coordinates") or []
    line = [[float(point[0]), float(point[1])] for point in coordinates if len(point) >= 2]
    return line if len(line) >= 2 else None


def _road_geometry(start, end, *, timeout: float = 6.0):
    """The cached ``(polyline, length_km)`` of a road pair, either ``None``."""

    key = (
        round(float(start[0]), 5),
        round(float(start[1]), 5),
        round(float(end[0]), 5),
        round(float(end[1]), 5),
    )
    if key in _ROAD_CACHE:
        return _ROAD_CACHE[key]

    line = _fetch_osrm(key[:2], key[2:], timeout=timeout)
    length = path_length_km(line) if line else None
    if len(_ROAD_CACHE) >= ROAD_CACHE_LIMIT:
        _ROAD_CACHE.clear()
    _ROAD_CACHE[key] = (line, length)
    return line, length


def road_polyline(start, end, *, timeout: float = 6.0):
    """Cached driving geometry between two ``(lon, lat)`` points, or ``None``."""

    return _road_geometry(start, end, timeout=timeout)[0]


def road_length_km(start, end, *, timeout: float = 6.0):
    """Cached driving distance in kilometres, or ``None`` when unavailable.

    This is the length of the line the map draws, not the straight line between the
    hubs - the two differ by 20-30 % on a real road, and the cost model is per km.
    """

    return _road_geometry(start, end, timeout=timeout)[1]


def hub_coordinates(scenario) -> dict[str, tuple[float, float]]:
    """Node id -> ``(longitude, latitude)`` for every node that has a position.

    A hub the GIS data does not place cannot be drawn or measured, so it is simply
    absent from the map rather than parked in the Gulf of Guinea at ``0, 0``.
    """

    coordinates: dict[str, tuple[float, float]] = {}
    for node in scenario.nodes:
        latitude = node.location.latitude
        longitude = node.location.longitude
        if latitude is None or longitude is None:
            continue
        coordinates[node.id] = (float(longitude), float(latitude))
    return coordinates


#: (from, to) -> polyline of the reference study, in WGS84
_GEOMETRY_CACHE: dict[tuple[str, str], list[list[float]]] | None = None


def route_geometries() -> dict[tuple[str, str], list[list[float]]]:
    """ GIS polylines keyed by the two hubs they connect.

    The reference study ships real routes; a link that matches one is drawn along it
    instead of as a straight line.  A missing or unreadable file is not an error - the
    caller falls back to the straight line.
    """

    global _GEOMETRY_CACHE
    if _GEOMETRY_CACHE is not None:
        return _GEOMETRY_CACHE

    geometries: dict[tuple[str, str], list[list[float]]] = {}
    data = _load("routes.geojson")
    for feature in (data or {}).get("features", []):
        properties = feature.get("properties") or {}
        start, end = properties.get("from_node"), properties.get("to_node")
        coordinates = (feature.get("geometry") or {}).get("coordinates")
        if not start or not end or not coordinates:
            continue
        line = [
            [float(point[0]), float(point[1])]
            for point in coordinates
            if len(point) >= 2
        ]
        if len(line) >= 2:
            geometries[(str(start), str(end))] = line
    _GEOMETRY_CACHE = geometries
    return geometries


def _line_for(
    start: str,
    end: str,
    coordinates: dict[str, tuple[float, float]],
    geometries: dict[tuple[str, str], list[list[float]]],
    *,
    mode: str = "pipeline",
    road: bool = True,
):
    """The line to draw for a link, and where it came from.

    ``"route"`` - the reference study surveyed this exact pair;
    ``"road"`` - the road geometry of a routing service;
    ``"straight"`` - no source, so the direct line between the hubs.
    """

    geometry = geometries.get((start, end))
    if geometry:
        return geometry, "route"

    first, second = coordinates.get(start), coordinates.get(end)
    if first is None or second is None:
        return None, "straight"

    if mode == "truck" and road:
        line = road_polyline(first, second)
        if line:
            return line, "road"

    return [list(first), list(second)], "straight"


def build_network_map(snapshot, scenario, *, year: int | None = None, highlight=None):
    """Return a ``pydeck.Deck`` or ``None`` when the data is insufficient.

    ``highlight`` optionally names one link (``{"from_node": ..., "to_node": ...}``):
    that link is drawn on top in a strong colour, its two hubs are enlarged, and
    the view is centred on the pair instead of on the whole network.
    """

    try:
        import pydeck as pdk
    except Exception:  # pragma: no cover - pydeck is optional
        return None

    features: list[dict] = []

    base = _load("routes.geojson")
    if base:
        context = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"kind": "gis-route"},
                    "geometry": feature["geometry"],
                }
                for feature in base.get("features", [])
            ],
        }
        features.append(
            pdk.Layer(
                "GeoJsonLayer",
                data=context,
                get_line_color=[140, 140, 140, 120],
                get_line_width=1,
                pickable=False,
            )
        )

    # scenario nodes with coordinates
    coordinates = hub_coordinates(scenario)

    lines: list[dict] = []
    for edge in snapshot.edges:
        start = coordinates.get(edge["from_node"])
        end = coordinates.get(edge["to_node"])
        if start is None or end is None:
            continue
        colour = MODE_COLOURS.get(edge["mode"] or "", [130, 130, 130])
        flow = float(edge.get("flow_t") or 0.0)
        lines.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "scenario-edge",
                    "mode": edge["mode"],
                    "flow_t": flow,
                    "colour": colour,
                    # a link without a computed flow (the editor, before a run)
                    # still needs a visible width
                    "width": flow if flow > 0.0 else 2.0,
                },
                "geometry": {"type": "LineString", "coordinates": [list(start), list(end)]},
            }
        )

    # the selected link, drawn on top of the rest
    highlighted: dict[str, list[float]] = {}
    if highlight:
        for edge in snapshot.edges:
            if edge["from_node"] != highlight.get("from_node"):
                continue
            if edge["to_node"] != highlight.get("to_node"):
                continue
            start = coordinates.get(edge["from_node"])
            end = coordinates.get(edge["to_node"])
            if start is None or end is None:
                continue
            highlighted = {"from_node": edge["from_node"], "to_node": edge["to_node"]}
            features.append(
                pdk.Layer(
                    "GeoJsonLayer",
                    data={
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"kind": "highlight"},
                                "geometry": {
                                    "type": "LineString",
                                    "coordinates": [list(start), list(end)],
                                },
                            }
                        ],
                    },
                    get_line_color=HIGHLIGHT_COLOUR,
                    get_line_width=6,
                    line_width_units=String("pixels"),
                    pickable=False,
                )
            )
            break

    points: list[dict] = []
    for node in scenario.nodes:
        if node.id not in coordinates:
            continue
        lon, lat = coordinates[node.id]
        is_sink = node.kind.value in {"storage", "geothermal"}
        is_port = node.kind.value in {"port", "offshore_terminal"}
        points.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "storage" if is_sink else ("port" if is_port else "other"),
                    "name": node.name,
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )

    if not coordinates:
        return None

    if lines:
        features.append(
            pdk.Layer(
                "GeoJsonLayer",
                data={"type": "FeatureCollection", "features": lines},
                get_line_color="properties.colour",
                get_line_width="properties.width",
                get_line_width_min_pixels=1,
                get_line_width_max_pixels=8,
                pickable=True,
            )
        )

    # the hubs of the highlighted link, larger than the rest
    if highlighted:
        markers = [
            {
                "type": "Feature",
                "properties": {"kind": "highlight", "name": node_id},
                "geometry": {"type": "Point", "coordinates": list(coordinates[node_id])},
            }
            for node_id in (highlighted["from_node"], highlighted["to_node"])
            if node_id in coordinates
        ]
        if markers:
            features.append(
                pdk.Layer(
                    "GeoJsonLayer",
                    data={"type": "FeatureCollection", "features": markers},
                    get_point_radius=9,
                    get_fill_color=HIGHLIGHT_COLOUR,
                    get_line_color=[255, 255, 255],
                    stroked=True,
                    line_width_min_pixels=1,
                    point_radius_min_pixels=7,
                    pickable=True,
                )
            )

    if points:
        features.append(
            pdk.Layer(
                "GeoJsonLayer",
                data={"type": "FeatureCollection", "features": points},
                get_point_radius=4,
                get_fill_color=[44, 62, 80, 220],
                point_radius_min_pixels=5,
                pickable=True,
            )
        )

    if highlighted:
        start = coordinates.get(highlighted["from_node"])
        end = coordinates.get(highlighted["to_node"])
        if start is not None and end is not None:
            longitudes = [start[0], end[0]]
            latitudes = [start[1], end[1]]
            view_state = pdk.ViewState(
                longitude=sum(longitudes) / 2.0,
                latitude=sum(latitudes) / 2.0,
                zoom=7.4,
                pitch=0,
            )
            return pdk.Deck(
                layers=features,
                initial_view_state=view_state,
                map_style=BASEMAP,
                tooltip={"text": "{name}\n{mode} {flow_t} t"},
            )

    longitudes = [lon for lon, _ in coordinates.values()]
    latitudes = [lat for _, lat in coordinates.values()]
    view_state = pdk.ViewState(
        longitude=sum(longitudes) / len(longitudes),
        latitude=sum(latitudes) / len(latitudes),
        zoom=6.2,
        pitch=0,
    )
    return pdk.Deck(
        layers=features,
        initial_view_state=view_state,
        map_style=BASEMAP,
        tooltip={"text": "{name}\n{mode} {flow_t} t"},
    )


def _focus_view(coordinates, focus, *, zoom_default=6.4):
    """A view state that frames one link, or the whole network.

    Two hubs 1.6 km apart are half a pixel wide on a national view, so a link that
    was just drawn would be invisible.  Centring on the pair and zooming in shows
    the line for what it is.
    """

    if not focus:
        return None
    start = coordinates.get(focus.get("from_node"))
    end = coordinates.get(focus.get("to_node"))
    if start is None or end is None:
        return None

    span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    if span <= 0.01:
        zoom = 13.0
    elif span <= 0.05:
        zoom = 12.0
    elif span <= 0.2:
        zoom = 10.5
    elif span <= 0.5:
        zoom = 9.0
    elif span <= 1.5:
        zoom = 7.5
    else:
        zoom = zoom_default

    return {
        "longitude": (start[0] + end[0]) / 2.0,
        "latitude": (start[1] + end[1]) / 2.0,
        "zoom": zoom,
    }


def build_hub_map(
    scenario,
    *,
    highlight=None,
    inlet=None,
    routes=None,
    hidden=(),
    road=True,
    context=False,
    focus=None,
):
    """A map of the scenario's hubs, its links, and a clickable hub layer.

    ``routes`` are the *edited* link rows (``from_node``, ``to_node``, ``mode``), so
    a link appears on the map as soon as it is drawn or imported, before any run.
    ``hidden`` lists hub ids that are ticked off and must not be drawn.

    Every layer declares an ``id`` because ``st.pydeck_chart(on_select=...)`` keeps
    the selection per layer; the hub layer's data carries the node id, so a click
    can be mapped straight back to a hub.
    """

    try:
        import pydeck as pdk
    except Exception:  # pragma: no cover - pydeck is optional
        return None

    coordinates = hub_coordinates(scenario)
    hidden = set(hidden or ())
    if not coordinates:
        return None

    layers = []

    # the reference study's routes: context only, and off by default - a band of
    # grey lines along the coast tells the reader nothing about *this* scenario
    base = _load("routes.geojson")
    if base and context:
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"kind": "gis-route"},
                            "geometry": feature["geometry"],
                        }
                        for feature in base.get("features", [])
                    ],
                },
                id="gis",
                get_line_color=[140, 140, 140, 120],
                get_line_width=1,
                line_width_units=String("pixels"),
                pickable=False,
            )
        )

    # every link of the scenario, coloured by transport mode: along the GIS route
    # when the study has one, otherwise as the straight line between the hubs
    geometries = route_geometries()
    links = []
    for row in routes or []:
        start = str(row.get("from_node") or "")
        end = str(row.get("to_node") or "")
        if start in hidden or end in hidden:
            continue
        mode = str(row.get("mode") or "pipeline")
        line, source = _line_for(
            start, end, coordinates, geometries, mode=mode, road=road
        )
        if line is None:
            continue
        links.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "link",
                    "name": f"{start} \u2192 {end}",
                    "mode": mode,
                    "geometry": source,
                    "colour": MODE_COLOURS.get(mode, [130, 130, 130]),
                    "width": MODE_LINE_WIDTH.get(mode, 8),
                    "casing": MODE_LINE_WIDTH.get(mode, 8) + CASING_EXTRA_WIDTH,
                    "exact": source == "route",
                },
                "geometry": {"type": "LineString", "coordinates": line},
            }
        )
    if links:
        features = {"type": "FeatureCollection", "features": links}
        # A pale casing under the coloured core separates a link from the basemap
        # and from the reference routes.  Widths are PIXELS - the default (metres)
        # would make a 9 m line sub-pixel at this zoom.
        specs = (
            ("links-casing", CASING_COLOUR, "casing"),
            ("links", "properties.colour", "width"),
        )
        for layer_id, colour, width_key in specs:
            layers.append(
                pdk.Layer(
                    "GeoJsonLayer",
                    data=features,
                    id=layer_id,
                    get_line_color=colour,
                    get_line_width=f"properties.{width_key}",
                    # pydeck turns a plain Python string into a JS expression
                    # ("@@=pixels"), which evaluates to undefined and silently
                    # restores deck's default units - hence pydeck.types.String
                    line_width_units=String("pixels"),
                    pickable=layer_id == "links",
                )
            )

    # the hubs themselves: one point each, coloured by role.  A ScatterplotLayer is
    # used rather than a GeoJsonLayer because its radius is a real pixel size and
    # its picking is what `st.pydeck_chart(on_select=...)` relies on.
    kinds = {"storage": "storage", "geothermal": "storage", "port": "port"}
    points = [
        {
            "id": node.id,
            "name": node.name,
            "position": list(coordinates[node.id]),
            "kind": kinds.get(node.kind.value, "other"),
        }
        for node in scenario.nodes
        if node.id in coordinates and node.id not in hidden
    ]
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=points,
            id="hubs",
            get_position="position",
            get_radius=6.0,
            get_fill_color=[44, 62, 80, 255],
            get_line_color=[255, 255, 255],
            stroked=True,
            line_width_min_pixels=1,
            radius_min_pixels=HUB_RADIUS_PX,
            radius_max_pixels=22,
            pickable=True,
        )
    )

    # the inlet already chosen, so the second click has a visible origin
    if inlet and inlet in coordinates:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=[{"id": inlet, "name": inlet, "position": list(coordinates[inlet])}],
                id="inlet",
                get_position="position",
                get_radius=12.0,
                get_fill_color=HIGHLIGHT_COLOUR,
                get_line_color=[255, 255, 255],
                stroked=True,
                line_width_min_pixels=2,
                radius_min_pixels=13,
                radius_max_pixels=26,
                pickable=False,
            )
        )

    # one existing link, drawn on top so it can be recognised
    if highlight:
        start = coordinates.get(highlight.get("from_node"))
        end = coordinates.get(highlight.get("to_node"))
        if start is not None and end is not None:
            layers.append(
                pdk.Layer(
                    "GeoJsonLayer",
                    data={
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"kind": "highlight"},
                                "geometry": {
                                    "type": "LineString",
                                    "coordinates": [list(start), list(end)],
                                },
                            }
                        ],
                    },
                    id="highlight",
                    get_line_color=HIGHLIGHT_COLOUR,
                    get_line_width=6,
                    line_width_units=String("pixels"),
                    pickable=False,
                )
            )

    focused = _focus_view(coordinates, focus)
    if focused is not None:
        return pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(pitch=0, **focused),
            map_style=BASEMAP,
            tooltip={"text": "{name}"},
        )

    longitudes = [lon for lon, _ in coordinates.values()]
    latitudes = [lat for _, lat in coordinates.values()]
    visible = [
        coordinates[node.id]
        for node in scenario.nodes
        if node.id in coordinates and node.id not in hidden
    ]
    if visible:
        longitudes = [lon for lon, _ in visible]
        latitudes = [lat for _, lat in visible]
    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            longitude=sum(longitudes) / len(longitudes),
            latitude=sum(latitudes) / len(latitudes),
            zoom=6.4,
            pitch=0,
        ),
        map_style=BASEMAP,
        tooltip={"text": "{name}"},
    )


__all__ = [
    "BASEMAP",
    "GIS_DIR",
    "OSRM_BASE",
    "build_hub_map",
    "build_network_map",
    "hub_coordinates",
    "road_length_km",
    "road_polyline",
    "route_geometries",
]