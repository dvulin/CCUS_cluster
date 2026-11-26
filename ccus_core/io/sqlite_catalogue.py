"""SQLite store for the reference catalogues (emitters, hubs, links, storage).

The catalogues are the study's reference data: the candidate emitters, hubs,
transport links and storage sites a scenario is built from.  SQLite gives them
what JSON cannot express - an auto-increment primary key, a foreign key from a
link to the two hubs it connects, unique slugs and checked vocabularies - while
the JSON files under ``json/`` remain the portable, git-diffable snapshot that the
engine reads.

Nothing here imports Streamlit or any UI toolkit.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = ROOT / "data"
JSON_DIRECTORY = ROOT / "json"
DEFAULT_DB_PATH = DATA_DIRECTORY / "ccus.sqlite3"

#: timestamped copies written before a restore
BACKUP_DIRECTORY = DATA_DIRECTORY / "backups"

#: tables a file must contain to be accepted as this application's catalogue
REQUIRED_TABLES = ("modes", "pipelines", "hubs", "links", "emitters", "storage_sites", "meta")

#: the SQLite file signature
SQLITE_HEADER = b"SQLite format 3\x00"

#: the one vocabulary of transport modes, shared by hubs and links
MODES: tuple[tuple[str, str, str], ...] = (
    ("pipeline", "Pipeline", "Cjevovod"),
    ("truck", "Truck", "Kamion"),
    ("rail", "Rail", "Željeznica"),
    ("marine", "Marine", "Brod"),
)
MODE_CODES = tuple(code for code, _, _ in MODES)

#: the single hub category vocabulary (was split between category and kind)
HUB_CATEGORIES = (
    "source",
    "chain",
    "sink",
    "buffer",
    "hub",
    "port",
    "offshore_terminal",
)

#: the GIS catalogue used ``road``/``ship``; the database uses the engine words
LEGACY_KIND_TO_MODE = {"pipeline": "pipeline", "road": "truck", "rail": "rail", "ship": "marine"}

#: bump when the table layout changes; a mismatch rebuilds from the JSON snapshot
SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS modes (
    code     TEXT PRIMARY KEY,
    label_en TEXT NOT NULL,
    label_hr TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipelines (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL UNIQUE,
    diameter_m           REAL NOT NULL DEFAULT 0.30 CHECK (diameter_m > 0.0),
    wall_thickness_m     REAL CHECK (wall_thickness_m IS NULL OR wall_thickness_m >= 0.0),
    roughness_m          REAL NOT NULL DEFAULT 4.5e-5 CHECK (roughness_m >= 0.0),
    material             TEXT,
    design_pressure_bar  REAL CHECK (design_pressure_bar IS NULL OR design_pressure_bar > 0.0),
    design_temperature_c REAL,
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS hubs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL
                    CHECK (category IN ('source', 'chain', 'sink', 'buffer', 'hub',
                                        'port', 'offshore_terminal')),
    country         TEXT,
    x               REAL NOT NULL DEFAULT 0.0,
    y               REAL NOT NULL DEFAULT 0.0,
    elevation_m     REAL,
    latitude        REAL,
    longitude       REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS links (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_hub_id         INTEGER NOT NULL REFERENCES hubs(id) ON DELETE RESTRICT,
    destination_hub_id    INTEGER NOT NULL REFERENCES hubs(id) ON DELETE RESTRICT,
    mode                  TEXT NOT NULL REFERENCES modes(code),
    pipeline_id           INTEGER REFERENCES pipelines(id) ON DELETE SET NULL,
    capex_eur             REAL NOT NULL DEFAULT 0.0,
    opex_eur_per_t        REAL NOT NULL DEFAULT 0.0,
    length_km             REAL,
    notes                 TEXT,
    CHECK (source_hub_id <> destination_hub_id),
    UNIQUE (source_hub_id, destination_hub_id, mode)
);

CREATE TABLE IF NOT EXISTS emitters (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug                        TEXT NOT NULL UNIQUE,
    name                        TEXT NOT NULL,
    industry                    TEXT,
    curve                       TEXT NOT NULL DEFAULT 'constant'
                                CHECK (curve IN ('constant', 'power_law', 'piecewise_linear')),
    reference_year              INTEGER,
    e0_t_per_year               REAL,
    a                           REAL,
    c                           REAL,
    b                           REAL,
    constant_t_per_year         REAL,
    points                      TEXT,
    activation_year             INTEGER,
    implementation_probability  REAL,
    hub_id                      INTEGER REFERENCES hubs(id) ON DELETE SET NULL,
    reference_sink_id           TEXT,
    notes                       TEXT
);

CREATE TABLE IF NOT EXISTS storage_sites (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    slug                TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    storage_type        TEXT NOT NULL DEFAULT 'DSA'
                        CHECK (storage_type IN ('DSA', 'DHF', 'DGF', 'DOF')),
    capacity_t          REAL NOT NULL DEFAULT 0.0,
    depth_m             REAL NOT NULL DEFAULT 0.0,
    porosity            REAL NOT NULL DEFAULT 0.20,
    permeability_m2     REAL NOT NULL DEFAULT 1.0e-13,
    pressure_bar        REAL NOT NULL DEFAULT 0.0,
    temperature_c       REAL NOT NULL DEFAULT 0.0,
    lithology           TEXT,
    hub_id              INTEGER REFERENCES hubs(id) ON DELETE SET NULL,
    well_diameter_m     REAL NOT NULL DEFAULT 0.30 CHECK (well_diameter_m > 0.0),
    well_number         INTEGER NOT NULL DEFAULT 1 CHECK (well_number >= 1),
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class CatalogueError(ValueError):
    """Raised when a catalogue row cannot be stored."""


# --------------------------------------------------------------------------- io
def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (and create) the catalogue database with foreign keys enforced."""

    target = Path(path) if path is not None else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialise(connection: sqlite3.Connection) -> None:
    """Create the schema and seed the transport-mode vocabulary.

    A database written by an older schema is dropped and rebuilt from the JSON
    snapshot on the next :func:`ensure_database` call - the snapshot is written on
    every save, so no catalogue data is lost.
    """

    version = _schema_version(connection)
    if (version is not None and version != SCHEMA_VERSION) or (
        version is None and _table_exists(connection, "hubs")
    ):
        # a database written by an older schema: rebuild it from the JSON snapshot
        for table in (
            "links",
            "emitters",
            "storage_sites",
            "hubs",
            "pipelines",
            "modes",
            "meta",
        ):
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.commit()

    connection.executescript(SCHEMA)
    connection.executemany(
        "INSERT OR IGNORE INTO modes (code, label_en, label_hr) VALUES (?, ?, ?)",
        MODES,
    )
    # a default design so a pipeline link is usable before the user defines one
    connection.execute(
        "INSERT OR IGNORE INTO pipelines (name, diameter_m, roughness_m)"
        " VALUES ('Default (0.30 m)', 0.30, 4.5e-5)"
    )
    connection.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()


