"""Simulation package: reservoir, wells, geothermal and the chronological solver."""

from __future__ import annotations

from .adapters import (
    SECONDS_PER_YEAR,
    geothermal_inputs,
    power_inputs,
    power_inputs_for_sink,
    reservoir_inputs,
    sink_defaults,
    well_inputs,
)
from .geothermal import GeothermalCoupling
from .pressures import pressure_table
from .reservoir import CapacityCurve, VariableRateReservoir
from .solver import ChronologicalSolver, SimulationResult

__all__ = [
    "SECONDS_PER_YEAR",
    "CapacityCurve",
    "ChronologicalSolver",
    "GeothermalCoupling",
    "SimulationResult",
    "VariableRateReservoir",
    "geothermal_inputs",
    "power_inputs",
    "power_inputs_for_sink",
    "pressure_table",
    "reservoir_inputs",
    "sink_defaults",
    "well_inputs",
]