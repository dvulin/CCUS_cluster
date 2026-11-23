"""Streamlit presentation layer for the CCUS cluster engine.

The UI is deliberately thin: it imports :mod:`ccus_core` and nothing else from the
project.  All physics, routing and financial logic lives in the engine, so this
module can be replaced (desktop app, Excel add-in, notebook) without touching the
model code.

The configuration tab edits the whole stakeholder set — emitters, their emission
curves, every emitter→sink access and every storage site — through editable
tables, so the UI stays as expressive as the JSON without asking the user to edit
JSON by hand.

Run with::

    streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ccus_core import ScenarioEngine, ScenarioConfig, year_snapshot  # noqa: E402
from ccus_core.io.catalogue import (  # noqa: E402
    HUB_KINDS,
    HUB_TRANSPORT_MODES,
    NETWORK_KINDS,
    STORAGE_TYPES,
)
from ccus_core.io.sqlite_catalogue import HUB_CATEGORIES, MODE_CODES  # noqa: E402

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0
HOURS_PER_YEAR = 8766.0

#: name of the catalogue download, as asked for by the study
DB_BACKUP_NAME = "gt_ccus_db.sqlite"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = REPOSITORY_ROOT / "inputs" / "examples" / "ccus_cluster_v1.json"
DEFAULT_CLUSTER = REPOSITORY_ROOT / "inputs" / "examples" / "cluster_three_emitters.json"

#: Source radio options.  The key is stable (so a language switch or a file change
#: does not reset the session); the *label* is built from the file that is really
#: loaded, because a hard-coded "14 emitters" lies as soon as the file changes.
SOURCE_KEYS = ("cluster", "single", "upload")
SOURCE_PATHS = {"cluster": DEFAULT_CLUSTER, "single": DEFAULT_SCENARIO}

MODE_COLOURS = {
    "pipeline": "#1f77b4",
    "truck": "#ff7f0e",
    "rail": "#2ca02c",
    "marine": "#17becf",
}

MODE_LABELS = {
    "pipeline": "Pipeline",
    "truck": "Truck",
    "rail": "Željeznica",
    "marine": "Marine",
}


# --------------------------------------------------------------------- helpers
def _number(value, default: float = 0.0) -> float:
    if value is None or isinstance(value, str) and not value.strip():
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value, default: int = 0) -> int:
    return int(round(_number(value, float(default))))


def _source_counts(st) -> dict[str, int | None]:
    """Emitter count of each bundled source file (cached per session).

    The count is read from the file itself instead of being written into the label,
    so the radio can never claim 14 emitters while the loaded scenario has 3.
    """

    cached = st.session_state.get("source_counts")
    if cached is None:
        cached = {}
        for key, path in SOURCE_PATHS.items():
            try:
                cached[key] = len(load_scenario(path).emitters)
            except Exception:  # noqa: BLE001 - an unreadable file still gets a label
                cached[key] = None
        st.session_state["source_counts"] = cached
    return cached


def _source_label(st, t: dict, key: str) -> str:
    """Truthful radio label for one source option."""

    if key == "upload":
        return t["source_upload"]
    template = t["source_cluster"] if key == "cluster" else t["source_single"]
    count = _source_counts(st).get(key)
    return template.format(count="?" if count is None else int(count))


def _optional_year(value, default: int):
    """Return an int for a year cell, or ``None`` when the cell is empty."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none"}:
        return None
    return int(round(float(value)))


def _optional_year_or(value, fallback):
    """Year cell with a fallback: an empty cell keeps the base value.

    The tables do not show every year field, so a blank cell must not be read as
    "delete this year" - that would silently drop a monitoring window on Apply.
    """

    if value is None:
        return fallback
    if isinstance(value, float) and math.isnan(value):
        return fallback
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none"}:
        return fallback
    return int(round(float(value)))


