"""Storage sinks and geothermal doublets attached to graph nodes."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from .base import CoreModel, Slug, fraction, positive, unit_fraction
from .edge import PipelineDesign


class StorageType(str, Enum):
    """Deep saline aquifer or depleted hydrocarbon field."""

    DSA = "DSA"
    DHF = "DHF"


class ReservoirDefaults(CoreModel):
    """Fallback reservoir properties for newly declared DSA/DHF sites.

    The workbook lists far fewer sites than a real cluster needs, and most of
    them only carry a name, a depth and a capacity.  These defaults let a user add
    a site with three numbers (depth, capacity, type) and still run the full
    pressure/BHP model:

    * porosity 0.20
    * permeability 100 mD = 1e-13 m²
    * depth 1500 m
    """

    area_m2: float = Field(default=25e6, gt=0.0)
    effective_thickness_m: float = Field(default=150.0, gt=0.0)
    porosity: float = Field(default=0.20, gt=0.0, le=1.0)
    permeability_m2: float = Field(default=1.0e-13, gt=0.0, description="100 mD")
    top_depth_m: float = Field(default=1500.0, gt=0.0)
    temperature_c: float = Field(default=60.0)
    reference_pressure_bar: float = Field(default=150.0, gt=0.0)
    pressure_step_bar: float = Field(default=0.5, gt=0.0)
    fracture_pressure_gradient_bar_per_m: float = Field(default=0.18, gt=0.0)

    def as_reservoir(self) -> "ReservoirProperties":
        return ReservoirProperties(
            area_m2=self.area_m2,
            effective_thickness_m=self.effective_thickness_m,
            porosity=self.porosity,
            permeability_m2=self.permeability_m2,
            top_depth_m=self.top_depth_m,
            temperature_c=self.temperature_c,
            reference_pressure_bar=self.reference_pressure_bar,
            pressure_step_bar=self.pressure_step_bar,
            fracture_pressure_gradient_bar_per_m=self.fracture_pressure_gradient_bar_per_m,
        )


class ReservoirProperties(CoreModel):
    """Aquifer properties, named exactly as the engineering inputs they feed."""

    area_m2: float = positive("area_m2")
    effective_thickness_m: float = positive("effective_thickness_m")
    porosity: float = Field(gt=0.0, le=1.0)
    top_depth_m: float = positive("top_depth_m")
    temperature_c: float
    reference_pressure_bar: float = positive("reference_pressure_bar")
    pressure_step_bar: float = positive("pressure_step_bar")
    pore_compressibility_per_bar: float = Field(default=5.0e-5, gt=0.0)
    salinity_g_per_l: float = Field(default=0.0, ge=0.0)
    permeability_m2: float = positive("permeability_m2")
    irreducible_water_saturation: float = Field(default=0.25, ge=0.0, lt=1.0)
    storage_efficiency: float = Field(default=0.02, gt=0.0, le=1.0)
    plume_core_saturation: float = Field(default=0.2, ge=0.0, lt=1.0)
    krw_max: float = Field(default=1.0, gt=0.0, le=1.0)
    krg_max: float = Field(default=0.5, gt=0.0, le=1.0)
    krw_min: float = Field(default=0.05, ge=0.0, le=1.0)
    krg_min: float = Field(default=0.05, ge=0.0, le=1.0)
    nw: float = Field(default=3.0, gt=0.0)
    ng: float = Field(default=4.5, gt=0.0)
    fracture_pressure_gradient_bar_per_m: float = Field(default=0.18, gt=0.0)

    @property
    def maximum_pressure_bar(self) -> float:
        """Fracture limit of the cap rock above the aquifer top."""

        return float(self.fracture_pressure_gradient_bar_per_m) * float(self.top_depth_m)

    @property
    def drainage_radius_m(self) -> float:
        import math

        return math.sqrt(float(self.area_m2) / math.pi)


class InjectionWellProperties(CoreModel):
    """CO2 injector geometry used by the VFP and material-balance models."""

    radius_m: float = positive("radius_m")
    depth_m: float = positive("depth_m")
    roughness_m: float = Field(default=5.0e-4, ge=0.0)


class StorageSink(CoreModel):
    """Geological CO2 sink with capacity, pressure and cost attributes."""

    id: Slug
    node_id: Slug
    name: str = Field(min_length=1)
    storage_type: StorageType = StorageType.DSA
    capacity_t: float = Field(gt=0.0)
    geothermal_coupled: bool = Field(
        default=False,
        description="True when the site hosts a geothermal doublet in parallel with CO2 injection.",
    )
    geothermal_start_year: int | None = Field(
        default=None,
        description="First year of geothermal operation; defaults to the commissioning year.",
    )
    max_injection_rate_t_per_year: float | None = Field(
        default=None,
        gt=0.0,
        description="Explicit well-capacity cap; when omitted it is derived from the BHP limit.",
    )
    reservoir: ReservoirProperties | None = None
    injection_well: InjectionWellProperties | None = None
    commissioning_year: int | None = None
    decommission_year: int | None = None
    capex_eur: float = Field(default=0.0, ge=0.0)
    opex_eur_per_t: float = Field(default=0.0, ge=0.0)
    monitoring_cost_during_injection_eur_per_year: float = Field(default=0.0, ge=0.0)
    monitoring_cost_after_injection_eur_per_year: float = Field(default=0.0, ge=0.0)
    monitoring_end_year: int | None = None
    compressor_inlet_pressure_bar: float = Field(default=25.0, gt=0.0)
    compressor_inlet_temperature_c: float = 20.0
    eta_orc: float = Field(default=0.20, gt=0.0, le=1.0)
    eta_gt_injection_pump: float = Field(default=0.90, gt=0.0, le=1.0)
    eta_co2_compressor_isentropic: float = Field(default=0.75, gt=0.0, le=1.0)
    eta_co2_dense_phase_pump: float = Field(default=0.90, gt=0.0, le=1.0)
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "StorageSink":
        if (
            self.commissioning_year is not None
            and self.decommission_year is not None
            and self.decommission_year < self.commissioning_year
        ):
            raise ValueError("decommission_year must not precede commissioning_year")
        return self

    def active_in(self, year: int) -> bool:
        year = int(year)
        if self.commissioning_year is not None and year < self.commissioning_year:
            return False
        return self.decommission_year is None or year <= self.decommission_year

    def maximum_pressure_bar(self) -> float | None:
        return None if self.reservoir is None else self.reservoir.maximum_pressure_bar


class GeothermalSystem(CoreModel):
    """Geothermal doublet coupled to the CO2 storage pressure."""

    id: Slug
    node_id: Slug
    name: str = Field(min_length=1)
    d_doublet_m: float = positive("d_doublet_m")
    reservoir_temperature_c: float
    bhp_dp_bar: float = Field(default=10.0, gt=0.0)
    eta_orc: float = fraction("eta_orc")
    p_out_bar: float = positive("p_out_bar")
    t_out_c: float
    rw_production_m: float = positive("rw_production_m")
    rw_injection_m: float = positive("rw_injection_m")
    h_ref_production_m: float = positive("h_ref_production_m")
    h_ref_injection_m: float = positive("h_ref_injection_m")
    roughness_m: float = Field(default=5.0e-4, ge=0.0)
    surface_formation_temperature_c: float = Field(default=20.0)
    water_pipeline: PipelineDesign | None = None
    operation_start_year: int | None = None
    operation_end_year: int | None = None
    capex_eur: float = Field(default=0.0, ge=0.0)
    fixed_opex_eur_per_year: float = Field(default=0.0, ge=0.0)
    variable_opex_eur_per_mwh: float = Field(default=0.0, ge=0.0)
    orc_availability: float = unit_fraction("orc_availability")
    pump_availability: float = unit_fraction("pump_availability")
    production_well_availability: float = unit_fraction("production_well_availability")
    injection_well_availability: float = unit_fraction("injection_well_availability")
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "GeothermalSystem":
        if (
            self.operation_start_year is not None
            and self.operation_end_year is not None
            and self.operation_end_year < self.operation_start_year
        ):
            raise ValueError("operation_end_year must not precede operation_start_year")
        if self.water_pipeline is not None and self.water_pipeline.mode.value != "pipeline":
            raise ValueError("the geothermal surface line must be a pipeline")
        return self

    def active_in(self, year: int) -> bool:
        year = int(year)
        if self.operation_start_year is not None and year < self.operation_start_year:
            return False
        return self.operation_end_year is None or year <= self.operation_end_year

    def available_hours_per_year(self) -> float:
        """Combined availability of the doublet, used as an annual derating."""

        return 8766.0 * min(
            float(self.orc_availability),
            float(self.pump_availability),
            float(self.production_well_availability),
            float(self.injection_well_availability),
        )


class MonitoringPlan(CoreModel):
    """Post-injection monitoring window of one storage complex."""

    sink_id: Slug
    start_year: int
    end_year: int
    annual_cost_eur: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _check(self) -> "MonitoringPlan":
        if self.end_year < self.start_year:
            raise ValueError("monitoring end_year must not precede start_year")
        return self
