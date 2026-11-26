"""Regression tests for the numbers-and-data-loss fix plan (P1).

Each test in this module is the one that would have caught the corresponding bug:

1. monitoring charged ``rate x years`` every year (not one pre-summed total);
2. stakeholder CAPEX booked once (covered in ``test_stakeholders.py``);
3. upgrade CAPEX booked only when the trigger fires;
6. compressor power summed across active sinks, per-sink injection-rate caps,
   BHP-above-the-limit and capacity-limited sinks flagged.
"""

from __future__ import annotations

import pytest

from ccus_core import ScenarioEngine
from ccus_core.finance.cashflow import build_cash_flow_config
from ccus_core.models import (
    EconomicsConfig,
    EmissionCurve,
    Emitter,
    GeoLocation,
    InfrastructureUpgrade,
    Node,
    NodeKind,
    ReservoirProperties,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
    UpgradeTrigger,
)
from ccus_core.network import NetworkGraph, RoutingEngine
from ccus_core.simulation import ChronologicalSolver

from .conftest import pipeline_state, truck_state

YEARS = list(range(2028, 2035))


def reservoir(**overrides) -> ReservoirProperties:
    values = dict(
        area_m2=225_000_000.0,
        effective_thickness_m=155.0,
        porosity=0.15,
        top_depth_m=2000.0,
        temperature_c=150.0,
        reference_pressure_bar=200.0,
        pressure_step_bar=0.5,
        permeability_m2=5e-14,
    )
    values.update(overrides)
    return ReservoirProperties(**values)


def scenario_with_sinks(
    *,
    sink_specs: list[dict],
    edges: list[TransportEdge],
    emitters: list[Emitter] | None = None,
    start_year: int = 2028,
    end_year: int = 2034,
) -> ScenarioConfig:
    nodes = [
        Node(id="plant", name="Plant", kind=NodeKind.EMITTER, location=GeoLocation()),
        Node(id="hub", name="Hub", kind=NodeKind.JUNCTION),
    ]
    sinks = []
    for index, spec in enumerate(sink_specs):
        node_id = f"sink_node_{index}"
        nodes.append(Node(id=node_id, name=f"Sink {index}", kind=NodeKind.STORAGE))
        spec.setdefault("node_id", node_id)
        spec.setdefault("reservoir", reservoir())
        sinks.append(StorageSink(**spec))
    return ScenarioConfig(
        id="fix_case",
        name="Fix case",
        start_year=start_year,
        end_year=end_year,
        nodes=nodes,
        emitters=emitters
        or [
            Emitter(
                id="source",
                name="Source",
                node_id="plant",
                activation_year=start_year,
                gross_emissions=EmissionCurve.constant(700_000.0),
            )
        ],
        edges=edges,
        storage_sinks=sinks,
        economics=EconomicsConfig(
            start_year=start_year, end_year=end_year, capex_start_year=start_year
        ),
    )


# --------------------------------------------------------------------- 1 monitoring
def test_monitoring_is_charged_rate_times_years_not_a_pre_summed_total():
    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 2_800_000.0,
                "commissioning_year": 2028,
                "opex_eur_per_t": 8.0,
                "monitoring_cost_during_injection_eur_per_year": 100_000.0,
                "monitoring_cost_after_injection_eur_per_year": 50_000.0,
                "monitoring_end_year": 2033,
            }
        ],
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk",
                from_node="plant",
                to_node="sink_node_0",
                states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)],
            )
        ],
    )
    result = ScenarioEngine(scenario).run()

    assert result.cash_flow is not None
    monitoring = result.cash_flow.set_index("year")["monitoring"]
    # injection runs 2028-2031 (700 kt/yr against a 9 Mt site), then monitoring only
    injected_years = [
        int(row.year)
        for row in result.ledger.itertuples(index=False)
        if float(row.co2_chain_t) > 0.0
    ]
    assert injected_years == [2028, 2029, 2030, 2031]
    expected = {
        2028: -100_000.0,
        2029: -100_000.0,
        2030: -100_000.0,
        2031: -100_000.0,
        2032: -50_000.0,  # first year after the last injection
        2033: -50_000.0,  # monitoring_end_year: last charged year
        2034: 0.0,  # after the monitoring window
    }
    for year, value in expected.items():
        assert float(monitoring.loc[year]) == pytest.approx(value, abs=1.0)
    # 4 years of injection + 2 years of post-injection monitoring
    assert float(monitoring.sum()) == pytest.approx(-(4 * 100_000.0 + 2 * 50_000.0), abs=1.0)


def test_monitoring_costs_require_an_explicit_end_year():
    with pytest.raises(ValueError, match="monitoring_end_year"):
        scenario_with_sinks(
            sink_specs=[
                {
                    "id": "sink_a",
                    "name": "Sink A",
                    "storage_type": StorageType.DSA,
                    "capacity_t": 9_000_000.0,
                    "commissioning_year": 2028,
                    "monitoring_cost_during_injection_eur_per_year": 100_000.0,
                }
            ],
            edges=[
                TransportEdge(
                    id="trunk",
                    name="Trunk",
                    from_node="plant",
                    to_node="sink_node_0",
                    states=[
                        pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)
                    ],
                )
            ],
        )


