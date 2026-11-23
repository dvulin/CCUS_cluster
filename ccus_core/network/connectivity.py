"""Can every emitter actually reach a storage site?

A scenario can be perfectly valid as a data model and still be useless: an emitter
with no link to any sink contributes nothing to the chain, and the solver only
reports it as "unallocated" at the end.  This module answers the question up front,
from the link graph alone - no simulation, no I/O, no UI.

It also answers the distance question the designer asks about every leg: how far
the CO2 still has to travel from that leg to each storage site
(:func:`distance_to_sinks`).
"""

from __future__ import annotations

from collections import deque
from heapq import heappop, heappush

#: the storage-like node kinds a sink can live on
SINK_KINDS = {"storage", "geothermal"}


def adjacency(scenario) -> dict[str, list[str]]:
    """Node -> the nodes a link leaves it for (links are directed)."""

    graph: dict[str, list[str]] = {}
    for edge in scenario.edges:
        graph.setdefault(edge.from_node, []).append(edge.to_node)
    return graph


def sink_nodes(scenario) -> set[str]:
    """Nodes that inject into a storage site."""

    nodes = {sink.node_id for sink in scenario.storage_sinks}
    nodes.update(node.id for node in scenario.nodes if node.kind.value in SINK_KINDS)
    return nodes


def reachable_from(scenario, start: str) -> set[str]:
    """Every node reachable from ``start`` by following links."""

    graph = adjacency(scenario)
    seen: set[str] = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbour in graph.get(current, []):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return seen


def unreachable_emitters(scenario) -> list[dict]:
    """Emitters with no path to a storage site, with the reason why.

    Each entry is ``{"emitter_id", "name", "node_id", "reason"}``.  An emitter whose
    node *is* a sink node counts as connected (it injects on the spot).
    """

    sinks = sink_nodes(scenario)
    if not sinks:
        return [
            {
                "emitter_id": emitter.id,
                "name": emitter.name,
                "node_id": emitter.node_id,
                "reason": "the scenario has no storage sink",
            }
            for emitter in scenario.emitters
        ]

    graph = adjacency(scenario)
    problems: list[dict] = []
    for emitter in scenario.emitters:
        start = emitter.node_id
        if start in sinks:
            continue
        reached = reachable_from(scenario, start)
        if reached & sinks:
            continue
        if not graph.get(start):
            reason = f"no link starts at '{start}'"
        else:
            reason = f"no path from '{start}' to a storage hub"
        problems.append(
            {
                "emitter_id": emitter.id,
                "name": emitter.name,
                "node_id": start,
                "reason": reason,
            }
        )
    return problems


def _arcs(scenario) -> list[tuple[str, str, str, float]]:
    """``(from_node, to_node, edge_id, length_km)`` for every traversable direction.

    Only the first state of an edge carries a length the designer's table edits;
    a state timeline keeps its own distances, so the first state is the reference
    (the same one ``scenario_to_frames`` shows).
    """

    arcs: list[tuple[str, str, str, float]] = []
    for edge in scenario.edges:
        length = float(edge.states[0].distance_km) if edge.states else 0.0
        arcs.append((edge.from_node, edge.to_node, edge.id, length))
        if edge.bidirectional:
            arcs.append((edge.to_node, edge.from_node, edge.id, length))
    return arcs


def _reverse_adjacency(scenario) -> dict[str, list[tuple[str, float]]]:
    """``node -> [(previous node, length)]``, i.e. the graph walked backwards."""

    reverse: dict[str, list[tuple[str, float]]] = {}
    for start, end, _edge_id, length in _arcs(scenario):
        reverse.setdefault(end, []).append((start, length))
    return reverse


def _distance_from(reverse: dict[str, list[tuple[str, float]]], source: str) -> dict[str, float]:
    """Dijkstra over the reversed graph: the distance from every node to ``source``."""

    distances = {source: 0.0}
    queue: list[tuple[float, str]] = [(0.0, source)]
    while queue:
        current, node = heappop(queue)
        if current > distances.get(node, float("inf")) + 1e-12:
            continue
        for previous, length in reverse.get(node, ()):
            candidate = current + length
            if candidate < distances.get(previous, float("inf")) - 1e-12:
                distances[previous] = candidate
                heappush(queue, (candidate, previous))
    return distances


def distance_to_sinks(scenario) -> dict[str, dict[str, float]]:
    """How far the CO2 on each leg still has to travel, per storage site.

    The convention is the one the designer shows:

    * ``total(edge) = length(edge) + total(next edge towards the sink)``;
    * the leg that enters a storage site is therefore worth its own length;
    * a chain ``emitter -> L2 -> L3 -> sink`` reports ``d(L1)+d(L2)+d(L3)`` on
      the first leg, ``d(L2)+d(L3)`` on the second, and ``d(L3)`` on the last.

    Returns ``{edge_id: {sink_id: km}}``.  A leg with no directed path to a
    storage site is **absent** from the mapping rather than reported as zero -
    "no path" and "zero distance" are different statements.  A bidirectional leg
    reports the cheaper of its two directions, because CO2 may enter it either
    way.
    """

    reverse = _reverse_adjacency(scenario)
    sinks_by_node: dict[str, list[str]] = {}
    for sink in scenario.storage_sinks:
        sinks_by_node.setdefault(sink.node_id, []).append(sink.id)

    cache = {node: _distance_from(reverse, node) for node in sinks_by_node}

    distances: dict[str, dict[str, float]] = {}
    for edge in scenario.edges:
        length = float(edge.states[0].distance_km) if edge.states else 0.0
        ends = [edge.to_node]
        if edge.bidirectional:
            ends.append(edge.from_node)

        per_sink: dict[str, float] = {}
        for node in ends:
            for sink_node, sink_ids in sinks_by_node.items():
                remaining = cache[sink_node].get(node)
                if remaining is None:
                    continue
                total = length + remaining
                for sink_id in sink_ids:
                    best = per_sink.get(sink_id)
                    if best is None or total < best:
                        per_sink[sink_id] = total
        if per_sink:
            distances[edge.id] = per_sink
    return distances


def edge_distance_to_sink(scenario, sink_id: str) -> dict[str, float]:
    """``{edge_id: km}`` for one storage site - the designer's selected target."""

    wanted = str(sink_id)
    return {
        edge_id: per_sink[wanted]
        for edge_id, per_sink in distance_to_sinks(scenario).items()
        if wanted in per_sink
    }


def connectivity_report(scenario) -> dict[str, object]:
    """A summary for the UI: counts plus the emitters that are cut off."""

    problems = unreachable_emitters(scenario)
    return {
        "emitters": len(scenario.emitters),
        "sinks": len(sinks) if (sinks := sink_nodes(scenario)) else 0,
        "unreachable": problems,
        "ok": not problems,
    }


__all__ = [
    "SINK_KINDS",
    "adjacency",
    "connectivity_report",
    "distance_to_sinks",
    "edge_distance_to_sink",
    "reachable_from",
    "sink_nodes",
    "unreachable_emitters",
]