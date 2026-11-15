"""Discrete time-step solver: route CO2, update the reservoir, value the cash flow.

One call to :meth:`ChronologicalSolver.run` performs the whole chronological
simulation:

1. resolve the active emitters and their captured CO2 for each year;
2. route the mass through the time-dependent multi-modal graph under capacity and
   residual-sink constraints;
3. update each storage complex with the routed mass (pressure, saturation, BHP);
4. run the geothermal doublet against the resulting pressure;
5. assemble the annual technical ledger and hand it to the audited cash-flow model.

The solver keeps no state between calls, so a UI can call it once and scrub the
returned per-year frames freely.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ccus_core.finance.cashflow import build_cash_flow_config
from ccus_core.models import ScenarioConfig
from ccus_core.network.graph import NetworkGraph
from ccus_core.network.routing import RoutingEngine, RoutingResult

from .adapters import power_inputs_for_sink
from .geothermal import GeothermalCoupling
from .reservoir import VariableRateReservoir

try:
    from economics import CashFlowRunner, summarize_cash_flow
    from engineering import FluidProperties, Power
except Exception:  # pragma: no cover - model-only environments
    CashFlowRunner = None  # type: ignore[assignment]
    summarize_cash_flow = None  # type: ignore[assignment]
    FluidProperties = None  # type: ignore[assignment]
    Power = None  # type: ignore[assignment]

HOURS_PER_YEAR = 8766.0


@dataclass
class SimulationResult:
    """Standardised output of one scenario run (DataFrames + JSON-safe dicts)."""

    scenario: ScenarioConfig
    routing: list[RoutingResult] = field(default_factory=list)
    reservoir: dict[str, pd.DataFrame] = field(default_factory=dict)
    geothermal: dict[str, pd.DataFrame] = field(default_factory=dict)
    ledger: pd.DataFrame | None = None
    cash_flow: pd.DataFrame | None = None
    kpis: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def routing_frame(self) -> pd.DataFrame:
        records = [record for result in self.routing for record in result.to_records()]
        return pd.DataFrame(
            records,
            columns=[
                "year",
                "emitter_id",
                "sink_id",
                "path",
                "quantity_t",
                "unit_cost_eur_per_t",
                "cost_eur",
            ],
        )

    def to_dict(self) -> dict[str, object]:
        """JSON-safe summary; the DataFrames are serialised by the export layer."""

        return {
            "scenario": self.scenario.summary(),
            "years": [self.scenario.start_year, self.scenario.end_year],
            "routing": [result.model_dump() for result in self.routing],
            "kpis": self.kpis,
            "notes": self.notes,
            "reservoir_sinks": sorted(self.reservoir),
            "geothermal_systems": sorted(self.geothermal),
            "ledger_rows": 0 if self.ledger is None else int(len(self.ledger)),
        }


class ChronologicalSolver:
    """Yearly routing + physics + finance over a :class:`ScenarioConfig`."""

    def __init__(self, scenario: ScenarioConfig, *, fluid_props=None, verbose: bool = False):
        self.scenario = scenario
        self.verbose = bool(verbose)
        if FluidProperties is not None:
            self.fluid_props = fluid_props if fluid_props is not None else FluidProperties()
        else:  # pragma: no cover
            self.fluid_props = fluid_props
        self.graph = NetworkGraph(scenario)

    # ------------------------------------------------------------------ helpers
    def _log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    def _effective_sink_capacity(self) -> dict[str, float]:
        """Capacity limited by both the nominal value and the pressure limit."""

        capacity: dict[str, float] = {}
        for sink in self.scenario.storage_sinks:
            limit = float(sink.capacity_t)
            if sink.reservoir is not None:
                curve = VariableRateReservoir(sink, self.fluid_props).capacity_curve()
                limit = min(limit, curve.maximum_mass_kg / 1000.0)
            capacity[sink.id] = limit
        return capacity

    def _route_all(self, capacity: dict[str, float]) -> list[RoutingResult]:
        engine = RoutingEngine(self.graph)
        remaining = dict(capacity)
        results: list[RoutingResult] = []
        for year in self.scenario.years():
            supplies = {
                emitter.id: emitter.captured_emissions(year)
                for emitter in self.scenario.emitters
            }
            result = engine.route(year=year, supplies=supplies, sink_remaining_capacity=remaining)
            for sink_id, injected in result.sink_injections.items():
                remaining[sink_id] = remaining.get(sink_id, 0.0) - injected
            if result.total_allocated_t > 0.0:
                self._log(f"{year}: routed {result.total_allocated_t:,.0f} t CO2")
            results.append(result)
        return results

    def _compressor_power_kw(self, sink, rate_kg_s: float, bhp_bar: float) -> float:
        if Power is None or rate_kg_s <= 0.0 or bhp_bar != bhp_bar:
            return 0.0
        power = Power(power_inputs_for_sink(sink, rate_kg_s), self.fluid_props)
        return float(
            power.calculate_compression_power(
                fluid="CO2",
                p_in_bar=float(sink.compressor_inlet_pressure_bar),
                p_out_bar=float(bhp_bar),
                t_in_C=float(sink.compressor_inlet_temperature_c),
                m_dot=float(rate_kg_s),
            )
        )

    # ------------------------------------------------------------------ main
    def run(self) -> SimulationResult:
        result = SimulationResult(scenario=self.scenario)
        years = self.scenario.years()

        capacity = self._effective_sink_capacity()
        routing = self._route_all(capacity)
        result.routing = routing

        injected: dict[str, dict[int, float]] = {
            sink.id: {year: 0.0 for year in years} for sink in self.scenario.storage_sinks
        }
        for routing_result in routing:
            for sink_id, quantity in routing_result.sink_injections.items():
                if sink_id in injected:
                    injected[sink_id][int(routing_result.year)] = float(quantity)

        for sink in self.scenario.storage_sinks:
            frame = VariableRateReservoir(sink, self.fluid_props).simulate(injected[sink.id])
            result.reservoir[sink.id] = frame
            self._log(
                f"{sink.id}: {frame['co2_cumulative_t'].iloc[-1]:,.0f} t stored, "
                f"final pressure {frame['pressure_bar'].iloc[-1]:.1f} bar"
            )

        for system in self.scenario.geothermal_systems:
            sink = next(
                (item for item in self.scenario.storage_sinks if item.node_id == system.node_id),
                None,
            )
            if sink is None or sink.reservoir is None:
                continue
            frame = result.reservoir[sink.id]
            pressure_series = dict(
                zip(frame["year"].astype(int), frame["pressure_bar"].astype(float))
            )
            coupling = GeothermalCoupling(system, sink.reservoir, fluid_props=self.fluid_props)
            result.geothermal[system.id] = coupling.simulate(pressure_series)

        result.ledger = self._build_ledger(result)
        config, notes = build_cash_flow_config(
            self.scenario,
            ledger=result.ledger,
            transport_cost_by_year={int(item.year): item.total_cost_eur for item in routing},
        )
        result.notes.extend(notes)

        if CashFlowRunner is not None:
            result.cash_flow = CashFlowRunner(config).run(result.ledger)
            economics = summarize_cash_flow(result.cash_flow)
            result.kpis.update(
                {
                    "npv_eur": economics.get("npv_eur"),
                    "irr": economics.get("irr"),
                    "irr_status": economics.get("irr_status"),
                    "pv_revenues_eur": economics.get("pv_revenues_eur"),
                    "pv_costs_eur": economics.get("pv_costs_eur"),
                }
            )

        result.kpis.update(
            {
                "stored_co2_t": float(result.ledger["co2_stored_cumulative_t"].max()),
                "routed_co2_t": float(result.ledger["co2_chain_t"].sum()),
                "transport_cost_eur": float(sum(item.total_cost_eur for item in routing)),
                "unallocated_co2_t": float(
                    sum(sum(item.unallocated.values()) for item in routing)
                ),
            }
        )
        return result

    # ------------------------------------------------------------------ ledger
    def _build_ledger(self, result: SimulationResult) -> pd.DataFrame:
        years = self.scenario.years()
        sinks = self.scenario.storage_sinks
        injection_years = [
            year
            for frame in result.reservoir.values()
            for year, injected in zip(frame["year"].astype(int), frame["co2_injected_t"])
            if injected > 0.0
        ]
        first_injection = min(injection_years) if injection_years else min(years)
        last_injection = max(injection_years) if injection_years else first_injection - 1

        monitoring_start = min(
            (sink.commissioning_year or first_injection) for sink in sinks
        )
        monitoring_end = max((sink.monitoring_end_year or max(years)) for sink in sinks)

        rows: list[dict[str, object]] = []
        cumulative = 0.0
        for year in years:
            injected = float(
                sum(
                    float(frame.loc[frame["year"] == year, "co2_injected_t"].iloc[0])
                    if not frame.loc[frame["year"] == year].empty
                    else 0.0
                    for frame in result.reservoir.values()
                )
            )
            cumulative += injected

            orc_mwh = 0.0
            pump_mwh = 0.0
            for frame in result.geothermal.values():
                row = frame.loc[frame["year"] == year]
                if row.empty or not bool(row["operating"].iloc[0]):
                    continue
                orc_mwh += float(row["orc_power_kw"].iloc[0]) * HOURS_PER_YEAR / 1000.0
                pump_mwh += float(row["pump_power_kw"].iloc[0]) * HOURS_PER_YEAR / 1000.0

            compressor_kw = 0.0
            compressor_mwh = 0.0
            for sink in sinks:
                frame = result.reservoir.get(sink.id)
                if frame is None:
                    continue
                row = frame.loc[frame["year"] == year]
                if row.empty or not bool(row["active"].iloc[0]):
                    continue
                compressor_kw = max(
                    compressor_kw,
                    self._compressor_power_kw(
                        sink,
                        float(row["injection_rate_kg_s"].iloc[0]),
                        float(row["bhp_bar"].iloc[0]),
                    ),
                )
            compressor_mwh = compressor_kw * HOURS_PER_YEAR / 1000.0

            net_mwh = orc_mwh - pump_mwh - compressor_mwh
            rows.append(
                {
                    "year": year,
                    "co2_chain_t": injected,
                    "co2_stored_cumulative_t": cumulative,
                    "orc_gross_mwh": orc_mwh,
                    "gt_pump_mwh": pump_mwh,
                    "co2_compressor_mwh": compressor_mwh,
                    "electricity_export_mwh": max(0.0, net_mwh),
                    "electricity_import_mwh": max(0.0, -net_mwh),
                    "compressor_peak_kw": compressor_kw,
                    "injection_active": injected > 0.0,
                    "geothermal_active": orc_mwh > 0.0 or pump_mwh > 0.0,
                    "monitoring_active": monitoring_start <= year <= monitoring_end,
                    "injection_stop_note": (
                        "planned end" if year == last_injection else None
                    ),
                }
            )
        frame = pd.DataFrame(rows)
        frame.attrs["injection_window"] = (first_injection, last_injection)
        frame.attrs["monitoring_window"] = (monitoring_start, monitoring_end)
        return frame