# ------------------------------------------------------------------- 3 upgrade CAPEX
def test_mass_triggered_upgrade_fires_once_and_pays_its_capex_once():
    new_state = pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)
    edge = TransportEdge(
        id="corridor",
        name="Corridor",
        from_node="plant",
        to_node="sink_node_0",
        # 25 t x 2 trips x 250 days x 40 vehicles = 500 kt/yr of truck capacity
        states=[truck_state(valid_from_year=2028, capacity_t_per_year=800_000.0, fleet_size=40)],
        upgrades=[
            InfrastructureUpgrade(
                id="truck_to_pipeline",
                trigger=UpgradeTrigger(kind="cumulative_mass", threshold_t=1_200_000.0),
                new_state=new_state.model_copy(update={"capex_eur": 50_000_000.0}),
            )
        ],
    )
    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 9_000_000.0,
                "commissioning_year": 2028,
            }
        ],
        edges=[edge],
    )
    result = ScenarioEngine(scenario).run()

    # the truck fleet moves 500 kt/yr, so the mass crosses 1.2 Mt at the end of
    # 2030 and the trigger fires at the start of 2031 (lead time 0)
    assert result.fired_upgrades["corridor"]["truck_to_pipeline"] == 2031
    assert result.edge_cumulative_mass["corridor"] == pytest.approx(4_300_000.0, rel=1e-6)
    assert float(result.ledger["co2_chain_t"].iloc[0]) == pytest.approx(500_000.0)
    assert float(result.ledger["co2_chain_t"].iloc[-1]) == pytest.approx(700_000.0)

    graph = NetworkGraph(scenario)
    engine = RoutingEngine(graph)
    before = engine.route(
        year=2030,
        supplies={"source": 700_000.0},
        sink_remaining_capacity={"sink_a": 9_000_000.0},
        fired_upgrades=result.fired_upgrades,
        cumulative_mass={"corridor": 1_000_000.0},
    )
    after = engine.route(
        year=2031,
        supplies={"source": 700_000.0},
        sink_remaining_capacity={"sink_a": 9_000_000.0},
        fired_upgrades=result.fired_upgrades,
        cumulative_mass={"corridor": 1_500_000.0},
    )
    # the truck bottleneck is gone once the pipeline is in force
    assert before.edge_flows["corridor"] == pytest.approx(500_000.0)
    assert after.edge_flows["corridor"] == pytest.approx(700_000.0)
    assert scenario.edge_by_id("corridor").resolve_state(
        2030, cumulative_mass_t=1_000_000.0
    ).mode.value == "truck"
    assert scenario.edge_by_id("corridor").resolve_state(
        2031, cumulative_mass_t=1_500_000.0
    ).mode.value == "pipeline"

    # transport CAPEX = the truck state (1.5 M) + the pipeline upgrade (50 M), once
    transport_capex = result.cash_flow.set_index("year")["transport_capex"]
    assert float(-transport_capex.sum()) == pytest.approx(51_500_000.0, abs=1.0)
    paid_years = [int(year) for year, value in transport_capex.items() if value < 0.0]
    assert paid_years == [2028, 2031]


def test_upgrade_capex_is_not_paid_when_the_trigger_never_fires():
    new_state = pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)
    edge = TransportEdge(
        id="corridor",
        name="Corridor",
        from_node="plant",
        to_node="sink_node_0",
        states=[truck_state(valid_from_year=2028, capacity_t_per_year=800_000.0)],
        upgrades=[
            InfrastructureUpgrade(
                id="truck_to_pipeline",
                trigger=UpgradeTrigger(kind="cumulative_mass", threshold_t=100_000_000.0),
                new_state=new_state.model_copy(update={"capex_eur": 50_000_000.0}),
            )
        ],
    )
    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 9_000_000.0,
                "commissioning_year": 2028,
            }
        ],
        edges=[edge],
    )
    result = ScenarioEngine(scenario).run()

    assert result.fired_upgrades.get("corridor", {}) == {}
    transport_capex = result.cash_flow.set_index("year")["transport_capex"]
    assert float(-transport_capex.sum()) == pytest.approx(1_500_000.0, abs=1.0)


