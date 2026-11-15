"""UI-agnostic CCUS engine.

``ccus_core`` contains the physics orchestration, the transport graph, the
chronological solver and the financial coupling.  It must never import
``streamlit``, ``matplotlib``, ``tkinter`` or ``xlwings``; the presentation layer
lives in a separate package.

Importing the package is cheap: the models are always available, while the solver
and the facade are loaded on first attribute access so that a UI can import the
data model without pulling in pandas, CoolProp and the engineering package.
"""

from __future__ import annotations

import importlib

from .models import *  # noqa: F401,F403
from .models import __all__ as _model_exports

__version__ = "0.1.0"

_LAZY_ATTRS = {
    "ScenarioEngine": "ccus_core.engine",
    "YearSnapshot": "ccus_core.engine",
    "run_scenario": "ccus_core.engine",
    "year_snapshot": "ccus_core.engine",
    "ChronologicalSolver": "ccus_core.simulation.solver",
    "SimulationResult": "ccus_core.simulation.solver",
    "NetworkGraph": "ccus_core.network.graph",
    "RoutingEngine": "ccus_core.network.routing",
    "RoutingResult": "ccus_core.network.routing",
    "VariableRateReservoir": "ccus_core.simulation.reservoir",
    "build_cash_flow_config": "ccus_core.finance.cashflow",
}


def __getattr__(name: str):
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'ccus_core' has no attribute '{name}'")
    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_ATTRS))


__all__ = ["__version__", *_model_exports, *_LAZY_ATTRS]