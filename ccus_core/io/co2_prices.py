"""CO2 price scenarios as an editable yearly time series (``json/CO2_prices.json``).

The three price paths of the study (optimistic, conservative, pessimistic) are
documented in the workbook ``cash-flow``!F25:AE27 as one value per year.  They used
to exist only as Python constants, so a reviewer had to read the source to know
what a scenario costs and a rerun meant editing code.  This module reads - and
writes - that yearly series, so the prices are ordinary reviewed data:

    {
      "_meta": {"schema": "gt-ccus-co2-prices/1.0", "unit": "EUR/t CO2", ...},
      "years": [2025, 2026, ...],
      "scenarios": {
        "optimistic":   [63.64, 93.99, ...],
        "conservative": [63.64, 68.08, ...],
        "pessimistic":  [63.64, 42.59, ...]
      }
    }

This module is I/O only: it returns :class:`~ccus_core.models.policy.Co2PriceScenario`
objects, so the Pydantic models stay free of file access.  A **missing** file falls
back to the built-in defaults (the workbook values), while a **malformed** file
raises :class:`Co2PriceFileError` - silently pricing a cluster with numbers nobody
reviewed would be worse than stopping.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

from ccus_core.models.policy import Co2PriceScenario, default_price_scenarios

ROOT = Path(__file__).resolve().parents[2]
JSON_DIRECTORY = ROOT / "json"

CO2_PRICES_PATH = JSON_DIRECTORY / "CO2_prices.json"

#: environment variable that points at a different price file
PRICE_DIRECTORY_ENV = "GT_CCS_CO2_PRICES"

#: the presets ``PricePath.mode`` and ``PolicyConfig.selected_price_scenario`` accept
PRICE_SCENARIO_NAMES = ("optimistic", "conservative", "pessimistic")

#: first year of the workbook series
DEFAULT_START_YEAR = 2025

SCHEMA = "gt-ccus-co2-prices/1.0"
UNIT = "EUR/t CO2"


class Co2PriceFileError(ValueError):
    """Raised when the CO2 price file is missing a year or holds an invalid value."""


# --------------------------------------------------------------------------- path
def price_file_path(path: str | Path | None = None) -> Path:
    """Resolve the price file: explicit argument, ``GT_CCS_CO2_PRICES``, default."""

    if path is not None:
        return Path(path).expanduser()
    configured = os.environ.get(PRICE_DIRECTORY_ENV)
    if configured:
        return Path(configured).expanduser()
    return CO2_PRICES_PATH


# ------------------------------------------------------------------------- reading
def _read(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"CO2 price file '{path}' does not exist") from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Co2PriceFileError(f"CO2 price file '{path}' is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise Co2PriceFileError(f"CO2 price file '{path}' must be a JSON object")
    return document


def _years_from(document: dict, path: Path) -> list[int]:
    """The year axis of the file (explicit ``years``, or derived from ``start_year``)."""

    raw = document.get("years")
    if raw is None:
        meta = document.get("_meta") if isinstance(document.get("_meta"), dict) else {}
        start = document.get("start_year", meta.get("start_year", DEFAULT_START_YEAR))
        try:
            start = int(start)
        except (TypeError, ValueError) as exc:
            raise Co2PriceFileError(
                f"CO2 price file '{path}': 'start_year' must be a whole year"
            ) from exc
        count = document.get("count", meta.get("count"))
        if count is None:
            # without an explicit axis the longest scenario defines the length
            raw = []
            scenarios = document.get("scenarios")
            if isinstance(scenarios, dict):
                for values in scenarios.values():
                    if isinstance(values, list):
                        raw = values
                        break
                    if isinstance(values, dict) and isinstance(values.get("values_eur_per_t"), list):
                        raw = values["values_eur_per_t"]
                        break
            if not raw:
                raise Co2PriceFileError(
                    f"CO2 price file '{path}': add a 'years' list or one scenario with values"
                )
            return [start + offset for offset in range(len(raw))]
        try:
            count = int(count)
        except (TypeError, ValueError) as exc:
            raise Co2PriceFileError(f"CO2 price file '{path}': 'count' must be a whole number") from exc
        return [start + offset for offset in range(count)]

    if not isinstance(raw, list) or not raw:
        raise Co2PriceFileError(f"CO2 price file '{path}': 'years' must be a non-empty list")
    years: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Co2PriceFileError(f"CO2 price file '{path}': every year must be a number")
        if float(value) != int(value):
            raise Co2PriceFileError(f"CO2 price file '{path}': '{value}' is not a whole year")
        years.append(int(value))
    if len(set(years)) != len(years):
        raise Co2PriceFileError(f"CO2 price file '{path}': 'years' must not repeat a year")
    if years != sorted(years):
        raise Co2PriceFileError(f"CO2 price file '{path}': 'years' must be sorted")
    return years


def _values_from(name: str, raw, path: Path) -> list[float]:
    """One scenario's series, accepting a bare list or a ``{values_eur_per_t: [...]}`` record."""

    if isinstance(raw, dict):
        for key in ("values_eur_per_t", "values", "prices"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raise Co2PriceFileError(
                f"CO2 price file '{path}': scenario '{name}' needs a list of yearly prices"
            )
    if not isinstance(raw, list) or not raw:
        raise Co2PriceFileError(
            f"CO2 price file '{path}': scenario '{name}' needs at least one price"
        )
    values: list[float] = []
    for index, value in enumerate(raw):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Co2PriceFileError(
                f"CO2 price file '{path}': scenario '{name}' value #{index + 1} is not a number"
            )
        value = float(value)
        if not math.isfinite(value):
            raise Co2PriceFileError(
                f"CO2 price file '{path}': scenario '{name}' value #{index + 1} is not finite"
            )
        if value < 0.0:
            raise Co2PriceFileError(
                f"CO2 price file '{path}': scenario '{name}' value #{index + 1} is negative"
            )
        values.append(value)
    return values


def scenarios_from_document(document: dict, *, path: str | Path = "co2 prices") -> dict[str, Co2PriceScenario]:
    """Validate a parsed price document into ``{name: Co2PriceScenario}``.

    The three presets must all be present: ``PricePath.mode`` and
    ``PolicyConfig.selected_price_scenario`` are restricted to them, so a file that
    drops one would make the remaining scenarios unusable.
    """

    years = _years_from(document, Path(str(path)))
    raw = document.get("scenarios")
    if not isinstance(raw, dict) or not raw:
        raise Co2PriceFileError(f"CO2 price file '{path}': 'scenarios' must be an object")

    scenarios: dict[str, Co2PriceScenario] = {}
    for name, payload in raw.items():
        key = str(name).strip()
        if not key:
            raise Co2PriceFileError(f"CO2 price file '{path}': a scenario needs a name")
        values = _values_from(key, payload, path)
        if len(values) != len(years):
            raise Co2PriceFileError(
                f"CO2 price file '{path}': scenario '{key}' has {len(values)} prices "
                f"for {len(years)} years - every year needs exactly one price"
            )
        scenarios[key] = Co2PriceScenario(name=key, start_year=years[0], values_eur_per_t=values)

    missing = [name for name in PRICE_SCENARIO_NAMES if name not in scenarios]
    if missing:
        raise Co2PriceFileError(
            f"CO2 price file '{path}' is missing the preset(s) {', '.join(missing)}; "
            f"expected {', '.join(PRICE_SCENARIO_NAMES)}"
        )
    return scenarios


def read_price_scenarios(path: str | Path | None = None) -> dict[str, Co2PriceScenario]:
    """Read the price file; raises when it is missing or malformed."""

    target = price_file_path(path)
    return scenarios_from_document(_read(target), path=target)


def load_price_scenarios(path: str | Path | None = None) -> dict[str, Co2PriceScenario]:
    """The price scenarios in force: the file, or the built-in defaults.

    A missing file is not an error - the workbook values are the documented
    fallback - but a file that exists and cannot be parsed is.
    """

    target = price_file_path(path)
    if not target.is_file():
        return default_price_scenarios()
    return read_price_scenarios(target)


def price_series(name: str, path: str | Path | None = None) -> list[float]:
    """The yearly series of one scenario, falling back to the defaults."""

    scenarios = load_price_scenarios(path)
    try:
        return list(scenarios[name].values_eur_per_t)
    except KeyError as exc:
        raise Co2PriceFileError(
            f"unknown CO2 price scenario '{name}'; available: {', '.join(scenarios)}"
        ) from exc


# ------------------------------------------------------------------------- writing
def scenarios_to_document(
    scenarios: dict[str, Co2PriceScenario],
    *,
    start_year: int | None = None,
    source: str | None = None,
) -> dict:
    """Render scenarios as the on-disk document (year axis plus one list each)."""

    if not scenarios:
        raise Co2PriceFileError("at least one CO2 price scenario is required")
    first = next(iter(scenarios.values()))
    start = int(start_year if start_year is not None else first.start_year)
    length = len(first.values_eur_per_t)
    names = list(scenarios)
    for name in names[1:]:
        if len(scenarios[name].values_eur_per_t) != length:
            raise Co2PriceFileError(
                f"scenario '{name}' has {len(scenarios[name].values_eur_per_t)} prices, "
                f"expected {length}"
            )

    return {
        "_meta": {
            "schema": SCHEMA,
            "source": source or "ccus_core.models.policy defaults",
            "unit": UNIT,
            "start_year": start,
            "years": length,
            "scenarios": names,
            "note": (
                "one price per year, EUR/t CO2; index 0 is start_year. "
                "The three presets are required by PricePath.mode."
            ),
        },
        "years": [start + offset for offset in range(length)],
        "scenarios": {name: list(scenarios[name].values_eur_per_t) for name in names},
    }


def save_price_scenarios(
    scenarios: dict[str, Co2PriceScenario],
    path: str | Path | None = None,
    *,
    source: str | None = None,
) -> Path:
    """Write the price file atomically; returns the path written."""

    target = price_file_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = scenarios_to_document(scenarios, source=source)

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.stem}_",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


__all__ = [
    "CO2_PRICES_PATH",
    "DEFAULT_START_YEAR",
    "PRICE_DIRECTORY_ENV",
    "PRICE_SCENARIO_NAMES",
    "SCHEMA",
    "UNIT",
    "Co2PriceFileError",
    "load_price_scenarios",
    "price_file_path",
    "price_series",
    "read_price_scenarios",
    "save_price_scenarios",
    "scenarios_from_document",
    "scenarios_to_document",
]