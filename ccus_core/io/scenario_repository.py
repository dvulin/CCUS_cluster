"""Named scenario files: save, load, list and delete whole scenarios.

The repository is deliberately simple and UI-agnostic: one directory of
``<name>.json`` documents in the canonical commented-JSON format.  Names are
validated and always stay inside the directory (no traversal), writes are atomic
and an existing name is never silently overwritten.

Default names are ``scenario_001``, ``scenario_002``, … so a user can store a run
without inventing a name.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ccus_core.models import ScenarioConfig

from .commented_json import dump, load_file

SCENARIO_DIRECTORY_ENV = "GT_CCS_SCENARIO_DIRECTORY"
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "inputs" / "scenarios"
DEFAULT_PREFIX = "scenario"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")


class ScenarioNotFoundError(FileNotFoundError):
    """Raised when a requested scenario name does not exist."""


@dataclass(frozen=True)
class ScenarioRecord:
    """A saved scenario file."""

    name: str
    path: Path

    @property
    def size_kb(self) -> float:
        return round(self.path.stat().st_size / 1024.0, 1)


def scenario_directory(directory: str | Path | None = None) -> Path:
    """Return (and create) the directory that stores named scenarios."""

    if directory is not None:
        root = Path(directory).expanduser().resolve()
    else:
        configured = os.environ.get(SCENARIO_DIRECTORY_ENV)
        root = Path(configured).expanduser().resolve() if configured else DEFAULT_DIRECTORY.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_name(name: str) -> str:
    """Return a safe scenario name (stem without ``.json``)."""

    if not isinstance(name, str):
        raise ValueError("Scenario name must be text.")
    candidate = name.strip()
    if candidate.lower().endswith(".json"):
        candidate = candidate[: -len(".json")].strip()
    if not NAME_PATTERN.fullmatch(candidate):
        raise ValueError(
            "Scenario name may contain letters, digits, spaces, dots, dashes and underscores."
        )
    if candidate.lower().startswith("."):
        raise ValueError("Scenario name may not start with a dot.")
    return candidate


def next_default_name(directory: str | Path | None = None) -> str:
    """Return ``scenario_001``, ``scenario_002``, … – the first free default name."""

    root = scenario_directory(directory)
    index = 1
    while True:
        candidate = f"{DEFAULT_PREFIX}_{index:03d}"
        if not (root / f"{candidate}.json").exists():
            return candidate
        index += 1


def list_scenarios(directory: str | Path | None = None) -> list[ScenarioRecord]:
    """Return the saved scenarios sorted by name."""

    root = scenario_directory(directory)
    records = [
        ScenarioRecord(name=path.stem, path=path)
        for path in root.glob("*.json")
        if path.is_file() and not path.name.startswith(".")
    ]
    return sorted(records, key=lambda record: record.name.lower())


def save_scenario(
    scenario: ScenarioConfig,
    name: str | None = None,
    *,
    directory: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    """Write ``scenario`` as ``<name>.json`` and return the path."""

    root = scenario_directory(directory)
    stem = validate_name(name or next_default_name(root))
    target = scenario_path(f"{stem}.json", directory=root)
    if target.parent != root:
        raise ValueError("Scenario files must stay inside the scenario directory.")

    payload = dump(scenario)
    if target.exists() and not overwrite:
        raise FileExistsError(f"Scenario '{stem}' already exists.")

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=root,
        prefix=f".{stem}_",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def scenario_path(name_or_path: str | Path, *, directory: str | Path | None = None) -> Path:
    """Resolve a scenario name (or path) to a file **inside** the scenario directory.

    Loading and deleting are confined to the directory on purpose: a scenario name
    must never be able to reach an arbitrary file through ``..`` or an absolute
    path.  ``ValueError`` is raised for anything outside it.
    """

    root = scenario_directory(directory).resolve()
    raw = str(name_or_path)
    looks_like_path = (
        Path(raw).is_absolute()
        or "/" in raw
        or "\\" in raw
        or Path(raw).suffix.lower() == ".json"
    )
    if looks_like_path:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        if resolved.parent != root:
            raise ValueError(
                "Scenario files must stay inside the scenario directory "
                f"({root}); refusing '{name_or_path}'."
            )
        return resolved

    stem = validate_name(raw)
    return root / f"{stem}.json"


def load_scenario_file(name_or_path: str | Path, *, directory: str | Path | None = None) -> ScenarioConfig:
    """Load a scenario by name (or by a path inside the scenario directory)."""

    path = scenario_path(name_or_path, directory=directory)
    if not path.is_file():
        raise ScenarioNotFoundError(f"Scenario '{path.stem}' was not found.")
    return load_file(path)


def delete_scenario(name_or_path: str | Path, *, directory: str | Path | None = None) -> None:
    """Delete one scenario file (never a directory, never outside the directory)."""

    path = scenario_path(name_or_path, directory=directory)
    if not path.is_file():
        raise ScenarioNotFoundError(f"Scenario '{path.stem}' was not found.")
    path.unlink()


__all__ = [
    "SCENARIO_DIRECTORY_ENV",
    "DEFAULT_DIRECTORY",
    "DEFAULT_PREFIX",
    "ScenarioNotFoundError",
    "ScenarioRecord",
    "scenario_directory",
    "scenario_path",
    "validate_name",
    "next_default_name",
    "list_scenarios",
    "save_scenario",
    "load_scenario_file",
    "delete_scenario",
]