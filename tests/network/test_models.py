import unittest
from dataclasses import FrozenInstanceError

from domain.ccs_network.models import (
    AnnualSchedule,
    Availability,
    CapturePlant,
    CcsNetworkScenario,
    InjectionWell,
    LegParticipation,
    NetworkEmitter,
    NetworkNode,
    NodeKind,
    PipelineSpec,
    StorageSite,
    TransportLeg,
    TruckSpec,
)


def _build_scenario():
    operating = Availability(2030, 2040)
    emitter_a = NetworkEmitter(
        id="emitter-a",
        name="Emitter A",
        capture_plant=CapturePlant(
            id="capture-a",
            name="Capture A",
            availability=operating,
            capacity_t_per_year=400_000.0,
            captured_co2_t=AnnualSchedule.constant(400_000.0, 2030, 2040),
            technology="amine-a",
            capex_eur=80_000_000.0,
            fixed_opex_eur_per_year=4_000_000.0,
            variable_opex_eur_per_t=18.0,
        ),
        delivery_node_id="node-a",
    )
    emitter_b = NetworkEmitter(
        id="emitter-b",
        name="Emitter B",
        capture_plant=CapturePlant(
            id="capture-b",
            name="Capture B",
            availability=Availability(2035, 2040),
            capacity_t_per_year=300_000.0,
            captured_co2_t=AnnualSchedule.constant(300_000.0, 2035, 2040),
            technology="membrane-b",
            capex_eur=55_000_000.0,
            fixed_opex_eur_per_year=2_500_000.0,
            variable_opex_eur_per_t=24.0,
        ),
        delivery_node_id="node-b",
    )
    nodes = (
        NetworkNode("node-a", "A delivery", NodeKind.EMITTER),
        NetworkNode("node-b", "B delivery", NodeKind.EMITTER),
        NetworkNode("shared-hub", "Shared hub", NodeKind.INTERMODAL),
        NetworkNode("storage-node", "Storage", NodeKind.STORAGE),
    )
    a_feeder = TransportLeg(
        id="a-feeder",
        name="A feeder",
        owner_id="emitter-a",
        origin_node_id="node-a",
        destination_node_id="shared-hub",
        mode=PipelineSpec(length_km=10.0, capacity_t_per_year=400_000.0),
        availability=operating,
    )
    b_truck = TransportLeg(
        id="b-truck",
        name="B truck leg",
        owner_id="emitter-b",
        origin_node_id="node-b",
        destination_node_id="shared-hub",
        mode=TruckSpec(
            length_km=25.0,
            payload_t_per_trip=25.0,
            trips_per_truck_per_day=2.0,
            operating_days_per_year=300,
        ),
        availability=Availability(2035, 2040),
    )
    shared_pipeline = TransportLeg(
        id="shared-pipeline",
        name="Shared pipeline",
        owner_id="network-operator",
        origin_node_id="shared-hub",
        destination_node_id="storage-node",
        mode=PipelineSpec(length_km=40.0, capacity_t_per_year=700_000.0),
        availability=operating,
    )
    participations = (
        LegParticipation("emitter-a", "a-feeder", 400_000.0, 1.0, 1.0),
        LegParticipation(
            "emitter-a", "shared-pipeline", 400_000.0, 4.0 / 7.0, 0.55, 3.5
        ),
        LegParticipation("emitter-b", "b-truck", 300_000.0, 1.0, 1.0),
        LegParticipation(
            "emitter-b", "shared-pipeline", 300_000.0, 3.0 / 7.0, 0.45, 4.25
        ),
    )
    well = InjectionWell(
        id="well-1",
        name="Injection well",
        storage_node_id="storage-node",
        availability=operating,
        capacity_t_per_year=700_000.0,
    )
    storage = StorageSite(
        id="storage-1",
        name="Storage site",
        node_id="storage-node",
        availability=operating,
        nominal_capacity_t=9_308_000.0,
        injection_wells=(well,),
    )
    return CcsNetworkScenario(
        id="two-emitter-example",
        name="Two emitters with shared pipeline",
        emitters=(emitter_a, emitter_b),
        nodes=nodes,
        transport_legs=(a_feeder, b_truck, shared_pipeline),
        participations=participations,
        storage_sites=(storage,),
    )


