"""Architectural rules of the core package (enforced, not documented only)."""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = REPOSITORY_ROOT / "ccus_core"

FORBIDDEN = {
    "streamlit",
    "tkinter",
    "xlwings",
    "plotly",
    "pydeck",
    "altair",
    "matplotlib",
    "seaborn",
    "bokeh",
}


def _python_files():
    return sorted(path for path in CORE_ROOT.rglob("*.py") if "__pycache__" not in path.parts)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_core_does_not_import_any_ui_or_plotting_library():
    offenders = {}
    for path in _python_files():
        imported = _imported_modules(path) & FORBIDDEN
        if imported:
            offenders[str(path.relative_to(REPOSITORY_ROOT))] = sorted(imported)
    assert not offenders, f"UI/plotting imports found in ccus_core: {offenders}"


def test_core_does_not_import_the_streamlit_app():
    for path in _python_files():
        imported = _imported_modules(path)
        assert "streamlit_app" not in imported, path


def test_models_do_not_import_pandas_or_the_engine():
    """``ccus_core.models`` must stay pure data (JSON-serialisable)."""

    for path in sorted((CORE_ROOT / "models").glob("*.py")):
        imported = _imported_modules(path)
        assert "pandas" not in imported, f"{path.name} must not import pandas"
        assert "ccus_core.simulation" not in " ".join(imported), path.name


def test_models_do_not_depend_on_the_solver_or_finance_layers():
    for path in sorted((CORE_ROOT / "models").glob("*.py")):
        imported = _imported_modules(path)
        for layer in ("ccus_core",):
            for forbidden in (f"{layer}.simulation", f"{layer}.finance", f"{layer}.network", f"{layer}.engine"):
                assert forbidden not in imported, f"{path.name} must not import {forbidden}"