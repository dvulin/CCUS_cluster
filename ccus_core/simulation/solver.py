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
from .geothermal import GeothermalCoupling, ensure_coupled_doublets
from .pressures import pressure_table
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
    """Standardised output of one scenario run (DataFrames + JSON-safe dicts).

    ``fired_upgrades`` (edge_id -> {upgrade_id: year the trigger fired}) and
    ``edge_cumulative_mass`` (edge_id -> t shipped) are the solver's bookkeeping of
    the conditional infrastructure upgrades: the finance layer needs the firing
    year to book each upgrade CAPEX exactly once.
    """

    scenario: ScenarioConfig
    routing: list[RoutingResult] = field(default_factory=list)
    reservoir: dict[str, pd.DataFrame] = field(default_factory=dict)
    geothermal: dict[str, pd.DataFrame] = field(default_factory=dict)
    ledger: pd.DataFrame | None = None
    cash_flow: pd.DataFrame | None = None
    pressures: pd.DataFrame | None = None
    kpis: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    fired_upgrades: dict[str, dict[str, int]] = field(default_factory=dict)
    edge_cumulative_mass: dict[str, float] = field(default_factory=dict)

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
            "pressure_rows": 0 if self.pressures is None else int(len(self.pressures)),
            "fired_upgrades": self.fired_upgrades,
        }


