# GT-CCUS GIS data (extracted)

Generated from `..\_mvp_zip\MVProbni_01_B_x`.

| Item | Value |
|---|---|
| routes | 12 |
| hubs | 33 |
| CRS | EPSG:3765 (HTRS96/TM) |
| WGS84 | converted with `ccus_core.geo.crs` (Krüger series) |

Projected coordinates are HTRS96/TM (EPSG:3765, X=northing, Y=easting); WGS84 is derived with `ccus_core.geo.crs`.

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
