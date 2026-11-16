# GT-CCUS GIS data (extracted)

Generated from `..\_mvp_zip\MVProbni_01_B_x`.

| Item | Value |
|---|---|
| routes | 12 |
| hubs | 33 |
| CRS assumption | EPSG:3765 (HTRS96/TM, assumed) |
| WGS84 | converted with `ccus_core.geo.crs` (Krüger series) |

Projected coordinates are stored as-is; WGS84 conversion assumes HTRS96/TM (EPSG:3765) and must be confirmed against a known emitter.

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