class ChronologicalSolver:
    """Yearly routing + physics + finance over a :class:`ScenarioConfig`."""

    def __init__(self, scenario: ScenarioConfig, *, fluid_props=None, verbose: bool = False):
        # a coupled sink gets its doublet here, not in the UI: the engine is the
        # single place that turns `geothermal_coupled` into a system
        self.scenario = ensure_coupled_doublets(scenario)
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

    def _injection_rate_limits(self) -> dict[str, float]:
        """Declared per-year injection cap of each sink (well capacity)."""

        return {
            sink.id: float(sink.max_injection_rate_t_per_year)
            for sink in self.scenario.storage_sinks
            if sink.max_injection_rate_t_per_year is not None
        }

    def _fire_due_upgrades(
        self,
        year: int,
        fired: dict[str, dict[str, int]],
        cumulative_mass: dict[str, float],
    ) -> list[str]:
        """Record every upgrade whose trigger is satisfied in ``year``.

        A year trigger is recorded with its *declared* year (so the lead time is
        counted from the plan, not from the first simulated year), while a
        cumulative-mass trigger is recorded with the year in which the running
        total crosses the threshold.  Recording the firing year is what keeps the
        upgrade CAPEX to a single booking.
        """

        fired_now: list[str] = []
        for edge in self.scenario.edges:
            recorded = fired.setdefault(edge.id, {})
            shipped = float(cumulative_mass.get(edge.id, 0.0))
            for upgrade in edge.upgrades:
                if upgrade.id in recorded:
                    continue
                trigger = upgrade.trigger
                if trigger.kind in ("year", "both") and trigger.year is not None and year >= int(trigger.year):
                    recorded[upgrade.id] = int(trigger.year)
                    fired_now.append(f"{edge.id}/{upgrade.id}")
                elif trigger.kind in ("cumulative_mass", "both") and trigger.fires_on_mass(shipped):
                    recorded[upgrade.id] = int(year)
                    fired_now.append(f"{edge.id}/{upgrade.id}")
        return fired_now

    def _route_all(self, capacity: dict[str, float]) -> tuple[list[RoutingResult], dict[str, dict[str, int]], dict[str, float]]:
        engine = RoutingEngine(self.graph)
        remaining = dict(capacity)
        limits = self._injection_rate_limits()
        fired: dict[str, dict[str, int]] = {}
        cumulative_mass: dict[str, float] = {edge.id: 0.0 for edge in self.scenario.edges}
        results: list[RoutingResult] = []
        for year in self.scenario.years():
            # an upgrade that fires in `year` is visible to the router immediately
            # (the lead time is applied inside InfrastructureUpgrade.effective_year)
            for label in self._fire_due_upgrades(year, fired, cumulative_mass):
                self._log(f"{year}: upgrade fired -> {label}")
            supplies = {
                emitter.id: emitter.captured_emissions(year)
                for emitter in self.scenario.emitters
            }
            result = engine.route(
                year=year,
                supplies=supplies,
                sink_remaining_capacity=remaining,
                fired_upgrades=fired,
                cumulative_mass=cumulative_mass,
                sink_injection_limits=limits or None,
            )
            for sink_id, injected in result.sink_injections.items():
                remaining[sink_id] = remaining.get(sink_id, 0.0) - injected
            for edge_id, flow in result.edge_flows.items():
                cumulative_mass[edge_id] = cumulative_mass.get(edge_id, 0.0) + float(flow)
            if result.total_allocated_t > 0.0:
                self._log(f"{year}: routed {result.total_allocated_t:,.0f} t CO2")
            if result.rate_limited_sinks:
                self._log(
                    f"{year}: injection-rate limited at "
                    + ", ".join(result.rate_limited_sinks)
                )
            results.append(result)
        return results, fired, cumulative_mass

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
        if self.scenario.step != "yearly":
            raise NotImplementedError(
                f"step '{self.scenario.step}' is not implemented: the chronological "
                "solver is yearly (use step='yearly')"
            )
        result = SimulationResult(scenario=self.scenario)
        years = self.scenario.years()

        capacity = self._effective_sink_capacity()
        routing, fired, cumulative_mass = self._route_all(capacity)
        result.routing = routing
        result.fired_upgrades = fired
        result.edge_cumulative_mass = cumulative_mass

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
            coupling = GeothermalCoupling(
                system,
                sink.reservoir,
                fluid_props=self.fluid_props,
                eta_pump=float(sink.eta_gt_injection_pump),
            )
            result.geothermal[system.id] = coupling.simulate(pressure_series)

        result.ledger = self._build_ledger(result)
        result.pressures = pressure_table(self.scenario, result)
        sink_injections = {
            sink_id: {
                int(row.year): float(row.co2_injected_t)
                for row in frame.itertuples(index=False)
            }
            for sink_id, frame in result.reservoir.items()
        }
        config, notes = build_cash_flow_config(
            self.scenario,
            ledger=result.ledger,
            transport_cost_by_year={int(item.year): item.total_cost_eur for item in routing},
            sink_injections=sink_injections,
            fired_upgrades=result.fired_upgrades,
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
        self._record_limits(result)
        return result

    # ------------------------------------------------------------------ diagnostics
    def _record_limits(self, result: SimulationResult) -> None:
        """Flag sinks that hit their rate limit, their pore volume or their BHP.

        A cluster study must *show* which constraint shaped the result instead of
        letting a silent cap look like a physical property of the reservoir.
        """

        rate_limited = sorted(
            {sink_id for item in result.routing for sink_id in item.rate_limited_sinks}
        )
        capacity_limited = sorted(
            {sink_id for item in result.routing for sink_id in item.capacity_limited_sinks}
        )
        bhp_limited: list[str] = []
        for sink in self.scenario.storage_sinks:
            frame = result.reservoir.get(sink.id)
            if frame is None or "bhp_above_limit" not in frame:
                continue
            if bool(frame["bhp_above_limit"].fillna(False).any()):
                bhp_limited.append(sink.id)

        result.kpis["rate_limited_sinks"] = rate_limited
        result.kpis["capacity_limited_sinks"] = capacity_limited
        result.kpis["bhp_limited_sinks"] = bhp_limited

        for sink_id in rate_limited:
            result.notes.append(
                f"sink '{sink_id}' hit its declared max_injection_rate_t_per_year"
            )
        for sink_id in capacity_limited:
            result.notes.append(f"sink '{sink_id}' exhausted its storage capacity")
        for sink_id in bhp_limited:
            result.notes.append(
                f"sink '{sink_id}' needs a bottomhole pressure above the fracture limit"
            )

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
                # the power of every running compressor adds up: each sink has its
                # own injection skid, they do not share one machine
                compressor_kw += self._compressor_power_kw(
                    sink,
                    float(row["injection_rate_kg_s"].iloc[0]),
                    float(row["bhp_bar"].iloc[0]),
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
                    "compressor_power_kw": compressor_kw,
                    # deprecated alias kept for the legacy ledger consumers
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