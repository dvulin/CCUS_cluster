"""Pure data models of the CCUS core (no I/O, no UI, no solver state)."""

from __future__ import annotations

from .base import MODEL_VERSION, CoreModel, Slug, interp_year, series_from_profile, year_axis
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
from .node import GeoLocation, Node, NodeKind, PortHub
from .scenario import ScenarioConfig
from .sink import (
    GeothermalSystem,
    InjectionWellProperties,
    MonitoringPlan,
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
    "GeoLocation",
    "Node",
    "NodeKind",
    "PortHub",
    "ScenarioConfig",
    "GeothermalSystem",
    "InjectionWellProperties",
    "MonitoringPlan",
    "ReservoirProperties",
    "StorageSink",
    "StorageType",
]