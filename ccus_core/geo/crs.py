"""Coordinate reference systems used by the CCUS cluster.

The route geometries shipped with the STRATEGY CCUS package are projected in
metres on the Croatian national grid (HTRS96/TM, EPSG:3765: central meridian
15°E, false easting 2 500 000 m, scale 0.9999, GRS80).  That assignment is an
**assumption to be confirmed** against a known emitter; every conversion here is
reversible and lives in one place, so a wrong assumption is a one-line fix.

Formulas: Snyder (USGS PP-1395) Transverse Mercator, series to A⁵/D⁶, with a
consistent e²-based meridional arc in both directions.  Accuracy is millimetres
in this region, far beyond the GIS data.
"""

from __future__ import annotations

import math

# GRS80 ellipsoid
_A = 6378137.0
_F = 1.0 / 298.257222101
_LON0 = 15.0
_X0 = 2_500_000.0
_Y0 = 0.0
_K0 = 0.9999
CRS_NAME = "EPSG:3765 (HTRS96/TM, assumed)"

_E2 = 2.0 * _F - _F * _F
_E4 = _E2 * _E2
_E6 = _E4 * _E2
_EP2 = _E2 / (1.0 - _E2)
_E1 = (1.0 - math.sqrt(1.0 - _E2)) / (1.0 + math.sqrt(1.0 - _E2))

# Snyder eq. 3-21 coefficients
_MU0 = 1.0 - _E2 / 4.0 - 3.0 * _E4 / 64.0 - 5.0 * _E6 / 256.0
_MU2 = 3.0 * _E2 / 8.0 + 3.0 * _E4 / 32.0 + 45.0 * _E6 / 1024.0
_MU4 = 15.0 * _E4 / 256.0 + 45.0 * _E6 / 1024.0
_MU6 = 35.0 * _E6 / 3072.0


def _meridional_arc(lat_rad: float) -> float:
    """Distance from the equator to ``lat`` along the meridian (Snyder 3-21)."""

    return _A * (
        _MU0 * lat_rad
        - _MU2 * math.sin(2.0 * lat_rad)
        + _MU4 * math.sin(4.0 * lat_rad)
        - _MU6 * math.sin(6.0 * lat_rad)
    )


def from_wgs84(longitude: float, latitude: float) -> tuple[float, float]:
    """WGS84 ``(lon, lat)`` → projected ``(X=northing, Y=easting)`` in metres."""

    lat = math.radians(float(latitude))
    lon = math.radians(float(longitude) - _LON0)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    tan_lat = math.tan(lat)
    nu = _A / math.sqrt(1.0 - _E2 * sin_lat * sin_lat)
    t = tan_lat * tan_lat
    c = _EP2 * cos_lat * cos_lat
    a = cos_lat * lon

    easting = _X0 + _K0 * nu * (
        a
        + (1.0 - t + c) * a**3 / 6.0
        + (5.0 - 18.0 * t + t * t + 72.0 * c - 58.0 * _EP2) * a**5 / 120.0
    )
    northing = _Y0 + _K0 * (
        _meridional_arc(lat)
        + nu
        * tan_lat
        * (
            a * a / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c * c) * a**4 / 24.0
            + (61.0 - 58.0 * t + t * t + 600.0 * c) * a**6 / 720.0
        )
    )
    return northing, easting


def _footpoint_latitude(northing: float) -> float:
    """Footpoint latitude from the meridional arc (Snyder 3-26)."""

    mu = (northing - _Y0) / (_K0 * _A * _MU0)
    e1 = _E1
    return (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1**2 / 16.0 - 55.0 * e1**4 / 32.0) * math.sin(4.0 * mu)
        + (151.0 * e1**3 / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * e1**4 / 512.0) * math.sin(8.0 * mu)
    )


def to_wgs84(northing: float, easting: float) -> tuple[float, float]:
    """Projected ``(X=northing, Y=easting)`` → WGS84 ``(longitude, latitude)``."""

    x = float(easting) - _X0
    y = float(northing) - _Y0

    lat1 = _footpoint_latitude(float(northing))
    sin1 = math.sin(lat1)
    cos1 = math.cos(lat1)
    tan1 = math.tan(lat1)
    nu1 = _A / math.sqrt(1.0 - _E2 * sin1 * sin1)
    t1 = tan1 * tan1
    c1 = _EP2 * cos1 * cos1
    r1 = _A * (1.0 - _E2) / (1.0 - _E2 * sin1 * sin1) ** 1.5
    d = x / (nu1 * _K0)

    lat = lat1 - (nu1 * tan1 / r1) * (
        d**2 / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1 * c1 - 9.0 * _EP2) * d**4 / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1 * t1 - 252.0 * _EP2 - 3.0 * c1 * c1)
        * d**6
        / 720.0
    )
    lon = _LON0 + math.degrees(
        (
            d
            - (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
            + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1 * c1 + 8.0 * _EP2 + 24.0 * t1 * t1)
            * d**5
            / 120.0
        )
        / cos1
    )
    return lon, math.degrees(lat)


def is_projected_crs_3765() -> bool:
    """The CRS assumption used for the shipped geometries."""

    return True


__all__ = ["CRS_NAME", "from_wgs84", "to_wgs84", "is_projected_crs_3765"]