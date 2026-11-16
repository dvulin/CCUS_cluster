"""Graph vertices: junctions, ports, storage sites and geothermal doublets."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .base import CoreModel, Slug, positive, unit_fraction
from .edge import TransportMode


class NodeKind(str, Enum):
    """Role of a vertex in the multi-modal transport graph."""

    EMITTER = "emitter"
    JUNCTION = "junction"
    HUB = "hub"
    PORT = "port"
    STORAGE = "storage"
    GEOTHERMAL = "geothermal"
    OFFSHORE_TERMINAL = "offshore_terminal"


class Hub(CoreModel):
    """A collection/booster hub: what can leave it, and at which conditions.

    The hub is the vertex that makes the pressure cascade and the modal choice
    explicit: it records the modes available at the site, the pressure and
    temperature the CO2 is expected to have, the processing that must happen
    there, and the storage sites it can feed.
    """

    name: str = Field(min_length=1)
    transport_options: list[TransportMode] = Field(
        default_factory=lambda: [TransportMode.PIPELINE]
    )
    expected_pressure_bar: float | None = Field(default=None, gt=0.0)
    expected_temperature_c: float | None = None
    processing: list[str] = Field(
        default_factory=list,
        description="e.g. purification, drying, compression, pumping",
    )
    storage_options: list[str] = Field(
        default_factory=list,
        description="storage site ids reachable from this hub",
    )
    port_node_id: Slug | None = None
    notes: str | None = None


class GeoLocation(CoreModel):
    """Coast/onshore flag plus optional WGS84 coordinates for mapping."""

    onshore: bool = True
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)

    @model_validator(mode="after")
    def _check_pair(self) -> "GeoLocation":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class PortHub(CoreModel):
    """Logistical constraints of a marine terminal.

    Throughput is the binding constraint for shipping: a port can only load as
    much CO2 as its berths and weather window allow, regardless of how many
    vessels are nominally available.
    """

    name: str = Field(min_length=1)
    berths: int = Field(default=1, ge=1)
    max_throughput_t_per_year: float = positive("max_throughput_t_per_year")
    load_rate_t_per_day: float = positive("load_rate_t_per_day")
    storage_capacity_t: float = Field(default=0.0, ge=0.0)
    weather_availability: float = unit_fraction("weather_availability")

    def effective_throughput_t_per_year(self) -> float:
        """Annual tonnage the terminal can actually handle."""

        return float(self.max_throughput_t_per_year) * float(self.weather_availability)


class Node(CoreModel):
    """A vertex of the transport graph."""

    id: Slug
    name: str = Field(min_length=1)
    kind: NodeKind
    location: GeoLocation = GeoLocation()
    port: PortHub | None = None
    hub: Hub | None = None
    commissioning_year: int | None = None
    decommission_year: int | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "Node":
        if self.kind is NodeKind.PORT and self.port is None:
            raise ValueError("a port node must define its PortHub constraints")
        if (
            self.commissioning_year is not None
            and self.decommission_year is not None
            and self.decommission_year < self.commissioning_year
        ):
            raise ValueError("decommission_year must not precede commissioning_year")
        return self

    def active_in(self, year: int) -> bool:
        year = int(year)
        if self.commissioning_year is not None and year < self.commissioning_year:
            return False
        return self.decommission_year is None or year <= self.decommission_year
