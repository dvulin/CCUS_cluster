"""Shared value objects and helpers for the UI-agnostic CCUS core.

Nothing in :mod:`ccus_core` may import a UI framework, a plotting library or a
database driver.  The models in this package accept plain Python/JSON input and
return plain Python/Pydantic output so that Streamlit, a desktop application or
Excel can all share the same engine.
"""

from __future__ import annotations

import re
from typing import Annotated, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

MODEL_VERSION = "1.0"

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

Slug = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=_ID_PATTERN.pattern,
        description="Stable identifier usable in JSON, URLs and file names.",
    ),
]

__all__ = [
    "MODEL_VERSION",
    "Slug",
    "CoreModel",
    "TimeStep",
    "interp_year",
    "year_axis",
    "positive",
    "fraction",
    "unit_fraction",
]


class CoreModel(BaseModel):
    """Base model: strict JSON schema, no silent extra fields."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )


TimeStep = Annotated[str, Field(description="Simulation step: 'yearly' or 'monthly'.")]


def positive(name: str):
    """Return a ``Field`` for a strictly positive finite number."""

    return Field(gt=0.0, description=f"{name} must be a strictly positive number.")


def fraction(name: str):
    """Return a required ``Field`` for a number in the closed unit interval."""

    return Field(ge=0.0, le=1.0, description=f"{name} must be between 0 and 1.")


def unit_fraction(name: str, default: float = 1.0):
    """Return an optional ``Field`` for a 0–1 factor that defaults to full availability."""

    return Field(default=default, ge=0.0, le=1.0, description=f"{name} must be between 0 and 1.")


def year_axis(start_year: int, end_year: int, step_years: int = 1) -> list[int]:
    """Return the inclusive calendar-year axis used by the solver."""

    if end_year < start_year:
        raise ValueError("end_year must not precede start_year")
    if step_years < 1:
        raise ValueError("step_years must be at least 1")
    return list(range(int(start_year), int(end_year) + 1, int(step_years)))


def interp_year(
    points: dict[int, float],
    year: int,
    *,
    before: float | None = None,
    after: float | None = None,
) -> float:
    """Piecewise-linear interpolation over ``{year: value}`` control points.

    ``before``/``after`` define the value outside the control-point range; when
    they are ``None`` the first/last control value is held constant, which is the
    behaviour of the existing annual ledger helper.
    """

    if not points:
        raise ValueError("At least one control point is required.")
    years = sorted(points)
    if year <= years[0]:
        return float(points[years[0]]) if before is None else float(before)
    if year >= years[-1]:
        return float(points[years[-1]]) if after is None else float(after)
    for lower, upper in zip(years, years[1:]):
        if lower <= year <= upper:
            span = upper - lower
            if span == 0:
                return float(points[upper])
            weight = (year - lower) / span
            return float(points[lower] * (1.0 - weight) + points[upper] * weight)
    raise AssertionError("unreachable")  # pragma: no cover


def series_from_profile(
    profile: "object",
    years: Sequence[int],
) -> list[float]:
    """Sample any object exposing ``value_at(year)`` on a year axis."""

    return [float(profile.value_at(int(year))) for year in years]


def flatten_unique(values: Iterable[object]) -> list[object]:
    """Return values in first-seen order without duplicates."""

    seen: dict[object, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)