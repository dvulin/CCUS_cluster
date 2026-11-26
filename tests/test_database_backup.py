"""Backup and restore of the catalogue database (``gt_ccus_db.sqlite``).

The database is git-ignored and holds every catalogue edit, so the app needs a way
to get the whole thing out and back in.  A restore replaces *everything*, which is
why the file is validated before it is allowed anywhere near the live database.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from ccus_core.io import sqlite_catalogue as store
from ccus_core.io.sqlite_catalogue import CatalogueError

ROOT = Path(__file__).resolve().parents[1]
JSON = ROOT / "json"


@pytest.fixture
def database(tmp_path):
    """A catalogue database built from a private copy of the snapshot.

    Every path the store can write to is redirected into ``tmp_path`` for the
    whole test: a restore writes the database, the JSON snapshot *and* a backup,
    and none of them may land in the repository.
    """

    path = tmp_path / "ccus.sqlite3"
    snapshot = tmp_path / "json"
    shutil.copytree(JSON, snapshot)
    with patch.object(store, "DEFAULT_DB_PATH", path), patch.object(
        store, "JSON_DIRECTORY", snapshot
    ), patch.object(store, "BACKUP_DIRECTORY", tmp_path / "backups"):
        connection = store.ensure_database()
        connection.close()
        yield path, snapshot


def _counts(path) -> dict:
    connection = sqlite3.connect(path)
    try:
        return {
            table: connection.execute(f"select count(*) from {table}").fetchone()[0]
            for table in ("hubs", "links", "emitters", "storage_sites")
        }
    finally:
        connection.close()


# ------------------------------------------------------------------- the bytes
def test_the_bytes_are_the_file_on_disk(database):
    path, _ = database

    assert store.database_bytes() == path.read_bytes()
    assert store.database_path() == path


def test_a_missing_database_is_reported_not_invented(tmp_path):
    with patch.object(store, "DEFAULT_DB_PATH", tmp_path / "absent.sqlite3"):
        with pytest.raises(CatalogueError, match="does not exist"):
            store.database_bytes()


# ------------------------------------------------------------------ inspection
def test_a_real_catalogue_passes_inspection(database):
    path, _ = database

    summary = store.inspect_database(store.database_bytes())

    assert summary["schema_version"] == store.SCHEMA_VERSION
    assert summary["counts"]["hubs"] == _counts(path)["hubs"]
    assert summary["counts"]["storage_sites"] == _counts(path)["storage_sites"]


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"this is not a database at all",
        b"SQLite format 3\x00" + b"\x00" * 64,  # right signature, no schema
    ],
)
def test_a_file_that_is_not_a_catalogue_is_refused(payload):
    with pytest.raises(CatalogueError):
        store.inspect_database(payload)


def test_another_apps_sqlite_file_is_refused(tmp_path):
    """A valid SQLite file without our tables must not be accepted."""

    foreign = tmp_path / "other.sqlite3"
    connection = sqlite3.connect(foreign)
    connection.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, total REAL)")
    connection.commit()
    connection.close()

    with pytest.raises(CatalogueError, match="missing table"):
        store.inspect_database(foreign.read_bytes())


def test_a_database_from_another_schema_version_is_refused(database, tmp_path):
    path, _ = database
    data = store.database_bytes()

    # pretend the file was written by an older layout
    connection = sqlite3.connect(path)
    connection.execute("UPDATE meta SET value = '999' WHERE key = 'schema_version'")
    connection.commit()
    connection.close()

    with pytest.raises(CatalogueError, match="schema 999"):
        store.inspect_database(store.database_bytes())

    # leave the fixture usable for the following tests
    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(store.SCHEMA_VERSION),)
    )
    connection.commit()
    connection.close()
    assert store.inspect_database(data)["schema_version"] == store.SCHEMA_VERSION


# ---------------------------------------------------------------------- backup
def test_a_backup_is_a_timestamped_copy(database):
    path, _ = database

    copy = store.backup_database()

    assert copy.parent == store.BACKUP_DIRECTORY
    assert copy.name.startswith("ccus_") and copy.suffix == ".sqlite"
    assert copy.read_bytes() == path.read_bytes()


def test_two_backups_inside_the_same_second_do_not_overwrite(tmp_path, database):
    path, _ = database

    first = store.backup_database(directory=tmp_path)
    second = store.backup_database(directory=tmp_path)

    assert first != second
    assert first.is_file() and second.is_file()


# --------------------------------------------------------------------- restore
def test_a_restore_replaces_the_catalogue_and_refreshes_the_snapshot(database):
    path, snapshot = database
    before = store.database_bytes()

    # change something recognisable, then restore the original bytes
    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM links")
    connection.commit()
    connection.close()
    assert _counts(path)["links"] == 0

    summary = store.restore_database(before)

    assert _counts(path) == _counts(store.database_path())
    assert _counts(path)["links"] == 11
    assert summary["backup"] is not None
    assert Path(summary["backup"]).is_file()
    assert "hubs.json" in summary["snapshot"]
    assert (snapshot / "hubs.json").is_file()


def test_a_restore_can_skip_the_backup(database, tmp_path):
    path, _ = database
    before = store.database_bytes()

    summary = store.restore_database(before, backup=False)

    assert summary["backup"] is None
    assert _counts(path)["links"] == 11


def test_an_invalid_restore_leaves_the_database_alone(database):
    path, _ = database
    before = path.read_bytes()

    with pytest.raises(CatalogueError):
        store.restore_database(b"not a database")

    assert path.read_bytes() == before


def test_a_restore_into_a_named_path_leaves_the_live_one_alone(database, tmp_path):
    _, _ = database
    source = store.database_bytes()
    target = tmp_path / "restored.sqlite3"

    summary = store.restore_database(source, target)

    assert target.is_file()
    assert Path(summary["restored_to"]) == target
    assert summary["snapshot"]  # the snapshot was refreshed