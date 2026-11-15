"""Emitter-to-sink connections (many-to-many cluster definition).

A connection is the *business* object an engineer edits: "emitter A can reach
storage site S from year Y with mode M, distance L and these costs".  The solver
consumes transport *edges*, so ``ScenarioConfig`` expands every connection into
one directed edge (and its time-dependent state) before validation finishes.

Because the expansion is per connection, the model naturally supports

* many sinks per emitter (several connections with different ``sink_id``),
* many emitters per sink (many connections pointing at the same sink),
* a different onboarding year for every pair (independent ``start_year``).
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .base import CoreModel, Slug
from .edge import (
    EdgeState,
    MarineDesign,
    PipelineDesign,
    RoadDesign,
    TransportEdge,
    TransportMode,
)


class EmitterSinkConnection(CoreModel):
    """One emitter → sink access, active from ``start_year``."""

    emitter_id: Slug
    sink_id: Slug
    start_year: int = Field(description="First year this access can be used.")
    end_year: int | None = None
    mode: TransportMode = TransportMode.PIPELINE
    distance_km: float = Field(default=0.0, ge=0.0)
    capacity_t_per_year: float | None = Field(default=None, gt=0.0)
    capex_eur: float = Field(default=0.0, ge=0.0)
    opex_eur_per_t: float = Field(default=0.0, ge=0.0)
    opex_eur_per_tkm: float = Field(default=0.0, ge=0.0)
    availability: float = Field(default=1.0, ge=0.0, le=1.0)
    pipeline: PipelineDesign | None = None
    road: RoadDesign | None = None
    marine: MarineDesign | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check_window(self) -> "EmitterSinkConnection":
        if self.end_year is not None and self.end_year < self.start_year:
            raise ValueError("end_year must not precede start_year")
        return self

    def edge_id(self) -> str:
        return f"{self.emitter_id}__to__{self.sink_id}"

    def state(self) -> EdgeState:
        pipeline = self.pipeline
        if self.mode is TransportMode.PIPELINE and pipeline is None:
            pipeline = PipelineDesign(
                inner_diameter_m=0.30, inlet_pressure_bar=150.0, inlet_temperature_c=20.0
            )
        return EdgeState(
            mode=self.mode,
            valid_from_year=int(self.start_year),
            valid_until_year=None if self.end_year is None else int(self.end_year),
            capacity_t_per_year=self.capacity_t_per_year,
            distance_km=float(self.distance_km),
            capex_eur=float(self.capex_eur),
            opex_eur_per_t=float(self.opex_eur_per_t),
            opex_eur_per_tkm=float(self.opex_eur_per_tkm),
            availability=float(self.availability),
            pipeline=pipeline,
            road=self.road,
            marine=self.marine,
            notes=self.notes,
        )

    def to_edge(self, *, from_node: str, to_node: str) -> TransportEdge:
        return TransportEdge(
            id=self.edge_id(),
            name=f"{self.emitter_id} → {self.sink_id}",
            from_node=from_node,
            to_node=to_node,
            states=[self.state()],
            notes=self.notes,
        )