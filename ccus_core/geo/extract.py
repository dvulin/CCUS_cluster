"""Extract every GIS layer of a STRATEGY CCUS package into a portable folder.

Usage (Tier 1)::

    python -m ccus_core.geo.extract <package_dir> <out_dir>

The output folder contains:

* ``routes.geojson``      – every pipeline route (WGS84 geometry + projected
  coordinates, elevation range, land-use shares, cumulative cost),
* ``hubs.geojson``        – hub points with their transport options,
* ``manifest.json``       – provenance, CRS, counts,
* ``README.md``           – how to reuse the data.

Tier 2 (geopandas/pyproj) can read the same folder without the original package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import crs
from .routes import RouteGeometry, load_routes, write_geojson


@dataclass
class ExtractResult:
    routes: int = 0
    hubs: int = 0
    output: Path | None = None


def extract(package: str | Path, out_dir: str | Path) -> ExtractResult:
    package = Path(package)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gis_dir = package / "Transport" / "GISfiles"
    if not gis_dir.is_dir():
        gis_dir = package / "GISfiles"
    routes = load_routes(gis_dir) if gis_dir.is_dir() else []

    write_geojson(routes, out_dir / "routes.geojson")
    for route in routes:
        write_geojson([route], out_dir / "routes" / f"{route.geometry_id}.geojson")

    hubs = _extract_hubs(package)
    if hubs:
        (out_dir / "hubs.geojson").write_text(
            json.dumps(_collection(hubs), indent=1), encoding="utf-8"
        )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_package": str(package),
        "crs": crs.CRS_NAME,
        "crs_note": (
            "Projected coordinates are HTRS96/TM (EPSG:3765, X=northing, "
            "Y=easting); WGS84 is derived with ccus_core.geo.crs."
        ),
        "routes": len(routes),
        "hubs": len(hubs),
        "route_ids": [route.route_id for route in routes],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    (out_dir / "README.md").write_text(_readme(manifest), encoding="utf-8")
    return ExtractResult(routes=len(routes), hubs=len(hubs), output=out_dir)


def _extract_hubs(package: Path) -> list[dict]:
    """Read the ``Hubs`` sheet of ``ScenarioManager.xlsx`` (if present)."""

    manager = package / "ScenarioManager.xlsx"
    if not manager.is_file():
        return []
    try:
        from ccus_core.io.excel_import import _XlsxReader

        rows = _XlsxReader(manager).sheet("Hubs")
    except Exception:  # noqa: BLE001 - the workbook is optional
        return []

    header = rows.get(1, [])
    if not header:
        return []

    points: list[dict] = []
    for number in sorted(rows):
        if number < 2:
            continue
        values = rows[number]
        hub_id = _text(_cell(values, 0))
        lat = _number(_cell(values, 1))
        lon = _number(_cell(values, 2))
        if not hub_id or lat is None or lon is None:
            continue
        points.append(
            {
                "type": "Feature",
                "properties": {
                    "hub_id": hub_id,
                    "country": hub_id.split(".")[0],
                    "lat": lat,
                    "lon": lon,
                    "storage_options": _text(_cell(values, 21)),
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    return points


def _collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "name": "ccus_hubs", "features": features}


def _readme(manifest: dict) -> str:
    return f"""# GT-CCUS GIS data (extracted)

Generated from `{manifest['source_package']}`.

| Item | Value |
|---|---|
| routes | {manifest['routes']} |
| hubs | {manifest['hubs']} |
| CRS | {manifest['crs']} |
| WGS84 | converted with `ccus_core.geo.crs` (Krüger series) |

{manifest['crs_note']}

## Files

* `routes.geojson` – all routes, one LineString each, with elevation range,
  land-use shares and cumulative cost in the properties.
* `routes/Pxx.geojson` – one file per route.
* `hubs.geojson` – hub points with their storage options.
* `manifest.json` – provenance and counts.

## Reuse

```python
import json
from pathlib import Path

routes = json.loads(Path("routes.geojson").read_text(encoding="utf-8"))
```

The data is read-only for the engine: `ccus_core` never writes back to it.
"""


def _cell(row: list, index: int):
    return row[index] if index < len(row) else None


def _text(value) -> str:
    return "" if value is None else str(value).strip()


def _number(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("usage: python -m ccus_core.geo.extract <package_dir> <out_dir>")
        raise SystemExit(2)
    result = extract(sys.argv[1], sys.argv[2])
    print(f"routes={result.routes} hubs={result.hubs} -> {result.output}")