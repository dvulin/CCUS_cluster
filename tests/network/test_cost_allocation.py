import unittest

from domain.ccs_network.costs import (
    AllocationBasis,
    TariffTreatment,
    TransportCostAllocator,
    TransportLegCostProfile,
)
from domain.ccs_network.flow import ExplicitFlowPlan, TransportFlow
from domain.ccs_network.models import (
    AnnualSchedule,
    Availability,
    CapturePlant,
    CcsNetworkScenario,
    LegParticipation,
    NetworkEmitter,
    NetworkNode,
    NodeKind,
    PipelineSpec,
    StorageSite,
    TransportLeg,
    TruckSpec,
)


YEAR = 2035


def _multi_emitter_scenario() -> CcsNetworkScenario:
    availability = Availability(YEAR, YEAR)
    nodes = (
        NetworkNode("hub", "Shared collection hub", NodeKind.HUB),
        NetworkNode("emitter-b", "Emitter B truck terminal", NodeKind.EMITTER),
        NetworkNode("storage", "Storage entry", NodeKind.STORAGE),
    )
    emitters = (
        NetworkEmitter(
            id="A",
            name="Emitter A",
            capture_plant=CapturePlant(
                id="capture-a",
                name="Capture A",
                availability=availability,
                capacity_t_per_year=400_000.0,
                captured_co2_t=AnnualSchedule.from_mapping({YEAR: 400_000.0}),
            ),
            delivery_node_id="hub",
        ),
        NetworkEmitter(
            id="B",
            name="Emitter B",
            capture_plant=CapturePlant(
                id="capture-b",
                name="Capture B",
                availability=availability,
                capacity_t_per_year=300_000.0,
                captured_co2_t=AnnualSchedule.from_mapping({YEAR: 300_000.0}),
            ),
            delivery_node_id="emitter-b",
        ),
    )
    transport_legs = (
        TransportLeg(
            id="shared-pipeline",
            name="Shared pipeline (1)",
            owner_id="network-operator",
            origin_node_id="hub",
            destination_node_id="storage",
            mode=PipelineSpec(length_km=40.0, capacity_t_per_year=700_000.0),
            availability=availability,
        ),
        TransportLeg(
            id="b-private-truck",
            name="Emitter B private truck leg (2)",
            owner_id="B",
            origin_node_id="emitter-b",
            destination_node_id="hub",
            mode=TruckSpec(
                length_km=25.0,
                payload_t_per_trip=30.0,
                trips_per_truck_per_day=2.0,
                operating_days_per_year=300,
                fleet_size=17,
            ),
            availability=availability,
        ),
    )
    participations = (
        LegParticipation(
            emitter_id="A",
            leg_id="shared-pipeline",
            reservation_capacity_t_per_year=500_000.0,
            ownership_share=0.70,
            fixed_cost_share=0.60,
            tariff_eur_per_t=2.00,
        ),
        LegParticipation(
            emitter_id="B",
            leg_id="shared-pipeline",
            reservation_capacity_t_per_year=300_000.0,
            ownership_share=0.30,
            fixed_cost_share=0.40,
            tariff_eur_per_t=2.50,
        ),
        LegParticipation(
            emitter_id="B",
            leg_id="b-private-truck",
            reservation_capacity_t_per_year=300_000.0,
            ownership_share=1.0,
            fixed_cost_share=1.0,
        ),
    )
    return CcsNetworkScenario(
        id="cost-allocation-example",
        name="A/B shared pipeline with B private truck feeder",
        emitters=emitters,
        nodes=nodes,
        transport_legs=transport_legs,
        participations=participations,
        storage_sites=(
            StorageSite(
                id="store",
                name="Storage",
                node_id="storage",
                availability=availability,
                nominal_capacity_t=10_000_000.0,
            ),
        ),
    )


