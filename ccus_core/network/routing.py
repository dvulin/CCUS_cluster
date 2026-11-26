"""Chronological, capacity-constrained CO2 routing over the transport graph.

The router is deliberately simple, deterministic and auditable: for each year it
allocates every emitter's captured CO2 along the cheapest feasible path to a
storage sink with residual capacity.  "Cheapest" is the sum of the per-tonne
tariffs of the arcs, with the hop count and the edge id as deterministic
tie-breakers.  Residual capacities (edges, sinks, injection rates) are updated as
the allocation proceeds, so a later emitter can be starved by an earlier one –
which is exactly the behaviour a cluster study needs to expose.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from ccus_core.models import TransportEdge

from .graph import Arc, NetworkGraph


class Allocation(BaseModel):
    """One emitter-to-sink flow along a concrete path."""

    emitter_id: str
    sink_id: str
    path_edge_ids: list[str]
    quantity_t: float = Field(ge=0.0)
    unit_cost_eur_per_t: float = Field(ge=0.0)
    cost_eur: float = Field(ge=0.0)


class RoutingResult(BaseModel):
    """Everything the solver and the cash-flow model need for one year."""

    year: int
    allocations: list[Allocation] = Field(default_factory=list)
    edge_flows: dict[str, float] = Field(default_factory=dict)
    sink_injections: dict[str, float] = Field(default_factory=dict)
    unallocated: dict[str, float] = Field(default_factory=dict)
    rate_limited_sinks: list[str] = Field(
        default_factory=list,
        description="Sinks whose declared injection-rate cap stopped the allocation this year.",
    )
    capacity_limited_sinks: list[str] = Field(
        default_factory=list,
        description="Sinks whose remaining pore volume reached zero this year.",
    )
    notes: list[str] = Field(default_factory=list)

    @property
    def total_allocated_t(self) -> float:
        return float(sum(item.quantity_t for item in self.allocations))

    @property
    def total_cost_eur(self) -> float:
        return float(sum(item.cost_eur for item in self.allocations))

    def to_records(self) -> list[dict[str, object]]:
        return [
            {
                "year": self.year,
                "emitter_id": item.emitter_id,
                "sink_id": item.sink_id,
                "path": " -> ".join(item.path_edge_ids),
                "quantity_t": item.quantity_t,
                "unit_cost_eur_per_t": item.unit_cost_eur_per_t,
                "cost_eur": item.cost_eur,
            }
            for item in self.allocations
        ]


@dataclass
class _Path:
    edge_ids: list[str]
    capacity_t: float
    tariff_eur_per_t: float
    hops: int

    @property
    def cost_eur_per_t(self) -> float:
        return self.tariff_eur_per_t


class RoutingEngine:
    """Stateless capacity-constrained allocator over a :class:`NetworkGraph`."""

    def __init__(self, graph: NetworkGraph):
        self.graph = graph

    # ------------------------------------------------------------------ internals
    def _enumerate_paths(
        self,
        start: str,
        year: int,
        residual_edge: dict[str, float],
        sink_nodes: set[str],
        *,
        fired_upgrades: Mapping[str, Mapping[str, int]] | None = None,
        cumulative_mass: Mapping[str, float] | None = None,
    ) -> list[_Path]:
        fired = dict(fired_upgrades or {})
        mass = dict(cumulative_mass or {})
        paths: list[_Path] = []

        def walk(node: str, visited: tuple[str, ...], edge_ids: list[str], bottleneck: float, tariff: float) -> None:
            for arc in self.graph.outgoing(node):
                if arc.to_node in visited:
                    continue
                edge = self.graph.edge(arc.edge_id)
                residual = residual_edge.get(arc.edge_id, 0.0)
                if residual <= 0.0:
                    continue
                state = edge.resolve_state(
                    year,
                    cumulative_mass_t=mass.get(edge.id),
                    fired_upgrades=fired.get(edge.id, {}),
                )
                if state is None:
                    continue
                capacity = state.effective_capacity_t_per_year()
                if capacity <= 0.0:
                    continue
                new_bottleneck = min(bottleneck, capacity, residual)
                if new_bottleneck <= 0.0:
                    continue
                next_visited = visited + (arc.to_node,)
                next_edges = edge_ids + [edge.id]
                next_tariff = tariff + state.variable_opex_eur_per_t()
                if arc.to_node in sink_nodes:
                    paths.append(
                        _Path(
                            edge_ids=next_edges,
                            capacity_t=new_bottleneck,
                            tariff_eur_per_t=next_tariff,
                            hops=len(next_edges),
                        )
                    )
                    continue
                if len(next_visited) > len(self.graph.nodes):
                    continue
                walk(arc.to_node, next_visited, next_edges, new_bottleneck, next_tariff)

        walk(start, (start,), [], float("inf"), 0.0)
        paths.sort(key=lambda item: (round(item.cost_eur_per_t, 9), item.hops, item.edge_ids))
        return paths

    def _sink_order(self, year: int) -> list[str]:
        """Deterministic sink processing order (commissioning year, then id)."""

        return sorted(
            self.graph.sinks,
            key=lambda sink_id: (
                self.graph.sinks[sink_id].commissioning_year or 0,
                sink_id,
            ),
        )

    # ------------------------------------------------------------------ public API
    def route(
        self,
        *,
        year: int,
        supplies: Mapping[str, float],
        sink_remaining_capacity: Mapping[str, float],
        fired_upgrades: Mapping[str, Mapping[str, int]] | None = None,
        cumulative_mass: Mapping[str, float] | None = None,
        sink_injection_limits: Mapping[str, float] | None = None,
        edge_prior_flow: Mapping[str, float] | None = None,
    ) -> RoutingResult:
        """Allocate ``supplies`` (t/yr) for one calendar year.

        ``fired_upgrades`` maps ``edge_id -> {upgrade_id: year the trigger fired}``
        and is what makes a *conditional* (cumulative-mass) upgrade visible to the
        router: the chronological solver records the firing year and feeds it back.
        ``cumulative_mass`` is the mass already shipped through each edge, used to
        evaluate a mass trigger in the year it is crossed.  ``sink_injection_limits``
        caps the injection rate of a sink independently of its total capacity.
        """

        result = RoutingResult(year=int(year))
        sink_nodes = self.graph.sink_nodes()
        if not sink_nodes:
            result.notes.append("no storage sink is connected to the graph")
            result.unallocated = {emitter: float(value) for emitter, value in supplies.items() if value > 0.0}
            return result

        residual_edge: dict[str, float] = {}
        for edge in self.graph.edges.values():
            state = edge.resolve_state(
                year,
                cumulative_mass_t=(cumulative_mass or {}).get(edge.id),
                fired_upgrades=dict((fired_upgrades or {}).get(edge.id, {})),
            )
            residual_edge[edge.id] = 0.0 if state is None else state.effective_capacity_t_per_year()

        limits = {key: float(value) for key, value in (sink_injection_limits or {}).items()}
        residual_sink: dict[str, float] = {}
        total_residual: dict[str, float] = {}
        for sink_id, value in sink_remaining_capacity.items():
            cap = float(value)
            limit = limits.get(sink_id)
            total_residual[sink_id] = cap
            if limit is not None:
                cap = min(cap, limit)
            residual_sink[sink_id] = cap
        injection_totals: dict[str, float] = dict.fromkeys(self.graph.sinks, 0.0)
        rate_limited: set[str] = set()

        for emitter_id in sorted(supplies):
            remaining = float(supplies[emitter_id])
            if remaining <= 0.0:
                continue
            start = self.graph.emitter_nodes().get(emitter_id)
            if start is None:
                result.unallocated[emitter_id] = remaining
                continue

            guard = 0
            while remaining > 1e-9 and guard < 64:
                guard += 1
                paths = self._enumerate_paths(
                    start,
                    year,
                    residual_edge,
                    sink_nodes,
                    fired_upgrades=fired_upgrades,
                    cumulative_mass=cumulative_mass,
                )
                chosen = None
                for path in paths:
                    sink_node = self.graph.edge(path.edge_ids[-1]).to_node
                    sink = self.graph.sink_for_node(sink_node)
                    if sink is None:
                        continue
                    residual_capacity = residual_sink.get(sink.id, 0.0)
                    if residual_capacity <= 1e-9:
                        # the sink still has pore volume but its well cannot take
                        # more this year: record the rate limit for the UI
                        if sink.id in limits and total_residual.get(sink.id, 0.0) > 1e-9:
                            rate_limited.add(sink.id)
                        continue
                    chosen = (path, sink, residual_capacity)
                    break

                if chosen is None:
                    break

                path, sink, residual_capacity = chosen
                quantity = min(remaining, path.capacity_t, residual_capacity)
                if quantity <= 1e-9:
                    break

                cost_per_t = path.cost_eur_per_t
                result.allocations.append(
                    Allocation(
                        emitter_id=emitter_id,
                        sink_id=sink.id,
                        path_edge_ids=path.edge_ids,
                        quantity_t=quantity,
                        unit_cost_eur_per_t=cost_per_t,
                        cost_eur=quantity * cost_per_t,
                    )
                )
                for edge_id in path.edge_ids:
                    residual_edge[edge_id] = residual_edge.get(edge_id, 0.0) - quantity
                    result.edge_flows[edge_id] = result.edge_flows.get(edge_id, 0.0) + quantity
                residual_sink[sink.id] = residual_capacity - quantity
                total_residual[sink.id] = total_residual.get(sink.id, 0.0) - quantity
                injection_totals[sink.id] = injection_totals.get(sink.id, 0.0) + quantity
                remaining -= quantity

            if remaining > 1e-9:
                result.unallocated[emitter_id] = remaining

        result.sink_injections = injection_totals
        result.rate_limited_sinks = sorted(rate_limited)
        result.capacity_limited_sinks = sorted(
            sink_id for sink_id, value in total_residual.items() if value <= 1e-9
        )
        if result.unallocated:
            result.notes.append(
                "unrouted CO2: "
                + ", ".join(f"{emitter}={value:,.0f} t" for emitter, value in sorted(result.unallocated.items()))
            )
        return result


def route_timeline(
    graph: NetworkGraph,
    years: Sequence[int],
    supplies_by_year: Mapping[int, Mapping[str, float]],
    sink_capacity: Mapping[str, float],
    *,
    injection_rate_limits: Mapping[str, float] | None = None,
    fired_upgrades: Mapping[int, Mapping[str, Mapping[str, int]]] | None = None,
    cumulative_mass: Mapping[str, float] | None = None,
) -> list[RoutingResult]:
    """Convenience helper: route a whole schedule while tracking sink capacity.

    ``injection_rate_limits`` caps the annual injection rate of a sink, and
    ``cumulative_mass`` seeds the mass-trigger bookkeeping (per edge) so a
    conditional upgrade can fire in the year its threshold is crossed.
    """

    engine = RoutingEngine(graph)
    remaining = {sink_id: float(value) for sink_id, value in sink_capacity.items()}
    limits = dict(injection_rate_limits or {})
    fired_by_year = dict(fired_upgrades or {})
    mass_by_year = dict(cumulative_mass or {})
    results: list[RoutingResult] = []
    for year in years:
        supplies = dict(supplies_by_year.get(int(year), {}))
        caps = dict(remaining)
        result = engine.route(
            year=year,
            supplies=supplies,
            sink_remaining_capacity=caps,
            sink_injection_limits=limits or None,
            cumulative_mass=mass_by_year,
            fired_upgrades=fired_by_year.get(int(year)),
        )
        for sink_id, injected in result.sink_injections.items():
            remaining[sink_id] = remaining.get(sink_id, 0.0) - injected
        for edge_id, flow in result.edge_flows.items():
            mass_by_year[edge_id] = mass_by_year.get(edge_id, 0.0) + float(flow)
        results.append(result)
    return results