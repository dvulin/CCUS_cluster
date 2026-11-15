"""Root scenario document: the JSON contract of the whole engine."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .base import MODEL_VERSION, CoreModel, Slug, year_axis
from .economics import EconomicsConfig
from .edge import TransportEdge
from .emitter import Emitter
from .node import Node
from .sink import GeothermalSystem, StorageSink


class ScenarioConfig(CoreModel):
    """Everything the engine needs, and nothing it does not.

    A scenario is pure data: it can be loaded from JSON, validated, round-tripped
    and handed to the solver.  It deliberately contains no solver state, so the
    same object can be reused by a web UI, a desktop app or a notebook.
    """

    schema_version: str = MODEL_VERSION
    id: Slug
    name: str = Field(min_length=1)
    start_year: int
    end_year: int
    step: Literal["yearly", "monthly"] = "yearly"
    nodes: list[Node] = Field(default_factory=list)
    emitters: list[Emitter] = Field(default_factory=list)
    edges: list[TransportEdge] = Field(default_factory=list)
    storage_sinks: list[StorageSink] = Field(default_factory=list)
    geothermal_systems: list[GeothermalSystem] = Field(default_factory=list)
    economics: EconomicsConfig | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_graph(self) -> "ScenarioConfig":
        if self.end_year < self.start_year:
            raise ValueError("end_year must not precede start_year")

        node_ids = [node.id for node in self.nodes]
        self._require_unique(node_ids, "node")
        known_nodes = set(node_ids)

        self._require_unique([emitter.id for emitter in self.emitters], "emitter")
        self._require_unique([edge.id for edge in self.edges], "edge")
        self._require_unique([sink.id for sink in self.storage_sinks], "storage sink")
        self._require_unique([system.id for system in self.geothermal_systems], "geothermal system")

        for emitter in self.emitters:
            if emitter.node_id not in known_nodes:
                raise ValueError(f"emitter '{emitter.id}' references unknown node '{emitter.node_id}'")

        for edge in self.edges:
            for endpoint in (edge.from_node, edge.to_node):
                if endpoint not in known_nodes:
                    raise ValueError(f"edge '{edge.id}' references unknown node '{endpoint}'")
            for state in edge.states:
                if state.marine is not None and state.marine.port_node_id not in known_nodes:
                    raise ValueError(
                        f"edge '{edge.id}' references unknown port '{state.marine.port_node_id}'"
                    )

        for sink in self.storage_sinks:
            if sink.node_id not in known_nodes:
                raise ValueError(f"storage sink '{sink.id}' references unknown node '{sink.node_id}'")

        for system in self.geothermal_systems:
            if system.node_id not in known_nodes:
                raise ValueError(
                    f"geothermal system '{system.id}' references unknown node '{system.node_id}'"
                )

        if self.economics is not None:
            if self.economics.start_year < self.start_year or self.economics.end_year > self.end_year:
                raise ValueError("the economic horizon must lie inside the simulation horizon")

        if not self.storage_sinks:
            raise ValueError("a scenario needs at least one storage sink")
        if not self.emitters:
            raise ValueError("a scenario needs at least one emitter")

        return self

    @staticmethod
    def _require_unique(values: list[str], label: str) -> None:
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ValueError(f"duplicate {label} id(s): {', '.join(duplicates)}")

    # ------------------------------------------------------------------ helpers
    def years(self) -> list[int]:
        """Calendar-year axis of the scenario."""

        return year_axis(self.start_year, self.end_year)

    def node_by_id(self, node_id: str) -> Node | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def emitter_by_id(self, emitter_id: str) -> Emitter | None:
        return next((emitter for emitter in self.emitters if emitter.id == emitter_id), None)

    def sink_by_id(self, sink_id: str) -> StorageSink | None:
        return next((sink for sink in self.storage_sinks if sink.id == sink_id), None)

    def edge_by_id(self, edge_id: str) -> TransportEdge | None:
        return next((edge for edge in self.edges if edge.id == edge_id), None)

    def geothermal_by_id(self, system_id: str) -> GeothermalSystem | None:
        return next((system for system in self.geothermal_systems if system.id == system_id), None)

    def emitters_active_in(self, year: int) -> list[Emitter]:
        return [emitter for emitter in self.emitters if emitter.active_in(int(year))]

    def total_captured_t_per_year(self, year: int) -> float:
        """CO2 offered by all emitters in ``year`` (t/yr)."""

        return float(sum(emitter.captured_emissions(year) for emitter in self.emitters))

    def total_capacity_t_per_year(self, year: int, **state_kwargs: float) -> float:
        """Sum of the capacities of every edge serving ``year``."""

        return float(sum(edge.capacity_in(year, **state_kwargs) for edge in self.edges))

    def summary(self) -> dict[str, object]:
        """Compact, JSON-safe description used by the UI header and by tests."""

        return {
            "id": self.id,
            "name": self.name,
            "schema_version": self.schema_version,
            "years": [self.start_year, self.end_year],
            "step": self.step,
            "counts": {
                "nodes": len(self.nodes),
                "emitters": len(self.emitters),
                "edges": len(self.edges),
                "storage_sinks": len(self.storage_sinks),
                "geothermal_systems": len(self.geothermal_systems),
            },
            "total_capacity_t": float(sum(sink.capacity_t for sink in self.storage_sinks)),
            "first_onboarding_year": (
                min(emitter.activation_year for emitter in self.emitters) if self.emitters else None
            ),
        }