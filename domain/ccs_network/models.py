"""UI-agnostic value objects for a multi-emitter CCS transport network.

The classes in this module deliberately contain no Streamlit, JSON, or current
``IOEndpoints`` dependencies.  A future web or file adapter can construct these
objects from primitive values and serialize them through their public fields.

Actual transported quantities are intentionally *not* stored on
``TransportLeg`` or ``LegParticipation``.  They belong to a time-indexed flow
ledger, where every record retains both ``emitter_id`` and ``leg_id``.  This
prevents loss of emitter provenance on shared transport legs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import ceil, isfinite
from typing import Dict, Iterable, Mapping, Optional, Tuple, Union


Number = Union[int, float]


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _finite_number(value: Number, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number")
    converted = float(value)
    if not isfinite(converted):
        raise ValueError(f"{field_name} must be a finite number")
    return converted


def _positive_number(value: Number, field_name: str) -> float:
    converted = _finite_number(value, field_name)
    if converted <= 0.0:
        raise ValueError(f"{field_name} must be greater than zero")
    return converted


def _non_negative_number(value: Number, field_name: str) -> float:
    converted = _finite_number(value, field_name)
    if converted < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return converted


def _optional_positive_number(
    value: Optional[Number], field_name: str
) -> Optional[float]:
    if value is None:
        return None
    return _positive_number(value, field_name)


def _optional_non_negative_number(
    value: Optional[Number], field_name: str
) -> Optional[float]:
    if value is None:
        return None
    return _non_negative_number(value, field_name)


def _optional_share(value: Optional[Number], field_name: str) -> Optional[float]:
    if value is None:
        return None
    converted = _finite_number(value, field_name)
    if converted < 0.0 or converted > 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return converted


def _require_year(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer year")


@dataclass(frozen=True)
class AnnualSchedule:
    """Immutable, ordered annual values suitable for adapter boundaries."""

    entries: Tuple[Tuple[int, float], ...] = ()

    def __post_init__(self) -> None:
        raw_entries: Iterable[Tuple[int, Number]]
        if isinstance(self.entries, Mapping):
            raw_entries = self.entries.items()
        else:
            raw_entries = self.entries

        normalized = []
        seen_years = set()
        for raw_entry in raw_entries:
            try:
                year, value = raw_entry
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "AnnualSchedule entries must be (year, value) pairs"
                ) from exc
            _require_year(year, "schedule year")
            if year in seen_years:
                raise ValueError(f"duplicate schedule year: {year}")
            normalized_value = _non_negative_number(value, f"value for {year}")
            seen_years.add(year)
            normalized.append((year, normalized_value))

        normalized.sort(key=lambda item: item[0])
        object.__setattr__(self, "entries", tuple(normalized))

    @classmethod
    def from_mapping(cls, values_by_year: Mapping[int, Number]) -> "AnnualSchedule":
        """Build a schedule from JSON/web-adapter-friendly key/value data."""

        if not isinstance(values_by_year, Mapping):
            raise ValueError("values_by_year must be a mapping")
        return cls(tuple(values_by_year.items()))

    @classmethod
    def constant(
        cls, value: Number, start_year: int, end_year: int
    ) -> "AnnualSchedule":
        availability = Availability(start_year=start_year, end_year=end_year)
        normalized_value = _non_negative_number(value, "value")
        return cls(
            tuple((year, normalized_value) for year in availability.years)
        )

    @property
    def years(self) -> Tuple[int, ...]:
        return tuple(year for year, _ in self.entries)

    @property
    def total(self) -> float:
        return sum(value for _, value in self.entries)

    def items(self) -> Tuple[Tuple[int, float], ...]:
        return self.entries

    def to_dict(self) -> Dict[int, float]:
        return dict(self.entries)

    def value(self, year: int, default: float = 0.0) -> float:
        _require_year(year, "year")
        for entry_year, entry_value in self.entries:
            if entry_year == year:
                return entry_value
        return float(default)

    def get(self, year: int, default: float = 0.0) -> float:
        return self.value(year, default)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)


@dataclass(frozen=True)
class Availability:
    """Inclusive operating interval."""

    start_year: int
    end_year: int

    def __post_init__(self) -> None:
        _require_year(self.start_year, "start_year")
        _require_year(self.end_year, "end_year")
        if self.end_year < self.start_year:
            raise ValueError("end_year must be greater than or equal to start_year")

    @property
    def years(self) -> Tuple[int, ...]:
        return tuple(range(self.start_year, self.end_year + 1))

    def contains(self, year: int) -> bool:
        _require_year(year, "year")
        return self.start_year <= year <= self.end_year

    def overlaps(self, other: "Availability") -> bool:
        return self.start_year <= other.end_year and other.start_year <= self.end_year


@dataclass(frozen=True)
class CapturePlant:
    """Emitter-owned capture asset and its available captured-CO2 supply."""

    id: str
    name: str
    availability: Availability
    capacity_t_per_year: float
    captured_co2_t: AnnualSchedule
    technology: Optional[str] = None
    capex_eur: float = 0.0
    fixed_opex_eur_per_year: float = 0.0
    variable_opex_eur_per_t: float = 0.0

    def __post_init__(self) -> None:
        _require_identifier(self.id, "capture plant id")
        _require_identifier(self.name, "capture plant name")
        capacity = _positive_number(self.capacity_t_per_year, "capacity_t_per_year")
        object.__setattr__(self, "capacity_t_per_year", capacity)
        if self.technology is not None:
            _require_identifier(self.technology, "capture technology")
        object.__setattr__(
            self, "capex_eur", _non_negative_number(self.capex_eur, "capex_eur")
        )
        object.__setattr__(
            self,
            "fixed_opex_eur_per_year",
            _non_negative_number(
                self.fixed_opex_eur_per_year, "fixed_opex_eur_per_year"
            ),
        )
        object.__setattr__(
            self,
            "variable_opex_eur_per_t",
            _non_negative_number(
                self.variable_opex_eur_per_t, "variable_opex_eur_per_t"
            ),
        )

        for year, quantity_t in self.captured_co2_t:
            if quantity_t > 0.0 and not self.availability.contains(year):
                raise ValueError(
                    f"captured CO2 for {year} is outside capture plant availability"
                )
            if quantity_t > capacity:
                raise ValueError(
                    f"captured CO2 for {year} exceeds capture plant capacity"
                )

    def captured_quantity_t(self, year: int) -> float:
        if not self.availability.contains(year):
            return 0.0
        return self.captured_co2_t.value(year)


@dataclass(frozen=True)
class NetworkEmitter:
    """A distinct emitter whose identity follows its CO2 through the network."""

    id: str
    name: str
    capture_plant: CapturePlant
    delivery_node_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.id, "emitter id")
        _require_identifier(self.name, "emitter name")
        _require_identifier(self.delivery_node_id, "delivery_node_id")


class NodeKind(str, Enum):
    EMITTER = "emitter"
    JUNCTION = "junction"
    HUB = "hub"
    INTERMODAL = "intermodal"
    STORAGE = "storage"


@dataclass(frozen=True)
class NetworkNode:
    id: str
    name: str
    kind: NodeKind

    def __post_init__(self) -> None:
        _require_identifier(self.id, "node id")
        _require_identifier(self.name, "node name")
        if not isinstance(self.kind, NodeKind):
            try:
                object.__setattr__(self, "kind", NodeKind(self.kind))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"unsupported node kind: {self.kind!r}") from exc


@dataclass(frozen=True)
class PipelineSpec:
    """Pipeline design data; hydraulic calculations intentionally live elsewhere."""

    length_km: float
    capacity_t_per_year: float
    inner_diameter_m: Optional[float] = None
    absolute_roughness_m: Optional[float] = None
    max_operating_pressure_bar: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "length_km", _positive_number(self.length_km, "length_km"))
        object.__setattr__(
            self,
            "capacity_t_per_year",
            _positive_number(self.capacity_t_per_year, "capacity_t_per_year"),
        )
        object.__setattr__(
            self,
            "inner_diameter_m",
            _optional_positive_number(self.inner_diameter_m, "inner_diameter_m"),
        )
        object.__setattr__(
            self,
            "absolute_roughness_m",
            _optional_non_negative_number(
                self.absolute_roughness_m, "absolute_roughness_m"
            ),
        )
        object.__setattr__(
            self,
            "max_operating_pressure_bar",
            _optional_positive_number(
                self.max_operating_pressure_bar, "max_operating_pressure_bar"
            ),
        )


@dataclass(frozen=True)
class TruckSpec:
    """Road transport assumptions and transparent fleet-sizing calculations."""

    length_km: float
    payload_t_per_trip: float
    trips_per_truck_per_day: float
    operating_days_per_year: int
    fleet_size: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "length_km", _positive_number(self.length_km, "length_km"))
        object.__setattr__(
            self,
            "payload_t_per_trip",
            _positive_number(self.payload_t_per_trip, "payload_t_per_trip"),
        )
        object.__setattr__(
            self,
            "trips_per_truck_per_day",
            _positive_number(
                self.trips_per_truck_per_day, "trips_per_truck_per_day"
            ),
        )
        if (
            isinstance(self.operating_days_per_year, bool)
            or not isinstance(self.operating_days_per_year, int)
            or self.operating_days_per_year <= 0
            or self.operating_days_per_year > 366
        ):
            raise ValueError("operating_days_per_year must be an integer from 1 to 366")
        if self.fleet_size is not None:
            if (
                isinstance(self.fleet_size, bool)
                or not isinstance(self.fleet_size, int)
                or self.fleet_size <= 0
            ):
                raise ValueError("fleet_size must be a positive integer when provided")

    @property
    def trips_per_truck_per_year(self) -> float:
        return self.trips_per_truck_per_day * self.operating_days_per_year

    @property
    def annual_capacity_per_truck_t(self) -> float:
        return self.payload_t_per_trip * self.trips_per_truck_per_year

    @property
    def capacity_t_per_year(self) -> Optional[float]:
        if self.fleet_size is None:
            return None
        return self.fleet_size * self.annual_capacity_per_truck_t

    def loaded_trips_per_day(self, annual_quantity_t: Number) -> float:
        quantity_t = _non_negative_number(annual_quantity_t, "annual_quantity_t")
        return quantity_t / (
            self.payload_t_per_trip * self.operating_days_per_year
        )

    def required_truck_count(self, annual_quantity_t: Number) -> int:
        quantity_t = _non_negative_number(annual_quantity_t, "annual_quantity_t")
        if quantity_t == 0.0:
            return 0
        return ceil(quantity_t / self.annual_capacity_per_truck_t)

    def required_fleet_size(self, annual_quantity_t: Number) -> int:
        return self.required_truck_count(annual_quantity_t)

    def required_average_trips_per_day(self, annual_quantity_t: Number) -> float:
        return self.loaded_trips_per_day(annual_quantity_t)


@dataclass(frozen=True)
class RailSpec:
    """Rail design capacity; detailed train scheduling can be added independently."""

    length_km: float
    capacity_t_per_year: float
    payload_t_per_train: Optional[float] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "length_km", _positive_number(self.length_km, "length_km"))
        object.__setattr__(
            self,
            "capacity_t_per_year",
            _positive_number(self.capacity_t_per_year, "capacity_t_per_year"),
        )
        object.__setattr__(
            self,
            "payload_t_per_train",
            _optional_positive_number(self.payload_t_per_train, "payload_t_per_train"),
        )


TransportMode = Union[PipelineSpec, TruckSpec, RailSpec]


@dataclass(frozen=True)
class TransportLeg:
    id: str
    name: str
    owner_id: str
    origin_node_id: str
    destination_node_id: str
    mode: TransportMode
    availability: Availability

    def __post_init__(self) -> None:
        _require_identifier(self.id, "transport leg id")
        _require_identifier(self.name, "transport leg name")
        _require_identifier(self.owner_id, "owner_id")
        _require_identifier(self.origin_node_id, "origin_node_id")
        _require_identifier(self.destination_node_id, "destination_node_id")
        if self.origin_node_id == self.destination_node_id:
            raise ValueError("a transport leg must connect two different nodes")
        if not isinstance(self.mode, (PipelineSpec, TruckSpec, RailSpec)):
            raise ValueError("mode must be PipelineSpec, TruckSpec, or RailSpec")

    @property
    def capacity_t_per_year(self) -> Optional[float]:
        return self.mode.capacity_t_per_year

    @property
    def mode_name(self) -> str:
        if isinstance(self.mode, PipelineSpec):
            return "pipeline"
        if isinstance(self.mode, TruckSpec):
            return "truck"
        return "rail"


@dataclass(frozen=True)
class LegParticipation:
    """Emitter-specific commercial rights on a transport leg.

    The fields are intentionally independent.  Reserved physical capacity,
    asset ownership, allocation of fixed costs, and a throughput tariff may
    follow different contracts and therefore must never overwrite one another.
    Actual annual flow share is recorded separately by the flow ledger.
    """

    emitter_id: str
    leg_id: str
    reservation_capacity_t_per_year: Optional[float] = None
    ownership_share: Optional[float] = None
    fixed_cost_share: Optional[float] = None
    tariff_eur_per_t: Optional[float] = None

    def __post_init__(self) -> None:
        _require_identifier(self.emitter_id, "emitter_id")
        _require_identifier(self.leg_id, "leg_id")
        object.__setattr__(
            self,
            "reservation_capacity_t_per_year",
            _optional_non_negative_number(
                self.reservation_capacity_t_per_year,
                "reservation_capacity_t_per_year",
            ),
        )
        object.__setattr__(
            self,
            "ownership_share",
            _optional_share(self.ownership_share, "ownership_share"),
        )
        object.__setattr__(
            self,
            "fixed_cost_share",
            _optional_share(self.fixed_cost_share, "fixed_cost_share"),
        )
        object.__setattr__(
            self,
            "tariff_eur_per_t",
            _optional_non_negative_number(self.tariff_eur_per_t, "tariff_eur_per_t"),
        )


@dataclass(frozen=True)
class InjectionWell:
    id: str
    name: str
    storage_node_id: str
    availability: Availability
    capacity_t_per_year: float

    def __post_init__(self) -> None:
        _require_identifier(self.id, "injection well id")
        _require_identifier(self.name, "injection well name")
        _require_identifier(self.storage_node_id, "storage_node_id")
        object.__setattr__(
            self,
            "capacity_t_per_year",
            _positive_number(self.capacity_t_per_year, "capacity_t_per_year"),
        )


@dataclass(frozen=True)
class StorageSite:
    """Storage endpoint and its wells.

    ``nominal_capacity_t`` is descriptive nameplate capacity.  It does not by
    itself define a pressure-based injection cutoff; that remains a physical
    storage/injection constraint outside this transport-network foundation.
    """

    id: str
    name: str
    node_id: str
    availability: Availability
    nominal_capacity_t: Optional[float] = None
    injection_wells: Tuple[InjectionWell, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "storage site id")
        _require_identifier(self.name, "storage site name")
        _require_identifier(self.node_id, "node_id")
        object.__setattr__(
            self,
            "nominal_capacity_t",
            _optional_positive_number(self.nominal_capacity_t, "nominal_capacity_t"),
        )
        object.__setattr__(self, "injection_wells", tuple(self.injection_wells))
        well_ids = set()
        for well in self.injection_wells:
            if well.id in well_ids:
                raise ValueError(f"duplicate injection well id in storage site: {well.id}")
            well_ids.add(well.id)
            if well.storage_node_id != self.node_id:
                raise ValueError(
                    f"injection well {well.id} references {well.storage_node_id}, "
                    f"expected storage node {self.node_id}"
                )
            if not (
                self.availability.contains(well.availability.start_year)
                and self.availability.contains(well.availability.end_year)
            ):
                raise ValueError(
                    f"injection well {well.id} availability is outside storage site availability"
                )


@dataclass(frozen=True)
class CcsNetworkScenario:
    """Complete, validated topology independent of any UI or input adapter."""

    id: str
    name: str
    emitters: Tuple[NetworkEmitter, ...] = ()
    nodes: Tuple[NetworkNode, ...] = ()
    transport_legs: Tuple[TransportLeg, ...] = ()
    participations: Tuple[LegParticipation, ...] = ()
    storage_sites: Tuple[StorageSite, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, "scenario id")
        _require_identifier(self.name, "scenario name")
        for field_name in (
            "emitters",
            "nodes",
            "transport_legs",
            "participations",
            "storage_sites",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        self._validate_references_and_topology()

    @property
    def injection_wells(self) -> Tuple[InjectionWell, ...]:
        return tuple(
            well for site in self.storage_sites for well in site.injection_wells
        )

    @staticmethod
    def _unique_by_id(values, label: str):
        result = {}
        for value in values:
            if value.id in result:
                raise ValueError(f"duplicate {label} id: {value.id}")
            result[value.id] = value
        return result

    def _validate_references_and_topology(self) -> None:
        emitters = self._unique_by_id(self.emitters, "emitter")
        capture_plants = self._unique_by_id(
            (emitter.capture_plant for emitter in self.emitters), "capture plant"
        )
        del capture_plants  # uniqueness is the only scenario-level requirement
        nodes = self._unique_by_id(self.nodes, "node")
        legs = self._unique_by_id(self.transport_legs, "transport leg")
        sites = self._unique_by_id(self.storage_sites, "storage site")
        del sites
        wells = self._unique_by_id(self.injection_wells, "injection well")
        del wells

        for emitter in self.emitters:
            if emitter.delivery_node_id not in nodes:
                raise ValueError(
                    f"emitter {emitter.id} references unknown delivery node "
                    f"{emitter.delivery_node_id}"
                )

        for leg in self.transport_legs:
            if leg.origin_node_id not in nodes:
                raise ValueError(
                    f"transport leg {leg.id} references unknown origin node "
                    f"{leg.origin_node_id}"
                )
            if leg.destination_node_id not in nodes:
                raise ValueError(
                    f"transport leg {leg.id} references unknown destination node "
                    f"{leg.destination_node_id}"
                )

        storage_node_ids = set()
        for site in self.storage_sites:
            if site.node_id not in nodes:
                raise ValueError(
                    f"storage site {site.id} references unknown node {site.node_id}"
                )
            if nodes[site.node_id].kind is not NodeKind.STORAGE:
                raise ValueError(
                    f"storage site {site.id} must reference a storage node"
                )
            if site.node_id in storage_node_ids:
                raise ValueError(
                    f"multiple storage sites reference node {site.node_id}"
                )
            storage_node_ids.add(site.node_id)

        participation_keys = set()
        leg_ids_by_emitter = {emitter_id: set() for emitter_id in emitters}
        for participation in self.participations:
            key = (participation.emitter_id, participation.leg_id)
            if key in participation_keys:
                raise ValueError(
                    "duplicate emitter/transport-leg participation: "
                    f"{participation.emitter_id}/{participation.leg_id}"
                )
            participation_keys.add(key)
            if participation.emitter_id not in emitters:
                raise ValueError(
                    f"participation references unknown emitter "
                    f"{participation.emitter_id}"
                )
            if participation.leg_id not in legs:
                raise ValueError(
                    f"participation references unknown transport leg "
                    f"{participation.leg_id}"
                )
            leg_ids_by_emitter[participation.emitter_id].add(participation.leg_id)

        if self.emitters and not storage_node_ids:
            raise ValueError("a scenario with emitters requires at least one storage site")

        for emitter in self.emitters:
            emitter_legs = (
                legs[leg_id] for leg_id in leg_ids_by_emitter[emitter.id]
            )
            adjacency = {}
            for leg in emitter_legs:
                adjacency.setdefault(leg.origin_node_id, set()).add(
                    leg.destination_node_id
                )
            if not self._can_reach_any_storage(
                emitter.delivery_node_id, adjacency, storage_node_ids
            ):
                raise ValueError(
                    f"emitter {emitter.id} has no participated transport path "
                    "from its delivery node to a storage site"
                )

    @staticmethod
    def _can_reach_any_storage(
        start_node_id: str,
        adjacency: Mapping[str, set],
        storage_node_ids: set,
    ) -> bool:
        pending = [start_node_id]
        visited = set()
        while pending:
            node_id = pending.pop()
            if node_id in storage_node_ids:
                return True
            if node_id in visited:
                continue
            visited.add(node_id)
            pending.extend(adjacency.get(node_id, ()))
        return False

    def emitter_by_id(self, emitter_id: str) -> NetworkEmitter:
        for emitter in self.emitters:
            if emitter.id == emitter_id:
                return emitter
        raise KeyError(f"unknown emitter id: {emitter_id}")

    def node_by_id(self, node_id: str) -> NetworkNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(f"unknown node id: {node_id}")

    def transport_leg_by_id(self, leg_id: str) -> TransportLeg:
        for leg in self.transport_legs:
            if leg.id == leg_id:
                return leg
        raise KeyError(f"unknown transport leg id: {leg_id}")

    def storage_site_by_id(self, site_id: str) -> StorageSite:
        for site in self.storage_sites:
            if site.id == site_id:
                return site
        raise KeyError(f"unknown storage site id: {site_id}")

    def injection_well_by_id(self, well_id: str) -> InjectionWell:
        for well in self.injection_wells:
            if well.id == well_id:
                return well
        raise KeyError(f"unknown injection well id: {well_id}")


__all__ = [
    "AnnualSchedule",
    "Availability",
    "CapturePlant",
    "CcsNetworkScenario",
    "InjectionWell",
    "LegParticipation",
    "NetworkEmitter",
    "NetworkNode",
    "NodeKind",
    "PipelineSpec",
    "RailSpec",
    "StorageSite",
    "TransportLeg",
    "TransportMode",
    "TruckSpec",
]
