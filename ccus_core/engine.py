"""Facade: load a scenario, run the simulation, return standardised results.

This is the only module an application needs to import::

    from ccus_core import ScenarioEngine

    engine = ScenarioEngine.from_json("scenario.json")
    result = engine.run()
    result.ledger            # pandas DataFrame, one row per year
    result.routing_frame()    # pandas DataFrame, one row per allocation
    result.snapshot(2032)     # per-year state for a timeline scrubber

Nothing here imports Streamlit, matplotlib or any other UI toolkit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ccus_core.models import ScenarioConfig
from ccus_core.network.graph import NetworkGraph

from .simulation.geothermal import ensure_coupled_doublets
from .simulation.solver import ChronologicalSolver, SimulationResult


@dataclass(frozen=True)
class YearSnapshot:
    """State of the whole system in one year (timeline scrubbing)."""

    year: int
    emitters: list[dict[str, object]]
    edges: list[dict[str, object]]
    sinks: list[dict[str, object]]
    totals: dict[str, float]


def year_snapshot(result: SimulationResult, year: int) -> YearSnapshot:
    """Return the per-year view used by the timeline slider and the map."""

    graph = NetworkGraph(result.scenario)
    year = int(year)

    emitters: list[dict[str, object]] = []
    for emitter in result.scenario.emitters:
        captured = emitter.captured_emissions(year)
        emitters.append(
            {
                "id": emitter.id,
                "name": emitter.name,
                "node_id": emitter.node_id,
                "active": emitter.active_in(year),
                "captured_t": float(captured),
            }
        )

    routing = next((item for item in result.routing if int(item.year) == year), None)
    flows = dict(routing.edge_flows) if routing is not None else {}

    edges: list[dict[str, object]] = []
    for edge in result.scenario.edges:
        state = edge.resolve_state(year)
        edges.append(
            {
                "id": edge.id,
                "name": edge.name,
                "from_node": edge.from_node,
                "to_node": edge.to_node,
                "mode": None if state is None else state.mode.value,
                "active": state is not None,
                "capacity_t": 0.0 if state is None else state.effective_capacity_t_per_year(),
                "flow_t": float(flows.get(edge.id, 0.0)),
                "tariff_eur_per_t": 0.0 if state is None else state.variable_opex_eur_per_t(),
            }
        )

    sinks: list[dict[str, object]] = []
    for sink in result.scenario.storage_sinks:
        frame = result.reservoir.get(sink.id)
        injected = 0.0
        cumulative = 0.0
        pressure = float("nan")
        if frame is not None:
            row = frame.loc[frame["year"] == year]
            if not row.empty:
                injected = float(row["co2_injected_t"].iloc[0])
                cumulative = float(row["co2_cumulative_t"].iloc[0])
                pressure = float(row["pressure_bar"].iloc[0])
        sinks.append(
            {
                "id": sink.id,
                "name": sink.name,
                "node_id": sink.node_id,
                "injected_t": injected,
                "cumulative_t": cumulative,
                "remaining_t": max(0.0, float(sink.capacity_t) - cumulative),
                "pressure_bar": pressure,
                "active": bool(injected > 0.0),
            }
        )

    totals = {
        "captured_t": float(sum(float(item["captured_t"]) for item in emitters)),
        "routed_t": float(routing.total_allocated_t) if routing is not None else 0.0,
        "injected_t": float(sum(float(item["injected_t"]) for item in sinks)),
        "stored_t": float(sum(float(item["cumulative_t"]) for item in sinks)),
    }
    return YearSnapshot(year=year, emitters=emitters, edges=edges, sinks=sinks, totals=totals)


class ScenarioEngine:
    """Initialise a scenario, run the simulation, expose standardised results."""

    def __init__(self, scenario: ScenarioConfig, *, fluid_props=None, verbose: bool = False):
        # engine-side defaults: a sink flagged `geothermal_coupled` receives its
        # doublet here so the UI never has to invent one
        self.scenario = ensure_coupled_doublets(scenario)
        self.fluid_props = fluid_props
        self.verbose = bool(verbose)

    # ------------------------------------------------------------------ constructors
    @classmethod
    def from_dict(cls, payload: dict, **kwargs) -> "ScenarioEngine":
        from ccus_core.io.commented_json import from_payload

        return cls(from_payload(payload), **kwargs)

    @classmethod
    def from_json(cls, path: str | Path, **kwargs) -> "ScenarioEngine":
        from ccus_core.io.commented_json import load_file

        return cls(load_file(path), **kwargs)

    # ------------------------------------------------------------------ run
    def run(self) -> SimulationResult:
        solver = ChronologicalSolver(
            self.scenario,
            fluid_props=self.fluid_props,
            verbose=self.verbose,
        )
        return solver.run()

    def snapshot(self, result: SimulationResult, year: int) -> YearSnapshot:
        return year_snapshot(result, year)

    def years(self) -> list[int]:
        return self.scenario.years()


def run_scenario(config: ScenarioConfig | dict, **kwargs) -> SimulationResult:
    """Convenience wrapper: config in, :class:`SimulationResult` out."""

    if isinstance(config, ScenarioConfig):
        scenario = config
    else:
        from ccus_core.io.commented_json import from_payload

        scenario = from_payload(config)
    return ScenarioEngine(scenario, **kwargs).run()