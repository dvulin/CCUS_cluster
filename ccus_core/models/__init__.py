"""Pure data models of the CCUS core (no I/O, no UI, no solver state)."""

from __future__ import annotations

from .base import MODEL_VERSION, CoreModel, Slug, interp_year, series_from_profile, year_axis
from .connection import EmitterSinkConnection
from .economics import CustomPricePath, EconomicsConfig, PricePath
from .edge import (
    EdgeState,
    InfrastructureUpgrade,
    MarineDesign,
    PipelineDesign,
    RoadDesign,
    TransportEdge,
    TransportMode,
    UpgradeTrigger,
)
from .emitter import CaptureTechnology, CaptureUnit, EmissionCurve, Emitter
from .node import GeoLocation, Hub, Node, NodeKind, PortHub
from .policy import (
    DEFAULT_PRICE_SCENARIOS,
    CaptureCostParameters,
    Co2PriceScenario,
    EtsAllowanceSchedule,
    EtsAllowanceStep,
    FinancialParameters,
    PolicyConfig,
    StorageCostParameters,
    TransportCostParameters,
    default_price_scenarios,
)
from .scenario import DEFAULT_ONBOARDING_YEARS, ScenarioConfig
from .sink import (
    GeothermalSystem,
    InjectionWellProperties,
    MonitoringPlan,
    ReservoirDefaults,
    ReservoirProperties,
    StorageSink,
    StorageType,
)

__all__ = [
    "MODEL_VERSION",
    "CoreModel",
    "Slug",
    "interp_year",
    "series_from_profile",
    "year_axis",
    "CustomPricePath",
    "EconomicsConfig",
    "PricePath",
    "EdgeState",
    "InfrastructureUpgrade",
    "MarineDesign",
    "PipelineDesign",
    "RoadDesign",
    "TransportEdge",
    "TransportMode",
    "UpgradeTrigger",
    "CaptureTechnology",
    "CaptureUnit",
    "EmissionCurve",
    "Emitter",
    "EmitterSinkConnection",
    "GeoLocation",
    "Node",
    "NodeKind",
    "PortHub",
    "DEFAULT_ONBOARDING_YEARS",
    "DEFAULT_PRICE_SCENARIOS",
    "CaptureCostParameters",
    "Co2PriceScenario",
    "EtsAllowanceSchedule",
    "EtsAllowanceStep",
    "FinancialParameters",
    "PolicyConfig",
    "StorageCostParameters",
    "TransportCostParameters",
    "default_price_scenarios",
    "ScenarioConfig",
    "GeothermalSystem",
    "InjectionWellProperties",
    "MonitoringPlan",
    "ReservoirDefaults",
    "ReservoirProperties",
    "StorageSink",
    "StorageType",
]