"""One-off generator: build json/network.json and json/storage.json.

* network  <- data/gis/routes.geojson (12 links) + ccus_core.geo.crs (EPSG:3765)
* storage  <- the workbook "storage" sheet (22 sites) + derived reservoir defaults
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from ccus_core.geo.crs import from_wgs84
from ccus_core.io.catalogue import save_records
from ccus_core.io.excel_import import _XlsxReader, slugify as _slug

ROOT = Path(__file__).resolve().parent
GIS = ROOT / "data" / "gis"
WORKBOOK = ROOT / "docs" / "examples" / "CCS TABLICE 2015-2022 example.xlsx"

# ------------------------------------------------------------------- network
routes = json.loads((GIS / "routes.geojson").read_text(encoding="utf-8"))["features"]
network = []
for feature in routes:
    props = feature["properties"]
    coordinates = feature["geometry"]["coordinates"]
    points = [
        (float(coord[0]), float(coord[1]))
        for coord in coordinates
        if len(coord) >= 2
    ]
    mid = points[len(points) // 2] if points else (0.0, 0.0)
    lon, lat = mid
    x, y = from_wgs84(lon, lat)  # X = northing, Y = easting (EPSG:3765)
    route_id = str(props.get("route_id") or "").strip()
    from_node = str(props.get("from_node") or "")
    to_node = str(props.get("to_node") or "")
    network.append(
        {
            "id": route_id,
            "name": f"{route_id} · {from_node} → {to_node}",
            "kind": "pipeline",
            "from_node": from_node,
            "to_node": to_node,
            "x": round(x, 1),
            "y": round(y, 1),
            "elevation_m": round(
                (float(props.get("elevation_min_m") or 0.0) + float(props.get("elevation_max_m") or 0.0)) / 2.0,
                1,
            ),
            "elevation_min_m": props.get("elevation_min_m"),
            "elevation_max_m": props.get("elevation_max_m"),
            "length_km": round(float(props.get("length_m") or 0.0) / 1000.0, 2),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
        }
    )

save_records(
    ROOT / "json" / "network.json",
    network,
    list_key="records",
    meta={
        "_meta": {
            "schema": "gt-ccus-network/1.0",
            "source": "data/gis/routes.geojson (12 pipeline links, EPSG:3765)",
            "generated": "2026-11-16",
            "crs": "x = northing, y = easting (EPSG:3765); latitude/longitude in WGS84",
            "count": len(network),
        }
    },
)

# ------------------------------------------------------------------- storage
rows = _XlsxReader(WORKBOOK).sheet("storage")
storage = []
for number in sorted(rows):
    if number < 8:
        continue
    cells = {chr(ord("A") + index): value for index, value in enumerate(rows[number])}
    name = str(cells.get("C") or "").strip()
    site_type = str(cells.get("B") or "").strip().upper()
    depth = cells.get("H")
    capacity_mt = cells.get("I")
    if not name or site_type not in {"DSA", "DHF"} or depth in (None, "") or capacity_mt in (None, ""):
        continue
    depth_m = float(depth)
    capacity_t = float(capacity_mt) * 1e6
    storage.append(
        {
            "id": _slug(name),
            "name": name,
            "storage_type": site_type,
            "capacity_t": capacity_t,
            "depth_m": depth_m,
            "porosity": 0.20,
            "permeability_m2": 1.0e-13,
            "pressure_bar": round(0.1 * depth_m, 1),  # hydrostatic, 0.1 bar/m
            "temperature_c": round(15.0 + 0.035 * depth_m, 1),
            "lithology": (str(cells.get("G") or "").strip() or None),
            "fluid": (str(cells.get("E") or "").strip() or None),
            "onshore": "onshore" in str(cells.get("F") or "").lower(),
            "notes": "reservoir defaults: phi 0.20, k 100 mD, hydrostatic pressure, 15 + 0.035*z",
        }
    )

save_records(
    ROOT / "json" / "storage.json",
    storage,
    list_key="records",
    meta={
        "_meta": {
            "schema": "gt-ccus-storage/1.0",
            "source": "docs/examples/CCS TABLICE 2015-2022 example.xlsx, sheet 'storage'",
            "generated": "2026-11-16",
            "note": (
                "capacity from the workbook (Mt); porosity, permeability, pressure and "
                "temperature are derived defaults (0.20, 100 mD, 0.1 bar/m, 15 + 0.035*z)"
            ),
            "count": len(storage),
        }
    },
)

print("network:", len(network), "links")
for item in network[:3]:
    print("  ", item["id"], item["name"], item["kind"], item["x"], item["y"], item["elevation_m"])
print("storage:", len(storage), "sites")
for item in storage[:3]:
    print("  ", item["id"], item["name"], item["storage_type"], item["capacity_t"], item["depth_m"])