def _schema_version(connection: sqlite3.Connection) -> int | None:
    try:
        row = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:  # no meta table yet
        return None
    return int(row[0]) if row is not None else None


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def is_empty(connection: sqlite3.Connection) -> bool:
    """True when no catalogue has been imported yet."""

    return all(
        _count(connection, table) == 0 for table in ("hubs", "links", "emitters", "storage_sites")
    )


def ensure_database(path: str | Path | None = None) -> sqlite3.Connection:
    """Open the database, creating and seeding it from the JSON snapshot if new."""

    connection = connect(path)
    try:
        initialise(connection)
        if is_empty(connection):
            migrate_from_json(connection)
    except Exception:
        connection.close()
        raise
    return connection


# ------------------------------------------------------------------ backup/restore
def database_path(path: str | Path | None = None) -> Path:
    """Resolve the catalogue file (the live database by default)."""

    return Path(path) if path is not None else DEFAULT_DB_PATH


def database_bytes(path: str | Path | None = None) -> bytes:
    """The raw file, for a download button or an external backup.

    Reading the bytes is safe while the app is running: SQLite allows concurrent
    readers, and the file is replaced atomically rather than written in place.
    """

    target = database_path(path)
    if not target.is_file():
        raise CatalogueError(
            f"the catalogue database '{target}' does not exist yet - save the Database tab once"
        )
    return target.read_bytes()


def inspect_database(data: bytes) -> dict:
    """Validate an uploaded database and describe what it holds.

    A restore replaces the whole catalogue, so an arbitrary file must never be
    accepted: this checks the SQLite signature, that every expected table exists,
    that SQLite itself considers the file intact, and that the schema version is
    one this code understands.
    """

    if not data or not bytes(data).startswith(SQLITE_HEADER):
        raise CatalogueError("this is not a SQLite database file")

    handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(data)
        try:
            connection = sqlite3.connect(temporary)
        except sqlite3.Error as exc:  # pragma: no cover - a written file opens
            raise CatalogueError(f"the file is not a readable SQLite database: {exc}") from exc
        try:
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            except sqlite3.DatabaseError as exc:
                raise CatalogueError(f"the file is not a SQLite database: {exc}") from exc

            if integrity is None or str(integrity[0]).lower() != "ok":
                raise CatalogueError(
                    f"the file fails the SQLite integrity check ({integrity[0] if integrity else 'no result'})"
                )

            missing = [table for table in REQUIRED_TABLES if table not in tables]
            if missing:
                raise CatalogueError(
                    "this is not a GT-CCUS catalogue database; missing table(s): "
                    + ", ".join(missing)
                )

            version = connection.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            found = int(version[0]) if version else None
            if found is not None and found != SCHEMA_VERSION:
                raise CatalogueError(
                    f"the file was written by catalogue schema {found}, "
                    f"this version expects {SCHEMA_VERSION}"
                )

            counts = {
                table: int(
                    connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                )
                for table in REQUIRED_TABLES
                if table != "meta"
            }
        finally:
            connection.close()
    finally:
        if temporary.exists():
            temporary.unlink()

    return {"schema_version": found, "counts": counts}


