"""Emitter database: the catalogue of emitters a study can draw from.

The engine models the emitters *of one scenario*.  A study, however, starts from a
catalogue of all candidate emitters (the plants of a region) and then selects which
ones take part.  This module reads that catalogue so any front end - Streamlit, a
desktop app, a notebook - can offer the same list.

The file is plain JSON (``json/emitters.json`` by default) so a domain expert can
edit it without touching code::

    {
      "id": "te-plomin",
      "name": "TE PLOMIN",
      "industry": "thermal power plant",
      "curve": {"kind": "power_law", "reference_year": 2025,
                 "e0_t_per_year": 1118203.087, "a": -0.03, "c": 1.5},
      "implementation_probability": 0.5,
      "activation_year": 2028,
      "reference_sink_id": "ivanic"
    }

Nothing here imports Streamlit or any UI toolkit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ccus_core.models import EmissionCurve

#: ``<repository>/json/emitters.json``
DEFAULT_CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "json" / "emitters.json"


@dataclass(frozen=True)
class EmitterRecord:
    """One catalogue entry: everything a study knows about a candidate emitter."""

    id: str
    name: str
    curve: EmissionCurve
    industry: str | None = None
    node_id: str | None = None
    implementation_probability: float | None = None
    activation_year: int | None = None
    capture_technology: str | None = None
    reference_sink_id: str | None = None
    notes: str | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def reference_year(self) -> int:
        """Year the emission figure refers to (the curve's own reference year)."""

        return int(self.curve.reference_year or 0)

    def emissions_in(self, year: int) -> float:
        """Gross CO2 of this emitter in ``year`` (t/yr), before capture."""

        return float(self.curve.value_at(int(year)))

    def available_emissions(self, year: int) -> float:
        """Emissions the emitter offers once it is online."""

        year = int(year)
        if self.activation_year is not None and year < int(self.activation_year):
            return 0.0
        return self.emissions_in(year)

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe view with the same layout as ``json/emitters.json``."""

        curve = self.curve
        if curve.kind == "power_law":
            curve_payload = {
                "kind": curve.kind,
                "reference_year": curve.reference_year,
                "e0_t_per_year": curve.e0_t_per_year,
                "a": curve.a,
                "c": curve.c,
            }
            if curve.b is not None:
                curve_payload["b"] = curve.b
        elif curve.kind == "piecewise_linear":
            curve_payload = {
                "kind": curve.kind,
                "points": {str(year): value for year, value in (curve.points or {}).items()},
            }
        elif curve.kind == "polynomial":
            curve_payload = {
                "kind": curve.kind,
                "reference_year": curve.reference_year,
                "base_t_per_year": curve.constant_t_per_year,
                "a": curve.polynomial_a,
                "c": curve.polynomial_c,
            }
        else:
            curve_payload = {"kind": curve.kind, "constant_t_per_year": curve.constant_t_per_year}

        return {
            "id": self.id,
            "name": self.name,
            "industry": self.industry,
            "node_id": self.node_id,
            "curve": curve_payload,
            "implementation_probability": self.implementation_probability,
            "activation_year": self.activation_year,
            "capture_technology": self.capture_technology,
            "reference_sink_id": self.reference_sink_id,
            "notes": self.notes,
        }


def _curve_from_payload(payload: Any) -> EmissionCurve:
    """Validate one curve block; a bare number is accepted as a constant."""

    if isinstance(payload, (int, float)):
        return EmissionCurve.constant(float(payload))
    if not isinstance(payload, dict):
        raise ValueError("an emitter curve must be an object or a number")
    return EmissionCurve.model_validate(payload)


def record_from_payload(payload: dict) -> EmitterRecord:
    """Validate one catalogue entry (the UI and the tests build the same dict)."""

    if not isinstance(payload, dict):
        raise ValueError("an emitter catalogue entry must be an object")
    emitter_id = str(payload.get("id") or "").strip()
    name = str(payload.get("name") or "").strip()
    if not emitter_id or not name:
        raise ValueError("an emitter catalogue entry needs both 'id' and 'name'")
    return EmitterRecord(
        id=emitter_id,
        name=name,
        curve=_curve_from_payload(payload.get("curve")),
        industry=(str(payload["industry"]).strip() or None) if payload.get("industry") else None,
        node_id=(str(payload["node_id"]).strip() or None) if payload.get("node_id") else None,
        implementation_probability=(
            None
            if payload.get("implementation_probability") is None
            else float(payload["implementation_probability"])
        ),
        activation_year=(
            None if payload.get("activation_year") is None else int(payload["activation_year"])
        ),
        capture_technology=(
            (str(payload["capture_technology"]).strip() or None)
            if payload.get("capture_technology")
            else None
        ),
        reference_sink_id=(
            (str(payload["reference_sink_id"]).strip() or None)
            if payload.get("reference_sink_id")
            else None
        ),
        notes=(str(payload["notes"]).strip() or None) if payload.get("notes") else None,
    )


def load_emitter_catalogue(
    path: str | Path | None = None,
) -> list[EmitterRecord]:
    """Read the emitter database and return one :class:`EmitterRecord` per entry.

    ``path`` defaults to ``json/emitters.json``; ``load_emitter_catalogue(None)``
    therefore gives the bundled catalogue.  Entries keep the file order, which is
    the order the UI shows.
    """

    target = Path(path) if path is not None else DEFAULT_CATALOGUE_PATH
    document = json.loads(target.read_text(encoding="utf-8"))
    entries = document.get("emitters", document) if isinstance(document, dict) else document
    if not isinstance(entries, list):
        raise ValueError(f"'{target}' must contain a list of emitters under 'emitters'")
    return [record_from_payload(entry) for entry in entries]


def catalogue_ids(path: str | Path | None = None) -> list[str]:
    """Ids of the catalogue entries, in file order."""

    return [record.id for record in load_emitter_catalogue(path)]


def save_emitter_catalogue(
    records: list[EmitterRecord],
    path: str | Path | None = None,
) -> Path:
    """Write the emitter database back (atomic, UTF-8, same layout)."""

    from .catalogue import save_records

    target = Path(path) if path is not None else DEFAULT_CATALOGUE_PATH
    payload = [record.as_dict() for record in records]
    meta = {
        "_meta": _catalogue_meta(target, len(payload)),
    }
    return save_records(target, payload, meta=meta, list_key="emitters")


def append_emitter(record: EmitterRecord, path: str | Path | None = None) -> EmitterRecord:
    """Add one emitter to the database, refusing a duplicate id.

    The ``_meta`` block (schema, source, generated date) is preserved and its
    ``count`` refreshed; a plain append would rewrite the file without it.
    """

    from .catalogue import CatalogueError, append_record, load_records

    target = Path(path) if path is not None else DEFAULT_CATALOGUE_PATH
    existing = load_records(target)
    if any(str(item.get("id", "")).strip() == record.id for item in existing):
        raise CatalogueError(f"'{record.id}' is already in '{target.name}'")
    append_record(
        target,
        record.as_dict(),
        key="id",
        meta={"_meta": _catalogue_meta(target, len(existing) + 1)},
        list_key="emitters",
    )
    return record


def _catalogue_meta(target: Path, count: int) -> dict:
    """The ``_meta`` block written next to the records."""

    try:
        document = json.loads(target.read_text(encoding="utf-8"))
        existing = document.get("_meta", {}) if isinstance(document, dict) else {}
    except Exception:  # noqa: BLE001 - a new file has no metadata yet
        existing = {}
    meta = dict(existing) if isinstance(existing, dict) else {}
    meta.update({"schema": "gt-ccus-emitters/1.0", "count": count})
    return meta


__all__ = [
    "DEFAULT_CATALOGUE_PATH",
    "EmitterRecord",
    "append_emitter",
    "catalogue_ids",
    "load_emitter_catalogue",
    "record_from_payload",
    "save_emitter_catalogue",
]