def _text(value, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    return text or default


def _optional_number(value):
    """Number cell with a blank/NaN reading as ``None`` (not as a real zero)."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none"}:
        return None
    return _number(value, 0.0)


# --------------------------------------------------------------------- data
def load_scenario(payload: bytes | str | Path):
    """Validate a JSON scenario from a path, a string or an uploaded file."""

    from ccus_core.io import commented_json

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, (str, Path)) and not str(payload).lstrip().startswith("{"):
        payload = Path(payload).read_text(encoding="utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    return commented_json.from_payload(payload)


def apply_overrides(scenario: ScenarioConfig, overrides: dict) -> ScenarioConfig:
    """Return a copy of ``scenario`` with simple scalar overrides applied."""

    payload = scenario.model_dump()
    for emitter in payload["emitters"]:
        activation_override = overrides.get("activation_year", {}).get(emitter["id"])
        if activation_override is not None:
            emitter["activation_year"] = int(activation_override)
            capture = emitter.get("capture")
            if capture is not None and capture["commissioning_year"] < emitter["activation_year"]:
                capture["commissioning_year"] = emitter["activation_year"]

        if emitter["id"] in overrides.get("emission_t_per_year", {}):
            value = float(overrides["emission_t_per_year"][emitter["id"]])
            profile = emitter["gross_emissions"]
            kind = profile.get("kind")
            if kind == "constant":
                profile["constant_t_per_year"] = value
            elif kind == "power_law":
                profile["e0_t_per_year"] = value
            elif kind == "piecewise_linear" and profile.get("points"):
                profile["points"] = {int(year): value for year in profile["points"]}
            else:
                profile["kind"] = "constant"
                profile["constant_t_per_year"] = value
                profile.pop("points", None)

    if "discount_rate" in overrides and payload.get("economics"):
        payload["economics"]["discount_rate"] = float(overrides["discount_rate"])
    if "end_year" in overrides:
        payload["end_year"] = int(overrides["end_year"])
        if payload.get("economics"):
            payload["economics"]["end_year"] = max(
                int(payload["economics"]["start_year"]), int(overrides["end_year"])
            )

    upgrade_year = overrides.get("upgrade_year", {})
    upgrade_threshold = overrides.get("upgrade_threshold", {})
    for edge in payload.get("edges", []):
        for upgrade in edge.get("upgrades", []):
            if upgrade["id"] in upgrade_year:
                upgrade["trigger"]["year"] = int(upgrade_year[upgrade["id"]])
                if upgrade["trigger"]["kind"] == "cumulative_mass":
                    upgrade["trigger"]["kind"] = "both"
            if upgrade["id"] in upgrade_threshold:
                threshold = float(upgrade_threshold[upgrade["id"]])
                upgrade["trigger"]["threshold_t"] = threshold
                if threshold > 0.0 and upgrade["trigger"]["kind"] == "year":
                    upgrade["trigger"]["kind"] = "both"
    return ScenarioConfig.model_validate(payload)


# --------------------------------------------------------------------- frames
EMITTER_COLUMNS = [
    "id",
    "name",
    "activation_year",
    "implementation_probability",
    "curve",
    "e0_t_per_year",
    "a",
    "c",
    "constant_t_per_year",
    "capture_capacity_t_per_year",
    "capture_capex_eur",
    "capture_opex_eur_per_t",
]

ROUTE_COLUMNS = [
    "sel",
    "id",
    "name",
    "from_node",
    "to_node",
    "mode",
    "distance_km",
    "total_distance_km",
    "capacity_t_per_year",
    "capex_eur",
    "opex_eur_per_t",
    "opex_eur_per_tkm",
    "valid_from_year",
]

#: the "who exists" table at the top of the Scenario tab; ``map`` is the per-row
#: tick that decides whether the hub is drawn, ``links`` is derived
SCENARIO_NODE_COLUMNS = ["map", "id", "name", "kind", "latitude", "longitude", "links"]

#: the node kinds a scenario row may have (the model's ``NodeKind``)
NODE_KINDS = (
    "emitter",
    "junction",
    "hub",
    "port",
    "storage",
    "geothermal",
    "offshore_terminal",
)

#: emitter -> route edge -> sink; ``sel`` is the leading tick that selects rows,
#: exactly like the links grid.  ``route_edge_id`` is the **first leg** the emitter
#: uses, so a connection that runs over a chain still points at one link.
CONNECTION_COLUMNS = [
    "sel",
    "emitter_id",
    "route_edge_id",
    "sink_id",
    "start_year",
]

SINK_COLUMNS = [
    "id",
    "name",
    "type",
    "geothermal_coupled",
    "geothermal_start_year",
    "capacity_t",
    "depth_m",
    "porosity",
    "permeability_m2",
    "commissioning_year",
    "capex_eur",
    "opex_eur_per_t",
    "monitoring_cost_during_injection_eur_per_year",
    "monitoring_cost_after_injection_eur_per_year",
    "monitoring_end_year",
]

#: columns of the editable emitter catalogue (Database section); ``emissions`` is
#: the constant rate the user types (derived for the other curve families)
DATABASE_COLUMNS = [
    "id",
    "slug",
    "name",
    "industry",
    "curve",
    "reference_year",
    "e0_t_per_year",
    "a",
    "c",
    "points",
    "activation_year",
    "implementation_probability",
    "hub",
    "emissions",
]

#: columns of the editable hub catalogue (Database section)
HUB_COLUMNS = [
    "id",
    "name",
    "category",
    "country",
    "x",
    "y",
    "elevation_m",
]

#: columns of the editable link catalogue; ``length_km`` is derived from the hubs
NETWORK_COLUMNS = [
    "id",
    "source_hub",
    "destination_hub",
    "mode",
    "length_km",
    "pipeline",
    "capex_eur",
    "opex_eur_per_t",
]

#: columns of the pipeline designs a pipeline link can reference
PIPELINE_COLUMNS = [
    "id",
    "name",
    "diameter_m",
    "wall_thickness_m",
    "roughness_m",
    "material",
    "design_pressure_bar",
    "design_temperature_c",
]

#: columns of the editable storage catalogue (Database section)
STORAGE_COLUMNS = [
    "id",
    "slug",
    "name",
    "hub",
    "storage_type",
    "capacity_mt",
    "depth_m",
    "porosity",
    "permeability_m2",
    "pressure_bar",
    "temperature_c",
    "lithology",
    "well_diameter_m",
    "well_number",
]

#: accepted emitter ids (same pattern as ``ccus_core.models.base.Slug``)
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

GEOTHERMAL_COLUMNS = [
    "id",
    "name",
    "sink_id",
    "d_doublet_m",
    "reservoir_temperature_c",
    "eta_orc",
    "p_out_bar",
    "t_out_c",
    "operation_start_year",
    "operation_end_year",
    "capex_eur",
    "fixed_opex_eur_per_year",
]


def _name_normaliser(st):
    """Build the scenario-name callback, closing over the ``st`` of the running app.

    Widget callbacks run outside :func:`main`, so they cannot see a module-level
    ``st`` - and the module deliberately has none, so that importing it stays cheap.
    """

    def _normalise() -> None:
        value = str(st.session_state.get("scenario_name", "")).strip()
        if value.lower().endswith(".json"):
            value = value[: -len(".json")].strip()
        st.session_state["scenario_name"] = value

    return _normalise


def _pop_flash(st) -> None:
    """Show the message left by the previous run (st.rerun drops st.success)."""

    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    kind = str(flash.get("kind", "info"))
    text = str(flash.get("text", ""))
    getattr(st, kind if kind in {"success", "info", "warning", "error"} else "info")(text)


def _display_year(st, scenario: ScenarioConfig) -> int:
    """Year the Database section reports emissions for.

    The timeline slider lives further down the page, but its value is kept in
    ``session_state`` under the widget key, so it can be read here - at the top of
    the page - and clamped to the scenario horizon.  ``st`` is passed in because
    the module imports Streamlit inside :func:`main` only.
    """

    fallback = int(scenario.start_year)
    value = st.session_state.get("timeline_year")
    if value is None:
        return fallback
    return min(max(int(value), int(scenario.start_year)), int(scenario.end_year))


def _split_list(value) -> list[str]:
    """Split a comma-separated cell into a clean list of codes."""

    return [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]


def _points_text(points) -> str:
    """Control points as the 'year: value' text of a table cell."""

    if not points:
        return ""
    return ", ".join(f"{int(year)}: {float(value):g}" for year, value in sorted(points.items()))


def _catalogue_connection():
    """Open the SQLite catalogue, creating it from the JSON snapshot when new."""

    from ccus_core.io.sqlite_catalogue import ensure_database

    return ensure_database()


def _read_catalogue(table: str) -> list[dict]:
    """Read one catalogue table (emitters, hubs, links or storage)."""

    from ccus_core.io import sqlite_catalogue as store

    connection = _catalogue_connection()
    try:
        return getattr(store, f"load_{table}")(connection)
    finally:
        connection.close()


def _hub_names(category: str | None = None) -> dict[int, str]:
    """Hub id -> name, optionally only for one category."""

    return {
        row["id"]: row["name"]
        for row in _read_catalogue("hubs")
        if category is None or row["category"] == category
    }


def _emitter_record_from_db_row(row: dict):
    """Rebuild an :class:`EmitterRecord` from a database row (for the curve value)."""

    from ccus_core.io import record_from_payload

    kind = row.get("curve")
    curve: dict = {"kind": kind}
    if kind == "power_law":
        curve.update(
            reference_year=row.get("reference_year"),
            e0_t_per_year=row.get("e0_t_per_year"),
            a=row.get("a"),
            c=row.get("c"),
        )
    elif kind == "piecewise_linear":
        curve["points"] = _parse_points(row.get("points"))
    else:
        curve["constant_t_per_year"] = row.get("constant_t_per_year")
    return record_from_payload(
        {
            "id": row.get("slug"),
            "name": row.get("name"),
            "industry": row.get("industry"),
            "curve": curve,
            "implementation_probability": row.get("implementation_probability"),
            "activation_year": row.get("activation_year"),
            "reference_sink_id": row.get("reference_sink_id"),
        }
    )


def emitter_database_rows(scenario: ScenarioConfig, year: int, records=None) -> list[dict]:
    """Rows of the Database section: every catalogue emitter with its data.

    ``records`` defaults to the SQLite catalogue; a caller can pass its own list
    (tests, a future Excel import) without touching the UI code.
    """

    if records is None:
        records = _read_catalogue("emitters")

    hub_names = _hub_names()
    rows: list[dict] = []
    for record in records:
        try:
            emissions = round(float(_emitter_record_from_db_row(record).emissions_in(int(year))), 0)
        except Exception:  # noqa: BLE001 - a half-typed curve must not break the table
            emissions = None
        rows.append(
            {
                "id": record.get("id"),
                "slug": record.get("slug"),
                "name": record.get("name"),
                "industry": record.get("industry"),
                "curve": record.get("curve"),
                "reference_year": record.get("reference_year"),
                "e0_t_per_year": record.get("e0_t_per_year"),
                "a": record.get("a"),
                "c": record.get("c"),
                "points": record.get("points"),
                "activation_year": record.get("activation_year"),
                "implementation_probability": record.get("implementation_probability"),
                "hub": hub_names.get(record.get("hub_id")),
                "emissions": emissions,
            }
        )
    return rows


def hub_database_rows(records=None) -> list[dict]:
    """Rows of the Database section: every candidate hub."""

    if records is None:
        records = _read_catalogue("hubs")

    rows: list[dict] = []
    for record in records:
        rows.append(
            {
                "id": record.get("id"),
                "name": record.get("name"),
                "category": record.get("category"),
                "country": record.get("country"),
                "x": round(float(record.get("x") or 0.0), 1),
                "y": round(float(record.get("y") or 0.0), 1),
                "elevation_m": record.get("elevation_m"),
            }
        )
    return rows


def pipeline_database_rows(records=None) -> list[dict]:
    """Rows of the Database section: the pipeline designs."""

    if records is None:
        records = _read_catalogue("pipelines")

    return [
        {
            "id": record.get("id"),
            "name": record.get("name"),
            "diameter_m": float(record.get("diameter_m") or 0.30),
            "wall_thickness_m": record.get("wall_thickness_m"),
            "roughness_m": float(record.get("roughness_m") or 0.0),
            "material": record.get("material"),
            "design_pressure_bar": record.get("design_pressure_bar"),
            "design_temperature_c": record.get("design_temperature_c"),
        }
        for record in records
    ]


def network_database_rows(records=None) -> list[dict]:
    """Rows of the Database section: every candidate transport link.

    A link is defined by the two hubs it connects; its length is derived from the
    hub coordinates and is therefore read-only.
    """

    if records is None:
        records = _read_catalogue("links")

    hub_names = _hub_names()
    pipeline_names = {row["id"]: row["name"] for row in _read_catalogue("pipelines")}
    rows: list[dict] = []
    for record in records:
        rows.append(
            {
                "id": record.get("id"),
                "source_hub": hub_names.get(record.get("source_hub_id")),
                "destination_hub": hub_names.get(record.get("destination_hub_id")),
                "mode": record.get("mode"),
                "length_km": record.get("length_km"),
                "pipeline": pipeline_names.get(record.get("pipeline_id")),
                "capex_eur": record.get("capex_eur"),
                "opex_eur_per_t": record.get("opex_eur_per_t"),
            }
        )
    return rows


def storage_database_rows(records=None) -> list[dict]:
    """Rows of the Database section: every candidate storage site.

    The capacity is shown in Mt (the database stores tonnes) because the tables of
    a national screening study are written in million tonnes.
    """

    if records is None:
        records = _read_catalogue("storage")

    hub_names = _hub_names()
    rows: list[dict] = []
    for record in records:
        rows.append(
            {
                "id": record.get("id"),
                "slug": record.get("slug"),
                "name": record.get("name"),
                "hub": hub_names.get(record.get("hub_id")),
                "storage_type": record.get("storage_type"),
                "capacity_mt": round(float(record.get("capacity_t") or 0.0) / 1e6, 6),
                "depth_m": round(float(record.get("depth_m") or 0.0), 1),
                "porosity": round(float(record.get("porosity") or 0.0), 4),
                "permeability_m2": float(record.get("permeability_m2") or 0.0),
                "pressure_bar": round(float(record.get("pressure_bar") or 0.0), 2),
                "temperature_c": round(float(record.get("temperature_c") or 0.0), 2),
                "lithology": record.get("lithology"),
                "well_diameter_m": float(record.get("well_diameter_m") or 0.30),
                "well_number": int(record.get("well_number") or 1),
            }
        )
    return rows


def _parse_points(value) -> dict[int, float]:
    """Parse the 'year: t/yr' control points of the emitter table."""

    points: dict[int, float] = {}
    for chunk in str(value or "").replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        year, separator, emissions = chunk.partition(":")
        if not separator:
            raise ValueError(f"'{chunk}' is not a 'year: value' control point")
        try:
            point_year = int(year.strip())
            point_value = float(emissions.strip())
        except ValueError as exc:
            raise ValueError(f"'{chunk}' is not a 'year: value' control point") from exc
        if point_year in points:
            raise ValueError(f"control-point year {point_year} appears twice")
        points[point_year] = point_value
    if not points:
        raise ValueError("a piecewise linear curve needs at least one 'year: value' pair")
    return points


def _optional_int(value):
    """Integer cell with a blank/NaN reading as ``None``."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "<na>"}:
        return None
    return int(round(float(value)))


def emitter_record_from_row(values: dict):
    """Build the database row of one emitter from the Database table.

    Raises ``ValueError`` (with a user-facing message) for an unusable row.
    """

    identifier = _text(values.get("id"))
    name = _text(values.get("name"))
    if not name:
        raise ValueError("the emitter name is required")

    kind = _text(values.get("curve"), "constant")
    curve: dict = {"kind": kind}
    if kind == "power_law":
        curve.update(
            reference_year=_optional_int(values.get("reference_year")),
            e0_t_per_year=_number(values.get("e0_t_per_year"), 0.0),
            a=_number(values.get("a"), 0.0),
            c=_number(values.get("c"), 1.5),
        )
    elif kind == "piecewise_linear":
        curve["points"] = _parse_points(values.get("points"))
    else:
        # the emissions column is the constant rate the user types
        curve["constant_t_per_year"] = _number(values.get("emissions"), 0.0)

    from ccus_core.models import EmissionCurve

    EmissionCurve.model_validate(curve)  # raises with the field that is wrong

    return {
        "id": _optional_int(values.get("id")),
        "slug": _text(values.get("slug")),
        "name": name,
        "industry": _text(values.get("industry")) or None,
        "curve": kind,
        "reference_year": curve.get("reference_year"),
        "e0_t_per_year": curve.get("e0_t_per_year"),
        "a": curve.get("a"),
        "c": curve.get("c"),
        "constant_t_per_year": curve.get("constant_t_per_year"),
        "points": _points_text(curve.get("points")) or None,
        "activation_year": _optional_int(values.get("activation_year")),
        "implementation_probability": _optional_number(values.get("implementation_probability")),
        "hub": _text(values.get("hub")) or None,
    }


def hub_record_from_row(values: dict):
    """Build the database row of one hub from the Database table."""

    name = _text(values.get("name"))
    if not name:
        raise ValueError("the hub name is required")
    category = _text(values.get("category"), "chain")
    if category not in HUB_CATEGORIES:
        raise ValueError(
            f"hub '{name}': the category must be one of {', '.join(HUB_CATEGORIES)}"
        )

    return {
        "id": _optional_int(values.get("id")),
        "name": name,
        "category": category,
        "country": _text(values.get("country")) or None,
        "x": _number(values.get("x"), 0.0),
        "y": _number(values.get("y"), 0.0),
        "elevation_m": _optional_number(values.get("elevation_m")),
    }


def network_record_from_row(values: dict):
    """Build the database row of one link from the Database table."""

    source = _text(values.get("source_hub"))
    destination = _text(values.get("destination_hub"))
    if not source or not destination:
        raise ValueError("a link needs a source and a destination hub")
    if source == destination:
        raise ValueError("a link cannot start and end at the same hub")
    mode = _text(values.get("mode"))
    if mode not in MODE_CODES:
        raise ValueError(f"unknown transport mode '{mode}'")

    return {
        "id": _optional_int(values.get("id")),
        "source_hub": source,
        "destination_hub": destination,
        "mode": mode,
        "pipeline": _text(values.get("pipeline")) or None,
        "capex_eur": _number(values.get("capex_eur"), 0.0),
        "opex_eur_per_t": _number(values.get("opex_eur_per_t"), 0.0),
    }


def pipeline_record_from_row(values: dict):
    """Build the database row of one pipeline design from the Database table."""

    name = _text(values.get("name"))
    if not name:
        raise ValueError("the pipeline design name is required")
    diameter = _number(values.get("diameter_m"), 0.30)
    if diameter <= 0.0:
        raise ValueError(f"pipeline '{name}': the diameter must be positive")
    roughness = _number(values.get("roughness_m"), 0.0)
    if roughness < 0.0:
        raise ValueError(f"pipeline '{name}': the roughness must not be negative")

    return {
        "id": _optional_int(values.get("id")),
        "name": name,
        "diameter_m": diameter,
        "wall_thickness_m": _optional_number(values.get("wall_thickness_m")),
        "roughness_m": roughness,
        "material": _text(values.get("material")) or None,
        "design_pressure_bar": _optional_number(values.get("design_pressure_bar")),
        "design_temperature_c": _optional_number(values.get("design_temperature_c")),
    }


def storage_record_from_row(values: dict):
    """Build the database row of one storage site from the Database table."""

    name = _text(values.get("name"))
    if not name:
        raise ValueError("the storage site name is required")
    storage_type = _text(values.get("storage_type"), "DSA")
    if storage_type not in STORAGE_TYPES:
        raise ValueError(f"storage '{name}': unknown type '{storage_type}'")
    wells = _optional_int(values.get("well_number")) or 1
    diameter = _optional_number(values.get("well_diameter_m")) or 0.30
    if wells < 1:
        raise ValueError(f"storage '{name}': the well number must be at least 1")
    if diameter <= 0.0:
        raise ValueError(f"storage '{name}': the well diameter must be positive")

    return {
        "id": _optional_int(values.get("id")),
        "slug": _text(values.get("slug")),
        "name": name,
        "hub": _text(values.get("hub")) or None,
        "storage_type": storage_type,
        "capacity_mt": _number(values.get("capacity_mt"), 0.0),
        "depth_m": _number(values.get("depth_m"), 0.0),
        "porosity": _number(values.get("porosity"), 0.0),
        "permeability_m2": _number(values.get("permeability_m2"), 0.0),
        "pressure_bar": _number(values.get("pressure_bar"), 0.0),
        "temperature_c": _number(values.get("temperature_c"), 0.0),
        "lithology": _text(values.get("lithology")) or None,
        "well_diameter_m": diameter,
        "well_number": wells,
    }


def _is_blank(row) -> bool:
    """True when every cell of a table row is empty (a freshly added row)."""

    for value in row.values():
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        if str(value).strip():
            return False
    return True


def _database_table(
    st,
    t: dict,
    *,
    title_key: str,
    failed_key: str,
    columns,
    labels: dict,
    loader,
    key: str,
    alt: str,
    select: dict | None = None,
    text: set[str] | None = None,
    disabled=(),
):
    """Render one editable catalogue table and return its edited frame.

    ``st.data_editor`` with ``num_rows="dynamic"`` gives the table its ``+`` row,
    the row menu and the spreadsheet paste/copy behaviour.  The ``id`` column is
    hidden: it is the database key, never something the user types.
    """

    st.markdown(f"### {t[title_key]}")
    try:
        rows = loader()
    except Exception as exc:  # noqa: BLE001 - a broken catalogue must not kill the app
        st.error(t[failed_key].format(error=exc))
        return None

    config = _column_config(
        st,
        labels,
        columns,
        number=True,
        text=set(text or ()),
        select=select or {},
    )
    config["id"] = None  # the database key stays out of the grid

    return st.data_editor(
        pd.DataFrame(rows, columns=columns),
        key=key,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        disabled=list(disabled),
        column_config=config,
        alt=alt,
    )


def _normalised(value):
    """Comparable view of a cell (NaN, blank and None are the same)."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "<na>"}:
        return None
    if isinstance(value, float):
        return round(value, 6)
    return value


def _same_rows(before: list[dict], after: list[dict]) -> bool:
    """True when an edited table still holds exactly what the database holds."""

    if len(before) != len(after):
        return False
    for old, new in zip(before, after):
        if _normalised(old.get("id")) != _normalised(new.get("id")):
            return False
        # ``length_km`` is derived from the hubs and ``emissions`` from the curve:
        # neither is ever typed into the grid
        for column in set(old) | set(new):
            if column in {"id", "length_km", "emissions"}:
                continue
            if _normalised(old.get(column)) != _normalised(new.get(column)):
                return False
    return True


def _save_database(st, t: dict, frames: dict, loaders: dict) -> None:
    """Validate the edited tables and write the database and its JSON snapshot."""

    from ccus_core.io import sqlite_catalogue as store

    steps = (
        ("hubs", store.save_hubs, hub_record_from_row),
        ("pipelines", store.save_pipelines, pipeline_record_from_row),
        ("links", store.save_links, network_record_from_row),
        ("emitters", store.save_emitters, emitter_record_from_row),
        ("storage", store.save_storage, storage_record_from_row),
    )
    problems: list[str] = []
    updated: dict[str, list[dict]] = {}
    before: dict[str, list[dict]] = {}

    connection = _catalogue_connection()
    try:
        for name, save, build in steps:
            rows = []
            frame = frames.get(name)
            for number, row in enumerate(
                [] if frame is None else frame.to_dict("records"), start=2
            ):
                if _is_blank(row):
                    continue
                try:
                    rows.append(build(row))
                except Exception as exc:  # noqa: BLE001 - one bad row must not hide the others
                    problems.append(f"{name}.json, {t['db_row']} {number}: {exc}")
            updated[name] = rows
            before[name] = loaders[name]()

        if problems:
            st.error(t["db_save_failed"].format(error="; ".join(problems)))
            return

        changed = [name for name, _, _ in steps if not _same_rows(before[name], updated[name])]
        if not changed:
            st.info(t["db_no_changes"])
            return

        for name, save, _ in steps:
            save(connection, updated[name])
        store.export_snapshot(connection)
    except Exception as exc:  # noqa: BLE001 - reported to the user, never fatal
        st.error(t["db_save_failed"].format(error=exc))
        return
    finally:
        connection.close()

    st.session_state["flash"] = {
        "kind": "success",
        "text": t["db_saved"].format(changes=", ".join(f"{name}.json" for name in changed)),
    }
    st.rerun()


def _node_rows(scenario: ScenarioConfig, routes, hidden=()) -> list[dict]:
    """Essential columns of the scenario's hubs, with their degree.

    This is the "who exists" table: a link may only join two ids that appear here.
    ``map`` is the per-row tick that decides whether the hub is drawn; ``links`` is
    derived and never typed.
    """

    degree: dict[str, int] = {}
    for row in routes.to_dict("records"):
        if _is_blank(row):
            continue
        for key in ("from_node", "to_node"):
            node = _text(row.get(key))
            if node:
                degree[node] = degree.get(node, 0) + 1

    hidden = set(hidden or ())
    rows: list[dict] = []
    for node in scenario.nodes:
        placed = node.location.latitude is not None and node.location.longitude is not None
        rows.append(
            {
                # a hub without coordinates cannot be drawn or linked: the tick is
                # forced off and the grid shows why
                "map": bool(placed) and node.id not in hidden,
                "id": node.id,
                "name": node.name,
                "kind": node.kind.value,
                "latitude": node.location.latitude,
                "longitude": node.location.longitude,
                "links": degree.get(node.id, 0),
            }
        )
    return rows


def _filter_rows(rows: list[dict], column: str, query: str) -> list[dict]:
    """Rows whose ``column`` contains ``query`` (case-insensitive).

    An empty query, an unknown column or a blank cell never hides a row: a filter
    must not be able to delete data.
    """

    needle = str(query or "").strip().lower()
    if not needle or column not in (rows[0] if rows else {}):
        return list(rows)
    return [row for row in rows if needle in _text(row.get(column)).lower()]


def _merge_filtered(full, shown, edited):
    """Rebuild the full frame from an editor that only showed ``shown`` rows.

    Rows hidden by the filter keep what they had, a row the editor dropped is gone,
    and a row the editor added (no id, or a new id) is new.  Without this a filter
    would look like a mass deletion of everything it hid.
    """

    edited_rows = [dict(row) for row in edited.to_dict("records")]
    shown_ids = {_text(row.get("id")) for row in shown.to_dict("records")}
    full_ids = {_text(row.get("id")) for row in full.to_dict("records")}

    by_id: dict[str, dict] = {}
    added: list[dict] = []
    for row in edited_rows:
        key = _text(row.get("id"))
        if key and key in full_ids:
            by_id[key] = row
        else:
            added.append(row)

    merged: list[dict] = []
    for row in full.to_dict("records"):
        key = _text(row.get("id"))
        if key not in shown_ids:
            merged.append(dict(row))  # hidden by the filter: untouched
        elif key in by_id:
            merged.append(by_id[key])  # edited, or still exactly as it was
        # a shown row that vanished from the editor was deleted on purpose
    merged.extend(added)
    return merged


def _hub_options(scenario: ScenarioConfig, routes) -> list[str]:
    """Node ids a link may start or end at - hubs that can be placed on the map.

    A hub without coordinates is not offered: it cannot be drawn, so it cannot be
    the end of a link either.  Ids already used by a route are kept, so opening the
    table never invalidates a stored value.
    """

    from streamlit_app.map_layers import hub_coordinates

    placed = set(hub_coordinates(scenario))
    ids = {node.id for node in scenario.nodes if node.id in placed}
    for row in routes.to_dict("records"):
        if _is_blank(row):
            continue
        for key in ("from_node", "to_node"):
            value = _text(row.get(key))
            if value:
                ids.add(value)
    return sorted(ids)


def _picked_hub(state) -> str | None:
    """The node id of the hub the user clicked, or ``None``.

    ``st.pydeck_chart`` returns ``{"selection": {"objects": {<layer id>: [row, ...]}}}``;
    the hub layer carries the node id in its data, so a click maps back directly.
    """

    if not state:
        return None
    try:
        selection = state.get("selection") or {}
        for hits in (selection.get("objects") or {}).values():
            for item in hits or []:
                if isinstance(item, dict) and item.get("id"):
                    return str(item["id"])
    except AttributeError:  # pragma: no cover - a different state shape
        return None
    return None


def _frames_equal(left, right) -> bool:
    """True when two lists of row dicts hold the same values (NaN == blank)."""

    if len(left) != len(right):
        return False
    for first, second in zip(left, right):
        for key in set(first) | set(second):
            if _normalised(first.get(key)) != _normalised(second.get(key)):
                return False
    return True


def _finish_edit(st, key: str, changed: bool) -> None:
    """Drop the editor's widget state and rerun when an edit changed the frame.

    A ``st.data_editor`` keeps its own widget state, so the grid would otherwise
    show the *old* values until the next interaction - which is what made a checkbox
    need two clicks.  Dropping the key makes the rerun rebuild the grid from the
    frame that was just stored.
    """

    if not changed:
        return
    st.session_state.pop(key, None)
    st.rerun()


def _set_column(frame, column: str, value: bool) -> None:
    """Tick or untick a whole checkbox column, in place."""

    frame[column] = bool(value)


def _toggle_all(
    st, t: dict, frame, column: str, editor_key: str, check_key: str, uncheck_key: str
) -> None:
    """Two compact buttons that tick or untick a whole checkbox column.

    Render them inside the table's toolbar: ticking forty rows one by one is not a
    plan, and the grid's own header has no select-all.
    """

    if st.button(t["check_all"], key=check_key):
        _set_column(frame, column, True)
        st.session_state.pop(editor_key, None)
        st.rerun()
    if st.button(t["uncheck_all"], key=uncheck_key):
        _set_column(frame, column, False)
        st.session_state.pop(editor_key, None)
        st.rerun()


def _force_ticks(rows):
    """No coordinates, no tick - a hub that cannot be drawn cannot be shown.

    Applied after every edit, so however a box was left the invariant holds.
    """

    return [
        {
            **row,
            "map": bool(row.get("map"))
            and _optional_float(row.get("latitude")) is not None
            and _optional_float(row.get("longitude")) is not None,
        }
        for row in rows
    ]


def _render_hub_table(st, t: dict, scenario: ScenarioConfig, frames: dict) -> set[str]:
    """The hubs at the top: editable, filterable, and in sync with the map.

    Returns the ids that are ticked off and must not be drawn.
    """

    st.markdown(f"#### {t['sec_hubs']}")
    st.caption(t["hubs_help"])

    from streamlit_app.map_layers import hub_coordinates

    placed = hub_coordinates(scenario)
    without = [node.id for node in scenario.nodes if node.id not in placed]
    if without:
        st.warning(
            t["hubs_no_map"].format(count=len(without), hubs=", ".join(sorted(without)))
        )
        st.caption(t["hubs_no_map_hint"])

    routes = frames["routes"]
    # The editor is fed from `frames["nodes"]`, never rebuilt from the scenario:
    # a tick has to survive the rerun it triggers, or every box needs two clicks.
    full = frames.get("nodes")
    if full is None:
        full = pd.DataFrame(
            _node_rows(scenario, routes, st.session_state.get("hidden_hubs") or ()),
            columns=SCENARIO_NODE_COLUMNS,
        )

    # one filter on any column; the editor still receives the full frame, and the
    # merge puts back what the filter hid.  Everything sits on one toolbar row.
    with st.container(horizontal=True, vertical_alignment="center"):
        column = st.selectbox(
            t["hubs_filter_column"],
            SCENARIO_NODE_COLUMNS,
            key="hubs_filter_column",
            label_visibility="collapsed",
        )
        query = st.text_input(
            t["hubs_filter_query"],
            key="hubs_filter_query",
            placeholder=t["hubs_filter_hint"],
            label_visibility="collapsed",
        )
        _toggle_all(
            st, t, full, "map", "editor_nodes", "hubs_check_all", "hubs_uncheck_all"
        )

    shown = pd.DataFrame(_filter_rows(full.to_dict("records"), column, query),
                         columns=SCENARIO_NODE_COLUMNS)
    edited = st.data_editor(
        shown,
        key="editor_nodes",
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        disabled=["links"],
        column_config=_column_config(
            st,
            t["col_scenario_hubs"],
            SCENARIO_NODE_COLUMNS,
            number=False,
            text={"id", "name"},
            select={"kind": list(NODE_KINDS)},
            checkbox={"map"},
        ),
        alt="Scenario hubs",
    )

    merged = _force_ticks(_merge_filtered(full, shown, edited))
    frames["nodes"] = pd.DataFrame(merged, columns=SCENARIO_NODE_COLUMNS)
    _finish_edit(
        st,
        "editor_nodes",
        not _frames_equal(merged, full.to_dict("records")),
    )
    return {
        _text(row.get("id"))
        for row in merged
        if not bool(row.get("map")) and _text(row.get("id"))
    }


def _render_link_builder(st, t: dict, scenario: ScenarioConfig, frames: dict) -> None:
    """Draw a link by clicking two hubs on the map.

    Streamlit runs the script once per click: the first click stores the inlet, the
    second creates the row.  Chaining (A-B, then B-C) is left to the router, which
    already finds a path across several edges.
    """

    import pandas as pd

    from streamlit_app.map_layers import build_hub_map, hub_coordinates

    st.markdown(f"#### {t['sec_link_builder']}")

    coordinates = hub_coordinates(scenario)
    step = st.session_state.get("link_step")
    inlet = st.session_state.get("link_inlet")

    # one toolbar row: the mode, then the one action that applies
    with st.container(horizontal=True, vertical_alignment="bottom"):
        mode = st.selectbox(t["link_mode"], list(MODE_CODES), key="link_mode")
        follow = st.toggle(
            t["map_follow_roads"],
            value=True,
            key="map_follow_roads",
            help=t["map_follow_roads_help"],
        )
        reference = st.toggle(
            t["map_show_reference"],
            value=False,
            key="map_show_reference",
            help=t["map_show_reference_help"],
        )
        if step is None:
            if st.button(
                t["btn_new_link"],
                key="btn_new_link",
                icon=":material/add_link:",
                disabled=not coordinates,
            ):
                st.session_state["link_step"] = "inlet"
                st.session_state.pop("link_inlet", None)
                st.session_state.pop("hub_pick", None)
                st.rerun()
        elif st.button(t["btn_cancel_link"], key="btn_cancel_link"):
            st.session_state.pop("link_step", None)
            st.session_state.pop("link_inlet", None)
            st.session_state.pop("hub_pick", None)
            st.rerun()

    if not coordinates:
        st.info(t["map_unavailable"], icon=":material/map:")
        return

    # the instruction is the point of the section: say exactly what to do next
    if step == "inlet":
        st.info(t["link_pick_inlet"], icon=":material/pan_tool_alt:")
    elif step == "outlet":
        st.info(
            t["link_pick_outlet"].format(hub=inlet),
            icon=":material/touch_app:",
        )

    deck = build_hub_map(
        scenario,
        inlet=inlet if step == "outlet" else None,
        routes=frames["routes"].to_dict("records"),
        hidden=st.session_state.get("hidden_hubs") or (),
        road=follow,
        context=reference,
        focus=st.session_state.get("map_focus"),
    )
    state = st.pydeck_chart(
        deck,
        on_select="rerun",
        selection_mode="single-object",
        key="hub_pick",
        height=420,
        width="stretch",
    )
    st.caption(t["map_legend"])

    if st.session_state.get("map_focus"):
        if st.button(t["map_show_all"], key="map_show_all"):
            st.session_state.pop("map_focus", None)
            st.rerun()

    # a link whose endpoint has no coordinates cannot be drawn at all: say so here,
    # next to the map, not only in the hubs section
    drawn = {
        (str(row.get("from_node") or ""), str(row.get("to_node") or ""))
        for row in frames["routes"].to_dict("records")
        if row.get("on", True) is not False
    }
    placed = set(coordinates)
    undrawn = sorted(
        f"{start} \u2192 {end}"
        for start, end in drawn
        if start not in placed or end not in placed
    )
    if undrawn:
        st.caption(t["map_undrawn"].format(links=", ".join(undrawn)))

    if step is None:
        return

    picked = _picked_hub(state)
    if not picked:
        return

    if step == "inlet":
        st.session_state["link_inlet"] = picked
        st.session_state["link_step"] = "outlet"
        st.session_state.pop("hub_pick", None)
        st.rerun()
        return

    if picked == inlet:
        st.warning(t["link_same_hub"])
        st.session_state.pop("hub_pick", None)
        st.rerun()
        return

    distance, source = _link_distance(
        scenario, inlet, picked, mode=mode, follow_roads=follow
    )
    row = route_row_from_hubs(
        inlet,
        picked,
        mode,
        distance,
        {_text(item.get("id")) for item in frames["routes"].to_dict("records")},
        scenario.start_year,
        _suggested_capacity(scenario),
    )
    frames["routes"] = pd.concat(
        [frames["routes"], pd.DataFrame([row], columns=ROUTE_COLUMNS)], ignore_index=True
    )
    # frame the link that was just drawn: two hubs 2 km apart are invisible on a
    # national view, and the point of drawing them was to see the connection
    st.session_state["map_focus"] = {
        "from_node": inlet,
        "to_node": picked,
    }
    st.session_state.pop("link_step", None)
    st.session_state.pop("link_inlet", None)
    st.session_state.pop("hub_pick", None)
    st.session_state["flash"] = {
        "kind": "success",
        "text": t["link_created"].format(
            id=row["id"], km=row["distance_km"], source=t[f"link_km_{source}"]
        ),
    }
    st.rerun()


def _link_distance(
    scenario: ScenarioConfig,
    first: str,
    second: str,
    *,
    mode: str = "pipeline",
    follow_roads: bool = False,
) -> tuple[float, str]:
    """The length of a new link, and where the number came from.

    ``"road"`` - the drawn road polyline, measured along its real geometry;
    ``"straight"`` - the great-circle estimate between the two hubs.

    A road is 20-30 % longer than the crow-flies line, and the cost model charges
    per km, so the estimate has to match the line the map draws.
    """

    from ccus_core.geo.distance import great_circle_km

    positions = {
        node.id: (node.location.latitude, node.location.longitude)
        for node in scenario.nodes
        if node.location.latitude is not None and node.location.longitude is not None
    }
    start, end = positions.get(first), positions.get(second)
    if start is None or end is None:
        return 0.0, "straight"

    if follow_roads and mode == "truck":
        from streamlit_app.map_layers import road_length_km

        road_km = road_length_km((start[1], start[0]), (end[1], end[0]))
        if road_km:
            return round(road_km, 2), "road"

    return round(great_circle_km(start[0], start[1], end[0], end[1]), 2), "straight"


def _render_scenario_tab(st, t: dict, scenario: ScenarioConfig, frames: dict) -> None:
    """First tab: what the scenario *is* - its hubs, links, and where they run.

    The links live here rather than in ``Database`` because they belong to one
    scenario: two studies of the same region rarely ship the same network.
    ``Database`` keeps the catalogue of *candidate* links a scenario is built from.
    """

    st.markdown(
        f"### {t['sec_scenario']} "
        f":gray[· {scenario.start_year}\u2013{scenario.end_year}]"
    )

    # `scenario_to_frames` always builds the links and the hubs; the guard only
    # covers a session that was restored from an older document shape
    if "routes" not in frames or "nodes" not in frames:
        rebuilt = scenario_to_frames(scenario)
        frames.setdefault("routes", rebuilt["routes"])
        frames.setdefault("nodes", rebuilt["nodes"])

    metrics = st.columns(4)
    metrics[0].metric(t["metric_scenario_nodes"], len(scenario.nodes), border=True)
    metrics[1].metric(t["metric_scenario_links"], len(scenario.edges), border=True)
    metrics[2].metric(t["metric_scenario_emitters"], len(scenario.emitters), border=True)
    metrics[3].metric(t["metric_scenario_sinks"], len(scenario.storage_sinks), border=True)

    hidden = _render_hub_table(st, t, scenario, frames)
    st.session_state["hidden_hubs"] = sorted(hidden)

    _render_connectivity(st, t, scenario, frames)

    # ------------------------------------------------------------- links
    st.markdown(f"#### {t['sec_links']}")
    st.caption(t["links_help"])
    hub_options = _hub_options(scenario, frames["routes"])

    # the total distance is measured against one storage site; the others are one
    # expander away instead of silently averaged into the number
    sink_ids = [sink.id for sink in scenario.storage_sinks]
    distance_sink = _selected_distance_sink(st, sink_ids, frames["connections"])
    if distance_sink is not None:
        st.selectbox(
            t["links_distance_to"],
            sink_ids,
            key=DISTANCE_SINK_KEY,
            help=t["links_distance_help"],
        )
    distances = _scenario_distances(scenario, frames)
    calculated = {
        edge_id: per_sink[distance_sink]
        for edge_id, per_sink in distances.items()
        if distance_sink is not None and distance_sink in per_sink
    }

    with st.container(horizontal=True, vertical_alignment="center"):
        _toggle_all(
            st,
            t,
            frames["routes"],
            "sel",
            "editor_routes",
            "links_check_all",
            "links_uncheck_all",
        )
        _render_links_tools(st, t, frames)

    routes_shown = _follow_distance_column(st, frames["routes"], calculated)
    routes_edited = st.data_editor(
        routes_shown,
        num_rows="dynamic",
        width="stretch",
        key="editor_routes",
        column_config=_column_config(
            st,
            t["col_routes"],
            routes_shown.columns,
            number=True,
            text={"id", "name"},
            select={
                "mode": list(MODE_CODES),
                "from_node": hub_options,
                "to_node": hub_options,
            },
            checkbox={"sel"},
        ),
    )
    frames["routes"] = _merge_edited_routes(st, frames["routes"], routes_shown, routes_edited)
    _finish_edit(
        st,
        "editor_routes",
        not _frames_equal(routes_edited.to_dict("records"), routes_shown.to_dict("records")),
    )
    _column_help(st, t["col_help"], t["col_routes"], frames["routes"].columns)

    if distance_sink is not None:
        _render_distance_gaps(st, t, frames["routes"], calculated, distance_sink)
        _render_all_sink_distances(st, t, distances, _link_names(frames["routes"]))

    active = [row for row in frames["routes"].to_dict("records") if not _is_blank(row)]
    if not active:
        st.info(t["links_empty"])

    locked_routes = _unrepresentable_edges(scenario)
    if locked_routes:
        st.caption(
            t["routes_locked"].format(
                routes=", ".join(sorted(edge.id for edge in locked_routes))
            )
        )

    _render_add_link(st, t, scenario, frames)
    _render_link_builder(st, t, scenario, frames)
    _render_connections(st, t, scenario, frames)
    _render_links_save(st, t, scenario, frames)


def _optional_float(value):
    """A float or ``None`` - blank cells in the hub table mean "no value"."""

    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _apply_node_table(nodes, node_by_id, rows, *, base, edges, emitters, sinks, systems):
    """Make the hub table authoritative for which nodes exist.

    A row updates the node (name, kind, position); a base node the table no longer
    lists is removed - unless a link, emitter, sink or geothermal system still uses
    it, in which case the edit is refused instead of silently breaking the graph.
    """

    from ccus_core.models import GeoLocation, Node, NodeKind

    order = [node.id for node in nodes]
    base_ids = {node.id for node in base.nodes}
    frame_ids: list[str] = []

    for row in rows:
        node_id = _text(row.get("id"))
        if not node_id:
            continue
        frame_ids.append(node_id)

        kind_name = _text(row.get("kind"), "junction")
        if kind_name not in NODE_KINDS:
            raise ValueError(
                f"hub '{node_id}': kind must be one of {', '.join(NODE_KINDS)}"
            )
        # `model_copy` skips validation, so the enum is built explicitly
        kind = NodeKind(kind_name)

        latitude = _optional_float(row.get("latitude"))
        longitude = _optional_float(row.get("longitude"))
        existing = node_by_id.get(node_id)

        if existing is None:
            if latitude is None or longitude is None:
                raise ValueError(
                    f"hub '{node_id}' needs latitude and longitude before it can be "
                    "added - a hub without coordinates cannot be mapped or linked"
                )
            node_by_id[node_id] = Node(
                id=node_id,
                name=_text(row.get("name"), node_id),
                kind=kind,
                location=GeoLocation(latitude=latitude, longitude=longitude),
            )
            order.append(node_id)
            continue

        update: dict = {
            "name": _text(row.get("name"), existing.name),
            "kind": kind,
        }
        if latitude is not None or longitude is not None:
            update["location"] = existing.location.model_copy(
                update={"latitude": latitude, "longitude": longitude}
            )
        node_by_id[node_id] = existing.model_copy(update=update)

    used = {edge.from_node for edge in edges} | {edge.to_node for edge in edges}
    used |= {emitter.node_id for emitter in emitters}
    used |= {sink.node_id for sink in sinks}
    used |= {system.node_id for system in systems}

    dropped = [node_id for node_id in base_ids if node_id not in frame_ids]
    still_used = sorted(node_id for node_id in dropped if node_id in used)
    if still_used:
        raise ValueError(
            "the hub table removes "
            + ", ".join(still_used)
            + " but a link, emitter or storage site still uses it"
        )

    keep = set(frame_ids)
    nodes[:] = [
        node_by_id[node_id]
        for node_id in order
        if node_id in node_by_id and (node_id in keep or node_id not in base_ids)
    ]
    node_by_id.update({node.id: node for node in nodes})


#: session keys of the designer's distance column: which storage site it measures
#: to, and which values the designer wrote itself (as opposed to typed by the user)
DISTANCE_SINK_KEY = "links_distance_sink"
AUTO_DISTANCE_KEY = "links_auto_distance"


def _distance_sink_default(sink_ids: list[str], connections) -> str:
    """The storage site the distance column starts on.

    The sink the most connections already point at wins - that is the sink the
    study is about - and the first one breaks a tie.
    """

    counts: dict[str, int] = {}
    records = connections.to_dict("records") if hasattr(connections, "to_dict") else connections
    for row in records or []:
        sink_id = _text(row.get("sink_id"))
        if sink_id in sink_ids:
            counts[sink_id] = counts.get(sink_id, 0) + 1
    return max(sink_ids, key=lambda sink_id: (counts.get(sink_id, 0), -sink_ids.index(sink_id)))


def _selected_distance_sink(st, sink_ids: list[str], connections) -> str | None:
    """The storage site ``total_distance_km`` is measured against, or ``None``.

    The choice lives in ``session_state`` so it survives a rerun; when the scenario
    no longer has that sink (another one was loaded) the default is taken again.
    """

    if not sink_ids:
        st.session_state.pop(DISTANCE_SINK_KEY, None)
        return None
    chosen = st.session_state.get(DISTANCE_SINK_KEY)
    if chosen not in sink_ids:
        chosen = _distance_sink_default(sink_ids, connections)
        st.session_state[DISTANCE_SINK_KEY] = chosen
    return chosen


def _scenario_distances(scenario: ScenarioConfig, frames: dict) -> dict[str, dict[str, float]]:
    """``{edge_id: {sink_id: km}}`` as the edited tables currently stand.

    Built from the rows rather than from the applied scenario, so the column moves
    while the user types.  A half-edited table has no answer yet - ``{}`` - and
    *Apply* is where the complaint belongs.
    """

    from ccus_core.network.connectivity import distance_to_sinks

    try:
        candidate = frames_to_scenario(scenario, frames)
    except Exception:  # noqa: BLE001 - the editor may be mid-edit
        return {}
    return distance_to_sinks(candidate)


def _follow_distance_column(st, routes, calculated: dict[str, float]):
    """Show the calculated distances, and remember which ones are ours.

    ``calculated`` is ``{edge_id: km}`` for the selected storage site.  A blank cell
    is filled; a cell the designer filled itself keeps following the calculation,
    so editing a leg's length updates every total above it instead of freezing the
    first number the grid ever showed.  A value the user typed is left alone and
    becomes an override.  Returns the frame to hand to the editor.
    """

    auto = st.session_state.setdefault(AUTO_DISTANCE_KEY, {})
    frame = routes.copy().reset_index(drop=True)
    if "total_distance_km" not in frame.columns:
        # a session restored from an older document shape
        frame["total_distance_km"] = None
    frame["total_distance_km"] = pd.to_numeric(frame["total_distance_km"], errors="coerce")
    live = {_text(row.get("id")) for row in frame.to_dict("records")}

    for index, row in enumerate(frame.to_dict("records")):
        edge_id = _text(row.get("id"))
        if not edge_id:
            continue
        current = _optional_float(row.get("total_distance_km"))
        fresh = calculated.get(edge_id)
        remembered = auto.get(edge_id)

        if remembered is not None and (current is None or abs(current - remembered) <= 1e-9):
            # still ours: follow the calculation, or drop it when no path is left
            frame.at[index, "total_distance_km"] = fresh
            if fresh is None:
                auto.pop(edge_id, None)
            else:
                auto[edge_id] = fresh
        elif current is None and fresh is not None:
            frame.at[index, "total_distance_km"] = fresh
            auto[edge_id] = fresh

    for edge_id in [key for key in auto if key not in live]:
        auto.pop(edge_id, None)
    return frame


def _merge_edited_routes(st, base, shown, edited):
    """Copy the user's edits from the editor onto the authoritative frame.

    The editor was handed ``shown`` (the frame plus the calculated distances), so a
    cell that differs from it is a user edit.  A distance the user clears goes back
    to being calculated on the next run; a distance the user types is kept as an
    override.
    """

    auto = st.session_state.setdefault(AUTO_DISTANCE_KEY, {})
    before = shown.to_dict("records")
    after = edited.to_dict("records")
    # ``shown`` is the authoritative frame plus the calculated distances; starting
    # from it keeps the values the designer filled itself
    merged = [dict(row) for row in before]

    if len(after) > len(merged):
        # rows appended in the grid are taken as they are
        merged.extend(after[len(merged) :])
        return pd.DataFrame(merged, columns=list(base.columns))

    for index, row in enumerate(after[: len(before)]):
        for column in base.columns:
            if column == "total_distance_km":
                continue
            if _normalised(row.get(column)) != _normalised(before[index].get(column)):
                merged[index][column] = row.get(column)

        if _normalised(row.get("total_distance_km")) != _normalised(
            before[index].get("total_distance_km")
        ):
            merged[index]["total_distance_km"] = row.get("total_distance_km")
            auto.pop(_text(row.get("id")), None)

    return pd.DataFrame(merged, columns=list(base.columns))


def _link_names(routes) -> dict[str, str]:
    """``{edge_id: name}`` - the labels of the distance expander."""

    return {
        _text(row.get("id")): _text(row.get("name"))
        for row in routes.to_dict("records")
        if _text(row.get("id"))
    }


def _render_all_sink_distances(st, t: dict, distances, names: dict[str, str]) -> None:
    """Every leg that reaches more than one storage site, with each distance."""

    rows = []
    for edge_id, per_sink in sorted(distances.items()):
        if len(per_sink) < 2:
            continue
        label = f"{edge_id} · {names[edge_id]}" if names.get(edge_id) else edge_id
        for sink_id, km in sorted(per_sink.items()):
            rows.append(
                {
                    "link": label,
                    "sink": sink_id,
                    "total_distance_km": round(float(km), 3),
                }
            )
    if not rows:
        return
    with st.expander(t["links_distance_all"].format(count=len(rows)), expanded=False):
        st.dataframe(
            pd.DataFrame(rows, columns=["link", "sink", "total_distance_km"]),
            width="stretch",
            hide_index=True,
        )


def _render_distance_gaps(st, t: dict, routes, calculated, sink_id: str) -> None:
    """Legs with no directed path to the selected storage site."""

    missing = [
        _text(row.get("id"))
        for row in routes.to_dict("records")
        if not _is_blank(row) and _text(row.get("id")) and _text(row.get("id")) not in calculated
    ]
    if not missing:
        return
    st.warning(
        t["links_distance_gap"].format(count=len(missing), sink=sink_id, links=", ".join(sorted(missing)))
    )


def _render_connections(st, t: dict, scenario: ScenarioConfig, frames: dict) -> None:
    """The emitter → route → sink table: which access belongs to which storage site.

    This is the business object the solver expands into directed edges, and it is
    edited here - next to the links it points at - rather than in ``Inputs``, so a
    study is wired up in one place: hubs, legs, then who uses which leg.
    """

    st.markdown(f"#### {t['sec_connections']}")
    st.caption(t["connections_help"])

    routes = frames["routes"]
    link_ids = [
        value
        for value in (_text(row.get("id")) for row in routes.to_dict("records"))
        if value
    ]
    emitter_ids = [emitter.id for emitter in scenario.emitters]
    sink_ids = [sink.id for sink in scenario.storage_sinks]

    if not emitter_ids or not sink_ids:
        st.info(t["connections_empty"])
        return

    frame = frames["connections"]
    rows = frame.to_dict("records")
    selected = [row for row in rows if bool(row.get("sel"))]

    with st.container(horizontal=True, vertical_alignment="center"):
        _toggle_all(
            st,
            t,
            frame,
            "sel",
            "editor_connections",
            "connections_check_all",
            "connections_uncheck_all",
        )
        if st.button(
            t["connections_delete_selected"].format(count=len(selected)),
            key="connections_delete_button",
            disabled=not selected,
            icon=":material/delete:",
        ):
            chosen = {
                (
                    _text(row.get("emitter_id")),
                    _text(row.get("sink_id")),
                    _text(row.get("route_edge_id")),
                    _integer(row.get("start_year"), scenario.start_year),
                )
                for row in selected
            }
            keep = [
                row
                for row in rows
                if (
                    _text(row.get("emitter_id")),
                    _text(row.get("sink_id")),
                    _text(row.get("route_edge_id")),
                    _integer(row.get("start_year"), scenario.start_year),
                )
                not in chosen
            ]
            frames["connections"] = pd.DataFrame(keep, columns=CONNECTION_COLUMNS)
            st.session_state["flash"] = {
                "kind": "success",
                "text": t["connections_deleted"].format(count=len(chosen)),
            }
            st.rerun()

    options = {
        "emitter_id": list(emitter_ids),
        "route_edge_id": [""] + link_ids,
        "sink_id": list(sink_ids),
    }
    # a stored id that no longer exists stays visible (and is refused by Apply)
    # instead of being silently rewritten into something else
    stale: list[str] = []
    for column, allowed in options.items():
        extra = sorted(
            {
                value
                for value in (_text(row.get(column)) for row in rows)
                if value and value not in allowed
            }
        )
        if extra:
            options[column] = allowed + extra
            stale.extend(f"{column}={value}" for value in extra)
    if stale:
        st.warning(t["connections_stale"].format(items=", ".join(sorted(stale))))

    frames["connections"] = st.data_editor(
        frame,
        num_rows="dynamic",
        width="stretch",
        key="editor_connections",
        column_config=_column_config(
            st,
            t["col_connections"],
            frame.columns,
            number=True,
            text=set(),
            select=options,
            checkbox={"sel"},
        ),
    )

    _column_help(st, t["col_help"], t["col_connections"], frames["connections"].columns)


def _render_connectivity(st, t: dict, scenario: ScenarioConfig, frames: dict) -> bool:
    """Report emitters that cannot reach a storage site. True when the graph is sound.

    One line, with the per-emitter reasons folded into an expander: the check is
    important enough to always show and too small to own half the tab.
    """

    from ccus_core.network.connectivity import unreachable_emitters

    # the links table is authoritative while it is being edited, so build the check
    # scenario from the rows rather than from the last applied model
    try:
        candidate = frames_to_scenario(scenario, frames)
    except Exception:  # noqa: BLE001 - a half-edited table is reported by Apply
        return True

    problems = unreachable_emitters(candidate)
    st.session_state["connectivity_problems"] = [item["emitter_id"] for item in problems]

    if not problems:
        st.success(t["links_connected"], icon=":material/check_circle:")
        return True

    st.error(
        t["links_disconnected"].format(count=len(problems)),
        icon=":material/link_off:",
    )
    with st.expander(t["links_details"], expanded=False):
        for item in problems:
            st.caption(f"**{item['name']}** ({item['emitter_id']}): {item['reason']}")
    return False


def _render_links_tools(st, t: dict, frames: dict) -> None:
    """The links toolbar: tick the rows, then delete them - all of them at once.

    The tick column is a selection, exactly like a file manager: ticking ten links
    and pressing *Delete selected* removes ten links.  *Delete all links* stays as
    the one-action shortcut, behind a confirmation.
    """

    rows = [row for row in frames["routes"].to_dict("records") if not _is_blank(row)]
    if not rows:
        return

    auto = st.session_state.get(AUTO_DISTANCE_KEY, {})
    typed = [
        _text(row.get("id"))
        for row in rows
        if _text(row.get("id"))
        and _optional_float(row.get("total_distance_km")) is not None
        and _text(row.get("id")) not in auto
    ]
    if st.button(
        t["links_distance_clear"].format(count=len(typed)),
        key="links_distance_clear",
        disabled=not typed,
        icon=":material/straighten:",
    ):
        frame = frames["routes"]
        frame["total_distance_km"] = None
        st.session_state.pop(AUTO_DISTANCE_KEY, None)
        st.session_state.pop("editor_routes", None)
        st.session_state["flash"] = {
            "kind": "success",
            "text": t["links_distance_cleared"].format(count=len(typed)),
        }
        st.rerun()

    selected = [row for row in rows if bool(row.get("sel"))]

    if st.button(
        t["links_delete_selected"].format(count=len(selected)),
        key="links_delete_button",
        disabled=not selected,
        icon=":material/delete:",
    ):
        chosen = {
            (_text(row.get("id")), _text(row.get("from_node")), _text(row.get("to_node")))
            for row in selected
        }
        keep = [
            row
            for row in frames["routes"].to_dict("records")
            if (_text(row.get("id")), _text(row.get("from_node")), _text(row.get("to_node")))
            not in chosen
        ]
        frames["routes"] = pd.DataFrame(keep, columns=ROUTE_COLUMNS)
        st.session_state["flash"] = {
            "kind": "success",
            "text": t["links_deleted"].format(count=len(chosen)),
        }
        st.rerun()

    confirmed = st.checkbox(
        t["links_clear_confirm"].format(count=len(rows)), key="links_clear_confirm"
    )
    if st.button(t["links_clear_btn"], key="links_clear_button", disabled=not confirmed):
        frames["routes"] = pd.DataFrame(columns=ROUTE_COLUMNS)
        st.session_state.pop("links_clear_confirm", None)
        st.session_state["flash"] = {
            "kind": "success",
            "text": t["links_cleared"].format(count=len(rows)),
        }
        st.rerun()


def _render_links_save(st, t: dict, scenario: ScenarioConfig, frames: dict) -> None:
    """Confirm the section's edits into the scenario file, without running it."""

    from ccus_core.io import save_scenario
    from ccus_core.network.connectivity import unreachable_emitters

    if not st.button(t["btn_save_links"], key="btn_save_links"):
        return

    try:
        updated = frames_to_scenario(scenario, frames)
    except Exception as exc:  # noqa: BLE001 - the editor may be mid-edit
        st.error(t["links_save_failed"].format(error=exc))
        return

    # a disconnected scenario is a legitimate thing to park mid-study, so it is not
    # refused - it is confirmed once, with the reasons in front of the user
    problems = unreachable_emitters(updated)
    if problems:
        st.warning(t["links_save_disconnected"].format(count=len(problems)))
        for item in problems:
            st.caption(f"**{item['name']}** ({item['emitter_id']}): {item['reason']}")
        if not st.checkbox(t["links_save_confirm"], key="links_save_confirm"):
            return

    name = _text(st.session_state.get("scenario_name"), "") or scenario.id
    try:
        path = save_scenario(updated, name, overwrite=True)
    except Exception as exc:  # noqa: BLE001 - reported, never fatal
        st.error(t["links_save_failed"].format(error=exc))
        return

    st.session_state["flash"] = {
        "kind": "success",
        "text": t["links_saved"].format(name=Path(path).stem),
    }
    st.rerun()


def _edge_slug(value: str) -> str:
    """ASCII slug for a generated edge id (matches the model's ``Slug`` pattern)."""

    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip("-.")
    return text or "link"


def _suggested_capacity(scenario: ScenarioConfig) -> float:
    """Capacity a new link needs to carry the peak captured stream.

    A candidate link in the catalogue has a length and a cost, but no throughput -
    and a pipeline state without an explicit capacity is refused by the engine.  The
    peak captured mass is the smallest defensible default; the user can change it in
    the links table straight away.
    """

    peak = 0.0
    for year in range(int(scenario.start_year), int(scenario.end_year) + 1):
        total = 0.0
        for emitter in scenario.emitters:
            try:
                total += float(emitter.captured_emissions(year))
            except Exception:  # noqa: BLE001 - a curve outside its range is not fatal
                continue
        peak = max(peak, total)
    return max(round(peak, -3), 1000.0)


def route_row_from_candidate(
    candidate: dict,
    existing_ids,
    start_year: int,
    capacity: float | None = None,
) -> dict:
    """A Routes-table row for one candidate link of the catalogue.

    The row is complete enough for :func:`frames_to_scenario`: the capacity defaults
    to the peak captured stream so the new pipeline link is runnable, and the id is
    derived from the two hubs and the mode, suffixed when it is already taken.
    """

    from_node = _text(candidate.get("source_hub"))
    to_node = _text(candidate.get("destination_hub"))
    mode = _text(candidate.get("mode"), "pipeline")

    base = _edge_slug(f"{from_node}-{to_node}-{mode}")
    edge_id = base
    counter = 2
    while edge_id in existing_ids:
        edge_id = f"{base}-{counter}"
        counter += 1

    return {
        "sel": False,
        "id": edge_id,
        "name": f"{from_node} \u2192 {to_node}",
        "from_node": from_node,
        "to_node": to_node,
        "mode": mode,
        "distance_km": _number(candidate.get("length_km"), 0.0),
        "total_distance_km": None,
        "capacity_t_per_year": _number(capacity, 0.0) or None,
        "capex_eur": _number(candidate.get("capex_eur"), 0.0),
        "opex_eur_per_t": _number(candidate.get("opex_eur_per_t"), 0.0),
        "opex_eur_per_tkm": 0.0,
        "valid_from_year": int(start_year),
    }


def route_row_from_hubs(
    inlet: str,
    outlet: str,
    mode: str,
    distance_km: float,
    existing_ids,
    start_year: int,
    capacity: float,
) -> dict:
    """A Routes row for a link drawn by clicking two hubs on the map.

    The two endpoints are known, the mode is chosen, and the length is the map
    estimate; CAPEX/OPEX are left at zero because nothing in the study prices a
    corridor the user just invented - the table is where they are filled in.
    """

    return route_row_from_candidate(
        {
            "source_hub": inlet,
            "destination_hub": outlet,
            "mode": mode,
            "length_km": distance_km,
            "capex_eur": 0.0,
            "opex_eur_per_t": 0.0,
        },
        existing_ids,
        start_year,
        capacity,
    )


def _hub_brief(name: str, hubs: dict, known: set[str]) -> str:
    """``HR.CH.001 (chain, HR)`` - enough to recognise a hub without opening a table.

    A catalogue id such as ``HRES002`` means nothing on its own, and the catalogue's
    hubs are not necessarily the scenario's, so a hub the scenario does not have is
    marked as new.
    """

    meta = hubs.get(name) or {}
    bits = [str(meta.get("category") or "").strip()]
    country = str(meta.get("country") or "").strip()
    if country:
        bits.append(country)
    detail = ", ".join(bit for bit in bits if bit)
    label = f"{name} ({detail})" if detail else name
    return label if name in known else f"{label} \u2014 new hub"


def _candidate_links(routes, scenario: ScenarioConfig | None = None) -> list[dict]:
    """Catalogue links that the scenario does not have yet.

    A link is "already in the scenario" when the same source, destination and mode
    are; adding it twice would only create a second edge between the same hubs.
    """

    present = {
        (_text(row.get("from_node")), _text(row.get("to_node")), _text(row.get("mode")))
        for row in routes.to_dict("records")
        if not _is_blank(row)
    }

    hubs = {row.get("name"): row for row in _read_catalogue("hubs")}
    known = {node.id for node in scenario.nodes} if scenario is not None else set()

    candidates: list[dict] = []
    for row in network_database_rows():
        key = (
            _text(row.get("source_hub")),
            _text(row.get("destination_hub")),
            _text(row.get("mode")),
        )
        if key in present:
            continue
        candidates.append(
            {
                **row,
                "label": (
                    f"{_hub_brief(key[0], hubs, known)} \u2192 "
                    f"{_hub_brief(key[1], hubs, known)} \u00b7 {key[2]} \u00b7 "
                    f"{_number(row.get('length_km'), 0.0):g} km"
                ),
            }
        )
    return candidates


def _render_add_link(st, t: dict, scenario: ScenarioConfig, frames: dict) -> None:
    """Pick a candidate link from the catalogue and append it to this scenario.

    The catalogue answers "which corridors exist"; a scenario answers "which ones am
    I building".  This is the bridge: the new link appears in the table above, and
    the Connections table can then route an emitter through it.
    """

    import pandas as pd

    candidates = _candidate_links(frames["routes"], scenario)
    with st.container(border=True):
        st.markdown(f"#### {t['sec_add_link']}")
        st.caption(t["add_link_help"])

        if not candidates:
            st.info(t["add_link_none"])
            return

        labels = [candidate["label"] for candidate in candidates]
        choice = st.selectbox(t["add_link_select"], labels, key="add_link_choice")
        if not st.button(t["add_link_btn"], type="primary", key="add_link_button"):
            return

        candidate = candidates[labels.index(choice)]
        row = route_row_from_candidate(
            candidate,
            {_text(item.get("id")) for item in frames["routes"].to_dict("records")},
            scenario.start_year,
            _suggested_capacity(scenario),
        )
        frames["routes"] = pd.concat(
            [frames["routes"], pd.DataFrame([row], columns=ROUTE_COLUMNS)],
            ignore_index=True,
        )
        st.session_state["flash"] = {
            "kind": "success",
            "text": t["add_link_added"].format(id=row["id"]),
        }
        st.rerun()


def _render_database_backup(st, t: dict) -> None:
    """Download / restore the whole catalogue as one SQLite file.

    The engine's state is ``data/ccus.sqlite3`` plus the JSON snapshot, and the
    database is git-ignored - so without this block the only copy lives on the
    machine that runs the app.  Downloading the file is the backup; restoring it
    validates the file first and copies the current database aside, so a restore
    can itself be undone.
    """

    from ccus_core.io import sqlite_catalogue as store

    with st.container(border=True):
        st.markdown(f"#### {t['db_sec_backup']}")
        st.caption(t["db_backup_help"])

        try:
            payload = store.database_bytes()
        except Exception as exc:  # noqa: BLE001 - a missing database is not fatal
            payload = None
            st.warning(t["db_backup_missing"].format(error=exc))

        download, upload = st.columns(2, vertical_alignment="bottom")
        with download:
            if payload is not None:
                st.download_button(
                    t["db_btn_download"],
                    data=payload,
                    file_name=DB_BACKUP_NAME,
                    mime="application/vnd.sqlite3",
                    icon=":material/download:",
                    key="db_download_backup",
                    width="stretch",
                )
        with upload:
            uploaded = st.file_uploader(
                t["db_upload_label"],
                type=["sqlite", "sqlite3", "db"],
                key="db_restore_upload",
            )

        if uploaded is None:
            return

        try:
            summary = store.inspect_database(uploaded.getvalue())
        except Exception as exc:  # noqa: BLE001 - reported, never fatal
            st.error(t["db_restore_invalid"].format(error=exc))
            return

        counts = summary["counts"]
        st.info(
            t["db_restore_summary"].format(
                hubs=counts.get("hubs", 0),
                links=counts.get("links", 0),
                emitters=counts.get("emitters", 0),
                storage=counts.get("storage_sites", 0),
            )
        )
        confirmed = st.checkbox(t["db_restore_confirm"], key="db_restore_confirm")
        if st.button(
            t["db_btn_restore"],
            type="primary",
            disabled=not confirmed,
            key="db_restore_now",
        ):
            try:
                result = store.restore_database(uploaded.getvalue())
            except Exception as exc:  # noqa: BLE001 - reported, never fatal
                st.error(t["db_restore_failed"].format(error=exc))
                return
            backup = result.get("backup")
            st.session_state.pop("db_restore_upload", None)
            st.session_state.pop("db_restore_confirm", None)
            st.session_state["flash"] = {
                "kind": "success",
                "text": (
                    t["db_restored"].format(backup=Path(backup).name)
                    if backup
                    else t["db_restored_no_backup"]
                ),
            }
            st.rerun()


def _render_database_tab(st, t: dict, scenario: ScenarioConfig) -> None:
    """The Database tab: four editable catalogues, spreadsheet in and out."""

    st.caption(t["database_tab_help"])
    for message in st.session_state.pop("db_warnings", None) or []:
        st.warning(message)
    _render_database_backup(st, t)
    save = st.button(t["db_btn_save"], type="primary", key="db_save_database")
    year = _display_year(st, scenario)

    hubs = _read_catalogue("hubs")
    hub_labels = {row["id"]: f"{row['name']} ({row['category']})" for row in hubs}
    hub_options = [hub_labels[row["id"]] for row in hubs]
    source_options = [hub_labels[row["id"]] for row in hubs if row["category"] == "source"]
    sink_options = [hub_labels[row["id"]] for row in hubs if row["category"] == "sink"]

    frames = {
        "emitters": _database_table(
            st,
            t,
            title_key="db_sec_emitters",
            failed_key="database_failed",
            columns=DATABASE_COLUMNS,
            labels=t["col_database"],
            loader=lambda: emitter_database_rows(scenario, year),
            key="db_emitters_editor",
            alt="Emitter database",
            select={
                "curve": ["constant", "power_law", "piecewise_linear"],
                "hub": source_options,
            },
            text={"slug", "name", "industry", "points"},
        ),
        "hubs": _database_table(
            st,
            t,
            title_key="db_sec_hubs",
            failed_key="db_failed_hubs",
            columns=HUB_COLUMNS,
            labels=t["col_hubs"],
            loader=hub_database_rows,
            key="db_hubs_editor",
            alt="Hub database",
            select={"category": list(HUB_CATEGORIES)},
            text={"name", "country"},
        ),
        "pipelines": _database_table(
            st,
            t,
            title_key="db_sec_pipelines",
            failed_key="db_failed_pipelines",
            columns=PIPELINE_COLUMNS,
            labels=t["col_pipelines"],
            loader=pipeline_database_rows,
            key="db_pipelines_editor",
            alt="Pipeline designs",
            text={"name", "material"},
        ),
        "links": _database_table(
            st,
            t,
            title_key="db_sec_network",
            failed_key="db_failed_network",
            columns=NETWORK_COLUMNS,
            labels=t["col_network"],
            loader=network_database_rows,
            key="db_network_editor",
            alt="Network database",
            select={
                "source_hub": hub_options,
                "destination_hub": hub_options,
                "mode": list(MODE_CODES),
                "pipeline": [row["name"] for row in _read_catalogue("pipelines")],
            },
            text=set(),
            disabled=("length_km",),
        ),
        "storage": _database_table(
            st,
            t,
            title_key="db_sec_storage",
            failed_key="db_failed_storage",
            columns=STORAGE_COLUMNS,
            labels=t["col_storage"],
            loader=storage_database_rows,
            key="db_storage_editor",
            alt="Storage database",
            select={
                "storage_type": list(STORAGE_TYPES),
                "hub": sink_options,
            },
            text={"slug", "name", "lithology"},
        ),
    }

    if save or st.button(t["db_btn_save"], type="primary", key="db_save_database_bottom"):
        _save_database(
            st,
            t,
            frames,
            {
                "hubs": hub_database_rows,
                "pipelines": pipeline_database_rows,
                "links": network_database_rows,
                "emitters": lambda: emitter_database_rows(scenario, year),
                "storage": storage_database_rows,
            },
        )

def scenario_to_frames(scenario: ScenarioConfig) -> dict[str, "object"]:

    import pandas as pd

    emitters = []
    for emitter in scenario.emitters:
        curve = emitter.gross_emissions
        capture = emitter.capture
        emitters.append(
            {
                "id": emitter.id,
                "name": emitter.name,
                "activation_year": emitter.activation_year,
                "implementation_probability": emitter.implementation_probability,
                "curve": curve.kind,
                "e0_t_per_year": curve.e0_t_per_year,
                "a": curve.a,
                "c": curve.c,
                "constant_t_per_year": curve.constant_t_per_year,
                "capture_capacity_t_per_year": capture.capacity_t_per_year if capture else None,
                "capture_capex_eur": capture.capex_eur if capture else None,
                "capture_opex_eur_per_t": capture.opex_eur_per_t if capture else None,
            }
        )

    routes = []
    for edge in scenario.edges:
        state = edge.resolve_state(edge.states[0].valid_from_year) or edge.states[0]
        routes.append(
            {
                "sel": False,
                "id": edge.id,
                "name": edge.name,
                "from_node": edge.from_node,
                "to_node": edge.to_node,
                "mode": state.mode.value,
                "distance_km": state.distance_km,
                "total_distance_km": edge.total_distance_km,
                "capacity_t_per_year": state.capacity_t_per_year,
                "capex_eur": state.capex_eur,
                "opex_eur_per_t": state.opex_eur_per_t,
                "opex_eur_per_tkm": state.opex_eur_per_tkm,
                "valid_from_year": state.valid_from_year,
            }
        )

    connections = []
    for connection in scenario.connections:
        connections.append(
            {
                "sel": False,
                "emitter_id": connection.emitter_id,
                "route_edge_id": connection.route_edge_id,
                "sink_id": connection.sink_id,
                "start_year": connection.start_year,
            }
        )

    sinks = []
    for sink in scenario.storage_sinks:
        reservoir = sink.reservoir
        sinks.append(
            {
                "id": sink.id,
                "name": sink.name,
                "type": sink.storage_type.value,
                "geothermal_coupled": sink.geothermal_coupled,
                "geothermal_start_year": sink.geothermal_start_year,
                "capacity_t": sink.capacity_t,
                "depth_m": reservoir.top_depth_m if reservoir else None,
                "porosity": reservoir.porosity if reservoir else None,
                "permeability_m2": reservoir.permeability_m2 if reservoir else None,
                "commissioning_year": sink.commissioning_year,
                "capex_eur": sink.capex_eur,
                "opex_eur_per_t": sink.opex_eur_per_t,
                "monitoring_cost_during_injection_eur_per_year": sink.monitoring_cost_during_injection_eur_per_year,
                "monitoring_cost_after_injection_eur_per_year": sink.monitoring_cost_after_injection_eur_per_year,
                "monitoring_end_year": sink.monitoring_end_year,
            }
        )

    geothermal = []
    sink_by_node = {sink.node_id: sink.id for sink in scenario.storage_sinks}
    for system in scenario.geothermal_systems:
        geothermal.append(
            {
                "id": system.id,
                "name": system.name,
                "sink_id": sink_by_node.get(system.node_id),
                "d_doublet_m": system.d_doublet_m,
                "reservoir_temperature_c": system.reservoir_temperature_c,
                "eta_orc": system.eta_orc,
                "p_out_bar": system.p_out_bar,
                "t_out_c": system.t_out_c,
                "operation_start_year": system.operation_start_year,
                "operation_end_year": system.operation_end_year,
                "capex_eur": system.capex_eur,
                "fixed_opex_eur_per_year": system.fixed_opex_eur_per_year,
            }
        )

    routes_frame = pd.DataFrame(routes, columns=ROUTE_COLUMNS)
    return {
        "nodes": pd.DataFrame(
            _node_rows(scenario, routes_frame), columns=SCENARIO_NODE_COLUMNS
        ),
        "routes": routes_frame,
        "emitters": pd.DataFrame(emitters, columns=EMITTER_COLUMNS),
        "connections": pd.DataFrame(connections, columns=CONNECTION_COLUMNS),
        "sinks": pd.DataFrame(sinks, columns=SINK_COLUMNS),
        "geothermal": pd.DataFrame(geothermal, columns=GEOTHERMAL_COLUMNS),
    }


def _route_state_from_row(row, start_year: int, default_mode: str = "pipeline"):
    """Build the transport state the Routes table describes."""

    from ccus_core.models import EdgeState, MarineDesign, PipelineDesign, RoadDesign

    mode = _text(row.get("mode"), default_mode)
    capacity = _number(row.get("capacity_t_per_year"), 0.0)
    return EdgeState(
        mode=mode,
        valid_from_year=_integer(row.get("valid_from_year"), start_year),
        capacity_t_per_year=capacity or None,
        distance_km=_number(row.get("distance_km"), 0.0),
        capex_eur=_number(row.get("capex_eur"), 0.0),
        opex_eur_per_t=_number(row.get("opex_eur_per_t"), 0.0),
        opex_eur_per_tkm=_number(row.get("opex_eur_per_tkm"), 0.0),
        pipeline=PipelineDesign(
            inner_diameter_m=0.30, inlet_pressure_bar=150.0, inlet_temperature_c=20.0
        )
        if mode == "pipeline"
        else None,
        road=RoadDesign(
            vehicle_capacity_t=25.0,
            trips_per_vehicle_per_day=2.0,
            working_days_per_year=250.0,
            fleet_size=10,
        )
        if mode in {"truck", "rail"}
        else None,
        marine=MarineDesign(
            vessel_capacity_t=8000.0,
            voyages_per_vessel_per_year=6.0,
            vessels=2,
            port_node_id=_text(row.get("to_node")) or "port",
            weather_availability=0.85,
        )
        if mode == "marine"
        else None,
    )


def _route_signature(state, row) -> tuple:
    """Normalised view of the editable fields of one transport state.

    The Routes table owns ``mode``, ``distance_km``, ``capacity_t_per_year``,
    ``capex_eur``, ``opex_eur_per_t``, ``opex_eur_per_tkm`` and ``valid_from_year``;
    everything else (modal designs, geometry, upgrades) stays as it is in the base
    scenario.
    """

    return (
        state.mode.value,
        round(float(state.distance_km), 6),
        None if state.capacity_t_per_year is None else round(float(state.capacity_t_per_year), 3),
        round(float(state.capex_eur), 2),
        round(float(state.opex_eur_per_t), 6),
        round(float(state.opex_eur_per_tkm), 6),
        int(state.valid_from_year),
    )


def _route_row_signature(row, start_year: int) -> tuple:
    state = _route_state_from_row(row, start_year)
    return (
        state.mode.value,
        round(float(state.distance_km), 6),
        None if state.capacity_t_per_year is None else round(float(state.capacity_t_per_year), 3),
        round(float(state.capex_eur), 2),
        round(float(state.opex_eur_per_t), 6),
        round(float(state.opex_eur_per_tkm), 6),
        int(state.valid_from_year),
    )


def _unrepresentable_edges(scenario: ScenarioConfig) -> list:
    """Edges whose definition the Routes table cannot express."""

    return [
        edge
        for edge in scenario.edges
        if edge.upgrades or len(edge.states) > 1
    ]


def frames_to_scenario(base: ScenarioConfig, frames: dict) -> ScenarioConfig:
    """Apply the edited tables on top of ``base`` and re-validate the scenario.

    The tables are *not* an alternative, complete description of the study: they own
    a handful of columns per entity.  Everything else - pipe/road/marine designs,
    upgrade triggers, node locations, the rest of the reservoir properties, capture
    technology - is taken from ``base``, so pressing *Apply* can never silently drop
    it.

    An edge whose row was edited while the edge carries more than the table can
    express (a state timeline or a conditional upgrade) is refused with a clear
    message instead of being flattened.
    """

    import pandas as pd

    from ccus_core.models import (
        CaptureUnit,
        EmissionCurve,
        Emitter,
        EmitterSinkConnection,
        GeoLocation,
        Node,
        NodeKind,
        ReservoirProperties,
        StorageSink,
        StorageType,
        TransportEdge,
    )

    start_year = int(base.start_year)
    end_year = int(base.end_year)

    base_emitters = {item.id: item for item in base.emitters}
    base_sinks = {item.id: item for item in base.storage_sinks}
    base_edges = {item.id: item for item in base.edges}
    base_connections = {
        (item.emitter_id, item.sink_id, item.route_edge_id): item
        for item in base.connections
    }

    # nodes are never rebuilt: their coordinates and port data must survive Apply
    nodes: list[Node] = [item.model_copy(deep=True) for item in base.nodes]
    node_by_id = {item.id: item for item in nodes}

    def ensure_node(node_id: str, name: str, kind: "NodeKind") -> Node:
        node = node_by_id.get(node_id)
        if node is None:
            node = Node(id=node_id, name=name or node_id, kind=kind, location=GeoLocation())
            node_by_id[node_id] = node
            nodes.append(node)
        return node

    # ------------------------------------------------------------- emitters
    emitters: list[Emitter] = []
    for row in frames["emitters"].to_dict("records"):
        emitter_id = _text(row.get("id"))
        if not emitter_id:
            continue
        existing = base_emitters.get(emitter_id)
        node_id = existing.node_id if existing is not None else emitter_id
        node = ensure_node(node_id, _text(row.get("name"), emitter_id), NodeKind.EMITTER)
        if existing is not None and node.id != node_id:  # pragma: no cover - defensive
            node_id = node.id

        curve = _emission_curve_from_row(row, existing, start_year)
        activation = _integer(row.get("activation_year"), start_year)
        capacity = _number(row.get("capture_capacity_t_per_year"), 0.0)
        capture = None
        if capacity > 0.0:
            previous = existing.capture if existing is not None else None
            capture = CaptureUnit(
                name=previous.name if previous is not None else f"{emitter_id} capture",
                technology=previous.technology if previous is not None else None,
                capacity_t_per_year=capacity,
                capex_eur=_number(row.get("capture_capex_eur"), 0.0),
                opex_eur_per_t=_number(row.get("capture_opex_eur_per_t"), 0.0),
                availability=previous.availability if previous is not None else 1.0,
                commissioning_year=_integer(
                    row.get("commissioning_year"),
                    previous.commissioning_year if previous is not None else activation,
                ),
                decommission_year=previous.decommission_year if previous is not None else None,
            )

        emitters.append(
            Emitter(
                id=emitter_id,
                name=_text(row.get("name"), emitter_id),
                node_id=node_id,
                activation_year=activation,
                implementation_probability=(
                    None
                    if row.get("implementation_probability") is None
                    or pd.isna(row.get("implementation_probability"))
                    else _number(row.get("implementation_probability"))
                ),
                decommission_year=existing.decommission_year if existing is not None else None,
                gross_emissions=curve,
                capture=capture,
                notes=existing.notes if existing is not None else None,
            )
        )

    # --------------------------------------------------------------- sinks
    sink_ids: list[str] = []
    sinks: list[StorageSink] = []
    for row in frames["sinks"].to_dict("records"):
        sink_id = _text(row.get("id"))
        if not sink_id:
            continue
        sink_ids.append(sink_id)
        existing = base_sinks.get(sink_id)
        node_id = existing.node_id if existing is not None else f"{sink_id}-site"
        ensure_node(node_id, _text(row.get("name"), sink_id), NodeKind.STORAGE)

        if existing is not None:
            reservoir = existing.reservoir.model_copy(deep=True) if existing.reservoir else None
        else:
            reservoir = None
        if reservoir is None:
            reservoir = ReservoirProperties(
                area_m2=25e6,
                effective_thickness_m=150.0,
                porosity=0.20,
                permeability_m2=1.0e-13,
                top_depth_m=1500.0,
                temperature_c=60.0,
                reference_pressure_bar=150.0,
                pressure_step_bar=0.5,
            )
        # only the three columns the Storage table owns are applied
        reservoir = reservoir.model_copy(
            update={
                "top_depth_m": _number(row.get("depth_m"), reservoir.top_depth_m),
                "porosity": _number(row.get("porosity"), reservoir.porosity),
                "permeability_m2": _number(
                    row.get("permeability_m2"), reservoir.permeability_m2
                ),
            }
        )

        sinks.append(
            StorageSink(
                id=sink_id,
                node_id=node_id,
                name=_text(row.get("name"), sink_id),
                storage_type=StorageType(_text(row.get("type"), "DSA").upper()),
                capacity_t=_number(row.get("capacity_t"), 1.0),
                geothermal_coupled=bool(row.get("geothermal_coupled") or False),
                geothermal_start_year=_optional_year_or(
                    row.get("geothermal_start_year"),
                    existing.geothermal_start_year if existing is not None else None,
                ),
                reservoir=reservoir,
                injection_well=existing.injection_well if existing is not None else None,
                commissioning_year=_optional_year_or(
                    row.get("commissioning_year"),
                    existing.commissioning_year if existing is not None else start_year,
                ),
                decommission_year=existing.decommission_year if existing is not None else None,
                capex_eur=_number(row.get("capex_eur"), 0.0),
                opex_eur_per_t=_number(row.get("opex_eur_per_t"), 0.0),
                monitoring_cost_during_injection_eur_per_year=_number(
                    row.get("monitoring_cost_during_injection_eur_per_year"), 0.0
                ),
                monitoring_cost_after_injection_eur_per_year=_number(
                    row.get("monitoring_cost_after_injection_eur_per_year"), 0.0
                ),
                monitoring_end_year=_optional_year_or(
                    row.get("monitoring_end_year"),
                    existing.monitoring_end_year if existing is not None else None,
                ),
                notes=existing.notes if existing is not None else None,
            )
        )

    # -------------------------------------------------------------- routes
    locked: list[str] = []
    edges: list[TransportEdge] = []
    if "routes" in frames:
        for row in frames["routes"].to_dict("records"):
            edge_id = _text(row.get("id"))
            if not edge_id:
                continue
            from_node = _text(row.get("from_node"))
            to_node = _text(row.get("to_node"))
            ensure_node(from_node, from_node, NodeKind.JUNCTION)
            ensure_node(to_node, to_node, NodeKind.JUNCTION)

            existing = base_edges.get(edge_id)
            # the total distance is a designer-side annotation, not a transport
            # state: it is patched onto a kept edge and never counts as an edit,
            # so a route with upgrades can carry it without being flattened
            total_distance = _optional_float(row.get("total_distance_km"))
            unchanged = existing is not None and _route_signature(
                existing.states[0], row
            ) == _route_row_signature(row, start_year)
            if unchanged:
                # the row still matches what the table showed: keep the full edge
                if total_distance != existing.total_distance_km:
                    edges.append(
                        existing.model_copy(update={"total_distance_km": total_distance})
                    )
                else:
                    edges.append(existing)
                continue
            if existing is not None and (existing.upgrades or len(existing.states) > 1):
                locked.append(edge_id)
                continue

            edges.append(
                TransportEdge(
                    id=edge_id,
                    name=_text(row.get("name"), edge_id),
                    from_node=from_node,
                    to_node=to_node,
                    states=[_route_state_from_row(row, start_year)],
                    total_distance_km=total_distance,
                    notes=existing.notes if existing is not None else None,
                )
            )
    else:
        edges = list(base.edges)

    if locked:
        raise ValueError(
            "the Routes table cannot express the edited route(s) "
            + ", ".join(sorted(locked))
            + ": they carry a state timeline or a conditional upgrade. "
            "Revert the edit or change the route in the JSON scenario."
        )

    # for a route that is not in the table at all, keep the base definition
    represented = {_text(row.get("id")) for row in frames["routes"].to_dict("records")} if "routes" in frames else set()
    for edge in base.edges:
        if edge.id not in represented and edge not in edges:
            edges.append(edge)

    # --------------------------------------------------------- connections
    connections = []
    if "connections" in frames:
        for row in frames["connections"].to_dict("records"):
            emitter_id = _text(row.get("emitter_id"))
            sink_id = _text(row.get("sink_id"))
            if not emitter_id or not sink_id:
                continue
            route_edge_id = _text(row.get("route_edge_id")) or None
            key = (emitter_id, sink_id, route_edge_id)
            previous = base_connections.get(key)
            start = _integer(row.get("start_year"), start_year)
            if previous is not None and int(previous.start_year) == start:
                connections.append(previous)
                continue
            connections.append(
                EmitterSinkConnection(
                    emitter_id=emitter_id,
                    sink_id=sink_id,
                    route_edge_id=route_edge_id,
                    start_year=start,
                    end_year=None if pd.isna(row.get("end_year")) else _integer(row.get("end_year"), end_year),
                    mode=_text(row.get("mode"), "pipeline"),
                    distance_km=_number(row.get("distance_km"), 0.0),
                    capacity_t_per_year=_number(row.get("capacity_t_per_year"), 0.0) or None,
                    capex_eur=_number(row.get("capex_eur"), 0.0),
                    opex_eur_per_t=_number(row.get("opex_eur_per_t"), 0.0),
                    opex_eur_per_tkm=_number(row.get("opex_eur_per_tkm"), 0.0),
                    notes=previous.notes if previous is not None else None,
                )
            )
    else:
        connections = [item.model_copy(deep=True) for item in base.connections]

    # ---------------------------------------------------------- geothermal
    geothermal = []
    base_geothermal = {item.id: item for item in base.geothermal_systems}
    for row in frames["geothermal"].to_dict("records"):
        system_id = _text(row.get("id"))
        if not system_id:
            continue
        sink_id = _text(row.get("sink_id")) or (sink_ids[0] if sink_ids else None)
        if sink_id is None or sink_id not in sink_ids:
            continue
        node_id = base_sinks[sink_id].node_id
        previous = base_geothermal.get(system_id)
        geothermal.append(
            (previous or _default_doublet_row(system_id, sink_id, node_id, row, start_year, end_year)).model_copy(
                update={
                    "name": _text(row.get("name"), system_id),
                    "d_doublet_m": _number(row.get("d_doublet_m"), 1500.0),
                    "reservoir_temperature_c": _number(row.get("reservoir_temperature_c"), 150.0),
                    "eta_orc": _number(row.get("eta_orc"), 0.2),
                    "p_out_bar": _number(row.get("p_out_bar"), 10.0),
                    "t_out_c": _number(row.get("t_out_c"), 35.0),
                    "operation_start_year": _integer(row.get("operation_start_year"), start_year),
                    "operation_end_year": _integer(row.get("operation_end_year"), end_year),
                    "capex_eur": _number(row.get("capex_eur"), 0.0),
                    "fixed_opex_eur_per_year": _number(row.get("fixed_opex_eur_per_year"), 0.0),
                }
            )
        )

    # the hub table owns which nodes exist; nodes added implicitly by a link keep
    # their place because they are not base nodes
    if frames.get("nodes") is not None:
        _apply_node_table(
            nodes,
            node_by_id,
            frames["nodes"].to_dict("records"),
            base=base,
            edges=edges,
            emitters=emitters,
            sinks=sinks,
            systems=geothermal,
        )

    economics = base.economics
    payload = {
        "id": base.id,
        "name": base.name,
        "start_year": start_year,
        "end_year": end_year,
        "step": base.step,
        "nodes": [node.model_dump() for node in nodes],
        "emitters": [emitter.model_dump() for emitter in emitters],
        "edges": [edge.model_dump() for edge in edges],
        "connections": [connection.model_dump() for connection in connections],
        "storage_sinks": [sink.model_dump() for sink in sinks],
        "geothermal_systems": [system.model_dump() for system in geothermal],
        "economics": economics.model_dump() if economics else None,
        "policy": base.policy.model_dump() if base.policy else None,
        "storage_defaults": base.storage_defaults.model_dump(),
        "onboarding_years": base.onboarding_years,
        # the tables do not show the free-text notes: carry them over, otherwise a
        # no-op Apply silently empties them
        "notes": base.notes,
    }
    return ScenarioConfig.model_validate(payload)


def _default_doublet_row(system_id, sink_id, node_id, row, start_year, end_year):
    """Fallback doublet for a row that has no counterpart in the base scenario."""

    from ccus_core.models import GeothermalSystem

    return GeothermalSystem(
        id=system_id,
        node_id=node_id,
        name=_text(row.get("name"), system_id),
        d_doublet_m=1500.0,
        reservoir_temperature_c=150.0,
        eta_orc=0.2,
        p_out_bar=10.0,
        t_out_c=35.0,
        rw_production_m=0.15,
        rw_injection_m=0.15,
        h_ref_production_m=1500.0,
        h_ref_injection_m=1500.0,
        operation_start_year=start_year,
        operation_end_year=end_year,
    )


def _emission_curve_from_row(row, existing, start_year: int):
    """Emission curve described by the Emitters table (base curve when unchanged).

    The table owns ``curve``, ``e0_t_per_year``, ``a``, ``c`` and
    ``constant_t_per_year``.  It does **not** show ``reference_year`` (or the
    derived ``b``), so the base curve is reused whenever the row still carries the
    same numbers: rebuilding an untouched power law with ``reference_year =
    start_year`` moves the whole curve (the tester's 2025 -> 2027 shift).
    """

    from ccus_core.models import EmissionCurve

    kind = _text(row.get("curve"), "constant")
    previous = existing.gross_emissions if existing is not None else None
    # the reference year is not editable: keep the base one and only fall back to
    # the start of the horizon for a curve that has no base at all
    base_year = (
        int(previous.reference_year)
        if previous is not None and previous.reference_year is not None
        else int(start_year)
    )

    def same(candidate: dict) -> bool:
        """True when the row's editable numbers equal the base curve's."""

        if previous is None or previous.kind != kind:
            return False
        for field, value in candidate.items():
            current = getattr(previous, field, None)
            if current is None or abs(float(current) - float(value)) > 1e-9:
                return False
        return True

    if kind == "power_law":
        e0 = _number(
            row.get("e0_t_per_year"), float(previous.e0_t_per_year or 0.0) if previous else 0.0
        )
        a = _number(row.get("a"), float(previous.a) if previous else 0.0)
        c = _number(row.get("c"), float(previous.c) if previous else 1.5)
        if same({"e0_t_per_year": e0, "a": a, "c": c}) and previous is not None:
            return previous
        return EmissionCurve.power_law(
            e0_t_per_year=e0, reference_year=base_year, a=a, c=c
        )

    if kind == "polynomial":
        base_t = _number(
            row.get("constant_t_per_year"),
            float(previous.constant_t_per_year or 0.0) if previous else 0.0,
        )
        a = _number(row.get("a"), float(previous.polynomial_a) if previous else 0.0)
        c = _number(row.get("c"), float(previous.polynomial_c) if previous else 1.0)
        if same({"constant_t_per_year": base_t, "polynomial_a": a, "polynomial_c": c}):
            return previous
        return EmissionCurve.polynomial(
            base_t_per_year=base_t, reference_year=base_year, a=a, c=c
        )

    if kind == "piecewise_linear":
        # the control points are not in the table: keep them or start from a flat curve
        if previous is not None and previous.kind == "piecewise_linear":
            return previous
        return EmissionCurve.constant(_number(row.get("constant_t_per_year"), 0.0))

    value = _number(row.get("constant_t_per_year"), 0.0)
    if same({"constant_t_per_year": value}):
        return previous
    return EmissionCurve.constant(value)


# --------------------------------------------------------------------- charts
def _year_chart_data(frame, columns, *, x_label: str = "Year"):
    """Chart data with the year as a discrete axis label.

    A numeric year index makes Vega-Lite format the ticks as ``2,028.0`` (decimal,
    thousands separator).  The study is yearly, so the year is passed as text
    and the axis reads ``2028, 2029, ...`` - no decimals, no comma.

    Returns ``(data, x_label, y_columns)`` for :func:`st.line_chart`.
    """

    data = frame[["year", *columns]].copy()
    data["year"] = data["year"].astype(int).astype(str)
    return data, x_label, list(columns)


def _year_line_chart(st, frame, columns, **kwargs):
    """``st.line_chart`` over a frame with a year column, with clean year ticks."""

    data, x_label, y = _year_chart_data(frame, columns)
    st.line_chart(data, x="year", y=y, x_label=x_label, **kwargs)


def _sink_flag_map(result) -> dict[str, list[str]]:
    """Constraint flags per sink: rate limit, pore volume, BHP above the limit.

    ``result.kpis`` carries the lists, so the UI does not have to decide what a
    limit is - it only labels what the engine already found.
    """

    flags: dict[str, list[str]] = {}
    kpis = getattr(result, "kpis", {}) or {}
    for key, flag in (
        ("rate_limited_sinks", "rate"),
        ("capacity_limited_sinks", "capacity"),
        ("bhp_limited_sinks", "bhp"),
    ):
        for sink_id in kpis.get(key, []) or []:
            flags.setdefault(str(sink_id), []).append(flag)
    return flags


def _write_sink_flags(st, t: dict, sink_id: str, flags_by_sink: dict, frame) -> None:
    """Show the constraint flags of one sink above its pressure chart."""

    flags = list(flags_by_sink.get(sink_id, []))
    if "bhp" not in flags and "bhp_above_limit" in getattr(frame, "columns", []):
        if bool(frame["bhp_above_limit"].fillna(False).any()):
            flags.append("bhp")
    if not flags:
        return
    labels = {"rate": t["flag_rate"], "capacity": t["flag_capacity"], "bhp": t["flag_bhp"]}
    st.warning(f"{t['flags_title']}: " + ", ".join(labels.get(flag, flag) for flag in flags))


def build_map_figure(snapshot, scenario: ScenarioConfig):
    """Draw a schematic of the transport network for one year.

    The layout is layered by graph distance (emitters on the left, storage on the
    right) so the figure reads as a network rather than a scatter plot.  This is a
    schematic: coordinates come from the scenario when present, otherwise from the
    layered layout.  Line width encodes the routed mass, the arrow the direction.
    """

    plt.rcParams["font.family"] = ["DejaVu Sans", "Arial", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    # ---------------------------------------------------------------- layers
    emitter_nodes = {emitter.node_id for emitter in scenario.emitters}
    sink_nodes = {sink.node_id for sink in scenario.storage_sinks}
    adjacency: dict[str, list[str]] = {}
    for edge in snapshot.edges:
        adjacency.setdefault(edge["from_node"], []).append(edge["to_node"])
        if edge.get("bidirectional"):
            adjacency.setdefault(edge["to_node"], []).append(edge["from_node"])

    layer: dict[str, int] = {node: 0 for node in emitter_nodes}
    queue = list(emitter_nodes)
    while queue:
        current = queue.pop(0)
        for neighbour in adjacency.get(current, []):
            if neighbour not in layer:
                layer[neighbour] = layer[current] + 1
                queue.append(neighbour)
    for node_id in scenario.nodes and [node.id for node in scenario.nodes] or []:
        layer.setdefault(node_id, max(layer.values(), default=0) + 1)

    grouped: dict[int, list[str]] = {}
    for node_id, depth in layer.items():
        grouped.setdefault(depth, []).append(node_id)

    positions: dict[str, tuple[float, float]] = {}
    for depth in sorted(grouped):
        members = sorted(grouped[depth])
        for index, node_id in enumerate(members):
            node = next((item for item in scenario.nodes if item.id == node_id), None)
            latitude = node.location.latitude if node else None
            longitude = node.location.longitude if node else None
            if latitude is not None and longitude is not None:
                positions[node_id] = (float(longitude), float(latitude))
            else:
                offset = (index - (len(members) - 1) / 2.0) * 0.9
                positions[node_id] = (float(depth), offset)

    # ---------------------------------------------------------------- edges
    figure, axis = plt.subplots(figsize=(8.6, 4.8))
    max_flow = max([float(edge["flow_t"]) for edge in snapshot.edges] or [1.0])

    for edge in snapshot.edges:
        start = positions.get(edge["from_node"])
        end = positions.get(edge["to_node"])
        if start is None or end is None:
            continue
        flow = float(edge["flow_t"])
        width = 0.8 + 3.2 * (flow / max_flow if max_flow else 0.0)
        colour = MODE_COLOURS.get(edge["mode"] or "", "#999999")
        if edge["active"]:
            axis.annotate(
                "",
                xy=(end[0], end[1]),
                xytext=(start[0], start[1]),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=colour,
                    linewidth=width,
                    alpha=0.9,
                    shrinkA=6,
                    shrinkB=6,
                ),
            )
        # inactive edges are not drawn at all: a thin line would suggest a
            # connection that does not exist in that year
        elif False:
            pass
        if flow > 0.0:
            axis.text(
                (start[0] + end[0]) / 2.0,
                (start[1] + end[1]) / 2.0,
                f"{flow / 1000.0:,.0f} kt",
                fontsize=6,
                color="#222222",
                ha="center",
                va="bottom",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.75),
            )

    # ---------------------------------------------------------------- nodes
    for node in scenario.nodes:
        if node.id not in positions:
            continue
        x, y = positions[node.id]
        is_sink = node.id in sink_nodes
        is_port = node.kind.value in {"port", "offshore_terminal"}
        if is_sink:
            marker, size, colour = "s", 120.0, "#c0392b"
        elif is_port:
            marker, size, colour = "^", 90.0, "#2980b9"
        elif node.id in emitter_nodes:
            marker, size, colour = "o", 80.0, "#2c3e50"
        else:
            marker, size, colour = "D", 60.0, "#7f8c8d"
        axis.scatter([x], [y], marker=marker, s=size, color=colour, edgecolor="white", linewidth=0.8, zorder=3)
        axis.annotate(node.name, (x, y), fontsize=6.8, xytext=(5, 5), textcoords="offset points")

    handles = [
        plt.Line2D([0], [0], color=colour, linewidth=3, label=MODE_LABELS.get(mode, mode))
        for mode, colour in MODE_COLOURS.items()
        if any(edge["mode"] == mode for edge in snapshot.edges)
    ]
    handles += [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor="#2c3e50", markersize=7, label="Emitter"),
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#c0392b", markersize=7, label="Storage"),
        plt.Line2D([0], [0], marker="^", color="none", markerfacecolor="#2980b9", markersize=7, label="Port"),
    ]
    if handles:
        axis.legend(handles=handles, fontsize=6.5, loc="lower left", frameon=False, ncol=2)
    axis.set_xlabel("Network layer (0 = emitters)")
    axis.set_ylabel("Position within the layer")
    axis.set_title(f"Transport network, {snapshot.year}.")
    axis.grid(alpha=0.18, linewidth=0.4)
    figure.tight_layout()
    return figure