# --------------------------------------------------------- 6 compressors and limits
def test_compressor_power_is_summed_across_active_sinks():
    edges = [
        TransportEdge(
            id="trunk_a",
            name="Trunk A",
            from_node="plant",
            to_node="sink_node_0",
            states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=400_000.0)],
        ),
        TransportEdge(
            id="trunk_b",
            name="Trunk B",
            from_node="plant",
            to_node="sink_node_1",
            states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=400_000.0)],
        ),
    ]
    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 9_000_000.0,
                "commissioning_year": 2028,
            },
            {
                "id": "sink_b",
                "name": "Sink B",
                "storage_type": StorageType.DSA,
                "capacity_t": 9_000_000.0,
                "commissioning_year": 2028,
            },
        ],
        edges=edges,
    )
    result = ScenarioEngine(scenario).run()
    solver = ChronologicalSolver(scenario)

    row = result.ledger.set_index("year").loc[2028]
    expected_kw = 0.0
    for sink in scenario.storage_sinks:
        frame = result.reservoir[sink.id]
        first = frame.loc[frame["year"] == 2028].iloc[0]
        expected_kw += solver._compressor_power_kw(
            sink, float(first["injection_rate_kg_s"]), float(first["bhp_bar"])
        )
    assert float(row["co2_chain_t"]) == pytest.approx(700_000.0)
    assert float(row["compressor_power_kw"]) == pytest.approx(expected_kw, rel=1e-9)
    # the deprecated alias must not drift from the corrected column
    assert float(row["compressor_peak_kw"]) == pytest.approx(float(row["compressor_power_kw"]))
    assert float(row["co2_compressor_mwh"]) == pytest.approx(
        expected_kw * 8766.0 / 1000.0, rel=1e-9
    )


def test_per_sink_injection_rate_cap_is_applied_and_flagged():
    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 9_000_000.0,
                "commissioning_year": 2028,
                "max_injection_rate_t_per_year": 300_000.0,
            }
        ],
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk",
                from_node="plant",
                to_node="sink_node_0",
                states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)],
            )
        ],
    )
    result = ScenarioEngine(scenario).run()

    assert result.routing[0].sink_injections["sink_a"] == pytest.approx(300_000.0)
    assert result.routing[0].rate_limited_sinks == ["sink_a"]
    assert result.routing[0].capacity_limited_sinks == []
    assert result.kpis["rate_limited_sinks"] == ["sink_a"]
    assert any("max_injection_rate_t_per_year" in note for note in result.notes)
    # the cap must not be mistaken for an empty reservoir
    assert float(result.ledger["co2_chain_t"].iloc[0]) == pytest.approx(300_000.0)


def test_bhp_above_the_fracture_limit_is_flagged():
    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 90_000_000.0,
                "commissioning_year": 2028,
                "reservoir": reservoir(fracture_pressure_gradient_bar_per_m=0.11),
            }
        ],
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk",
                from_node="plant",
                to_node="sink_node_0",
                states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)],
            )
        ],
    )
    result = ScenarioEngine(scenario).run()

    frame = result.reservoir["sink_a"]
    assert bool(frame["bhp_above_limit"].any())
    assert result.kpis["bhp_limited_sinks"] == ["sink_a"]
    assert any("bottomhole pressure" in note for note in result.notes)


def test_capacity_limited_sink_is_flagged_in_the_kpis():
    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 500_000.0,
                "commissioning_year": 2028,
            }
        ],
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk",
                from_node="plant",
                to_node="sink_node_0",
                states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)],
            )
        ],
    )
    result = ScenarioEngine(scenario).run()

    assert "sink_a" in result.kpis["capacity_limited_sinks"]
    assert any("exhausted its storage capacity" in note for note in result.notes)


def test_cash_flow_config_reports_annual_monitoring_rates():
    from ccus_core.finance.cashflow import monitoring_cost_by_sink

    scenario = scenario_with_sinks(
        sink_specs=[
            {
                "id": "sink_a",
                "name": "Sink A",
                "storage_type": StorageType.DSA,
                "capacity_t": 2_800_000.0,
                "commissioning_year": 2028,
                "monitoring_cost_during_injection_eur_per_year": 100_000.0,
                "monitoring_cost_after_injection_eur_per_year": 50_000.0,
                "monitoring_end_year": 2033,
            }
        ],
        edges=[
            TransportEdge(
                id="trunk",
                name="Trunk",
                from_node="plant",
                to_node="sink_node_0",
                states=[pipeline_state(valid_from_year=2028, capacity_t_per_year=5_000_000.0)],
            )
        ],
    )
    result = ScenarioEngine(scenario).run()
    injections = {
        sink_id: {
            int(row.year): float(row.co2_injected_t)
            for row in frame.itertuples(index=False)
        }
        for sink_id, frame in result.reservoir.items()
    }
    config, _notes = build_cash_flow_config(
        scenario, ledger=result.ledger, sink_injections=injections
    )
    monitoring = config["monitoring"]
    during = monitoring["annual_cost_during_injection"]
    after = monitoring["annual_cost_after_injection"]
    assert isinstance(during, dict) and isinstance(after, dict)
    # one annual rate per year, never a total that grows with the horizon
    assert during[2028] == pytest.approx(100_000.0)
    # 2032 is the first year after the last injection: the "after" rate applies
    assert during[2032] == pytest.approx(50_000.0)
    assert after[2032] == pytest.approx(50_000.0)
    # the monitored window ends in 2033, so 2034 is zero
    assert during[2034] == pytest.approx(0.0)

    # the per-sink helper keeps the phase split (who is still injecting, who is not)
    per_sink = monitoring_cost_by_sink(scenario, [int(y) for y in result.ledger["year"]], injections)
    assert per_sink["sink_a"][2028] == pytest.approx(100_000.0)
    assert per_sink["sink_a"][2032] == pytest.approx(50_000.0)