def backup_database(path: str | Path | None = None, directory: str | Path | None = None) -> Path:
    """Copy the live database to a timestamped backup; returns the copy.

    Used before a restore, so that restoring is itself reversible.
    """

    target = database_path(path)
    if not target.is_file():
        raise CatalogueError(f"the catalogue database '{target}' does not exist yet")

    folder = Path(directory) if directory is not None else BACKUP_DIRECTORY
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = folder / f"ccus_{stamp}.sqlite"
    counter = 1
    while destination.exists():  # two restores inside one second
        destination = folder / f"ccus_{stamp}_{counter}.sqlite"
        counter += 1
    shutil.copy2(target, destination)
    return destination


def restore_database(
    data: bytes,
    path: str | Path | None = None,
    *,
    backup: bool = True,
) -> dict:
    """Replace the catalogue with an uploaded file and refresh the JSON snapshot.

    The file is validated first (:func:`inspect_database`), the current database is
    copied aside unless ``backup=False``, and the replacement is written to a
    temporary file and moved into place, so an interrupted restore cannot leave a
    half-written catalogue behind.  The snapshot under ``json/`` is regenerated
    afterwards, because that is what the engine reads.
    """

    summary = inspect_database(data)
    target = database_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    saved = backup_database(target) if backup and target.is_file() else None

    handle = tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.stem}_", suffix=".tmp", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(data)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()

    connection = connect(target)
    try:
        files = export_snapshot(connection)
    finally:
        connection.close()

    summary["restored_to"] = str(target)
    summary["backup"] = str(saved) if saved is not None else None
    summary["snapshot"] = sorted(Path(item).name for item in files.values())
    return summary