def snapshot_frame(rows: list[dict]):
    import pandas as pd

    return pd.DataFrame(rows)


# --------------------------------------------------------------------- app


def main() -> None:
    import streamlit as st

    try:  # package import (tests) or script import (streamlit run)
        from .i18n import strings
    except ImportError:  # pragma: no cover - script execution
        from i18n import strings

    st.set_page_config(page_title="CCUS cluster", layout="wide")

    if "language" not in st.session_state:
        st.session_state["language"] = "en"
    t = strings(st.session_state["language"])
    st.title(t["app_title"])
    _pop_flash(st)

    with st.sidebar:
        st.header("CCUS cluster")
        language = st.selectbox(
            t.get("language", "Jezik"),
            ["en", "hr"],
            format_func=lambda code: {"en": "English", "hr": "Hrvatski"}[code],
            index=["en", "hr"].index(st.session_state["language"]),
            key="language",
        )
        t = strings(st.session_state["language"])

        st.subheader(t["sidebar_scenario"])
        source = st.radio(
            t["sidebar_source"],
            list(SOURCE_KEYS),
            index=0,
            format_func=lambda key: _source_label(st, t, key),
            key="source_choice",
        )
        if source == "cluster":
            payload = DEFAULT_CLUSTER
        elif source == "single":
            payload = DEFAULT_SCENARIO
        else:
            uploaded = st.file_uploader(t["upload_label"], type=["json"])
            payload = uploaded.getvalue() if uploaded is not None else DEFAULT_CLUSTER

        if st.session_state.get("active_source") != source:
            st.session_state["active_source"] = source
            # switching the source drops a scenario loaded from the repository
            st.session_state.pop("active_scenario", None)
            st.session_state.pop("active_name", None)
            st.session_state.pop("frames", None)
            st.session_state.pop("result", None)
            st.session_state.pop("scenario", None)
            st.session_state.pop("error", None)

        # one active scenario: a file loaded from the repository wins over the source
        # radio, so "Run" computes what the user loaded and not the bundled example
        active = st.session_state.get("active_scenario")
        if active is not None:
            try:
                base_scenario = ScenarioConfig.model_validate(active)
            except Exception:  # noqa: BLE001 - a stale document falls back to the source
                st.session_state.pop("active_scenario", None)
                st.session_state.pop("active_name", None)
                active = None
        if active is None:
            try:
                base_scenario = load_scenario(payload)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                st.error(t["scenario_invalid"].format(error=exc))
                return
        st.success(t["scenario_loaded"].format(name=base_scenario.name))

        if st.button(t["btn_run"], type="primary"):
            try:
                st.session_state["result"] = ScenarioEngine(base_scenario).run()
                st.session_state["scenario"] = base_scenario
                st.session_state["frames"] = scenario_to_frames(base_scenario)
                st.session_state["base"] = base_scenario.model_dump()
                st.session_state["last_run_fingerprint"] = _fingerprint(base_scenario)
                st.session_state.pop("error", None)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                st.session_state["error"] = str(exc)
                st.error(t["save_failed"].format(error=exc))

        if st.button(t["load_scenario"]):
            st.session_state["frames"] = scenario_to_frames(base_scenario)
            st.session_state["base"] = base_scenario.model_dump()
            st.session_state.pop("result", None)
            st.rerun()


    with st.sidebar:
        from ccus_core.io import (
            delete_scenario,
            list_scenarios,
            load_scenario_file,
            next_default_name,
            save_scenario,
        )

        st.subheader(t["save_section"])

        # A new study starts with an empty network: the emitters and the sinks are
        # the brief, the links are what the study decides.  Loading a saved scenario
        # still brings its links back.
        if st.button(t["btn_new_scenario"], key="btn_new_scenario"):
            fresh = base_scenario.model_copy(
                update={"edges": [], "connections": []}
            )
            st.session_state["frames"] = scenario_to_frames(fresh)
            st.session_state["base"] = fresh.model_dump()
            st.session_state["scenario_name"] = next_default_name()
            st.session_state.pop("result", None)
            st.session_state.pop("scenario", None)
            st.session_state.pop("last_run_fingerprint", None)
            st.session_state["flash"] = {
                "kind": "success",
                "text": t["new_scenario_started"],
            }
            st.rerun()

        # the widget is seeded through session_state *before* it exists: writing the
        # key after instantiation raises "cannot be modified after the widget..."
        if not st.session_state.get("scenario_name"):
            st.session_state["scenario_name"] = next_default_name()
        name = st.text_input(
            t["save_name"],
            key="scenario_name",
            on_change=_name_normaliser(st),
            placeholder="scenario_001",
        )

        scenario_to_save = None
        frames_error = None
        if st.session_state.get("frames") is not None:
            try:
                scenario_to_save = frames_to_scenario(base_scenario, st.session_state["frames"])
            except Exception as exc:  # noqa: BLE001 - the editor may be mid-edit
                # an invalid table set must never be replaced by the untouched base:
                # saving would silently drop the user's edits
                frames_error = exc
        if scenario_to_save is None and frames_error is None:
            scenario_to_save = base_scenario

        if st.button(t["btn_save"]):
            if scenario_to_save is None:
                st.error(t["save_failed"].format(error=frames_error))
            else:
                try:
                    path = save_scenario(scenario_to_save, name)
                    # never write back into the widget key: report the saved name
                    st.session_state["last_saved_name"] = path.stem
                    st.session_state["flash"] = {
                        "kind": "success",
                        "text": t["saved_ok"].format(name=path.stem),
                    }
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 - surfaced to the user
                    st.error(t["save_failed"].format(error=exc))

        saved = list_scenarios()
        if saved:
            choice = st.selectbox(
                t["select_saved"],
                [record.name for record in saved],
                key="saved_choice",
            )
            if st.button(t["btn_load"]):
                try:
                    loaded = load_scenario_file(choice)
                    st.session_state["active_scenario"] = loaded.model_dump()
                    st.session_state["active_name"] = choice
                    st.session_state["frames"] = scenario_to_frames(loaded)
                    st.session_state["base"] = loaded.model_dump()
                    # a loaded scenario has not been run yet
                    st.session_state.pop("result", None)
                    st.session_state.pop("scenario", None)
                    st.session_state.pop("last_run_fingerprint", None)
                    st.session_state.pop("error", None)
                    st.session_state["flash"] = {
                        "kind": "success",
                        "text": t["loaded_ok"].format(name=choice),
                    }
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 - surfaced to the user
                    st.error(t["save_failed"].format(error=exc))
            if st.checkbox(t["confirm_delete"], key="confirm_delete"):
                if st.button(t["btn_delete"]):
                    try:
                        delete_scenario(choice)
                        st.session_state["flash"] = {
                            "kind": "success",
                            "text": t["deleted_ok"].format(name=choice),
                        }
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001 - surfaced to the user
                        st.error(t["save_failed"].format(error=exc))
        else:
            st.caption(t["no_saved"])

    frames = st.session_state.get("frames")
    if frames is None:
        frames = scenario_to_frames(base_scenario)
        st.session_state["frames"] = frames
        st.session_state["base"] = base_scenario.model_dump()
    base = st.session_state.get("base")
    base_scenario = ScenarioConfig.model_validate(base) if base else base_scenario

    # The banner is rendered through a placeholder that is filled *after* the Apply
    # handler below has run.  Streamlit executes the script top to bottom, so a
    # banner written here would always describe the state from before the click -
    # which is exactly why "Apply and run" used to leave a stale "up to date".
    status_slot = st.empty()

    (
        scenario_tab,
        inputs_tab,
        emitters_tab,
        overview,
        network,
        reservoir,
        economics,
        tables,
        database_tab,
    ) = st.tabs(
        [
            t["tab_scenario"],
            t["tab_inputs"],
            t["tab_emitters"],
            t["tab_overview"],
            t["tab_network"],
            t["tab_reservoir"],
            t["tab_economics"],
            t["tab_tables"],
            t["tab_database"],
        ]
    )

    with scenario_tab:
        _render_scenario_tab(st, t, base_scenario, frames)

    with inputs_tab:
        st.caption(t["inputs_hint"])

        st.markdown(f"#### {t['sec_emitters']}")
        frames["emitters"] = st.data_editor(
            frames["emitters"],
            num_rows="dynamic",
            width="stretch",
            key="editor_emitters",
            column_config=_column_config(st, t["col_emitters"], frames["emitters"].columns, number=True, text={"id", "name"}),
        )

        _column_help(st, t["col_help"], t["col_emitters"], frames["emitters"].columns)

        # connections moved to the Scenario tab: they belong next to the links they
        # point at, so a study is wired up (hubs -> legs -> who uses which leg) in
        # one place.  The Inputs tab keeps emitters, sinks, geothermal and economics.

        st.markdown(f"#### {t['sec_sinks']}")
        frames["sinks"] = st.data_editor(
            frames["sinks"],
            num_rows="dynamic",
            width="stretch",
            key="editor_sinks",
            column_config=_column_config(
                st,
                t["col_sinks"],
                frames["sinks"].columns,
                number=True,
                text={"id", "name"},
                select={"type": ["DSA", "DHF"]},
                checkbox={"geothermal_coupled"},
            ),
        )

        _column_help(st, t["col_help"], t["col_sinks"], frames["sinks"].columns)

        st.markdown(f"#### {t['sec_geothermal']}")
        frames["geothermal"] = st.data_editor(
            frames["geothermal"],
            num_rows="dynamic",
            width="stretch",
            key="editor_geothermal",
            column_config=_column_config(
                st,
                t["col_geothermal"],
                frames["geothermal"].columns,
                number=True,
                text={"id", "name", "sink_id"},
            ),
        )

        _column_help(st, t["col_help"], t["col_geothermal"], frames["geothermal"].columns)

        st.markdown(f"#### {t['sec_economics']}")
        column_a, column_b, column_c, column_d = st.columns(4)
        start_year = column_a.number_input(t["econ_start"], 2000, 2100, int(base_scenario.start_year))
        end_year = column_b.number_input(t["econ_end"], 2000, 2100, int(base_scenario.end_year))
        discount = column_c.number_input(
            t["econ_discount"],
            0.0,
            0.5,
            float(base_scenario.economics.discount_rate) if base_scenario.economics else 0.05,
            0.005,
        )
        inflation = column_d.number_input(
            t["econ_inflation"],
            0.0,
            0.5,
            float(base_scenario.economics.inflation_rate) if base_scenario.economics else 0.05,
            0.005,
        )

        if st.button(t["btn_apply"], type="primary"):
            try:
                scenario = frames_to_scenario(base_scenario, frames)
                scenario = scenario.model_copy(
                    update={
                        "start_year": int(start_year),
                        "end_year": int(end_year),
                        "economics": scenario.economics.model_copy(
                            update={
                                "start_year": int(start_year),
                                "end_year": int(end_year),
                                "discount_rate": float(discount),
                                "inflation_rate": float(inflation),
                            }
                        )
                        if scenario.economics
                        else None,
                    }
                )
                engine = ScenarioEngine(scenario)
                st.session_state["result"] = engine.run()
                st.session_state["scenario"] = engine.scenario
                st.session_state["base"] = engine.scenario.model_dump()
                # Apply *is* a run: record the fingerprint of the scenario that
                # produced these results, so the banner is truthful immediately
                st.session_state["last_run_fingerprint"] = _fingerprint(engine.scenario)
                st.session_state.pop("error", None)
                st.success(t["applied_ok"])
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                st.session_state.pop("result", None)
                st.session_state["error"] = str(exc)
                st.error(t["scenario_invalid_short"].format(error=exc))

    with database_tab:
        _render_database_tab(st, t, base_scenario)

    # the banner reads the session state *after* the handler above
    _write_status_banner(st, status_slot, t)

    result = st.session_state.get("result")
    if result is None:
        st.info(t["info_start"])
        return

    active_scenario = st.session_state.get("scenario", base_scenario)
    years = active_scenario.years()
    # keep a stored slider value inside the horizon before the widget is created
    stored_year = st.session_state.get("timeline_year")
    if stored_year is not None and not (min(years) <= int(stored_year) <= max(years)):
        st.session_state["timeline_year"] = min(years)
    year = st.slider(
        t["slider_time"],
        min(years),
        max(years),
        min(years),
        step=1,
        key="timeline_year",
    )
    st.caption(t["slider_help"])
    snapshot = year_snapshot(result, year)

    with emitters_tab:
        st.markdown(f"### {t['sec_compression']}")
        st.caption(t["emitters_help"])
        rows = []
        for emitter in active_scenario.emitters:
            series = {
                int(row.year): float(row.co2_chain_t)
                for row in result.ledger.itertuples(index=False)
            }
            captured = [emitter.captured_emissions(year) for year in years]
            peak_year = years[int(max(range(len(captured)), key=lambda index: captured[index]))]
            peak = max(captured) if captured else 0.0
            first_edge = next(
                (edge for edge in active_scenario.edges if edge.from_node == emitter.node_id),
                None,
            )
            state = first_edge.resolve_state(peak_year) if first_edge else None
            inlet_pressure = float(state.pipeline.inlet_pressure_bar) if state and state.pipeline else float("nan")
            distance = float(state.distance_km) if state else 0.0
            sink = None
            if first_edge is not None:
                node_id = first_edge.to_node
                sink = next((s for s in active_scenario.storage_sinks if s.node_id == node_id), None)
            rate_kg_s = peak * 1000.0 / SECONDS_PER_YEAR
            power_kw = 0.0
            if sink is not None and rate_kg_s > 0.0:
                power_kw = _compressor_power_kw(sink, rate_kg_s, inlet_pressure)
            rows.append(
                {
                    "emitter": emitter.name,
                    "activation_year": emitter.activation_year,
                    "peak_t_per_year": round(peak, 0),
                    "first_hub": first_edge.to_node if first_edge else "–",
                    "distance_km": round(distance, 1),
                    "design_inlet_pressure_bar": round(inlet_pressure, 1),
                    "compression_power_kw": round(power_kw, 1),
                    "compression_mwh_per_year": round(power_kw * HOURS_PER_YEAR / 1000.0, 1),
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch")

        st.markdown(f"#### {t['sec_tech']}")
        chart_data = {}
        for item in snapshot.emitters:
            chart_data[item["id"]] = item["captured_t"]
        yearly = pd.DataFrame(
            {
                "year": years,
                **{
                    emitter.id: [emitter.captured_emissions(year) for year in years]
                    for emitter in active_scenario.emitters
                },
            }
        ).set_index("year")
        st.bar_chart(yearly / 1e6)

    with overview:
        columns = st.columns(4)
        columns[0].metric(t["metric_captured"], f"{snapshot.totals['captured_t']:,.0f}")
        columns[1].metric(t["metric_routed"], f"{snapshot.totals['routed_t']:,.0f}")
        columns[2].metric(t["metric_injected"], f"{snapshot.totals['injected_t']:,.0f}")
        columns[3].metric(t["metric_stored"], f"{snapshot.totals['stored_t']:,.0f}")
        st.markdown(f"#### {t['sec_emitters']}")
        st.dataframe(snapshot_frame(snapshot.emitters), width="stretch")
        st.markdown(f"#### {t['sec_ledger']}")
        st.dataframe(result.ledger, width="stretch")

    with network:
        try:
            from streamlit_app.map_layers import build_network_map

            deck = build_network_map(snapshot, active_scenario)
        except Exception:  # noqa: BLE001 - the interactive map is optional
            deck = None
        if deck is not None:
            st.pydeck_chart(deck, width="stretch")
        else:
            st.pyplot(build_map_figure(snapshot, active_scenario), width="stretch")
        st.caption(t["net_help"])
        st.markdown(f"#### {t['sec_edges']}")
        st.dataframe(snapshot_frame(snapshot.edges), width="stretch")


        pressures = getattr(result, "pressures", None)
        if pressures is not None and not pressures.empty:
            st.markdown(f"#### {t['sec_pressures']}")
            st.dataframe(
                pressures[pressures["year"] == year],
                width="stretch",
            )
            pivot = pressures.pivot_table(
                index="year", columns="edge_id", values="p_in_bar", aggfunc="max"
            )
            st.line_chart(pivot)
            st.caption(t["pressures_help"])

        st.markdown(f"#### {t['sec_flows']}")
        flows = (
            result.routing_frame()
            .pivot_table(index="year", columns="path", values="quantity_t", aggfunc="sum")
            .fillna(0.0)
        )
        st.bar_chart(flows / 1e6)
        st.dataframe(flows, width="stretch")

        pressure_frames = [frame for frame in result.reservoir.values()]
        if pressure_frames:
            pressures = pressure_frames[0][["year", "pressure_bar", "bhp_bar"]]
            for frame in pressure_frames[1:]:
                pressures = pressures.merge(
                    frame[["year", "pressure_bar", "bhp_bar"]].rename(
                        columns={"pressure_bar": "pressure_bar", "bhp_bar": "bhp_bar"}
                    ),
                    on="year",
                    how="outer",
                )
            st.line_chart(pressures.set_index("year"))


    with reservoir:

        sink_options = list(result.reservoir.keys())
        flags_by_sink = _sink_flag_map(result)
        if sink_options:
            chosen = st.selectbox(t["sec_sink_select"], sink_options, key="sink_choice")
            frame = result.reservoir[chosen]
            _write_sink_flags(st, t, chosen, flags_by_sink, frame)
            with st.expander(t["sec_sink_cum"], expanded=False):
                _year_line_chart(
                    st,
                    frame,
                    ["co2_cumulative_t"],
                    y_label="Cumulative stored CO2 (t)",
                    alt="Cumulative stored CO2 in the selected storage site by year",
                )
                st.dataframe(frame, width="stretch")
        for sink_id, frame in result.reservoir.items():
            st.markdown(f"**{sink_id}**")
            _write_sink_flags(st, t, sink_id, flags_by_sink, frame)
            _year_line_chart(
                st,
                frame,
                ["pressure_bar", "bhp_bar"],
                y_label="Pressure (bar)",
                alt=f"Reservoir pressure and bottomhole pressure of {sink_id} by year",
            )


    with economics:
        if result.cash_flow is not None:
            columns = st.columns(4)
            columns[0].metric(t["metric_npv"], f"{result.kpis.get('npv_eur') or 0.0:,.0f}")
            columns[1].metric(t["metric_irr"], f"{(result.kpis.get('irr') or 0.0) * 100:.2f} %")
            columns[2].metric(t["metric_pv_revenue"], f"{result.kpis.get('pv_revenues_eur') or 0.0:,.0f}")
            columns[3].metric(t["metric_pv_cost"], f"{result.kpis.get('pv_costs_eur') or 0.0:,.0f}")
            st.line_chart(result.cash_flow.set_index("year")[["net_cash_flow", "cumulative_npv"]])
            st.dataframe(result.cash_flow, width="stretch")

        from ccus_core.finance import build_stakeholder_table, stakeholder_summary

        st.markdown(f"#### {t['sec_stakeholders']}")
        st.caption(t["stakeholders_help"])
        table = build_stakeholder_table(active_scenario, result)
        summary = stakeholder_summary(table)
        st.dataframe(summary, width="stretch")
        if not summary.empty:
            st.bar_chart(summary.pivot(index="year", columns="stakeholder", values="net_cash_flow_eur"))
        with st.expander(t["stakeholders_detail"], expanded=False):
            st.dataframe(table, width="stretch")

        # ------------------------------------------------ cumulative cost
        from ccus_core.finance import (
            cost_breakdown_for_year,
            cumulative_costs,
            entity_index,
            entity_statement,
        )

        st.markdown(f"#### {t['cum_cost']}")
        cumulative = cumulative_costs(result.cash_flow)
        cost_columns = [column for column in cumulative.columns if column not in {"year", "total"}]
        st.line_chart(cumulative.set_index("year")[cost_columns])
        st.caption(t["cum_cost_note"])

        # ------------------------------------------------ cost pie (last year)
        st.markdown(f"#### {t['pie_last']}")
        pie_year = st.selectbox(
            t["pie_year"],
            list(reversed([int(year) for year in result.cash_flow["year"]])),
            index=0,
            key="pie_year",
        )
        breakdown = cost_breakdown_for_year(result.cash_flow, int(pie_year))
        if len(breakdown) >= 2:
            labels = list(breakdown)
            values = [breakdown[key] for key in labels]
            figure, axis = plt.subplots(figsize=(5.6, 3.4))
            axis.pie(
                values,
                labels=labels,
                autopct="%1.1f%%",
                startangle=90,
                counterclock=False,
                textprops={"fontsize": 7.5},
                colors=plt.get_cmap("tab20").colors[: len(labels)],
            )
            axis.set_title(f"{t['pie_last']} ({int(pie_year)}.)")
            figure.tight_layout()
            st.pyplot(figure, width="stretch")
            plt.close(figure)
        else:
            st.info(t["pie_none"])

        # ------------------------------------------------ per-entity economics
        st.markdown(f"#### {t['entity_select']}")
        entities = entity_index(active_scenario)
        if entities:
            labels = [entity["label"] for entity in entities]
            choice = st.selectbox(t["entity_select"], labels, key="entity_choice")
            entity = next(item for item in entities if item["label"] == choice)
            statement = entity_statement(
                table,
                entity["stakeholder"],
                entity["id"],
                discount_rate=float(active_scenario.economics.discount_rate) if active_scenario.economics else None,
            )
            if statement["years"]:
                totals = statement["totals"]
                columns = st.columns(4)
                columns[0].metric(t["entity_capex"], f"{totals.get('capex', 0.0):,.0f} EUR")
                columns[1].metric(t["entity_opex"], f"{totals.get('opex', 0.0):,.0f} EUR")
                columns[2].metric(t["entity_transfers"], f"{totals.get('tariff_paid', 0.0) + totals.get('tariff_collected', 0.0):,.0f} EUR")
                columns[3].metric(t["entity_net"], f"{totals.get('net', 0.0):,.0f} EUR")
                if statement["npv"] is not None:
                    st.metric(t["entity_npv"], f"{statement['npv']:,.0f} EUR")

                entity_frame = pd.DataFrame(
                    {
                        "year": statement["years"],
                        **{line: statement["items"][line] for line in statement["items"]},
                        "net": statement["net_by_year"],
                    }
                ).set_index("year")
                st.dataframe(entity_frame, width="stretch")
                st.line_chart(entity_frame[["net"]])
                cumulative_net = entity_frame["net"].cumsum().rename("cumulative")
                st.line_chart(cumulative_net)
            else:
                st.info(t["entity_empty"])


    with tables:
        st.markdown(f"#### {t['sec_routes']}")
        st.dataframe(result.routing_frame(), width="stretch")
        st.download_button(
            t["download_ledger"],
            result.ledger.to_csv(index=False).encode("utf-8-sig"),
            file_name=t["file_ledger"],
            mime="text/csv; charset=utf-8",
        )


def _compressor_power_kw(sink, rate_kg_s: float, p_out_bar: float) -> float:
    """CO2 compressor power (kW) required to reach ``p_out_bar`` for one sink."""

    if rate_kg_s <= 0.0 or p_out_bar != p_out_bar:
        return 0.0
    try:
        from engineering import Power

        from ccus_core.simulation.adapters import power_inputs_for_sink

        power = Power(power_inputs_for_sink(sink, rate_kg_s), None)
        return float(
            power.calculate_compression_power(
                fluid="CO2",
                p_in_bar=float(sink.compressor_inlet_pressure_bar),
                p_out_bar=float(p_out_bar),
                t_in_C=float(sink.compressor_inlet_temperature_c),
                m_dot=float(rate_kg_s),
            )
        )
    except Exception:  # noqa: BLE001 - never break the UI on a power estimate
        return 0.0


def _column_help(st, title: str, labels: dict, columns) -> None:
    """Expandable list of column descriptions, so the headers can stay short."""

    rows = "\n".join(
        f"| `{column}` | {labels.get(column, (column, ''))[1] or '–'} |" for column in columns
    )
    with st.expander(title, expanded=False):
        st.markdown(f"| Stupac | Opis |\n|---|---|\n{rows}")


def _fingerprint(scenario: ScenarioConfig) -> str:
    """Short, stable hash of a scenario document (used for the dirty indicator)."""

    import hashlib

    payload = scenario.model_dump_json()
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _write_status_banner(st, slot, t: dict) -> None:
    """Fill the status placeholder with the state *after* this script pass.

    Called at the end of the input section so that ``Apply and run`` is reflected in
    the same rerun: the banner then compares the results on display with the scenario
    they were computed from.  The native widgets are used on purpose - they carry
    their own colour and icon, so no raw HTML is sent to the browser.  ``st`` is
    passed in because the module imports it inside :func:`main` only.
    """

    error = st.session_state.get("error")
    if error:
        slot.error(f"{t['status_error']}: {error}")
        return

    if st.session_state.get("result") is None:
        slot.info(t["status_idle"])
        return

    base = st.session_state.get("base")
    current = (
        ScenarioConfig.model_validate(base)
        if base is not None
        else st.session_state.get("scenario")
    )
    if current is None or st.session_state.get("last_run_fingerprint") == _fingerprint(current):
        slot.success(t["status_ok"])
    else:
        slot.warning(t["status_dirty"])


def _column_config(st, labels: dict, columns, *, number: bool, text: set[str], select: dict | None = None, checkbox: set[str] | None = None):
    """Build a ``column_config`` mapping from the translation table."""

    select = select or {}
    checkbox = checkbox or {}
    config = {}
    for column in columns:
        label, help_text = labels.get(column, (column, ""))
        if column in checkbox:
            config[column] = st.column_config.CheckboxColumn(label, help=help_text or None)
        elif column in select:
            config[column] = st.column_config.SelectboxColumn(label, options=select[column], help=help_text or None)
        elif column in text:
            config[column] = st.column_config.TextColumn(label, help=help_text or None)
        elif number:
            config[column] = st.column_config.NumberColumn(label, help=help_text or None)
        else:
            config[column] = st.column_config.Column(label, help=help_text or None)
    return config


if __name__ == "__main__":
    main()
