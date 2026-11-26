"""Reference data catalogues for the front ends (emitters, hubs, network, storage).

A cluster study needs four reference tables before any scenario exists:

=========================  ===========================================
``json/emitters.json``     candidate emitters (point sources)
``json/hubs.json``         candidate hubs (collection / booster sites)
``json/network.json``      candidate transport links and their geometry
``json/storage.json``      storage sites with their geology
=========================  ===========================================

The files are plain JSON so a domain expert can edit them; this module reads them,
appends validated records and writes them back atomically.  Nothing here imports
Streamlit or any other UI toolkit.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
JSON_DIRECTORY = ROOT / "json"

EMITTERS_PATH = JSON_DIRECTORY / "emitters.json"
NETWORK_PATH = JSON_DIRECTORY / "network.json"
STORAGE_PATH = JSON_DIRECTORY / "storage.json"
HUBS_PATH = JSON_DIRECTORY / "hubs.json"

#: transport kinds a network link can have
NETWORK_KINDS = ("pipeline", "road", "rail", "ship")
#: accepted spellings of a transport kind (the UI says "railway", the data "rail")
NETWORK_KIND_ALIASES = {"railway": "rail"}
#: node kinds a hub database entry can describe
HUB_KINDS = ("hub", "port", "offshore_terminal")
#: transport modes a hub can offer (the vocabulary of ``TransportMode``)
HUB_TRANSPORT_MODES = ("pipeline", "truck", "rail", "marine")
#: storage site types: a deep saline aquifer, a depleted hydrocarbon field
#: (``dgf``/``dof`` in the request) or one of its two sub-types
STORAGE_TYPES = ("DSA", "DHF", "DGF", "DOF")


class CatalogueError(ValueError):
    """Raised when a catalogue file or record is not usable."""


# --------------------------------------------------------------------------- io
def _read(path: Path) -> dict:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogueError(f"catalogue '{path}' does not exist") from exc
    except json.JSONDecodeError as exc:
        raise CatalogueError(f"catalogue '{path}' is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise CatalogueError(f"catalogue '{path}' must be a JSON object")
    return document


def load_records(path: str | Path) -> list[dict]:
    """Return the records of a catalogue file (list order is preserved)."""

    document = _read(Path(path))
    records = document.get("records", document.get("emitters"))
    if not isinstance(records, list):
        raise CatalogueError(f"catalogue '{path}' has no 'records' list")
    return [dict(record) for record in records]


def save_records(
    path: str | Path,
    records: Iterable[dict],
    *,
    meta: dict | None = None,
    list_key: str = "records",
) -> Path:
    """Write ``records`` back to a catalogue file, atomically."""

    target = Path(path)
    document: dict[str, Any] = dict(meta or {})
    document[list_key] = [dict(record) for record in records]
    target.parent.mkdir(parents=True, exist_ok=True)

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


def append_record(
    path: str | Path,
    record: dict,
    *,
    key: str = "id",
    meta: dict | None = None,
    list_key: str = "records",
) -> dict:
    """Append one record, refusing a duplicate ``key``; returns the stored record."""

    records = load_records(path)
    identifier = str(record.get(key, "")).strip()
    if not identifier:
        raise CatalogueError(f"a record needs a non-empty '{key}'")
    if any(str(existing.get(key, "")).strip() == identifier for existing in records):
        raise CatalogueError(f"'{identifier}' is already in '{Path(path).name}'")
    stored = dict(record)
    stored[key] = identifier
    records.append(stored)
    save_records(path, records, meta=meta, list_key=list_key)
    return stored


def save_catalogue(
    path: str | Path,
    records: Iterable[dict],
    *,
    list_key: str = "records",
) -> Path:
    """Replace a whole catalogue, keeping its ``_meta`` block and record count.

    ``records`` are plain dicts - the ``as_dict()`` view of a record class - so a
    front end can write back the table it just showed without losing provenance.
    """

    target = Path(path)
    payloads = [dict(record) for record in records]
    save_records(
        target,
        payloads,
        meta={"_meta": _meta_for(target, len(payloads))},
        list_key=list_key,
    )
    return target


def _meta_for(target: Path, count: int) -> dict:
    """The ``_meta`` block of a catalogue file, with an updated record count.

    Appending must not drop the provenance block (schema, source, CRS note): a
    plain ``save_records`` call would rewrite the file without it.
    """

    try:
        document = _read(target)
    except CatalogueError:  # a new catalogue has no metadata yet
        document = {}
    meta = document.get("_meta", {})
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta["count"] = int(count)
    return meta


def _append_catalogued(target: Path, record: dict, *, list_key: str) -> dict:
    """Append one record to a catalogue, refusing a duplicate id, keeping ``_meta``."""

    records = load_records(target)
    identifier = str(record.get("id", "")).strip()
    if not identifier:
        raise CatalogueError("a record needs a non-empty 'id'")
    if any(str(existing.get("id", "")).strip() == identifier for existing in records):
        raise CatalogueError(f"'{identifier}' is already in '{target.name}'")
    stored = dict(record)
    stored["id"] = identifier
    records.append(stored)
    save_records(
        target,
        records,
        meta={"_meta": _meta_for(target, len(records))},
        list_key=list_key,
    )
    return stored


# ----------------------------------------------------------------- network links
@dataclass(frozen=True)
class NetworkRecord:
    """One candidate transport link of the network database."""

    id: str
    name: str
    kind: str
    from_node: str
    to_node: str
    x: float
    y: float
    elevation_m: float
    length_km: float
    latitude: float | None = None
    longitude: float | None = None
    elevation_min_m: float | None = None
    elevation_max_m: float | None = None
    notes: str | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}

    def capacity_for(self, mode: str) -> bool:
        """True when this link can carry ``mode`` (pipeline links carry only CO2)."""

        return str(self.kind).lower() == str(mode).lower()


def network_from_dict(payload: dict) -> NetworkRecord:
    """Validate one network entry (the UI and the tests build the same dict)."""

    def number(key: str, default: float | None = None) -> float | None:
        value = payload.get(key)
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise CatalogueError(f"network '{payload.get('id')}': {key} must be a number") from exc

    identifier = str(payload.get("id") or "").strip()
    kind = str(payload.get("kind") or "pipeline").strip().lower()
    kind = NETWORK_KIND_ALIASES.get(kind, kind)
    if not identifier:
        raise CatalogueError("a network record needs an 'id'")
    if kind not in NETWORK_KINDS:
        raise CatalogueError(
            f"network '{identifier}': kind must be one of {', '.join(NETWORK_KINDS)}"
        )
    return NetworkRecord(
        id=identifier,
        name=str(payload.get("name") or identifier),
        kind=kind,
        from_node=str(payload.get("from_node") or ""),
        to_node=str(payload.get("to_node") or ""),
        x=number("x") or 0.0,
        y=number("y") or 0.0,
        elevation_m=number("elevation_m") or 0.0,
        length_km=number("length_km") or 0.0,
        latitude=number("latitude"),
        longitude=number("longitude"),
        elevation_min_m=number("elevation_min_m"),
        elevation_max_m=number("elevation_max_m"),
        notes=(str(payload["notes"]).strip() or None) if payload.get("notes") else None,
    )


def load_network_catalogue(path: str | Path | None = None) -> list[NetworkRecord]:
    """Read the network database (default ``json/network.json``)."""

    return [network_from_dict(record) for record in load_records(path or NETWORK_PATH)]


def append_network(record: NetworkRecord, path: str | Path | None = None) -> NetworkRecord:
    """Add one link to the network database, refusing a duplicate id."""

    target = Path(path) if path is not None else NETWORK_PATH
    _append_catalogued(target, record.as_dict(), list_key="records")
    return record


# ------------------------------------------------------------------ storage sites
@dataclass(frozen=True)
class StorageRecord:
    """One candidate storage site of the storage database."""

    id: str
    name: str
    storage_type: str
    capacity_t: float
    depth_m: float
    porosity: float
    permeability_m2: float
    pressure_bar: float
    temperature_c: float
    thickness_m: float | None = None
    area_km2: float | None = None
    lithology: str | None = None
    fluid: str | None = None
    onshore: bool = True
    notes: str | None = None

    @property
    def capacity_mt(self) -> float:
        return float(self.capacity_t) / 1e6

    def as_dict(self) -> dict:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


def storage_from_dict(payload: dict) -> StorageRecord:
    """Validate one storage entry (the UI and the tests build the same dict)."""

    def number(key: str, default: float | None = None) -> float | None:
        value = payload.get(key)
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise CatalogueError(f"storage '{payload.get('id')}': {key} must be a number") from exc

    identifier = str(payload.get("id") or "").strip()
    storage_type = str(payload.get("storage_type") or "DSA").strip().upper()
    if not identifier:
        raise CatalogueError("a storage record needs an 'id'")
    if storage_type not in STORAGE_TYPES:
        raise CatalogueError(
            f"storage '{identifier}': storage_type must be one of {', '.join(STORAGE_TYPES)}"
        )
    return StorageRecord(
        id=identifier,
        name=str(payload.get("name") or identifier),
        storage_type=storage_type,
        capacity_t=number("capacity_t", 0.0) or 0.0,
        depth_m=number("depth_m", 0.0) or 0.0,
        porosity=number("porosity", 0.2) or 0.0,
        permeability_m2=number("permeability_m2", 1.0e-13) or 0.0,
        pressure_bar=number("pressure_bar", 0.0) or 0.0,
        temperature_c=number("temperature_c", 0.0) or 0.0,
        thickness_m=number("thickness_m"),
        area_km2=number("area_km2"),
        lithology=(str(payload["lithology"]).strip() or None) if payload.get("lithology") else None,
        fluid=(str(payload["fluid"]).strip() or None) if payload.get("fluid") else None,
        onshore=bool(payload.get("onshore", True)),
        notes=(str(payload["notes"]).strip() or None) if payload.get("notes") else None,
    )


def load_storage_catalogue(path: str | Path | None = None) -> list[StorageRecord]:
    """Read the storage database (default ``json/storage.json``)."""

    return [storage_from_dict(record) for record in load_records(path or STORAGE_PATH)]


def append_storage(record: StorageRecord, path: str | Path | None = None) -> StorageRecord:
    """Add one storage site to the storage database, refusing a duplicate id."""

    target = Path(path) if path is not None else STORAGE_PATH
    _append_catalogued(target, record.as_dict(), list_key="records")
    return record


# ------------------------------------------------------------------------- hubs
def _as_list(value) -> list[str]:
    """Accept a list or a comma-separated string of codes (GIS exports use both).

    The GIS hub export groups some storage options in parentheses
    (``"(SP.SU.016, SP.SU.020)"``); the brackets are an artefact of that export and
    are stripped from each code.
    """

    if value is None or value == "":
        return []
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = [str(item) for item in value]
    return [code for code in (item.strip().strip("()[]").strip() for item in items) if code]


@dataclass(frozen=True)
class HubRecord:
    """One candidate hub of the hub database.

    A hub is the vertex that makes the pressure cascade and the modal choice
    explicit: the modes available at the site, the pressure and temperature the
    CO2 is expected to have, the processing that must happen there and the
    storage sites it can feed.
    """

    id: str
    name: str
    kind: str = "hub"
    x: float = 0.0
    y: float = 0.0
    elevation_m: float | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    transport_options: list[str] = field(default_factory=lambda: ["pipeline"])
    expected_pressure_bar: float | None = None
    expected_temperature_c: float | None = None
    processing: list[str] = field(default_factory=list)
    storage_options: list[str] = field(default_factory=list)
    commissioning_year: int | None = None
    notes: str | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


def hub_from_dict(payload: dict) -> HubRecord:
    """Validate one hub entry (the UI and the tests build the same dict)."""

    def number(key: str, default: float | None = None) -> float | None:
        value = payload.get(key)
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise CatalogueError(f"hub '{payload.get('id')}': {key} must be a number") from exc

    identifier = str(payload.get("id") or "").strip()
    if not identifier:
        raise CatalogueError("a hub record needs an 'id'")
    kind = str(payload.get("kind") or "hub").strip().lower()
    if kind not in HUB_KINDS:
        raise CatalogueError(f"hub '{identifier}': kind must be one of {', '.join(HUB_KINDS)}")

    modes = [str(item).strip().lower() for item in _as_list(payload.get("transport_options"))]
    unknown = [mode for mode in modes if mode not in HUB_TRANSPORT_MODES]
    if unknown:
        raise CatalogueError(
            f"hub '{identifier}': transport_options must be one of "
            f"{', '.join(HUB_TRANSPORT_MODES)} (got {', '.join(unknown)})"
        )

    return HubRecord(
        id=identifier,
        name=str(payload.get("name") or identifier),
        kind=kind,
        x=number("x") or 0.0,
        y=number("y") or 0.0,
        elevation_m=number("elevation_m"),
        country=(str(payload["country"]).strip() or None) if payload.get("country") else None,
        latitude=number("latitude"),
        longitude=number("longitude"),
        transport_options=modes or ["pipeline"],
        expected_pressure_bar=number("expected_pressure_bar"),
        expected_temperature_c=number("expected_temperature_c"),
        processing=_as_list(payload.get("processing")),
        storage_options=_as_list(payload.get("storage_options")),
        commissioning_year=(
            None
            if payload.get("commissioning_year") in (None, "")
            else int(number("commissioning_year"))
        ),
        notes=(str(payload["notes"]).strip() or None) if payload.get("notes") else None,
    )


def load_hub_catalogue(path: str | Path | None = None) -> list[HubRecord]:
    """Read the hub database (default ``json/hubs.json``)."""

    return [hub_from_dict(record) for record in load_records(path or HUBS_PATH)]


def append_hub(record: HubRecord, path: str | Path | None = None) -> HubRecord:
    """Add one hub to the hub database, refusing a duplicate id."""

    target = Path(path) if path is not None else HUBS_PATH
    _append_catalogued(target, record.as_dict(), list_key="records")
    return record


__all__ = [
    "CatalogueError",
    "EMITTERS_PATH",
    "HUBS_PATH",
    "HUB_KINDS",
    "HUB_TRANSPORT_MODES",
    "HubRecord",
    "JSON_DIRECTORY",
    "NETWORK_KINDS",
    "NETWORK_KIND_ALIASES",
    "NETWORK_PATH",
    "NetworkRecord",
    "STORAGE_PATH",
    "STORAGE_TYPES",
    "StorageRecord",
    "append_hub",
    "append_network",
    "append_record",
    "append_storage",
    "hub_from_dict",
    "load_hub_catalogue",
    "load_network_catalogue",
    "load_records",
    "load_storage_catalogue",
    "network_from_dict",
    "save_catalogue",
    "save_records",
    "storage_from_dict",
]