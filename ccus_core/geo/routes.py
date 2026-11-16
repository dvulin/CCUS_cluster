"""Read the transport GIS files (elevation profile + land use) into GeoJSON.

File convention (STRATEGY CCUS package)::

    P01 HRES002_to_HRCH003_EP.csv   → id, XCoord, YCoord, COST, ELEV, Distance
    P01 HRES002_to_HRCH003_TF.csv   → Land Use, Length (%), TF_CLASS, lengths

The elevation profile gives the route polyline (metres, projected CRS), the
elevation along it and the cumulative cost; the land-use table gives the terrain
composition used for cost/permit factors.  Both are kept so Tier-2 analysis can
work without the original workbook.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import crs

FILENAME_RE = re.compile(r"^(?P<id>P\d+)\s+(?P<from>\w+)_to_(?P<to>\w+)_(?P<kind>EP|TF)\.csv$")


@dataclass
class RouteGeometry:
    """One transport route with its profile and land-use composition."""

    route_id: str
    from_node: str
    to_node: str
    projected: list[tuple[float, float]] = field(default_factory=list)
    elevations_m: list[float] = field(default_factory=list)
    distances_m: list[float] = field(default_factory=list)
    cumulative_cost: float = 0.0
    land_use: dict[str, float] = field(default_factory=dict)
    source_ep: str | None = None
    source_tf: str | None = None

    @property
    def length_m(self) -> float:
        return float(self.distances_m[-1]) if self.distances_m else 0.0

    @property
    def geometry_id(self) -> str:
        """Unique id of the route (the package reuses ``P01`` for two directions)."""

        return f"{self.route_id}-{self.from_node}-{self.to_node}"

    @property
    def elevation_range_m(self) -> tuple[float, float]:
        if not self.elevations_m:
            return (0.0, 0.0)
        return (min(self.elevations_m), max(self.elevations_m))

    def wgs84(self) -> list[tuple[float, float]]:
        """Polyline in WGS84, converted from HTRS96/TM (EPSG:3765)."""

        return [crs.to_wgs84(x, y) for x, y in self.projected]

    def properties(self) -> dict[str, object]:
        low, high = self.elevation_range_m
        return {
            "route_id": self.route_id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "length_m": round(self.length_m, 1),
            "elevation_min_m": round(low, 1),
            "elevation_max_m": round(high, 1),
            "elevation_gain_m": round(high - low, 1),
            "cost_total": round(float(self.cumulative_cost), 1),
            "land_use": {key: round(value, 2) for key, value in sorted(self.land_use.items())},
            "crs": crs.CRS_NAME,
            "crs_source": "EP/TF geometry",
        }

    def to_geojson(self) -> dict:
        coordinates = [[lon, lat] for lon, lat in self.wgs84()]
        return {
            "type": "Feature",
            "properties": self.properties(),
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_route(ep_path: str | Path, tf_path: str | Path | None = None) -> RouteGeometry:
    """Parse one route from its EP file and optional TF file."""

    ep_path = Path(ep_path)
    match = FILENAME_RE.match(ep_path.name)
    if match is None:
        raise ValueError(f"unexpected elevation-profile file name: {ep_path.name}")

    route = RouteGeometry(
        route_id=match.group("id"),
        from_node=match.group("from"),
        to_node=match.group("to"),
        source_ep=str(ep_path),
    )
    for row in _read_csv(ep_path):
        x = _as_float(row.get("XCoord"))
        y = _as_float(row.get("YCoord"))
        if x is None or y is None:
            continue
        route.projected.append((x, y))
        route.elevations_m.append(_as_float(row.get("ELEV")) or 0.0)
        route.distances_m.append(_as_float(row.get("Distance")) or 0.0)
        route.cumulative_cost = _as_float(row.get("COST")) or route.cumulative_cost

    if tf_path is not None:
        route.source_tf = str(tf_path)
        route.land_use = parse_land_use(Path(tf_path))
    return route


def parse_land_use(tf_path: str | Path) -> dict[str, float]:
    """Land-use composition of one route (class → length share in %)."""

    shares: dict[str, float] = {}
    current = ""
    for row in _read_csv(Path(tf_path)):
        label = _text(row.get("Land Use")) or _text(row.get("TF_CLASS"))
        if label:
            current = label
        share = _as_float(row.get("Length (%)"))
        if share is not None and current:
            shares[current] = shares.get(current, 0.0) + share
    return shares


def load_routes(directory: str | Path) -> list[RouteGeometry]:
    """Load every route found in ``directory`` (matched EP/TF pairs)."""

    root = Path(directory)
    routes: list[RouteGeometry] = []
    for ep_path in sorted(root.glob("*_EP.csv")):
        match = FILENAME_RE.match(ep_path.name)
        if match is None:
            continue
        tf_path = root / f"{match.group('id')} {match.group('from')}_to_{match.group('to')}_TF.csv"
        routes.append(parse_route(ep_path, tf_path if tf_path.exists() else None))
    return routes


def feature_collection(routes: list[RouteGeometry]) -> dict:
    """GeoJSON FeatureCollection of every route."""

    return {
        "type": "FeatureCollection",
        "name": "ccus_routes",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [route.to_geojson() for route in routes],
    }


def write_geojson(routes: list[RouteGeometry], target: str | Path) -> Path:
    """Write all routes as one GeoJSON file."""

    import json

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(feature_collection(routes), indent=1), encoding="utf-8")
    return target


# --------------------------------------------------------------------- helpers
def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


__all__ = [
    "RouteGeometry",
    "parse_route",
    "parse_land_use",
    "load_routes",
    "feature_collection",
    "write_geojson",
]