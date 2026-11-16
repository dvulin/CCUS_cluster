"""Build a pydeck map (OpenStreetMap-based basemap) for the scenario network.

Tier 1 of the GIS work: the extracted STRATEGY CCUS routes (``data/gis``) give
context, and the scenario's own edges are drawn on top using the node
coordinates.  No new dependency is required – pydeck ships with Streamlit.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
GIS_DIR = HERE / "data" / "gis"
BASEMAP = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"

MODE_COLOURS = {
    "pipeline": [31, 119, 180],
    "truck": [230, 126, 34],
    "rail": [44, 160, 44],
    "marine": [23, 190, 207],
}


def _load(name: str) -> dict | None:
    path = GIS_DIR / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_network_map(snapshot, scenario, *, year: int | None = None):
    """Return a ``pydeck.Deck`` or ``None`` when the data is insufficient."""

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
    coordinates: dict[str, tuple[float, float]] = {}
    for node in scenario.nodes:
        if node.location.latitude is None or node.location.longitude is None:
            continue
        coordinates[node.id] = (float(node.location.longitude), float(node.location.latitude))

    lines: list[dict] = []
    for edge in snapshot.edges:
        start = coordinates.get(edge["from_node"])
        end = coordinates.get(edge["to_node"])
        if start is None or end is None:
            continue
        colour = MODE_COLOURS.get(edge["mode"] or "", [130, 130, 130])
        lines.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "scenario-edge",
                    "mode": edge["mode"],
                    "flow_t": edge["flow_t"],
                    "colour": colour,
                },
                "geometry": {"type": "LineString", "coordinates": [list(start), list(end)]},
            }
        )

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
                get_line_width="properties.flow_t",
                get_line_width_min_pixels=1,
                get_line_width_max_pixels=8,
                pickable=True,
            )
        )
    if points:
        features.append(
            pdk.Layer(
                "GeoJsonLayer",
                data={"type": "FeatureCollection", "features": points},
                get_point_radius="properties.kind",
                get_fill_color=[44, 62, 80, 220],
                point_radius_min_pixels=5,
                pickable=True,
            )
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


__all__ = ["BASEMAP", "GIS_DIR", "build_network_map"]