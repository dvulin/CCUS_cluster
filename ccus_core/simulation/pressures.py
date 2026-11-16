"""Hub pressure cascade: emitter → hub → hub → storage, year by year.

For every routed path the module walks backwards from the storage hub
(``target_precompression_bar``, default 10 bar) and adds the friction loss of each
leg, producing the pressure that must exist at every node.  The resulting table is
the technical basis for the compression duty of each emitter.
"""

from __future__ import annotations

import pandas as pd

from ccus_core.models import ScenarioConfig

from ..network.pressure import DEFAULT_PRECOMPRESSION_BAR, LegSpec, solve_chain

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0


def _fluid_props():
    try:
        from engineering import FluidProperties

        return FluidProperties()
    except Exception:  # pragma: no cover
        return None


def pressure_table(
    scenario: ScenarioConfig,
    result,
    *,
    target_precompression_bar: float = DEFAULT_PRECOMPRESSION_BAR,
    temperature_c: float = 20.0,
) -> pd.DataFrame:
    """Year-by-year pressure state of every chain leg (and the compression point)."""

    fluid_props = _fluid_props()
    rows: list[dict[str, object]] = []

    for routing in result.routing:
        year = int(routing.year)
        edge_flow = {edge_id: float(value) for edge_id, value in routing.edge_flows.items()}

        # allocations that share a path are solved together, because the shared
        # legs carry the *sum* of their flows (that is what changes the pressure)
        by_path: dict[tuple[str, ...], list] = {}
        for allocation in routing.allocations:
            by_path.setdefault(tuple(allocation.path_edge_ids), []).append(allocation)

        for path, allocations in by_path.items():
            first = allocations[0]
            if scenario.sink_by_id(first.sink_id) is None:
                continue
            chain: list[LegSpec] = []
            for edge_id in path:
                edge = scenario.edge_by_id(edge_id)
                if edge is None:
                    continue
                state = edge.resolve_state(year)
                if state is None or state.pipeline is None:
                    continue
                flow_kg_s = edge_flow.get(edge_id, 0.0) * 1000.0 / SECONDS_PER_YEAR
                chain.append(
                    LegSpec(
                        edge_id=edge.id,
                        from_node=edge.from_node,
                        to_node=edge.to_node,
                        length_m=float(state.distance_km) * 1000.0,
                        diameter_m=float(state.pipeline.inner_diameter_m),
                        flow_kg_s=flow_kg_s,
                        roughness_m=float(state.pipeline.roughness_m),
                    )
                )
            if not chain:
                continue

            states = solve_chain(
                chain,
                target_outlet_bar=target_precompression_bar,
                temperature_c=temperature_c,
                fluid_props=fluid_props,
            )
            for index, leg in enumerate(states):
                for allocation in allocations:
                    rows.append(
                        {
                            "year": year,
                            "emitter_id": allocation.emitter_id,
                            "sink_id": allocation.sink_id,
                            "leg_index": index,
                            "edge_id": leg.edge_id,
                            "from_node": leg.from_node,
                            "to_node": leg.to_node,
                            "length_km": round(leg.length_km, 1),
                            "flow_kg_s": round(leg.flow_kg_s, 2),
                            "p_in_bar": round(leg.inlet_pressure_bar, 3),
                            "p_out_bar": round(leg.outlet_pressure_bar, 3),
                            "dp_bar": round(leg.dp_bar, 3),
                            "compression_outlet_bar": round(leg.inlet_pressure_bar, 3),
                            "target_precompression_bar": float(target_precompression_bar),
                            "shared_path": " + ".join(path),
                        }
                    )

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(
            ["year", "sink_id", "emitter_id", "leg_index"]
        ).reset_index(drop=True)
    return frame


__all__ = ["pressure_table"]