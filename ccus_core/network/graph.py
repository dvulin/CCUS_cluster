"""Transport network topology derived from a :class:`ScenarioConfig`."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ccus_core.models import ScenarioConfig, TransportEdge


@dataclass(frozen=True)
class Arc:
    """A directed, time-dependent traversal of an edge."""

    edge_id: str
    from_node: str
    to_node: str


class NetworkGraph:
    """Read-only view of the scenario graph.

    The graph holds no solver state: capacities and tariffs are resolved per
    year from the edge models, so the same object can be queried for any year
    without being mutated.
    """

    def __init__(self, scenario: ScenarioConfig):
        self.scenario = scenario
        self.nodes = {node.id: node for node in scenario.nodes}
        self.edges = {edge.id: edge for edge in scenario.edges}
        self.sinks = {sink.id: sink for sink in scenario.storage_sinks}
        self._outgoing: dict[str, list[Arc]] = defaultdict(list)
        self._incoming: dict[str, list[Arc]] = defaultdict(list)
        for edge in scenario.edges:
            arcs = [(edge.from_node, edge.to_node)]
            if edge.bidirectional:
                arcs.append((edge.to_node, edge.from_node))
            for start, end in arcs:
                arc = Arc(edge_id=edge.id, from_node=start, to_node=end)
                self._outgoing[start].append(arc)
                self._incoming[end].append(arc)

    # ------------------------------------------------------------------ topology
    def outgoing(self, node_id: str) -> list[Arc]:
        return list(self._outgoing.get(node_id, []))

    def incoming(self, node_id: str) -> list[Arc]:
        return list(self._incoming.get(node_id, []))

    def edge(self, edge_id: str) -> TransportEdge:
        try:
            return self.edges[edge_id]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"unknown edge '{edge_id}'") from exc

    def sink_nodes(self) -> set[str]:
        return {sink.node_id for sink in self.scenario.storage_sinks}

    def sink_for_node(self, node_id: str):
        return next((sink for sink in self.scenario.storage_sinks if sink.node_id == node_id), None)

    def emitter_nodes(self) -> dict[str, str]:
        """Map ``emitter_id -> node_id`` for every emitter in the scenario."""

        return {emitter.id: emitter.node_id for emitter in self.scenario.emitters}

    def active_arcs(self, year: int, **state_kwargs: float) -> list[tuple[Arc, TransportEdge, object]]:
        """Arcs whose edge offers positive capacity in ``year``."""

        result = []
        for node_id in self._outgoing:
            for arc in self._outgoing[node_id]:
                edge = self.edges[arc.edge_id]
                state = edge.resolve_state(year, **state_kwargs)
                if state is None:
                    continue
                if state.effective_capacity_t_per_year() <= 0.0:
                    continue
                result.append((arc, edge, state))
        return result

    def summary(self) -> dict[str, object]:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "sinks": len(self.sinks),
            "modes": sorted({state.mode.value for edge in self.edges.values() for state in edge.states}),
        }