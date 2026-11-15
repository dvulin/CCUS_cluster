"""Time-dependent, multi-modal transport edges with infrastructure upgrades.

An edge is a directed connection between two nodes.  Its state is a *schedule*:
trucks may serve a route for the first three years and be replaced by a pipeline
in year four.  A state also carries the capacity and the tariff that the routing
engine must respect for the years in which it is active.

Two mechanisms express change over time:

* ``states`` â€“ a planned, year-based timeline (the deterministic upgrade case);
* ``upgrades`` â€“ a conditional trigger (``year`` and/or ``cumulative_mass``) that
  supersedes the timeline once it fires (the "build a pipeline when more than
  X Mt has been shipped" case).  Because a mass trigger can only be evaluated
  chronologically, the solver records the firing year and feeds it back through
  ``fired_upgrades``; the model itself stays free of solver state.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Mapping

from pydantic import Field, model_validator

from .base import CoreModel, Slug, fraction, positive, unit_fraction


class TransportMode(str, Enum):
    PIPELINE = "pipeline"
    TRUCK = "truck"
    RAIL = "rail"
    MARINE = "marine"


class PipelineDesign(CoreModel):
    """Geometry and boundary conditions of a CO2 pipeline state."""

    inner_diameter_m: float = positive("inner_diameter_m")
    roughness_m: float = Field(default=4.5e-5, ge=0.0)
    elbows_90_count: int = Field(default=0, ge=0)
    elbows_45_count: int = Field(default=0, ge=0)
    elbows_30_count: int = Field(default=0, ge=0)
    inlet_pressure_bar: float = positive("inlet_pressure_bar")
    inlet_temperature_c: float
    environment_type: Literal["soil", "air"] = "soil"
    ambient_temperature_c: float = 12.0
    burial_depth_m: float = Field(default=1.0, ge=0.0)
    wall_thickness_m: float = Field(default=0.01, gt=0.0)
    wall_thermal_conductivity_w_m_k: float = Field(default=45.0, gt=0.0)
    insulation_thickness_m: float = Field(default=0.05, ge=0.0)
    insulation_thermal_conductivity_w_m_k: float = Field(default=0.035, gt=0.0)
    external_heat_transfer_coefficient_w_m2_k: float = Field(default=10.0, gt=0.0)
    environment_thermal_conductivity_w_m_k: float = Field(default=1.5, gt=0.0)
    environment_volumetric_heat_capacity_j_m3_k: float = Field(default=2.0e6, gt=0.0)

    @property
    def elbow_counts(self) -> dict[int, int]:
        return {
            90: int(self.elbows_90_count),
            45: int(self.elbows_45_count),
            30: int(self.elbows_30_count),
        }


class MarineDesign(CoreModel):
    """Shipping constraints: vessel size, port hub and weather downtime."""

    vessel_capacity_t: float = positive("vessel_capacity_t")
    voyages_per_vessel_per_year: float = positive("voyages_per_vessel_per_year")
    vessels: int = Field(default=1, ge=1)
    port_node_id: Slug
    load_days: float = Field(default=2.0, gt=0.0)
    unload_days: float = Field(default=2.0, gt=0.0)
    one_way_voyage_days: float = Field(default=3.0, gt=0.0)
    weather_availability: float = unit_fraction("weather_availability")

    def cycle_days(self) -> float:
        return float(self.load_days + self.unload_days + 2.0 * float(self.one_way_voyage_days))

    def nominal_capacity_t_per_year(self) -> float:
        return float(self.vessel_capacity_t) * float(self.voyages_per_vessel_per_year) * float(self.vessels)

    def effective_capacity_t_per_year(self) -> float:
        """Capacity after weather downtime (deterministic derating)."""

        return self.nominal_capacity_t_per_year() * float(self.weather_availability)


class RoadDesign(CoreModel):
    """Truck or rail fleet description used for capacity and fleet sizing."""

    vehicle_capacity_t: float = positive("vehicle_capacity_t")
    trips_per_vehicle_per_day: float = positive("trips_per_vehicle_per_day")
    working_days_per_year: float = Field(default=250.0, gt=0.0, le=366.0)
    fleet_size: int | None = Field(default=None, ge=1)
    availability: float = unit_fraction("availability")

    def annual_capacity_per_vehicle_t(self) -> float:
        return (
            float(self.vehicle_capacity_t)
            * float(self.trips_per_vehicle_per_day)
            * float(self.working_days_per_year)
            * float(self.availability)
        )

    def required_fleet_size(self, annual_t: float) -> int:
        """Smallest integer fleet that can move ``annual_t`` tonnes per year."""

        per_vehicle = self.annual_capacity_per_vehicle_t()
        if per_vehicle <= 0.0:
            raise ValueError("vehicle capacity, trips or working days must be positive")
        if annual_t <= 0.0:
            return 0
        return int(-(-annual_t // per_vehicle))  # ceil without float noise

    def effective_capacity_t_per_year(self) -> float:
        if self.fleet_size is None:
            raise ValueError("fleet_size is required to derive road capacity")
        return self.annual_capacity_per_vehicle_t() * float(self.fleet_size)


class EdgeState(CoreModel):
    """One transport state of an edge over a contiguous year window."""

    mode: TransportMode
    valid_from_year: int
    valid_until_year: int | None = None
    capacity_t_per_year: float | None = Field(
        default=None,
        gt=0.0,
        description="Explicit capacity; when omitted it is derived from the mode design.",
    )
    distance_km: float = Field(default=0.0, ge=0.0)
    capex_eur: float = Field(default=0.0, ge=0.0)
    opex_eur_per_t: float = Field(default=0.0, ge=0.0)
    opex_eur_per_tkm: float = Field(default=0.0, ge=0.0)
    availability: float = unit_fraction("availability")
    pipeline: PipelineDesign | None = None
    marine: MarineDesign | None = None
    road: RoadDesign | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "EdgeState":
        if self.valid_until_year is not None and self.valid_until_year < self.valid_from_year:
            raise ValueError("valid_until_year must not precede valid_from_year")
        if self.mode is TransportMode.PIPELINE and self.pipeline is None:
            raise ValueError("a pipeline state requires its PipelineDesign")
        if self.mode is TransportMode.MARINE:
            if self.marine is None:
                raise ValueError("a marine state requires its MarineDesign")
        if self.mode in (TransportMode.TRUCK, TransportMode.RAIL) and self.road is None:
            raise ValueError("a road/rail state requires its RoadDesign")
        if self.mode is not TransportMode.MARINE and self.distance_km <= 0.0 and self.opex_eur_per_tkm > 0.0:
            raise ValueError("opex_eur_per_tkm requires a positive distance_km")
        return self

    def active_in(self, year: int) -> bool:
        year = int(year)
        if year < self.valid_from_year:
            return False
        return self.valid_until_year is None or year <= self.valid_until_year

    def effective_capacity_t_per_year(self) -> float:
        """Capacity offered by this state, after modal and availability limits.

        An explicit ``capacity_t_per_year`` acts as an upper bound, while the
        mode design (fleet size, vessel/weather cycle) determines what can
        actually be moved: the smaller of the two wins.  ``availability`` is the
        route-level factor (maintenance, right-of-way) and is applied on top of
        the modal design's own operational derating.
        """

        bounds: list[float] = []
        if self.capacity_t_per_year is not None:
            bounds.append(float(self.capacity_t_per_year))

        if self.mode is TransportMode.MARINE:
            assert self.marine is not None
            bounds.append(self.marine.effective_capacity_t_per_year())
        elif self.mode in (TransportMode.TRUCK, TransportMode.RAIL):
            assert self.road is not None
            if self.road.fleet_size is None:
                raise ValueError("fleet_size is required to derive road/rail capacity")
            bounds.append(self.road.effective_capacity_t_per_year())

        if not bounds:
            raise ValueError(
                "a pipeline state must declare capacity_t_per_year explicitly"
            )
        return min(bounds) * float(self.availability)

    def variable_opex_eur_per_t(self) -> float:
        """Variable transport cost per tonne for this state."""

        if self.mode in (TransportMode.TRUCK, TransportMode.RAIL):
            return float(self.opex_eur_per_t) + float(self.opex_eur_per_tkm) * float(self.distance_km)
        return float(self.opex_eur_per_t)


class UpgradeTrigger(CoreModel):
    """Condition that fires an infrastructure upgrade."""

    kind: Literal["year", "cumulative_mass", "both"]
    year: int | None = None
    threshold_t: float | None = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def _check(self) -> "UpgradeTrigger":
        if self.kind in ("year", "both") and self.year is None:
            raise ValueError("kind 'year' requires a year")
        if self.kind in ("cumulative_mass", "both") and self.threshold_t is None:
            raise ValueError("kind 'cumulative_mass' requires threshold_t")
        return self

    def fires_on_year(self, year: int) -> bool:
        if self.kind in ("year", "both"):
            return self.year is not None and int(year) >= int(self.year)
        return False

    def fires_on_mass(self, cumulative_mass_t: float | None) -> bool:
        if cumulative_mass_t is None:
            return False
        if self.kind in ("cumulative_mass", "both"):
            return self.threshold_t is not None and float(cumulative_mass_t) >= float(self.threshold_t)
        return False


class InfrastructureUpgrade(CoreModel):
    """A capacity/technology change applied to an edge in a given year."""

    id: Slug
    trigger: UpgradeTrigger
    new_state: EdgeState
    lead_time_years: int = Field(default=0, ge=0)
    notes: str | None = None

    def effective_year(
        self,
        *,
        current_year: int,
        cumulative_mass_t: float | None = None,
        fired_year: int | None = None,
    ) -> int | None:
        """First year the new state is in force, or ``None`` if it has not fired.

        ``fired_year`` is the year the solver recorded for a mass trigger; it is
        required because a cumulative threshold cannot be evaluated without the
        chronological history of the edge.
        """

        if fired_year is not None:
            start = int(fired_year)
        elif self.trigger.fires_on_year(current_year):
            start = int(self.trigger.year or current_year)
        elif self.trigger.fires_on_mass(cumulative_mass_t):
            start = int(current_year)
        else:
            return None
        return start + int(self.lead_time_years)


class TransportEdge(CoreModel):
    """Directed, time-dependent connection between two nodes."""

    id: Slug
    name: str = Field(min_length=1)
    from_node: Slug
    to_node: Slug
    bidirectional: bool = False
    states: list[EdgeState] = Field(min_length=1)
    upgrades: list[InfrastructureUpgrade] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def _check_timeline(self) -> "TransportEdge":
        if self.from_node == self.to_node and not self.bidirectional:
            raise ValueError("an edge must connect two different nodes")
        ordered = sorted(self.states, key=lambda state: state.valid_from_year)
        if ordered[0].valid_from_year != min(state.valid_from_year for state in self.states):
            raise AssertionError("unreachable")  # pragma: no cover
        for previous, current in zip(ordered, ordered[1:]):
            if (
                previous.valid_until_year is not None
                and current.valid_from_year <= previous.valid_until_year
            ):
                raise ValueError(
                    "edge state windows must not overlap: "
                    f"{previous.valid_from_year}-{previous.valid_until_year} and "
                    f"{current.valid_from_year}-{current.valid_until_year}"
                )
            if current.valid_from_year <= previous.valid_from_year:
                raise ValueError("edge state windows must be strictly increasing")
        upgrade_ids = [upgrade.id for upgrade in self.upgrades]
        if len(set(upgrade_ids)) != len(upgrade_ids):
            raise ValueError("upgrade ids must be unique within an edge")
        return self

    def base_state(self, year: int) -> EdgeState | None:
        """Planned state from the year-based timeline (ignores upgrades)."""

        applicable = [
            state
            for state in self.states
            if state.active_in(int(year))
        ]
        if not applicable:
            return None
        return max(applicable, key=lambda state: state.valid_from_year)

    def resolve_state(
        self,
        year: int,
        *,
        cumulative_mass_t: float | None = None,
        fired_upgrades: Mapping[str, int] | None = None,
    ) -> EdgeState | None:
        """State in force in ``year`` after applying any fired upgrades.

        The later of the planned state and the newest fired upgrade wins, so a
        conditional upgrade can never silently downgrade an already upgraded
        route.
        """

        year = int(year)
        base = self.base_state(year)
        if base is None and not self.upgrades:
            return None

        candidates: list[tuple[int, EdgeState]] = []
        if base is not None:
            candidates.append((base.valid_from_year, base))

        fired = dict(fired_upgrades or {})
        for upgrade in self.upgrades:
            recorded = fired.get(upgrade.id)
            start = upgrade.effective_year(
                current_year=year,
                cumulative_mass_t=cumulative_mass_t,
                fired_year=recorded,
            )
            if start is None or year < start:
                continue
            candidates.append((start, upgrade.new_state))

        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def capacity_in(self, year: int, **kwargs: float) -> float:
        state = self.resolve_state(year, **kwargs)
        return 0.0 if state is None else state.effective_capacity_t_per_year()

    def tariff_in(self, year: int, **kwargs: float) -> float:
        state = self.resolve_state(year, **kwargs)
        return 0.0 if state is None else state.variable_opex_eur_per_t()

    def states_summary(self) -> list[dict[str, object]]:
        """Auditable description of the planned timeline."""

        return [
            {
                "mode": state.mode.value,
                "valid_from_year": state.valid_from_year,
                "valid_until_year": state.valid_until_year,
                "capacity_t_per_year": state.capacity_t_per_year,
                "capex_eur": state.capex_eur,
            }
            for state in sorted(self.states, key=lambda item: item.valid_from_year)
        ]