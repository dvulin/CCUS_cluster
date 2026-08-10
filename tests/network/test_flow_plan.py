import unittest
from dataclasses import FrozenInstanceError, replace

from domain.ccs_network.flow import (
    CaptureFlow,
    ExplicitFlowPlan,
    InjectionFlow,
    NetworkFlowValidator,
    TransportFlow,
)
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


class MultiEmitterFlowPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.years_a = tuple(range(2030, 2041))
        cls.years_b = tuple(range(2035, 2041))

        cls.a_node = NetworkNode("a_junction", "Emitter A / junction", NodeKind.JUNCTION)
        cls.b_node = NetworkNode("b_source", "Emitter B", NodeKind.EMITTER)
        cls.storage_node = NetworkNode("storage", "Storage entry", NodeKind.STORAGE)

        cls.emitter_a = NetworkEmitter(
            id="A",
            name="Emitter A",
            delivery_node_id=cls.a_node.id,
            capture_plant=CapturePlant(
                id="capture_A",
                name="Capture A",
                availability=Availability(2030, 2040),
                capacity_t_per_year=400_000.0,
                captured_co2_t=AnnualSchedule.from_mapping(
                    {year: 400_000.0 for year in cls.years_a}
                ),
            ),
        )
        cls.emitter_b = NetworkEmitter(
            id="B",
            name="Emitter B",
            delivery_node_id=cls.b_node.id,
            capture_plant=CapturePlant(
                id="capture_B",
                name="Capture B",
                availability=Availability(2035, 2040),
                capacity_t_per_year=300_000.0,
                captured_co2_t=AnnualSchedule.from_mapping(
                    {year: 300_000.0 for year in cls.years_b}
                ),
            ),
        )

        cls.truck_spec = TruckSpec(
            length_km=25.0,
            payload_t_per_trip=25.0,
            trips_per_truck_per_day=2.0,
            operating_days_per_year=300,
            fleet_size=20,
        )
        cls.truck_leg = TransportLeg(
            id="b_truck_25km",
            name="Emitter B private truck leg",
            owner_id="B",
            origin_node_id=cls.b_node.id,
            destination_node_id=cls.a_node.id,
            mode=cls.truck_spec,
            availability=Availability(2035, 2040),
        )
        cls.shared_pipeline = TransportLeg(
            id="shared_pipeline_40km",
            name="Shared pipeline",
            owner_id="network_operator",
            origin_node_id=cls.a_node.id,
            destination_node_id=cls.storage_node.id,
            mode=PipelineSpec(length_km=40.0, capacity_t_per_year=700_000.0),
            availability=Availability(2030, 2040),
        )

        cls.injection_well = InjectionWell(
            id="well_1",
            name="Injection well 1",
            storage_node_id=cls.storage_node.id,
            availability=Availability(2030, 2040),
            capacity_t_per_year=700_000.0,
        )
        cls.storage_site = StorageSite(
            id="site_1",
            name="Storage site",
            node_id=cls.storage_node.id,
            availability=Availability(2030, 2040),
            nominal_capacity_t=20_000_000.0,
            injection_wells=(cls.injection_well,),
        )

        cls.scenario = CcsNetworkScenario(
            id="two_emitters_mixed_transport",
            name="Two emitters, private truck feeder and shared pipeline",
            emitters=(cls.emitter_a, cls.emitter_b),
            nodes=(cls.a_node, cls.b_node, cls.storage_node),
            transport_legs=(cls.truck_leg, cls.shared_pipeline),
            participations=(
                LegParticipation(
                    emitter_id="A",
                    leg_id=cls.shared_pipeline.id,
                    reservation_capacity_t_per_year=400_000.0,
                    ownership_share=4.0 / 7.0,
                    fixed_cost_share=4.0 / 7.0,
                ),
                LegParticipation(
                    emitter_id="B",
                    leg_id=cls.truck_leg.id,
                    reservation_capacity_t_per_year=300_000.0,
                    ownership_share=1.0,
                    fixed_cost_share=1.0,
                ),
                LegParticipation(
                    emitter_id="B",
                    leg_id=cls.shared_pipeline.id,
                    reservation_capacity_t_per_year=300_000.0,
                    ownership_share=3.0 / 7.0,
                    fixed_cost_share=3.0 / 7.0,
                ),
            ),
            storage_sites=(cls.storage_site,),
        )

        cls.plan = ExplicitFlowPlan(
            capture_flows=(
                *(CaptureFlow(year, "A", cls.a_node.id, 400_000.0) for year in cls.years_a),
                *(CaptureFlow(year, "B", cls.b_node.id, 300_000.0) for year in cls.years_b),
            ),
            transport_flows=(
                *(
                    TransportFlow(year, "A", cls.shared_pipeline.id, 400_000.0)
                    for year in cls.years_a
                ),
                *(TransportFlow(year, "B", cls.truck_leg.id, 300_000.0) for year in cls.years_b),
                *(
                    TransportFlow(year, "B", cls.shared_pipeline.id, 300_000.0)
                    for year in cls.years_b
                ),
            ),
            injection_flows=(
                *(InjectionFlow(year, "A", cls.injection_well.id, 400_000.0) for year in cls.years_a),
                *(InjectionFlow(year, "B", cls.injection_well.id, 300_000.0) for year in cls.years_b),
            ),
        )

    def test_valid_plan_preserves_emitter_provenance_and_actual_leg_shares(self):
        result = NetworkFlowValidator().validate(self.scenario, self.plan)

        self.assertTrue(result.is_valid, result.issues)
        self.assertEqual(
            self.plan.transported_quantity_t(
                year=2035, leg_id=self.truck_leg.id, emitter_id="B"
            ),
            300_000.0,
        )
        self.assertEqual(
            self.plan.transported_quantity_t(
                year=2035, leg_id=self.shared_pipeline.id, emitter_id="B"
            ),
            300_000.0,
        )
        self.assertEqual(
            result.leg_throughput_t(year=2035, leg_id=self.truck_leg.id),
            300_000.0,
        )
        self.assertEqual(
            result.leg_throughput_t(year=2035, leg_id=self.shared_pipeline.id),
            700_000.0,
        )
        self.assertAlmostEqual(
            result.actual_flow_share(
                year=2035, leg_id=self.truck_leg.id, emitter_id="B"
            ),
            1.0,
        )
        self.assertAlmostEqual(
            result.actual_flow_share(
                year=2035, leg_id=self.shared_pipeline.id, emitter_id="A"
            ),
            4.0 / 7.0,
        )
        self.assertAlmostEqual(
            result.actual_flow_share(
                year=2035, leg_id=self.shared_pipeline.id, emitter_id="B"
            ),
            3.0 / 7.0,
        )

        summed_leg_throughput = sum(
            result.leg_throughput_t(year=2035, leg_id=leg.id)
            for leg in self.scenario.transport_legs
        )
        injected = self.plan.injected_quantity_t(year=2035)
        self.assertEqual(summed_leg_throughput, 1_000_000.0)
        self.assertEqual(injected, 700_000.0)
        self.assertGreater(summed_leg_throughput, injected)

    def test_truck_leg_calculates_payload_trips_and_required_daily_fleet(self):
        self.assertEqual(self.truck_spec.payload_t_per_trip, 25.0)
        self.assertEqual(self.truck_spec.loaded_trips_per_day(300_000.0), 40.0)
        self.assertEqual(self.truck_spec.required_truck_count(300_000.0), 20)
        self.assertEqual(self.truck_spec.capacity_t_per_year, 300_000.0)

    def test_validator_finds_per_emitter_node_mass_imbalance(self):
        changed_flows = tuple(
            replace(flow, quantity_t=299_000.0)
            if flow.year == 2035
            and flow.emitter_id == "B"
            and flow.leg_id == self.shared_pipeline.id
            else flow
            for flow in self.plan.transport_flows
        )
        changed_plan = replace(self.plan, transport_flows=changed_flows)

        result = NetworkFlowValidator().validate(self.scenario, changed_plan)
        b_imbalances = {
            issue.node_id
            for issue in result.issues
            if issue.code == "node_mass_imbalance"
            and issue.year == 2035
            and issue.emitter_id == "B"
        }

        self.assertFalse(result.is_valid)
        self.assertEqual(b_imbalances, {self.a_node.id, self.storage_node.id})

    def test_validator_checks_capture_leg_reservation_and_well_capacities(self):
        enlarged_capture = tuple(
            replace(flow, quantity_t=400_001.0)
            if flow.year == 2035 and flow.emitter_id == "A"
            else flow
            for flow in self.plan.capture_flows
        )
        enlarged_transport = tuple(
            replace(flow, quantity_t=400_001.0)
            if flow.year == 2035 and flow.emitter_id == "A"
            else flow
            for flow in self.plan.transport_flows
        )
        enlarged_injection = tuple(
            replace(flow, quantity_t=400_001.0)
            if flow.year == 2035 and flow.emitter_id == "A"
            else flow
            for flow in self.plan.injection_flows
        )
        changed_plan = replace(
            self.plan,
            capture_flows=enlarged_capture,
            transport_flows=enlarged_transport,
            injection_flows=enlarged_injection,
        )

        result = NetworkFlowValidator().validate(self.scenario, changed_plan)
        codes = {issue.code for issue in result.issues}

        self.assertIn("capture_capacity_exceeded", codes)
        self.assertIn("reservation_capacity_exceeded", codes)
        self.assertIn("leg_capacity_exceeded", codes)
        self.assertIn("injection_well_capacity_exceeded", codes)

    def test_records_are_immutable_and_reference_activity_is_validated(self):
        with self.assertRaises(FrozenInstanceError):
            self.plan.transport_flows[0].quantity_t = 1.0

        extra_flows = (
            CaptureFlow(2041, "A", self.a_node.id, 1.0),
            TransportFlow(2041, "A", self.shared_pipeline.id, 1.0),
            InjectionFlow(2041, "A", self.injection_well.id, 1.0),
        )
        inactive_plan = replace(
            self.plan,
            capture_flows=(*self.plan.capture_flows, extra_flows[0]),
            transport_flows=(*self.plan.transport_flows, extra_flows[1]),
            injection_flows=(*self.plan.injection_flows, extra_flows[2]),
        )
        inactive_result = NetworkFlowValidator().validate(self.scenario, inactive_plan)
        inactive_codes = {issue.code for issue in inactive_result.issues}
        self.assertIn("inactive_capture_plant", inactive_codes)
        self.assertIn("inactive_transport_leg", inactive_codes)
        self.assertIn("inactive_injection_well", inactive_codes)

        unknown_leg_plan = replace(
            self.plan,
            transport_flows=(
                *self.plan.transport_flows,
                TransportFlow(2035, "A", "unknown_leg", 1.0),
            ),
        )
        unknown_result = NetworkFlowValidator().validate(self.scenario, unknown_leg_plan)
        self.assertIn("unknown_leg", {issue.code for issue in unknown_result.issues})


if __name__ == "__main__":
    unittest.main()
