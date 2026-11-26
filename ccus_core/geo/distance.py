"""Great-circle distance between two points (no UI, no I/O).

A link drawn on the map needs a length before a GIS expert measures it, and the
engine needs a length for every corridor.  Both use the same formula, so it lives
here rather than in the front end.
"""

from __future__ import annotations

import math

#: mean Earth radius (IUGG), km
EARTH_RADIUS_KM = 6371.0


def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometres.

    ``0.0`` for two identical points.  This is the straight-line estimate a map can
    offer; a pipeline or road is longer, and the editable distance field is where a
    GIS measurement replaces it.
    """

    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    d_phi = phi2 - phi1
    d_lambda = math.radians(float(lon2) - float(lon1))
    arc = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    return EARTH_RADIUS_KM * 2.0 * math.asin(min(1.0, math.sqrt(arc)))


def path_length_km(coordinates) -> float:
    """Length of a polyline in kilometres.

    ``coordinates`` is a sequence of ``(longitude, latitude)`` pairs - the shape a
    routing service returns and the shape the map draws.  Summing the segments gives
    the distance a road (or pipeline) really covers, which is what a cost model
    needs, rather than the straight line between its endpoints.
    """

    points = [(float(pair[0]), float(pair[1])) for pair in coordinates or [] if len(pair) >= 2]
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(points, points[1:]):
        total += great_circle_km(lat1, lon1, lat2, lon2)
    return total


__all__ = ["EARTH_RADIUS_KM", "great_circle_km", "path_length_km"]