def load_modes(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT * FROM modes ORDER BY code")]


def load_pipelines(connection: sqlite3.Connection) -> list[dict]:
    """The pipeline designs a link can reference."""

    return [dict(row) for row in connection.execute("SELECT * FROM pipelines ORDER BY id")]


def load_hubs(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT * FROM hubs ORDER BY id")]


def load_links(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT * FROM links ORDER BY id")]


def load_emitters(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT * FROM emitters ORDER BY id")]


def load_storage(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT * FROM storage_sites ORDER BY id")]


# ----------------------------------------------------------------------- writing
def _slugify(value: str) -> str:
    """ASCII slug of a display name (``TE PLOMIN`` -> ``te-plomin``)."""

    text = str(value or "").strip().lower()
    replacements = {
        "š": "s", "ž": "z", "č": "c", "ć": "c", "đ": "d", "đ": "d",
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    slug = "".join(char if char.isalnum() else "-" for char in text)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _unique_slug(connection: sqlite3.Connection, table: str, slug: str, skip_id: int | None) -> str:
    """Return ``slug``, suffixed with -2, -3... until it is free in ``table``."""

    taken = {
        row[0]
        for row in connection.execute(
            f"SELECT slug FROM {table} WHERE id IS NOT ?", (skip_id,)
        )
    }
    if slug not in taken:
        return slug
    index = 2
    while f"{slug}-{index}" in taken:
        index += 1
    return f"{slug}-{index}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogueError(message)


def _hub_lookup(connection: sqlite3.Connection) -> dict[str, int]:
    """Hub name (and the UI's ``name (category)`` label) -> hub id."""

    lookup: dict[str, int] = {}
    for row in load_hubs(connection):
        lookup[row["name"]] = row["id"]
        lookup[f"{row['name']} ({row['category']})"] = row["id"]
    return lookup


def save_hubs(connection: sqlite3.Connection, rows: Iterable[dict]) -> None:
    """Replace the hub table with ``rows`` (id=None inserts a new hub)."""

    rows = list(rows)
    seen: set[int] = set()
    with connection:
        for row in rows:
            identifier = row.get("id")
            name = str(row.get("name") or "").strip()
            _require(bool(name), "a hub needs a name")
            category = str(row.get("category") or "").strip().lower()
            _require(
                category in HUB_CATEGORIES,
                f"hub '{name}': category must be one of {', '.join(HUB_CATEGORIES)}",
            )
            values = (
                name,
                category,
                str(row.get("country")).strip() or None,
                float(row.get("x") or 0.0),
                float(row.get("y") or 0.0),
                row.get("elevation_m"),
                row.get("latitude"),
                row.get("longitude"),
                str(row.get("notes")).strip() or None,
            )
            if identifier is None:
                cursor = connection.execute(
                    "INSERT INTO hubs (name, category, country, x, y, elevation_m,"
                    " latitude, longitude, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
                seen.add(int(cursor.lastrowid))
            else:
                connection.execute(
                    "UPDATE hubs SET name=?, category=?, country=?, x=?, y=?,"
                    " elevation_m=?, latitude=?, longitude=?, notes=? WHERE id=?",
                    (*values, int(identifier)),
                )
                seen.add(int(identifier))

        # rows the grid no longer shows are deleted; a referenced hub is refused
        stale = [
            row[0]
            for row in connection.execute("SELECT id FROM hubs")
            if row[0] not in seen
        ]
        for identifier in stale:
            try:
                connection.execute("DELETE FROM hubs WHERE id=?", (identifier,))
            except sqlite3.IntegrityError as exc:
                raise CatalogueError(
                    f"hub {identifier} is still used by a link and cannot be deleted"
                ) from exc


def save_pipelines(connection: sqlite3.Connection, rows: Iterable[dict]) -> None:
    """Replace the pipeline-design table with ``rows``."""

    rows = list(rows)
    seen: set[int] = set()
    with connection:
        for row in rows:
            identifier = row.get("id")
            name = str(row.get("name") or "").strip()
            _require(bool(name), "a pipeline design needs a name")
            diameter = float(row.get("diameter_m") or 0.30)
            _require(diameter > 0.0, f"pipeline '{name}': the diameter must be positive")
            roughness = float(row.get("roughness_m") or 0.0)
            _require(roughness >= 0.0, f"pipeline '{name}': the roughness must not be negative")
            values = (
                name,
                diameter,
                row.get("wall_thickness_m"),
                roughness,
                str(row.get("material")).strip() or None,
                row.get("design_pressure_bar"),
                row.get("design_temperature_c"),
                str(row.get("notes")).strip() or None,
            )
            if identifier is None:
                try:
                    cursor = connection.execute(
                        "INSERT INTO pipelines (name, diameter_m, wall_thickness_m,"
                        " roughness_m, material, design_pressure_bar, design_temperature_c,"
                        " notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        values,
                    )
                except sqlite3.IntegrityError as exc:
                    raise CatalogueError(f"a pipeline design '{name}' already exists") from exc
                seen.add(int(cursor.lastrowid))
            else:
                connection.execute(
                    "UPDATE pipelines SET name=?, diameter_m=?, wall_thickness_m=?,"
                    " roughness_m=?, material=?, design_pressure_bar=?, design_temperature_c=?,"
                    " notes=? WHERE id=?",
                    (*values, int(identifier)),
                )
                seen.add(int(identifier))

        stale = [
            row[0]
            for row in connection.execute("SELECT id FROM pipelines")
            if row[0] not in seen
        ]
        for identifier in stale:
            connection.execute("DELETE FROM pipelines WHERE id=?", (identifier,))


def save_links(connection: sqlite3.Connection, rows: Iterable[dict]) -> None:
    """Replace the link table with ``rows``."""

    rows = list(rows)
    seen: set[int] = set()
    hubs = _hub_lookup(connection)
    pipelines = {row["name"]: row["id"] for row in load_pipelines(connection)}
    previous = {row["id"]: row for row in load_links(connection)}
    with connection:
        for row in rows:
            identifier = row.get("id")
            source = str(row.get("source_hub") or "").strip()
            destination = str(row.get("destination_hub") or "").strip()
            _require(bool(source) and bool(destination), "a link needs a source and a destination hub")
            _require(source in hubs, f"unknown source hub '{source}'")
            _require(destination in hubs, f"unknown destination hub '{destination}'")
            _require(source != destination, "a link cannot start and end at the same hub")
            mode = str(row.get("mode") or "").strip().lower()
            _require(mode in MODE_CODES, f"unknown transport mode '{mode}'")
            pipeline = str(row.get("pipeline") or "").strip()
            if pipeline and pipeline not in pipelines:
                raise CatalogueError(f"unknown pipeline design '{pipeline}'")
            if mode != "pipeline":
                pipeline = ""  # a design only applies to a pipeline link
            length = _link_length_km(connection, hubs[source], hubs[destination])
            if length is None and identifier is not None:
                # keep the length a migration brought over when the hubs have no coordinates
                length = (previous.get(int(identifier)) or {}).get("length_km")
            values = (
                hubs[source],
                hubs[destination],
                mode,
                pipelines.get(pipeline),
                float(row.get("capex_eur") or 0.0),
                float(row.get("opex_eur_per_t") or 0.0),
                length,
                str(row.get("notes")).strip() or None,
            )
            if identifier is None:
                try:
                    cursor = connection.execute(
                        "INSERT INTO links (source_hub_id, destination_hub_id, mode,"
                        " pipeline_id, capex_eur, opex_eur_per_t, length_km, notes)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        values,
                    )
                    seen.add(int(cursor.lastrowid))
                except sqlite3.IntegrityError as exc:
                    raise CatalogueError(f"a link {source} -> {destination} ({mode}) already exists") from exc
            else:
                connection.execute(
                    "UPDATE links SET source_hub_id=?, destination_hub_id=?, mode=?,"
                    " pipeline_id=?, capex_eur=?, opex_eur_per_t=?, length_km=?, notes=?"
                    " WHERE id=?",
                    (*values, int(identifier)),
                )
                seen.add(int(identifier))

        stale = [
            row[0] for row in connection.execute("SELECT id FROM links") if row[0] not in seen
        ]
        for identifier in stale:
            connection.execute("DELETE FROM links WHERE id=?", (identifier,))


def save_emitters(connection: sqlite3.Connection, rows: Iterable[dict]) -> None:
    """Replace the emitter table with ``rows`` (id=None inserts a new emitter)."""

    rows = list(rows)
    seen: set[int] = set()
    hubs = _hub_lookup(connection)
    with connection:
        for row in rows:
            identifier = row.get("id")
            name = str(row.get("name") or "").strip()
            _require(bool(name), "an emitter needs a name")
            slug = str(row.get("slug") or "").strip() or _slugify(name)
            _require(bool(slug) and not any(char.isspace() for char in slug),
                     f"emitter '{name}': the slug must not contain spaces")
            kind = str(row.get("curve") or "constant").strip()
            _require(
                kind in {"constant", "power_law", "piecewise_linear"},
                f"emitter '{name}': unknown curve '{kind}'",
            )
            values = {
                "slug": _unique_slug(connection, "emitters", slug, int(identifier) if identifier else None),
                "name": name,
                "industry": str(row.get("industry")).strip() or None,
                "curve": kind,
                "reference_year": _as_int(row.get("reference_year")),
                "e0_t_per_year": _as_float(row.get("e0_t_per_year")),
                "a": _as_float(row.get("a")),
                "c": _as_float(row.get("c")),
                "b": _as_float(row.get("b")),
                "constant_t_per_year": _as_float(row.get("constant_t_per_year")),
                "points": str(row.get("points")).strip() or None if kind == "piecewise_linear" else None,
                "activation_year": _as_int(row.get("activation_year")),
                "implementation_probability": _as_float(row.get("implementation_probability")),
                "hub_id": hubs.get(str(row.get("hub") or "").strip()),
                "reference_sink_id": str(row.get("sink")).strip() or None,
                "notes": None,
            }
            if kind == "power_law" and values["e0_t_per_year"] is None:
                raise CatalogueError(f"emitter '{name}': a power law needs E0")
            if kind == "piecewise_linear" and not values["points"]:
                raise CatalogueError(f"emitter '{name}': a piecewise curve needs its control points")

            if identifier is None:
                cursor = connection.execute(
                    "INSERT INTO emitters (slug, name, industry, curve, reference_year,"
                    " e0_t_per_year, a, c, b, constant_t_per_year, points, activation_year,"
                    " implementation_probability, hub_id, reference_sink_id)"
                    " VALUES (:slug, :name, :industry, :curve, :reference_year, :e0_t_per_year,"
                    " :a, :c, :b, :constant_t_per_year, :points, :activation_year,"
                    " :implementation_probability, :hub_id, :reference_sink_id)",
                    values,
                )
                seen.add(int(cursor.lastrowid))
            else:
                connection.execute(
                    "UPDATE emitters SET slug=:slug, name=:name, industry=:industry,"
                    " curve=:curve, reference_year=:reference_year, e0_t_per_year=:e0_t_per_year,"
                    " a=:a, c=:c, b=:b, constant_t_per_year=:constant_t_per_year,"
                    " points=:points, activation_year=:activation_year,"
                    " implementation_probability=:implementation_probability, hub_id=:hub_id,"
                    " reference_sink_id=:reference_sink_id WHERE id=:id",
                    {**values, "id": int(identifier)},
                )
                seen.add(int(identifier))

        stale = [
            row[0] for row in connection.execute("SELECT id FROM emitters") if row[0] not in seen
        ]
        for identifier in stale:
            connection.execute("DELETE FROM emitters WHERE id=?", (identifier,))


def save_storage(connection: sqlite3.Connection, rows: Iterable[dict]) -> None:
    """Replace the storage-site table with ``rows``."""

    rows = list(rows)
    seen: set[int] = set()
    hubs = _hub_lookup(connection)
    with connection:
        for row in rows:
            identifier = row.get("id")
            name = str(row.get("name") or "").strip()
            _require(bool(name), "a storage site needs a name")
            slug = str(row.get("slug") or "").strip() or _slugify(name)
            _require(bool(slug) and not any(char.isspace() for char in slug),
                     f"storage '{name}': the slug must not contain spaces")
            storage_type = str(row.get("storage_type") or "DSA").strip().upper()
            _require(
                storage_type in {"DSA", "DHF", "DGF", "DOF"},
                f"storage '{name}': unknown type '{storage_type}'",
            )
            wells = _as_int(row.get("well_number")) or 1
            diameter = _as_float(row.get("well_diameter_m")) or 0.30
            _require(wells >= 1, f"storage '{name}': the well number must be at least 1")
            _require(diameter > 0.0, f"storage '{name}': the well diameter must be positive")
            values = {
                "slug": _unique_slug(
                    connection, "storage_sites", slug, int(identifier) if identifier else None
                ),
                "name": name,
                "storage_type": storage_type,
                "capacity_t": float(row.get("capacity_mt") or 0.0) * 1e6,
                "depth_m": float(row.get("depth_m") or 0.0),
                "porosity": float(row.get("porosity") or 0.0),
                "permeability_m2": float(row.get("permeability_m2") or 0.0),
                "pressure_bar": float(row.get("pressure_bar") or 0.0),
                "temperature_c": float(row.get("temperature_c") or 0.0),
                "lithology": str(row.get("lithology")).strip() or None,
                "hub_id": hubs.get(str(row.get("hub") or "").strip()),
                "well_diameter_m": diameter,
                "well_number": wells,
                "notes": None,
            }
            if identifier is None:
                cursor = connection.execute(
                    "INSERT INTO storage_sites (slug, name, storage_type, capacity_t, depth_m,"
                    " porosity, permeability_m2, pressure_bar, temperature_c, lithology,"
                    " hub_id, well_diameter_m, well_number)"
                    " VALUES (:slug, :name, :storage_type, :capacity_t, :depth_m, :porosity,"
                    " :permeability_m2, :pressure_bar, :temperature_c, :lithology, :hub_id,"
                    " :well_diameter_m, :well_number)",
                    values,
                )
                seen.add(int(cursor.lastrowid))
            else:
                connection.execute(
                    "UPDATE storage_sites SET slug=:slug, name=:name, storage_type=:storage_type,"
                    " capacity_t=:capacity_t, depth_m=:depth_m, porosity=:porosity,"
                    " permeability_m2=:permeability_m2, pressure_bar=:pressure_bar,"
                    " temperature_c=:temperature_c, lithology=:lithology, hub_id=:hub_id,"
                    " well_diameter_m=:well_diameter_m, well_number=:well_number WHERE id=:id",
                    {**values, "id": int(identifier)},
                )
                seen.add(int(identifier))

        stale = [
            row[0]
            for row in connection.execute("SELECT id FROM storage_sites")
            if row[0] not in seen
        ]
        for identifier in stale:
            connection.execute("DELETE FROM storage_sites WHERE id=?", (identifier,))


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _as_int(value) -> int | None:
    number = _as_float(value)
    return None if number is None else int(round(number))


# -------------------------------------------------------------------- migration
def migrate_from_json(
    connection: sqlite3.Connection, json_directory: str | Path | None = None
) -> None:
    """Import the four JSON catalogues into an empty database."""

    directory = Path(json_directory) if json_directory is not None else JSON_DIRECTORY
    from .catalogue import load_hub_catalogue, load_network_catalogue, load_storage_catalogue
    from .emitter_catalogue import load_emitter_catalogue

    hub_ids: dict[str, int] = {}
    for record in load_hub_catalogue(directory / "hubs.json"):
        cursor = connection.execute(
            "INSERT INTO hubs (name, category, country, x, y, elevation_m, latitude,"
            " longitude, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.name,
                "chain",
                record.country,
                float(record.x),
                float(record.y),
                record.elevation_m,
                record.latitude,
                record.longitude,
                record.notes,
            ),
        )
        hub_ids[record.id] = int(cursor.lastrowid)

    for record in load_network_catalogue(directory / "network.json"):
        source = _ensure_hub(connection, hub_ids, record.from_node, record.x, record.y, record.elevation_m)
        destination = _ensure_hub(
            connection, hub_ids, record.to_node, record.x, record.y, record.elevation_m
        )
        if source == destination:  # pragma: no cover - defensive
            continue
        mode = LEGACY_KIND_TO_MODE.get(record.kind, "pipeline")
        try:
            connection.execute(
                "INSERT INTO links (source_hub_id, destination_hub_id, mode,"
                " capex_eur, opex_eur_per_t, length_km) VALUES (?, ?, ?, 0, 0, ?)",
                (source, destination, mode, float(record.length_km)),
            )
        except sqlite3.IntegrityError:  # the same pair and mode twice
            continue

    for record in load_emitter_catalogue(directory / "emitters.json"):
        curve = record.curve
        connection.execute(
            "INSERT INTO emitters (slug, name, industry, curve, reference_year, e0_t_per_year,"
            " a, c, b, constant_t_per_year, points, activation_year,"
            " implementation_probability, reference_sink_id, notes)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _unique_slug(connection, "emitters", record.id, None),
                record.name,
                record.industry,
                curve.kind if curve.kind != "polynomial" else "power_law",
                curve.reference_year,
                curve.e0_t_per_year,
                curve.a,
                curve.c,
                curve.b,
                curve.constant_t_per_year,
                _points_to_text(curve.points),
                record.activation_year,
                record.implementation_probability,
                record.reference_sink_id,
                record.notes,
            ),
        )

    for record in load_storage_catalogue(directory / "storage.json"):
        connection.execute(
            "INSERT INTO storage_sites (slug, name, storage_type, capacity_t, depth_m, porosity,"
            " permeability_m2, pressure_bar, temperature_c, lithology, well_diameter_m,"
            " well_number, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.30, 1, ?)",
            (
                _unique_slug(connection, "storage_sites", record.id, None),
                record.name,
                record.storage_type,
                float(record.capacity_t),
                float(record.depth_m),
                float(record.porosity),
                float(record.permeability_m2),
                float(record.pressure_bar),
                float(record.temperature_c),
                record.lithology,
                record.notes,
            ),
        )

    # every pipeline link starts on the default design until the user defines one
    connection.execute(
        "UPDATE links SET pipeline_id = (SELECT id FROM pipelines"
        " WHERE name = 'Default (0.30 m)') WHERE mode = 'pipeline' AND pipeline_id IS NULL"
    )

    connection.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema', 'gt-ccus-sqlite/1.0')"
    )
    connection.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('migrated_from', 'json')"
    )
    connection.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('migrated_on', ?)",
        (date.today().isoformat(),),
    )
    connection.commit()


def _ensure_hub(
    connection: sqlite3.Connection,
    hub_ids: dict[str, int],
    name: str,
    x: float,
    y: float,
    elevation: float,
) -> int:
    """Return the id of a hub called ``name``, creating a chain hub when needed."""

    if name in hub_ids:
        return hub_ids[name]
    # the legacy network file carries one coordinate per link, not per node: the
    # generated hub has no position, so the link keeps the length it was imported with
    cursor = connection.execute(
        "INSERT INTO hubs (name, category) VALUES (?, 'chain')",
        (name,),
    )
    hub_ids[name] = int(cursor.lastrowid)
    return hub_ids[name]


def _points_to_text(points) -> str | None:
    if not points:
        return None
    return ", ".join(f"{int(year)}: {float(value):g}" for year, value in sorted(points.items()))


# --------------------------------------------------------------------- snapshot
def export_snapshot(
    connection: sqlite3.Connection, json_directory: str | Path | None = None
) -> dict[str, Path]:
    """Write the JSON snapshot the engine reads; returns the files written."""

    directory = Path(json_directory) if json_directory is not None else JSON_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    hubs = load_hubs(connection)
    hub_by_id = {hub["id"]: hub for hub in hubs}
    pipeline_by_id = {row["id"]: row["name"] for row in load_pipelines(connection)}
    links = load_links(connection)
    emitters = load_emitters(connection)
    storage = load_storage(connection)

    files = {
        "hubs.json": _write_json(
            directory / "hubs.json",
            {
                "_meta": {
                    "schema": "gt-ccus-hubs/1.0",
                    "source": "ccus.sqlite3",
                    "generated": today,
                    "count": len(hubs),
                },
                "records": [
                    {
                        "id": hub["name"],
                        "name": hub["name"],
                        "category": hub["category"],
                        "country": hub["country"],
                        "latitude": hub["latitude"],
                        "longitude": hub["longitude"],
                        "x": round(float(hub["x"]), 1),
                        "y": round(float(hub["y"]), 1),
                        "elevation_m": hub["elevation_m"],
                    }
                    for hub in hubs
                ],
            },
        ),
        "network.json": _write_json(
            directory / "network.json",
            {
                "_meta": {
                    "schema": "gt-ccus-network/1.0",
                    "source": "ccus.sqlite3",
                    "generated": today,
                    "count": len(links),
                },
                "records": [
                    _link_snapshot(link, hub_by_id, pipeline_by_id) for link in links
                ],
            },
        ),
        "emitters.json": _write_json(
            directory / "emitters.json",
            {
                "_meta": {
                    "schema": "gt-ccus-emitters/1.0",
                    "source": "ccus.sqlite3",
                    "generated": today,
                    "count": len(emitters),
                },
                "emitters": [_emitter_snapshot(row, hub_by_id) for row in emitters],
            },
        ),
        "storage.json": _write_json(
            directory / "storage.json",
            {
                "_meta": {
                    "schema": "gt-ccus-storage/1.0",
                    "source": "ccus.sqlite3",
                    "generated": today,
                    "count": len(storage),
                },
                "records": [_storage_snapshot(row) for row in storage],
            },
        ),
    }
    return files


def _write_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _distance_km(source: dict, destination: dict) -> float | None:
    """Great-circle distance between two hubs (km), or ``None`` if unknown."""

    from ccus_core.geo.distance import great_circle_km

    lat1, lon1 = source.get("latitude"), source.get("longitude")
    lat2, lon2 = destination.get("latitude"), destination.get("longitude")
    if None not in (lat1, lon1, lat2, lon2):
        return round(great_circle_km(lat1, lon1, lat2, lon2), 2)
    x1, y1 = float(source.get("x") or 0.0), float(source.get("y") or 0.0)
    x2, y2 = float(destination.get("x") or 0.0), float(destination.get("y") or 0.0)
    if (x1, y1) == (x2, y2):
        return None
    return round(math.hypot(x2 - x1, y2 - y1) / 1000.0, 2)


def _link_length_km(
    connection: sqlite3.Connection, source_id: int, destination_id: int
) -> float | None:
    rows = {
        row["id"]: row
        for row in connection.execute(
            "SELECT id, x, y, latitude, longitude FROM hubs WHERE id IN (?, ?)",
            (source_id, destination_id),
        )
    }
    source, destination = rows.get(source_id), rows.get(destination_id)
    if source is None or destination is None:
        return None
    return _distance_km(dict(source), dict(destination))


def _link_snapshot(link: dict, hub_by_id: dict, pipeline_by_id: dict | None = None) -> dict:
    source = hub_by_id.get(link["source_hub_id"], {})
    destination = hub_by_id.get(link["destination_hub_id"], {})
    mode = link["mode"]
    kind = {"truck": "road", "marine": "ship"}.get(mode, mode)
    return {
        "id": f"L{int(link['id']):03d}",
        "name": f"{source.get('name', '?')} -> {destination.get('name', '?')}",
        "kind": kind,
        "mode": mode,
        "pipeline": (pipeline_by_id or {}).get(link.get("pipeline_id")),
        "from_node": source.get("name"),
        "to_node": destination.get("name"),
        "x": source.get("x"),
        "y": source.get("y"),
        "elevation_m": source.get("elevation_m"),
        "length_km": link.get("length_km")
        if link.get("length_km") is not None
        else _distance_km(source, destination),
        "capex_eur": link.get("capex_eur"),
        "opex_eur_per_t": link.get("opex_eur_per_t"),
    }


def _emitter_snapshot(row: dict, hub_by_id: dict) -> dict:
    hub = hub_by_id.get(row.get("hub_id"))
    curve: dict[str, Any] = {"kind": row["curve"]}
    if row["curve"] == "power_law":
        curve.update(
            reference_year=row.get("reference_year"),
            e0_t_per_year=row.get("e0_t_per_year"),
            a=row.get("a"),
            c=row.get("c"),
            b=row.get("b"),
        )
    elif row["curve"] == "piecewise_linear":
        curve["points"] = _points_from_text(row.get("points"))
    else:
        curve["constant_t_per_year"] = row.get("constant_t_per_year")
    return {
        "id": row["slug"],
        "name": row["name"],
        "industry": row.get("industry"),
        "node_id": hub["name"] if hub else None,
        "curve": curve,
        "implementation_probability": row.get("implementation_probability"),
        "activation_year": row.get("activation_year"),
        "reference_sink_id": row.get("reference_sink_id"),
        "notes": row.get("notes"),
    }


def _storage_snapshot(row: dict) -> dict:
    return {
        "id": row["slug"],
        "name": row["name"],
        "storage_type": row["storage_type"],
        "capacity_t": float(row["capacity_t"]),
        "depth_m": float(row["depth_m"]),
        "porosity": float(row["porosity"]),
        "permeability_m2": float(row["permeability_m2"]),
        "pressure_bar": float(row["pressure_bar"]),
        "temperature_c": float(row["temperature_c"]),
        "lithology": row.get("lithology"),
        "well_diameter_m": float(row["well_diameter_m"]),
        "well_number": int(row["well_number"]),
        "notes": row.get("notes"),
    }


def _points_from_text(value) -> dict[int, float] | None:
    if not value:
        return None
    points: dict[int, float] = {}
    for chunk in str(value).replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        year, _, emissions = chunk.partition(":")
        points[int(year.strip())] = float(emissions.strip())
    return points or None


__all__ = [
    "BACKUP_DIRECTORY",
    "CatalogueError",
    "DEFAULT_DB_PATH",
    "JSON_DIRECTORY",
    "MODES",
    "MODE_CODES",
    "REQUIRED_TABLES",
    "SQLITE_HEADER",
    "backup_database",
    "connect",
    "database_bytes",
    "database_path",
    "ensure_database",
    "export_snapshot",
    "initialise",
    "inspect_database",
    "is_empty",
    "load_emitters",
    "load_hubs",
    "load_links",
    "load_modes",
    "load_pipelines",
    "load_storage",
    "migrate_from_json",
    "restore_database",
    "save_emitters",
    "save_hubs",
    "save_links",
    "save_pipelines",
    "save_storage",
]