class TransportCostAllocationTests(unittest.TestCase):
    def test_shared_pipeline_and_private_truck_keep_emitter_provenance(self):
        scenario = _multi_emitter_scenario()
        flow_plan = ExplicitFlowPlan(
            transport_flows=(
                TransportFlow(YEAR, "A", "shared-pipeline", 400_000.0),
                TransportFlow(YEAR, "B", "b-private-truck", 300_000.0),
                TransportFlow(YEAR, "B", "shared-pipeline", 300_000.0),
            )
        )
        allocator = TransportCostAllocator(
            scenario,
            cost_profiles=(
                TransportLegCostProfile(
                    leg_id="shared-pipeline",
                    variable_opex_eur_per_t=1.0,
                    fixed_opex_eur_by_year={YEAR: 800_000.0},
                    capex_eur_by_year={YEAR: 10_000_000.0},
                    fixed_opex_allocation_basis=AllocationBasis.FIXED_COST_SHARE,
                    capex_allocation_basis=AllocationBasis.OWNERSHIP,
                    tariff_treatment=TariffTreatment.INTERNAL_TRANSFER,
                ),
                TransportLegCostProfile(
                    leg_id="b-private-truck",
                    variable_opex_eur_per_t=3.0,
                    fixed_opex_eur_by_year={YEAR: 200_000.0},
                    capex_eur_by_year={YEAR: 1_000_000.0},
                    fixed_opex_allocation_basis=AllocationBasis.RESERVED_CAPACITY,
                    capex_allocation_basis=AllocationBasis.OWNERSHIP,
                ),
            ),
        )

        result = allocator.allocate(flow_plan)

        self.assertEqual(len(result.records), 3)
        by_key = {
            (record.emitter_id, record.leg_id): record
            for record in result.records
        }
        a_pipeline = by_key[("A", "shared-pipeline")]
        b_pipeline = by_key[("B", "shared-pipeline")]
        b_truck = by_key[("B", "b-private-truck")]

        # Actual, reserved, ownership and fixed-cost shares remain distinct.
        self.assertAlmostEqual(a_pipeline.actual_flow_share, 4.0 / 7.0)
        self.assertAlmostEqual(a_pipeline.reservation_share, 5.0 / 8.0)
        self.assertAlmostEqual(a_pipeline.ownership_share, 0.70)
        self.assertAlmostEqual(a_pipeline.fixed_cost_share, 0.60)
        self.assertAlmostEqual(b_pipeline.actual_flow_share, 3.0 / 7.0)
        self.assertAlmostEqual(b_pipeline.reservation_share, 3.0 / 8.0)
        self.assertAlmostEqual(b_pipeline.ownership_share, 0.30)
        self.assertAlmostEqual(b_pipeline.fixed_cost_share, 0.40)

        self.assertIs(
            a_pipeline.fixed_opex_allocation_basis,
            AllocationBasis.FIXED_COST_SHARE,
        )
        self.assertIs(
            a_pipeline.capex_allocation_basis,
            AllocationBasis.OWNERSHIP,
        )
        self.assertAlmostEqual(a_pipeline.fixed_opex_eur, 480_000.0)
        self.assertAlmostEqual(b_pipeline.fixed_opex_eur, 320_000.0)
        self.assertAlmostEqual(a_pipeline.capex_eur, 7_000_000.0)
        self.assertAlmostEqual(b_pipeline.capex_eur, 3_000_000.0)
        self.assertAlmostEqual(a_pipeline.variable_opex_eur, 400_000.0)
        self.assertAlmostEqual(b_pipeline.variable_opex_eur, 300_000.0)

        # B's 300 kt keeps its identity on both its private truck feeder and
        # the shared pipeline; summing every leg would therefore double-count.
        self.assertEqual(b_truck.transported_t, 300_000.0)
        self.assertEqual(b_pipeline.transported_t, 300_000.0)
        self.assertEqual(sum(r.transported_t for r in result.records), 1_000_000.0)
        self.assertEqual(b_truck.actual_flow_share, 1.0)
        self.assertEqual(b_truck.reservation_share, 1.0)
        self.assertEqual(b_truck.ownership_share, 1.0)
        self.assertEqual(b_truck.fixed_cost_share, 1.0)
        self.assertAlmostEqual(b_truck.variable_opex_eur, 900_000.0)
        self.assertAlmostEqual(b_truck.fixed_opex_eur, 200_000.0)
        self.assertAlmostEqual(b_truck.capex_eur, 1_000_000.0)

        # Internal tariffs are visible for settlement, but are not added to
        # the system's physical transport resource cost a second time.
        self.assertAlmostEqual(a_pipeline.tariff_charge_eur, 800_000.0)
        self.assertAlmostEqual(b_pipeline.tariff_charge_eur, 750_000.0)
        self.assertAlmostEqual(result.internal_tariff_transfers_eur, 1_550_000.0)
        self.assertAlmostEqual(result.external_tariff_charges_eur, 0.0)
        self.assertAlmostEqual(result.physical_resource_cost_eur, 13_600_000.0)


if __name__ == "__main__":
    unittest.main()
