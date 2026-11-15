"""Dynamic CO2 emitters: staggered onboarding and time-varying emission curves."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Sequence

from pydantic import Field, model_validator

from .base import CoreModel, Slug, interp_year


class EmissionCurve(CoreModel):
    """Annual gross CO2 emission profile of a single emitter.

    Three curve families are supported so that legacy scenarios keep working:

    * ``constant`` – one value for every year;
    * ``piecewise_linear`` – explicit ``{year: t/yr}`` control points; this is the
      canonical way to describe ramp-up, steady state and decline;
    * ``polynomial`` – the legacy ``E(t) = E0 + a * E0 * (t - t0) ** c`` shape.
    """

    kind: Literal["constant", "piecewise_linear", "polynomial"]
    constant_t_per_year: float | None = None
    points: dict[int, float] | None = None
    polynomial_a: float = 0.0
    polynomial_c: float = 1.0
    reference_year: int | None = None
    zero_outside_points: bool = True

    @model_validator(mode="after")
    def _check_family(self) -> "EmissionCurve":
        if self.kind == "constant":
            if self.constant_t_per_year is None:
                raise ValueError("constant curve requires constant_t_per_year")
            if self.constant_t_per_year < 0.0:
                raise ValueError("constant emissions must be non-negative")
        elif self.kind == "piecewise_linear":
            if not self.points:
                raise ValueError("piecewise_linear curve requires at least one point")
            if len(self.points) < 2:
                raise ValueError("piecewise_linear curve requires at least two points")
            years = sorted(self.points)
            if len(set(years)) != len(years):
                raise ValueError("control-point years must be unique")
            if any(value < 0.0 for value in self.points.values()):
                raise ValueError("control-point emissions must be non-negative")
        elif self.kind == "polynomial":
            if self.polynomial_c <= 0.0:
                raise ValueError("polynomial exponent c must be positive")
        else:  # pragma: no cover - Literal guards this
            raise ValueError(f"unsupported emission curve kind: {self.kind}")
        return self

    @classmethod
    def constant(cls, t_per_year: float) -> "EmissionCurve":
        return cls(kind="constant", constant_t_per_year=float(t_per_year))

    @classmethod
    def piecewise(cls, points: dict[int, float]) -> "EmissionCurve":
        return cls(kind="piecewise_linear", points=dict(points))

    @classmethod
    def ramp(
        cls,
        *,
        start_year: int,
        start_t_per_year: float,
        plateau_year: int,
        plateau_t_per_year: float,
        decline_year: int | None = None,
        decline_t_per_year: float = 0.0,
    ) -> "EmissionCurve":
        """Convenience builder for the classic ramp → steady → decline shape."""

        points = {
            int(start_year): float(start_t_per_year),
            int(plateau_year): float(plateau_t_per_year),
        }
        if decline_year is not None:
            points[int(decline_year)] = float(decline_t_per_year)
        return cls.piecewise(points)

    @classmethod
    def polynomial(
        cls,
        *,
        base_t_per_year: float,
        reference_year: int,
        a: float = 0.0,
        c: float = 1.0,
    ) -> "EmissionCurve":
        return cls(
            kind="polynomial",
            constant_t_per_year=float(base_t_per_year),
            reference_year=int(reference_year),
            polynomial_a=float(a),
            polynomial_c=float(c),
        )

    def value_at(self, year: int) -> float:
        """Return the gross emission rate (t CO2/yr) for one calendar year."""

        year = int(year)
        if self.kind == "constant":
            return float(self.constant_t_per_year or 0.0)

        if self.kind == "polynomial":
            base = float(self.constant_t_per_year or 0.0)
            reference = int(self.reference_year or 0)
            return max(0.0, base + self.polynomial_a * base * (year - reference) ** self.polynomial_c)

        assert self.points is not None
        if self.zero_outside_points:
            years = sorted(self.points)
            if year < years[0] or year > years[-1]:
                return 0.0
        return interp_year(self.points, year)

    def to_series(self, years: Sequence[int]) -> list[float]:
        return [self.value_at(int(year)) for year in years]


class CaptureTechnology(str, Enum):
    """Capture technology codes retained from the legacy domain model."""

    POST_INFRASTRUCTURE = "PI"
    NITROGEN_DERIVED = "NI"
    OXY_FUEL = "OXY"


class CaptureUnit(CoreModel):
    """Capture plant attached to one emitter."""

    name: str = Field(min_length=1)
    technology: CaptureTechnology | None = None
    capacity_t_per_year: float = Field(default=0.0, ge=0.0)
    capex_eur: float = Field(default=0.0, ge=0.0)
    opex_eur_per_t: float = Field(default=0.0, ge=0.0)
    availability: float = Field(default=1.0, ge=0.0, le=1.0)
    commissioning_year: int
    decommission_year: int | None = None

    @model_validator(mode="after")
    def _check_window(self) -> "CaptureUnit":
        if self.decommission_year is not None and self.decommission_year < self.commissioning_year:
            raise ValueError("decommission_year must not precede commissioning_year")
        return self

    def available_capacity_t_per_year(self, year: int) -> float:
        """Capacity actually offered in ``year`` (0 outside the service window)."""

        year = int(year)
        if year < self.commissioning_year:
            return 0.0
        if self.decommission_year is not None and year > self.decommission_year:
            return 0.0
        return float(self.capacity_t_per_year) * float(self.availability)

    def active_in(self, year: int) -> bool:
        return self.available_capacity_t_per_year(year) > 0.0


class Emitter(CoreModel):
    """Industrial CO2 source with an onboarding year and an emission profile."""

    id: Slug
    name: str = Field(min_length=1)
    node_id: Slug = Field(description="Network node where captured CO2 enters the system.")
    activation_year: int = Field(description="First year the emitter can contribute.")
    decommission_year: int | None = None
    gross_emissions: EmissionCurve
    capture: CaptureUnit | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_window(self) -> "Emitter":
        if self.decommission_year is not None and self.decommission_year < self.activation_year:
            raise ValueError("decommission_year must not precede activation_year")
        if self.capture is not None and self.capture.commissioning_year < self.activation_year:
            raise ValueError("capture commissioning_year must not precede activation_year")
        return self

    def active_in(self, year: int) -> bool:
        """True when the emitter itself is online (independent of capture)."""

        year = int(year)
        if year < self.activation_year:
            return False
        return self.decommission_year is None or year <= self.decommission_year

    def available_emissions(self, year: int) -> float:
        """Gross CO2 generated in ``year`` (t/yr), zero before onboarding."""

        return self.gross_emissions.value_at(year) if self.active_in(year) else 0.0

    def captured_emissions(self, year: int) -> float:
        """CO2 offered to the transport network in ``year`` (t/yr).

        With a capture unit the offer is the smaller of the generated emissions
        and the capture capacity; without one the emitter is assumed to be a
        capture-ready source and all generated CO2 enters the network.
        """

        available = self.available_emissions(year)
        if available <= 0.0:
            return 0.0
        if self.capture is None:
            return available
        return min(available, self.capture.available_capacity_t_per_year(year))

    def emissions_series(self, years: Sequence[int]) -> list[float]:
        return [self.available_emissions(year) for year in years]

    def captured_series(self, years: Sequence[int]) -> list[float]:
        return [self.captured_emissions(year) for year in years]