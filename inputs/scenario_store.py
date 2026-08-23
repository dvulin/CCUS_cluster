"""Safe persistence helpers for named Streamlit input scenarios."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Mapping


SCENARIO_DIRECTORY_ENV = "GT_CCS_SCENARIO_DIRECTORY"
LAST_INPUTS_FILENAME = "last_inputs.json"
ARCHIVE_FILENAME_PATTERN = re.compile(
    r"^\d{6}_\d{4}_inputs(?:_\d+)?\.json$"
)


@dataclass(frozen=True)
class SavedScenario:
    """A scenario file that is safe to expose in the Streamlit selectors."""

    scenario_name: str
    filename: str
    path: Path

    @property
    def label(self) -> str:
        return f"{self.scenario_name}, {self.filename}"


def scenario_directory(directory: str | Path | None = None) -> Path:
    """Return the configured scenario directory without creating it."""
    if directory is not None:
        return Path(directory).expanduser().resolve()
    configured = os.environ.get(SCENARIO_DIRECTORY_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parent / "scenarios").resolve()


def scenario_name_from_inputs(inputs: Mapping) -> str:
    """Read and validate the canonical ``scenario_name`` JSON entry."""
    entry = inputs.get("scenario_name")
    if not isinstance(entry, list) or not entry:
        raise ValueError(
            "Scenarij nema valjani scenario_name u formatu "
            "[vrijednost, jedinica, opis]."
        )
    value = entry[0]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Naziv scenarija ne smije biti prazan.")
    return value.strip()


def _validated_filename(filename: str, *, allow_last: bool) -> str:
    """Accept only an exact scenario basename, never a path or traversal."""
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError("Neispravno ime datoteke scenarija.")
    if allow_last and filename == LAST_INPUTS_FILENAME:
        return filename
    if not ARCHIVE_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError("Datoteka nije prepoznata arhiva ulaznog scenarija.")
    return filename


def _scenario_path(
    filename: str,
    *,
    directory: str | Path | None,
    allow_last: bool,
) -> Path:
    root = scenario_directory(directory)
    safe_name = _validated_filename(filename, allow_last=allow_last)
    candidate = (root / safe_name).resolve()
    if candidate.parent != root:
        raise ValueError("Datoteka scenarija mora biti unutar spremišta scenarija.")
    return candidate


def _write_last_inputs(path: Path, payload: str) -> None:
    """Atomically replace ``last_inputs.json`` in its own directory."""
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".last_inputs_",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(payload)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def save_scenario(
    inputs: Mapping,
    *,
    directory: str | Path | None = None,
    now: datetime | None = None,
) -> tuple[Path, Path]:
    """Save the latest inputs and a non-overwriting timestamped archive."""
    if not isinstance(inputs, Mapping):
        raise TypeError("Ulazni scenarij mora biti JSON objekt.")
    scenario_name_from_inputs(inputs)
    root = scenario_directory(directory)
    root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(inputs, ensure_ascii=False, indent=2) + "\n"

    last_path = _scenario_path(
        LAST_INPUTS_FILENAME,
        directory=root,
        allow_last=True,
    )
    _write_last_inputs(last_path, payload)

    timestamp = (now or datetime.now()).strftime("%y%m%d_%H%M")
    archive_index = 1
    while True:
        suffix = "" if archive_index == 1 else f"_{archive_index}"
        archive_name = f"{timestamp}_inputs{suffix}.json"
        archive_path = _scenario_path(
            archive_name,
            directory=root,
            allow_last=False,
        )
        try:
            with archive_path.open("x", encoding="utf-8") as archive_file:
                archive_file.write(payload)
            break
        except FileExistsError:
            archive_index += 1

    return last_path, archive_path


def load_scenario(
    filename: str,
    *,
    directory: str | Path | None = None,
) -> dict:
    """Load one validated scenario file from the configured directory."""
    path = _scenario_path(filename, directory=directory, allow_last=True)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Scenarij više ne postoji: {filename}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Scenarij se ne može učitati: {filename}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Ulazni scenarij mora sadržavati JSON objekt.")
    scenario_name_from_inputs(data)
    return data


def list_saved_scenarios(
    *,
    directory: str | Path | None = None,
    include_last: bool = True,
) -> list[SavedScenario]:
    """List valid scenarios, newest archive first, with ``last`` at the top."""
    root = scenario_directory(directory)
    if not root.exists():
        return []
    records: list[SavedScenario] = []
    for path in root.glob("*.json"):
        if path.name == LAST_INPUTS_FILENAME:
            if not include_last:
                continue
        elif not ARCHIVE_FILENAME_PATTERN.fullmatch(path.name):
            continue
        try:
            data = load_scenario(path.name, directory=root)
            records.append(
                SavedScenario(
                    scenario_name=scenario_name_from_inputs(data),
                    filename=path.name,
                    path=path.resolve(),
                )
            )
        except ValueError:
            continue
    return sorted(
        records,
        key=lambda item: (
            item.filename == LAST_INPUTS_FILENAME,
            item.filename,
        ),
        reverse=True,
    )


def delete_scenario(
    filename: str,
    *,
    directory: str | Path | None = None,
) -> Path:
    """Delete one exact timestamped archive; ``last_inputs.json`` is protected."""
    path = _scenario_path(filename, directory=directory, allow_last=False)
    try:
        path.unlink()
    except FileNotFoundError as exc:
        raise ValueError(f"Scenarij više ne postoji: {filename}") from exc
    return path
