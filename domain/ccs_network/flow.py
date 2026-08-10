"""Explicit, emitter-resolved CO2 flow plans for a CCS transport network.

The first network-model version deliberately has no losses and no intermediate
inventory.  Consequently, conservation is checked for every emitter, node and
year.  Keeping ``emitter_id`` on every flow record preserves provenance after
several emitters enter a shared transport leg.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .models import CcsNetworkScenario


def _validated_year(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("year must be an integer")
    return value


def _validated_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validated_quantity(value: float, field_name: str = "quantity_t") -> float:
    quantity = float(value)
    if not math.isfinite(quantity) or quantity < 0.0:
        raise ValueError(f"{field_name} must be a finite, non-negative number")
    return quantity


@dataclass(frozen=True, slots=True)
class CaptureFlow:
    """CO2 captured by one emitter and made available at a network node."""

    year: int
    emitter_id: str
    node_id: str
    quantity_t: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "year", _validated_year(self.year))
        object.__setattr__(self, "emitter_id", _validated_id(self.emitter_id, "emitter_id"))
        object.__setattr__(self, "node_id", _validated_id(self.node_id, "node_id"))
        object.__setattr__(self, "quantity_t", _validated_quantity(self.quantity_t))


@dataclass(frozen=True, slots=True)
class TransportFlow:
    """Annual CO2 throughput of one emitter on one transport leg."""

    year: int
    emitter_id: str
    leg_id: str
    quantity_t: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "year", _validated_year(self.year))
        object.__setattr__(self, "emitter_id", _validated_id(self.emitter_id, "emitter_id"))
        object.__setattr__(self, "leg_id", _validated_id(self.leg_id, "leg_id"))
        object.__setattr__(self, "quantity_t", _validated_quantity(self.quantity_t))


@dataclass(frozen=True, slots=True)
class InjectionFlow:
    """Annual CO2 injection assigned to one emitter and one injection well."""

    year: int
    emitter_id: str
    well_id: str
    quantity_t: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "year", _validated_year(self.year))
        object.__setattr__(self, "emitter_id", _validated_id(self.emitter_id, "emitter_id"))
        object.__setattr__(self, "well_id", _validated_id(self.well_id, "well_id"))
        object.__setattr__(self, "quantity_t", _validated_quantity(self.quantity_t))


@dataclass(frozen=True, slots=True)
class ExplicitFlowPlan:
    """Serialization-friendly annual flow input, independent of any UI.

    ``losses_t`` and ``inventory_change_t`` make the v1 assumptions explicit.
    The validator rejects non-zero values until those processes can be located
    by emitter, node and year in a future ledger model.
    """

    capture_flows: tuple[CaptureFlow, ...] = field(default_factory=tuple)
    transport_flows: tuple[TransportFlow, ...] = field(default_factory=tuple)
    injection_flows: tuple[InjectionFlow, ...] = field(default_factory=tuple)
    losses_t: float = 0.0
    inventory_change_t: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "capture_flows", tuple(self.capture_flows))
        object.__setattr__(self, "transport_flows", tuple(self.transport_flows))
        object.__setattr__(self, "injection_flows", tuple(self.injection_flows))
        object.__setattr__(self, "losses_t", _validated_quantity(self.losses_t, "losses_t"))
        inventory = float(self.inventory_change_t)
        if not math.isfinite(inventory):
            raise ValueError("inventory_change_t must be finite")
        object.__setattr__(self, "inventory_change_t", inventory)

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                {
                    flow.year
                    for flow in (
                        *self.capture_flows,
                        *self.transport_flows,
                        *self.injection_flows,
                    )
                }
            )
        )

    def transported_quantity_t(
        self,
        *,
        year: int,
        leg_id: str,
        emitter_id: str | None = None,
    ) -> float:
        """Return throughput without discarding optional emitter provenance."""

        return sum(
            flow.quantity_t
            for flow in self.transport_flows
            if flow.year == year
            and flow.leg_id == leg_id
            and (emitter_id is None or flow.emitter_id == emitter_id)
        )

    def injected_quantity_t(
        self,
        *,
        year: int,
        emitter_id: str | None = None,
    ) -> float:
        return sum(
            flow.quantity_t
            for flow in self.injection_flows
            if flow.year == year
            and (emitter_id is None or flow.emitter_id == emitter_id)
        )


@dataclass(frozen=True, slots=True)
class LegFlowAllocation:
    """One emitter's actual share of a leg's physical annual throughput."""

    year: int
    leg_id: str
    emitter_id: str
    quantity_t: float
    leg_throughput_t: float
    actual_flow_share: float


@dataclass(frozen=True, slots=True)
class FlowValidationIssue:
    code: str
    message: str
    year: int | None = None
    emitter_id: str | None = None
    node_id: str | None = None
    leg_id: str | None = None
    well_id: str | None = None


class FlowValidationError(ValueError):
    """Raised by :meth:`FlowValidationResult.raise_for_errors`."""

    def __init__(self, result: "FlowValidationResult") -> None:
        self.result = result
        super().__init__("; ".join(issue.message for issue in result.issues))


@dataclass(frozen=True, slots=True)
class FlowValidationResult:
    issues: tuple[FlowValidationIssue, ...]
    leg_allocations: tuple[LegFlowAllocation, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues

    def raise_for_errors(self) -> None:
        if self.issues:
            raise FlowValidationError(self)

    def leg_throughput_t(self, *, year: int, leg_id: str) -> float:
        return sum(
            allocation.quantity_t
            for allocation in self.leg_allocations
            if allocation.year == year and allocation.leg_id == leg_id
        )

    def actual_flow_share(
        self,
        *,
        year: int,
        leg_id: str,
        emitter_id: str,
    ) -> float:
        return sum(
            allocation.actual_flow_share
            for allocation in self.leg_allocations
            if allocation.year == year
            and allocation.leg_id == leg_id
            and allocation.emitter_id == emitter_id
        )


class NetworkFlowValidator:
    """Validate an explicit v1 plan against a static network scenario."""

    def __init__(
        self,
        *,
        absolute_tolerance_t: float = 1e-6,
        relative_tolerance: float = 1e-9,
    ) -> None:
        self.absolute_tolerance_t = _validated_quantity(
            absolute_tolerance_t, "absolute_tolerance_t"
        )
        self.relative_tolerance = _validated_quantity(
            relative_tolerance, "relative_tolerance"
        )

    def validate(
        self,
        scenario: "CcsNetworkScenario",
        plan: ExplicitFlowPlan,
    ) -> FlowValidationResult:
        issues: list[FlowValidationIssue] = []

        emitters = _indexed(_items(scenario, "emitters"))
        nodes = _indexed(_items(scenario, "nodes"))
        legs = _indexed(_items(scenario, "transport_legs", "legs"))
        wells = _indexed(_injection_wells(scenario))
        participations = tuple(_items(scenario, "leg_participations", "participations"))
        participation_by_key = {
            (item.emitter_id, item.leg_id): item for item in participations
        }

        if not self._close(plan.losses_t, 0.0):
            issues.append(
                FlowValidationIssue(
                    code="unsupported_losses",
                    message="Explicit flow plan v1 requires losses_t = 0.",
                )
            )
        if not self._close(plan.inventory_change_t, 0.0):
            issues.append(
                FlowValidationIssue(
                    code="unsupported_inventory",
                    message="Explicit flow plan v1 requires inventory_change_t = 0.",
                )
            )

        self._report_duplicate_flows(plan.capture_flows, ("year", "emitter_id", "node_id"), issues)
        self._report_duplicate_flows(plan.transport_flows, ("year", "emitter_id", "leg_id"), issues)
        self._report_duplicate_flows(plan.injection_flows, ("year", "emitter_id", "well_id"), issues)

        valid_capture: list[CaptureFlow] = []
        valid_transport: list[TransportFlow] = []
        valid_injection: list[InjectionFlow] = []

        for flow in plan.capture_flows:
            emitter = emitters.get(flow.emitter_id)
            if emitter is None:
                issues.append(self._unknown("emitter", flow))
                continue
            if flow.node_id not in nodes:
                issues.append(self._unknown("node", flow))
                continue
            if flow.node_id != emitter.delivery_node_id:
                issues.append(
                    FlowValidationIssue(
                        code="capture_node_mismatch",
                        message=(
                            f"Emitter {flow.emitter_id!r} delivers at "
                            f"{emitter.delivery_node_id!r}, not {flow.node_id!r}."
                        ),
                        year=flow.year,
                        emitter_id=flow.emitter_id,
                        node_id=flow.node_id,
                    )
                )
                continue
            capture_plant = emitter.capture_plant
            if not capture_plant.availability.contains(flow.year):
                issues.append(
                    FlowValidationIssue(
                        code="inactive_capture_plant",
                        message=f"Capture plant for emitter {flow.emitter_id!r} is inactive in {flow.year}.",
                        year=flow.year,
                        emitter_id=flow.emitter_id,
                        node_id=flow.node_id,
                    )
                )
            if self._exceeds(flow.quantity_t, capture_plant.capacity_t_per_year):
                issues.append(
                    FlowValidationIssue(
                        code="capture_capacity_exceeded",
                        message=f"Capture capacity for emitter {flow.emitter_id!r} is exceeded in {flow.year}.",
                        year=flow.year,
                        emitter_id=flow.emitter_id,
                        node_id=flow.node_id,
                    )
                )
            valid_capture.append(flow)

        for flow in plan.transport_flows:
            if flow.emitter_id not in emitters:
                issues.append(self._unknown("emitter", flow))
                continue
            leg = legs.get(flow.leg_id)
            if leg is None:
                issues.append(self._unknown("leg", flow))
                continue
            if not leg.availability.contains(flow.year):
                issues.append(
                    FlowValidationIssue(
                        code="inactive_transport_leg",
                        message=f"Transport leg {flow.leg_id!r} is inactive in {flow.year}.",
                        year=flow.year,
                        emitter_id=flow.emitter_id,
                        leg_id=flow.leg_id,
                    )
                )
            participation = participation_by_key.get((flow.emitter_id, flow.leg_id))
            if participation is None:
                issues.append(
                    FlowValidationIssue(
                        code="missing_leg_participation",
                        message=f"Emitter {flow.emitter_id!r} has no participation on leg {flow.leg_id!r}.",
                        year=flow.year,
                        emitter_id=flow.emitter_id,
                        leg_id=flow.leg_id,
                    )
                )
            else:
                reserved = participation.reservation_capacity_t_per_year
                if reserved is not None and self._exceeds(flow.quantity_t, reserved):
                    issues.append(
                        FlowValidationIssue(
                            code="reservation_capacity_exceeded",
                            message=(
                                f"Emitter {flow.emitter_id!r} exceeds its reserved capacity "
                                f"on leg {flow.leg_id!r} in {flow.year}."
                            ),
                            year=flow.year,
                            emitter_id=flow.emitter_id,
                            leg_id=flow.leg_id,
                        )
                    )
            valid_transport.append(flow)

        for flow in plan.injection_flows:
            if flow.emitter_id not in emitters:
                issues.append(self._unknown("emitter", flow))
                continue
            well = wells.get(flow.well_id)
            if well is None:
                issues.append(self._unknown("well", flow))
                continue
            if not well.availability.contains(flow.year):
                issues.append(
                    FlowValidationIssue(
                        code="inactive_injection_well",
                        message=f"Injection well {flow.well_id!r} is inactive in {flow.year}.",
                        year=flow.year,
                        emitter_id=flow.emitter_id,
                        well_id=flow.well_id,
                    )
                )
            valid_injection.append(flow)

        self._validate_declared_capture_schedules(emitters, valid_capture, issues)
        self._validate_leg_capacities(legs, valid_transport, issues)
        self._validate_well_capacities(wells, valid_injection, issues)
        self._validate_node_mass_balance(
            emitters,
            legs,
            wells,
            valid_capture,
            valid_transport,
            valid_injection,
            issues,
        )

        return FlowValidationResult(
            issues=tuple(issues),
            leg_allocations=_leg_allocations(plan.transport_flows),
        )

    def _validate_declared_capture_schedules(
        self,
        emitters: dict[str, object],
        flows: Iterable[CaptureFlow],
        issues: list[FlowValidationIssue],
    ) -> None:
        actual: defaultdict[tuple[str, int], float] = defaultdict(float)
        for flow in flows:
            actual[(flow.emitter_id, flow.year)] += flow.quantity_t

        for emitter_id, emitter in emitters.items():
            schedule = emitter.capture_plant.captured_co2_t
            if schedule is None:
                continue
            years = set(schedule.years)
            years.update(year for candidate, year in actual if candidate == emitter_id)
            for year in sorted(years):
                expected = schedule.value(year)
                supplied = actual[(emitter_id, year)]
                if not self._close(supplied, expected):
                    issues.append(
                        FlowValidationIssue(
                            code="capture_schedule_mismatch",
                            message=(
                                f"Captured flow for emitter {emitter_id!r} in {year} is "
                                f"{supplied:g} t; declared schedule is {expected:g} t."
                            ),
                            year=year,
                            emitter_id=emitter_id,
                            node_id=emitter.delivery_node_id,
                        )
                    )

    def _validate_leg_capacities(
        self,
        legs: dict[str, object],
        flows: Iterable[TransportFlow],
        issues: list[FlowValidationIssue],
    ) -> None:
        throughput: defaultdict[tuple[str, int], float] = defaultdict(float)
        for flow in flows:
            throughput[(flow.leg_id, flow.year)] += flow.quantity_t
        for (leg_id, year), quantity in sorted(throughput.items()):
            capacity = legs[leg_id].capacity_t_per_year
            if capacity is not None and self._exceeds(quantity, capacity):
                issues.append(
                    FlowValidationIssue(
                        code="leg_capacity_exceeded",
                        message=f"Transport leg {leg_id!r} exceeds annual capacity in {year}.",
                        year=year,
                        leg_id=leg_id,
                    )
                )

    def _validate_well_capacities(
        self,
        wells: dict[str, object],
        flows: Iterable[InjectionFlow],
        issues: list[FlowValidationIssue],
    ) -> None:
        throughput: defaultdict[tuple[str, int], float] = defaultdict(float)
        for flow in flows:
            throughput[(flow.well_id, flow.year)] += flow.quantity_t
        for (well_id, year), quantity in sorted(throughput.items()):
            if self._exceeds(quantity, wells[well_id].capacity_t_per_year):
                issues.append(
                    FlowValidationIssue(
                        code="injection_well_capacity_exceeded",
                        message=f"Injection well {well_id!r} exceeds annual capacity in {year}.",
                        year=year,
                        well_id=well_id,
                    )
                )

    def _validate_node_mass_balance(
        self,
        emitters: dict[str, object],
        legs: dict[str, object],
        wells: dict[str, object],
        captures: Iterable[CaptureFlow],
        transports: Iterable[TransportFlow],
        injections: Iterable[InjectionFlow],
        issues: list[FlowValidationIssue],
    ) -> None:
        balance: defaultdict[tuple[int, str, str], float] = defaultdict(float)

        for flow in captures:
            balance[(flow.year, flow.emitter_id, flow.node_id)] += flow.quantity_t
        for flow in transports:
            leg = legs[flow.leg_id]
            balance[(flow.year, flow.emitter_id, leg.origin_node_id)] -= flow.quantity_t
            balance[(flow.year, flow.emitter_id, leg.destination_node_id)] += flow.quantity_t
        for flow in injections:
            node_id = _well_node_id(wells[flow.well_id])
            balance[(flow.year, flow.emitter_id, node_id)] -= flow.quantity_t

        for (year, emitter_id, node_id), net_quantity in sorted(balance.items()):
            if emitter_id not in emitters:
                continue
            if not self._close(net_quantity, 0.0):
                issues.append(
                    FlowValidationIssue(
                        code="node_mass_imbalance",
                        message=(
                            f"CO2 mass imbalance for emitter {emitter_id!r} at node "
                            f"{node_id!r} in {year}: net {net_quantity:g} t."
                        ),
                        year=year,
                        emitter_id=emitter_id,
                        node_id=node_id,
                    )
                )

    def _report_duplicate_flows(
        self,
        flows: Iterable[object],
        field_names: tuple[str, ...],
        issues: list[FlowValidationIssue],
    ) -> None:
        seen: set[tuple[object, ...]] = set()
        for flow in flows:
            key = tuple(getattr(flow, field_name) for field_name in field_names)
            if key in seen:
                issues.append(
                    FlowValidationIssue(
                        code="duplicate_flow",
                        message=f"Duplicate flow record for key {key!r}.",
                        year=getattr(flow, "year", None),
                        emitter_id=getattr(flow, "emitter_id", None),
                        node_id=getattr(flow, "node_id", None),
                        leg_id=getattr(flow, "leg_id", None),
                        well_id=getattr(flow, "well_id", None),
                    )
                )
            seen.add(key)

    @staticmethod
    def _unknown(reference: str, flow: object) -> FlowValidationIssue:
        field_name = {
            "emitter": "emitter_id",
            "node": "node_id",
            "leg": "leg_id",
            "well": "well_id",
        }[reference]
        value = getattr(flow, field_name)
        return FlowValidationIssue(
            code=f"unknown_{reference}",
            message=f"Unknown {reference} reference {value!r}.",
            year=getattr(flow, "year", None),
            emitter_id=getattr(flow, "emitter_id", None),
            node_id=getattr(flow, "node_id", None),
            leg_id=getattr(flow, "leg_id", None),
            well_id=getattr(flow, "well_id", None),
        )

    def _close(self, left: float, right: float) -> bool:
        return math.isclose(
            left,
            right,
            rel_tol=self.relative_tolerance,
            abs_tol=self.absolute_tolerance_t,
        )

    def _exceeds(self, quantity: float, capacity: float) -> bool:
        return quantity > capacity and not self._close(quantity, capacity)


def _items(instance: object, *field_names: str) -> tuple[object, ...]:
    for field_name in field_names:
        if hasattr(instance, field_name):
            return tuple(getattr(instance, field_name))
    return ()


def _indexed(items: Iterable[object]) -> dict[str, object]:
    return {item.id: item for item in items}


def _injection_wells(scenario: object) -> tuple[object, ...]:
    direct = _items(scenario, "injection_wells")
    if direct:
        return direct
    return tuple(
        well
        for storage_site in _items(scenario, "storage_sites")
        for well in _items(storage_site, "injection_wells", "wells")
    )


def _well_node_id(well: object) -> str:
    for field_name in ("node_id", "storage_node_id", "injection_node_id"):
        if hasattr(well, field_name):
            return getattr(well, field_name)
    raise AttributeError(f"Injection well {well!r} has no network-node reference")


def _leg_allocations(flows: Iterable[TransportFlow]) -> tuple[LegFlowAllocation, ...]:
    per_emitter: defaultdict[tuple[int, str, str], float] = defaultdict(float)
    throughput: defaultdict[tuple[int, str], float] = defaultdict(float)
    for flow in flows:
        per_emitter[(flow.year, flow.leg_id, flow.emitter_id)] += flow.quantity_t
        throughput[(flow.year, flow.leg_id)] += flow.quantity_t

    allocations: list[LegFlowAllocation] = []
    for (year, leg_id, emitter_id), quantity in sorted(per_emitter.items()):
        total = throughput[(year, leg_id)]
        allocations.append(
            LegFlowAllocation(
                year=year,
                leg_id=leg_id,
                emitter_id=emitter_id,
                quantity_t=quantity,
                leg_throughput_t=total,
                actual_flow_share=quantity / total if total else 0.0,
            )
        )
    return tuple(allocations)
