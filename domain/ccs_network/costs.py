"""Transparent transport-cost attribution for a multi-emitter CCS network.

The allocator deliberately keeps one record for every emitter, transport leg
and year.  It does not collapse a shared leg into a single network-wide cost,
because doing so would lose the commercial and physical provenance needed for
later reporting and settlement.

Tariffs are kept separate from physical resource costs.  In particular, a
tariff paid by an emitter to a transport asset that is inside the same modeled
system is an internal cash transfer, not an additional system resource cost.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

if TYPE_CHECKING:
    from .flow import ExplicitFlowPlan, TransportFlow
    from .models import CcsNetworkScenario, LegParticipation


class CostAllocationError(ValueError):
    """Raised when a cost cannot be allocated without inventing a share."""


class AllocationBasis(str, Enum):
    """Supported bases for allocating annual fixed OPEX and CAPEX."""

    ACTUAL_FLOW = "actual_flow"
    RESERVED_CAPACITY = "reserved_capacity"
    OWNERSHIP = "ownership"
    FIXED_COST_SHARE = "fixed_cost_share"


class TariffTreatment(str, Enum):
    """How a commercial tariff is viewed at the modeled-system boundary."""

    INTERNAL_TRANSFER = "internal_transfer"
    EXTERNAL_SERVICE = "external_service"


CostScheduleInput = Mapping[int, float] | Iterable[tuple[int, float]]


def _finite_nonnegative(value: float, *, field_name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return converted


def _normalize_schedule(
    schedule: CostScheduleInput,
    *,
    field_name: str,
) -> tuple[tuple[int, float], ...]:
    items = schedule.items() if isinstance(schedule, Mapping) else schedule
    normalized: dict[int, float] = {}
    for raw_year, raw_value in items:
        if isinstance(raw_year, bool) or not isinstance(raw_year, int):
            raise TypeError(f"{field_name} years must be integers")
        if raw_year in normalized:
            raise ValueError(f"duplicate {field_name} value for year {raw_year}")
        normalized[raw_year] = _finite_nonnegative(
            raw_value,
            field_name=f"{field_name}[{raw_year}]",
        )
    return tuple(sorted(normalized.items()))


@dataclass(frozen=True)
class TransportLegCostProfile:
    """Physical and commercial cost assumptions for one transport leg.

    ``fixed_opex_eur_by_year`` and ``capex_eur_by_year`` are explicit annual
    schedules.  Explicit schedules avoid silently extending costs beyond an
    asset's intended economic period and are straightforward to deserialize
    from a future web or Streamlit input adapter.

    A participant-specific tariff is read from ``LegParticipation``.  The
    profile only defines whether that tariff is internal to the modeled system
    or paid to an external transport service.
    """

    leg_id: str
    variable_opex_eur_per_t: float = 0.0
    fixed_opex_eur_by_year: CostScheduleInput = ()
    capex_eur_by_year: CostScheduleInput = ()
    fixed_opex_allocation_basis: AllocationBasis = AllocationBasis.FIXED_COST_SHARE
    capex_allocation_basis: AllocationBasis = AllocationBasis.OWNERSHIP
    tariff_treatment: TariffTreatment = TariffTreatment.INTERNAL_TRANSFER

    def __post_init__(self) -> None:
        if not isinstance(self.leg_id, str) or not self.leg_id.strip():
            raise ValueError("leg_id must be a non-empty string")
        object.__setattr__(
            self,
            "variable_opex_eur_per_t",
            _finite_nonnegative(
                self.variable_opex_eur_per_t,
                field_name="variable_opex_eur_per_t",
            ),
        )
        object.__setattr__(
            self,
            "fixed_opex_eur_by_year",
            _normalize_schedule(
                self.fixed_opex_eur_by_year,
                field_name="fixed_opex_eur_by_year",
            ),
        )
        object.__setattr__(
            self,
            "capex_eur_by_year",
            _normalize_schedule(
                self.capex_eur_by_year,
                field_name="capex_eur_by_year",
            ),
        )
        object.__setattr__(
            self,
            "fixed_opex_allocation_basis",
            AllocationBasis(self.fixed_opex_allocation_basis),
        )
        object.__setattr__(
            self,
            "capex_allocation_basis",
            AllocationBasis(self.capex_allocation_basis),
        )
        object.__setattr__(
            self,
            "tariff_treatment",
            TariffTreatment(self.tariff_treatment),
        )

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(
            sorted(
                {
                    *(year for year, _ in self.fixed_opex_eur_by_year),
                    *(year for year, _ in self.capex_eur_by_year),
                }
            )
        )

    def fixed_opex_eur(self, year: int) -> float:
        return _schedule_value(self.fixed_opex_eur_by_year, year)

    def capex_eur(self, year: int) -> float:
        return _schedule_value(self.capex_eur_by_year, year)


def _schedule_value(schedule: Sequence[tuple[int, float]], year: int) -> float:
    for scheduled_year, value in schedule:
        if scheduled_year == year:
            return value
    return 0.0


@dataclass(frozen=True)
class TransportCostAllocationRecord:
    """One auditable emitter x transport-leg x year cost record."""

    year: int
    emitter_id: str
    leg_id: str
    transported_t: float
    leg_throughput_t: float

    actual_flow_share: float
    reserved_capacity_t_per_year: float | None
    reservation_share: float | None
    ownership_share: float | None
    normalized_ownership_share: float | None
    fixed_cost_share: float | None
    normalized_fixed_cost_share: float | None

    variable_opex_eur_per_t: float
    variable_opex_eur: float
    tariff_eur_per_t: float
    tariff_charge_eur: float
    tariff_treatment: TariffTreatment

    fixed_opex_allocation_basis: AllocationBasis
    fixed_opex_allocation_share: float
    fixed_opex_eur: float
    capex_allocation_basis: AllocationBasis
    capex_allocation_share: float
    capex_eur: float

    @property
    def physical_resource_cost_eur(self) -> float:
        """Allocated physical cost, excluding every commercial tariff."""

        return self.variable_opex_eur + self.fixed_opex_eur + self.capex_eur

    @property
    def internal_tariff_transfer_eur(self) -> float:
        """Informational internal transfer, excluded from physical cost."""

        if self.tariff_treatment is TariffTreatment.INTERNAL_TRANSFER:
            return self.tariff_charge_eur
        return 0.0

    @property
    def external_tariff_charge_eur(self) -> float:
        """Tariff paid outside the modeled system boundary, if any."""

        if self.tariff_treatment is TariffTreatment.EXTERNAL_SERVICE:
            return self.tariff_charge_eur
        return 0.0


@dataclass(frozen=True)
class TransportCostAllocationResult:
    """Detailed records plus clearly separated derived ledger totals."""

    records: tuple[TransportCostAllocationRecord, ...]

    def select(
        self,
        *,
        year: int | None = None,
        emitter_id: str | None = None,
        leg_id: str | None = None,
    ) -> tuple[TransportCostAllocationRecord, ...]:
        return tuple(
            record
            for record in self.records
            if (year is None or record.year == year)
            and (emitter_id is None or record.emitter_id == emitter_id)
            and (leg_id is None or record.leg_id == leg_id)
        )

    @property
    def physical_resource_cost_eur(self) -> float:
        return sum(record.physical_resource_cost_eur for record in self.records)

    @property
    def internal_tariff_transfers_eur(self) -> float:
        return sum(record.internal_tariff_transfer_eur for record in self.records)

    @property
    def external_tariff_charges_eur(self) -> float:
        return sum(record.external_tariff_charge_eur for record in self.records)


class TransportCostAllocator:
    """Allocate transport-leg costs while retaining emitter provenance."""

    _TOLERANCE = 1e-12

    def __init__(
        self,
        scenario: CcsNetworkScenario,
        cost_profiles: Iterable[TransportLegCostProfile],
    ) -> None:
        self._scenario = scenario
        self._profiles = self._unique_profiles(cost_profiles)
        self._legs = {
            leg.id: leg
            for leg in getattr(scenario, "transport_legs", getattr(scenario, "legs", ()))
        }
        participations = getattr(
            scenario,
            "leg_participations",
            getattr(scenario, "participations", ()),
        )
        self._participations = self._unique_participations(participations)

        unknown_profiles = set(self._profiles).difference(self._legs)
        if unknown_profiles:
            unknown = ", ".join(sorted(unknown_profiles))
            raise CostAllocationError(f"cost profile references unknown leg(s): {unknown}")

    @staticmethod
    def _unique_profiles(
        profiles: Iterable[TransportLegCostProfile],
    ) -> dict[str, TransportLegCostProfile]:
        result: dict[str, TransportLegCostProfile] = {}
        for profile in profiles:
            if profile.leg_id in result:
                raise CostAllocationError(
                    f"duplicate cost profile for leg {profile.leg_id!r}"
                )
            result[profile.leg_id] = profile
        return result

    @staticmethod
    def _unique_participations(
        participations: Iterable[LegParticipation],
    ) -> dict[tuple[str, str], LegParticipation]:
        result: dict[tuple[str, str], LegParticipation] = {}
        for participation in participations:
            key = (participation.emitter_id, participation.leg_id)
            if key in result:
                raise CostAllocationError(
                    "duplicate leg participation for emitter "
                    f"{participation.emitter_id!r} and leg {participation.leg_id!r}"
                )
            result[key] = participation
        return result

    def allocate(
        self,
        flows: Iterable[TransportFlow] | ExplicitFlowPlan,
        *,
        years: Iterable[int] | None = None,
    ) -> TransportCostAllocationResult:
        """Allocate costs for raw flows or an ``ExplicitFlowPlan``.

        ``years`` can explicitly request zero-flow CAPEX/OPEX records.  Without
        it, the allocator uses all flow years and all years present in a cost
        schedule.
        """

        raw_flows = getattr(flows, "transport_flows", flows)
        flows_by_key = self._index_flows(raw_flows)

        flowed_legs = {leg_id for _, leg_id, _ in flows_by_key}
        missing_profiles = flowed_legs.difference(self._profiles)
        if missing_profiles:
            missing = ", ".join(sorted(missing_profiles))
            raise CostAllocationError(
                f"transport flow has no cost profile for leg(s): {missing}"
            )

        if years is None:
            selected_years = {
                year for _, _, year in flows_by_key
            }
            for profile in self._profiles.values():
                selected_years.update(profile.years)
        else:
            selected_years = set()
            for year in years:
                if isinstance(year, bool) or not isinstance(year, int):
                    raise TypeError("allocation years must be integers")
                selected_years.add(year)

        records: list[TransportCostAllocationRecord] = []
        for year in sorted(selected_years):
            for leg_id, profile in sorted(self._profiles.items()):
                participant_items = sorted(
                    (
                        (emitter_id, participation)
                        for (emitter_id, participant_leg_id), participation
                        in self._participations.items()
                        if participant_leg_id == leg_id
                    ),
                    key=lambda item: item[0],
                )
                if not participant_items:
                    raise CostAllocationError(
                        f"leg {leg_id!r} has a cost profile but no participants"
                    )

                has_flow = any(
                    (emitter_id, leg_id, year) in flows_by_key
                    for emitter_id, _ in participant_items
                )
                has_cost = (
                    profile.fixed_opex_eur(year) > 0.0
                    or profile.capex_eur(year) > 0.0
                )
                if years is None and not has_flow and not has_cost:
                    continue

                records.extend(
                    self._allocate_leg_year(
                        year=year,
                        leg_id=leg_id,
                        profile=profile,
                        participant_items=participant_items,
                        flows_by_key=flows_by_key,
                    )
                )

        return TransportCostAllocationResult(tuple(records))

    def _index_flows(
        self,
        flows: Iterable[TransportFlow],
    ) -> dict[tuple[str, str, int], float]:
        indexed: dict[tuple[str, str, int], float] = {}
        for flow in flows:
            key = (flow.emitter_id, flow.leg_id, flow.year)
            if key in indexed:
                raise CostAllocationError(
                    "duplicate transport flow for emitter "
                    f"{flow.emitter_id!r}, leg {flow.leg_id!r}, year {flow.year}"
                )
            if (flow.emitter_id, flow.leg_id) not in self._participations:
                raise CostAllocationError(
                    f"emitter {flow.emitter_id!r} is not registered on leg "
                    f"{flow.leg_id!r}"
                )
            if isinstance(flow.year, bool) or not isinstance(flow.year, int):
                raise TypeError("transport flow years must be integers")
            indexed[key] = _finite_nonnegative(
                flow.quantity_t,
                field_name=(
                    "transport flow quantity for "
                    f"{flow.emitter_id}/{flow.leg_id}/{flow.year}"
                ),
            )
        return indexed

    def _allocate_leg_year(
        self,
        *,
        year: int,
        leg_id: str,
        profile: TransportLegCostProfile,
        participant_items: Sequence[tuple[str, LegParticipation]],
        flows_by_key: Mapping[tuple[str, str, int], float],
    ) -> list[TransportCostAllocationRecord]:
        quantities = {
            emitter_id: flows_by_key.get((emitter_id, leg_id, year), 0.0)
            for emitter_id, _ in participant_items
        }
        leg_throughput = sum(quantities.values())

        reservation_values = {
            emitter_id: self._optional_nonnegative(
                participation.reservation_capacity_t_per_year,
                field_name=(
                    f"reservation_capacity_t_per_year for {emitter_id}/{leg_id}"
                ),
            )
            for emitter_id, participation in participant_items
        }
        ownership_values = {
            emitter_id: self._optional_nonnegative(
                participation.ownership_share,
                field_name=f"ownership_share for {emitter_id}/{leg_id}",
            )
            for emitter_id, participation in participant_items
        }
        fixed_share_values = {
            emitter_id: self._optional_nonnegative(
                participation.fixed_cost_share,
                field_name=f"fixed_cost_share for {emitter_id}/{leg_id}",
            )
            for emitter_id, participation in participant_items
        }

        reservation_shares = self._normalized_optional_shares(reservation_values)
        normalized_ownership = self._normalized_optional_shares(ownership_values)
        normalized_fixed = self._normalized_optional_shares(fixed_share_values)
        actual_shares = {
            emitter_id: quantity / leg_throughput if leg_throughput > 0.0 else 0.0
            for emitter_id, quantity in quantities.items()
        }

        basis_shares = {
            AllocationBasis.ACTUAL_FLOW: actual_shares,
            AllocationBasis.RESERVED_CAPACITY: reservation_shares,
            AllocationBasis.OWNERSHIP: normalized_ownership,
            AllocationBasis.FIXED_COST_SHARE: normalized_fixed,
        }

        fixed_total = profile.fixed_opex_eur(year)
        capex_total = profile.capex_eur(year)
        fixed_allocation = self._require_basis(
            basis=profile.fixed_opex_allocation_basis,
            shares=basis_shares[profile.fixed_opex_allocation_basis],
            total_cost=fixed_total,
            leg_id=leg_id,
            year=year,
            component="fixed OPEX",
        )
        capex_allocation = self._require_basis(
            basis=profile.capex_allocation_basis,
            shares=basis_shares[profile.capex_allocation_basis],
            total_cost=capex_total,
            leg_id=leg_id,
            year=year,
            component="CAPEX",
        )

        records: list[TransportCostAllocationRecord] = []
        for emitter_id, participation in participant_items:
            quantity = quantities[emitter_id]
            tariff_rate = self._optional_nonnegative(
                participation.tariff_eur_per_t,
                field_name=f"tariff_eur_per_t for {emitter_id}/{leg_id}",
            )
            tariff_rate = 0.0 if tariff_rate is None else tariff_rate
            records.append(
                TransportCostAllocationRecord(
                    year=year,
                    emitter_id=emitter_id,
                    leg_id=leg_id,
                    transported_t=quantity,
                    leg_throughput_t=leg_throughput,
                    actual_flow_share=actual_shares[emitter_id],
                    reserved_capacity_t_per_year=reservation_values[emitter_id],
                    reservation_share=reservation_shares[emitter_id],
                    ownership_share=ownership_values[emitter_id],
                    normalized_ownership_share=normalized_ownership[emitter_id],
                    fixed_cost_share=fixed_share_values[emitter_id],
                    normalized_fixed_cost_share=normalized_fixed[emitter_id],
                    variable_opex_eur_per_t=profile.variable_opex_eur_per_t,
                    variable_opex_eur=quantity * profile.variable_opex_eur_per_t,
                    tariff_eur_per_t=tariff_rate,
                    tariff_charge_eur=quantity * tariff_rate,
                    tariff_treatment=profile.tariff_treatment,
                    fixed_opex_allocation_basis=profile.fixed_opex_allocation_basis,
                    fixed_opex_allocation_share=fixed_allocation[emitter_id],
                    fixed_opex_eur=fixed_total * fixed_allocation[emitter_id],
                    capex_allocation_basis=profile.capex_allocation_basis,
                    capex_allocation_share=capex_allocation[emitter_id],
                    capex_eur=capex_total * capex_allocation[emitter_id],
                )
            )
        return records

    @classmethod
    def _normalized_optional_shares(
        cls,
        values: Mapping[str, float | None],
    ) -> dict[str, float | None]:
        declared = [value for value in values.values() if value is not None]
        if not declared or sum(declared) <= cls._TOLERANCE:
            return {key: None for key in values}
        denominator = sum(declared)
        return {
            key: (None if value is None else value / denominator)
            for key, value in values.items()
        }

    @staticmethod
    def _require_basis(
        *,
        basis: AllocationBasis,
        shares: Mapping[str, float | None],
        total_cost: float,
        leg_id: str,
        year: int,
        component: str,
    ) -> dict[str, float]:
        if total_cost <= 0.0:
            return {
                emitter_id: 0.0 if share is None else share
                for emitter_id, share in shares.items()
            }
        if not shares or any(share is None for share in shares.values()):
            raise CostAllocationError(
                f"cannot allocate {component} for leg {leg_id!r} in {year}: "
                f"basis {basis.value!r} has no usable shares"
            )
        numeric = {key: float(value) for key, value in shares.items()}
        if sum(numeric.values()) <= TransportCostAllocator._TOLERANCE:
            raise CostAllocationError(
                f"cannot allocate {component} for leg {leg_id!r} in {year}: "
                f"basis {basis.value!r} sums to zero"
            )
        return numeric

    @staticmethod
    def _optional_nonnegative(
        value: float | None,
        *,
        field_name: str,
    ) -> float | None:
        if value is None:
            return None
        return _finite_nonnegative(value, field_name=field_name)