class AnnualScheduleTests(unittest.TestCase):
    def test_schedule_is_sorted_immutable_and_adapter_friendly(self):
        source = {2035: 300_000, 2030: 0}
        schedule = AnnualSchedule.from_mapping(source)
        source[2035] = 1

        self.assertEqual(schedule.years, (2030, 2035))
        self.assertEqual(schedule.value(2035), 300_000.0)
        self.assertEqual(schedule.value(2031), 0.0)
        self.assertEqual(schedule.to_dict(), {2030: 0.0, 2035: 300_000.0})
        with self.assertRaises(FrozenInstanceError):
            schedule.entries = ()

    def test_schedule_rejects_negative_quantities_and_duplicate_years(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            AnnualSchedule(((2030, -1.0),))
        with self.assertRaisesRegex(ValueError, "duplicate schedule year"):
            AnnualSchedule(((2030, 1.0), (2030, 2.0)))


class TransportModeTests(unittest.TestCase):
    def test_truck_leg_derives_daily_trips_and_required_fleet(self):
        truck = TruckSpec(
            length_km=25.0,
            payload_t_per_trip=25.0,
            trips_per_truck_per_day=2.0,
            operating_days_per_year=300,
        )

        self.assertEqual(truck.loaded_trips_per_day(300_000.0), 40.0)
        self.assertEqual(truck.required_truck_count(300_000.0), 20)
        self.assertEqual(truck.required_fleet_size(300_000.0), 20)
        self.assertEqual(truck.annual_capacity_per_truck_t, 15_000.0)
        self.assertIsNone(truck.capacity_t_per_year)

    def test_fixed_truck_fleet_exposes_annual_capacity(self):
        truck = TruckSpec(25.0, 25.0, 2.0, 300, fleet_size=20)
        self.assertEqual(truck.capacity_t_per_year, 300_000.0)


class ScenarioTopologyTests(unittest.TestCase):
    def test_scenario_preserves_each_emitters_independent_leg_interests(self):
        scenario = _build_scenario()

        shared = scenario.transport_leg_by_id("shared-pipeline")
        self.assertEqual(shared.owner_id, "network-operator")
        self.assertEqual(shared.mode.length_km, 40.0)
        b_truck = scenario.transport_leg_by_id("b-truck")
        self.assertEqual(b_truck.owner_id, "emitter-b")
        self.assertEqual(b_truck.mode.length_km, 25.0)
        b_shared = next(
            participation
            for participation in scenario.participations
            if participation.emitter_id == "emitter-b"
            and participation.leg_id == "shared-pipeline"
        )
        self.assertEqual(b_shared.reservation_capacity_t_per_year, 300_000.0)
        self.assertAlmostEqual(b_shared.ownership_share, 3.0 / 7.0)
        self.assertEqual(b_shared.fixed_cost_share, 0.45)
        self.assertEqual(b_shared.tariff_eur_per_t, 4.25)
        self.assertEqual(scenario.injection_well_by_id("well-1").capacity_t_per_year, 700_000.0)
        capture_a = scenario.emitter_by_id("emitter-a").capture_plant
        capture_b = scenario.emitter_by_id("emitter-b").capture_plant
        self.assertNotEqual(capture_a.technology, capture_b.technology)
        self.assertNotEqual(capture_a.capex_eur, capture_b.capex_eur)
        self.assertNotEqual(
            capture_a.variable_opex_eur_per_t,
            capture_b.variable_opex_eur_per_t,
        )

    def test_unknown_leg_reference_is_rejected(self):
        scenario = _build_scenario()
        bad_participations = scenario.participations + (
            LegParticipation("emitter-a", "missing-leg"),
        )

        with self.assertRaisesRegex(ValueError, "unknown transport leg"):
            CcsNetworkScenario(
                id=scenario.id,
                name=scenario.name,
                emitters=scenario.emitters,
                nodes=scenario.nodes,
                transport_legs=scenario.transport_legs,
                participations=bad_participations,
                storage_sites=scenario.storage_sites,
            )

    def test_each_emitter_must_participate_in_a_complete_storage_path(self):
        scenario = _build_scenario()
        incomplete_b_route = tuple(
            participation
            for participation in scenario.participations
            if not (
                participation.emitter_id == "emitter-b"
                and participation.leg_id == "shared-pipeline"
            )
        )

        with self.assertRaisesRegex(ValueError, "emitter-b.*no participated transport path"):
            CcsNetworkScenario(
                id=scenario.id,
                name=scenario.name,
                emitters=scenario.emitters,
                nodes=scenario.nodes,
                transport_legs=scenario.transport_legs,
                participations=incomplete_b_route,
                storage_sites=scenario.storage_sites,
            )


if __name__ == "__main__":
    unittest.main()
