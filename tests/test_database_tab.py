"""The database layer: SQLite store, JSON snapshot and the Database tab.

The catalogues live in SQLite (``data/ccus.sqlite3``): auto-increment integer ids,
a foreign key from a link to the hubs it connects, unique slugs and checked
vocabularies.  The JSON files under ``json/`` are the snapshot the engine reads.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from ccus_core.io import (
    load_emitter_catalogue,
    load_hub_catalogue,
    load_network_catalogue,
    load_storage_catalogue,
)
from ccus_core.io import sqlite_catalogue as store
from ccus_core.io.sqlite_catalogue import CatalogueError
from streamlit_app.app import (
    DATABASE_COLUMNS,
    HUB_COLUMNS,
    NETWORK_COLUMNS,
    STORAGE_COLUMNS,
    emitter_database_rows,
    emitter_record_from_row,
    hub_database_rows,
    hub_record_from_row,
    network_database_rows,
    network_record_from_row,
    storage_database_rows,
    storage_record_from_row,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit_app" / "app.py"
JSON = ROOT / "json"


@pytest.fixture
def database(tmp_path):
    """A fresh catalogue database, migrated from a private copy of the snapshot.

    The snapshot copy keeps the tests from writing into the repository's ``json/``.
    """

    path = tmp_path / "ccus.sqlite3"
    snapshot = tmp_path / "json"
    shutil.copytree(JSON, snapshot)
    with patch.object(store, "DEFAULT_DB_PATH", path), patch.object(
        store, "JSON_DIRECTORY", snapshot
    ):
        connection = store.ensure_database()
        yield path, connection
        connection.close()


def _names(connection, table: str, loader) -> list[str]:
    return [row["name"] for row in loader(connection)]


# ------------------------------------------------------------------ migration
def test_the_json_catalogues_migrate_into_sqlite(database):
    _, connection = database

    assert store._count(connection, "hubs") >= len(load_hub_catalogue(JSON / "hubs.json"))
    hub_names = {row["name"] for row in store.load_hubs(connection)}
    assert {record.name for record in load_hub_catalogue(JSON / "hubs.json")} <= hub_names
    # every endpoint of every link resolves to a hub, whether the snapshot already
    # carried it or the migration had to create it
    links = load_network_catalogue(JSON / "network.json")
    endpoints = {record.from_node for record in links} | {record.to_node for record in links}
    assert endpoints <= hub_names
    # the database refuses a second link between the same hubs with the same mode
    unique_links = {
        (record.from_node, record.to_node, {"road": "truck", "ship": "marine"}.get(record.kind, record.kind))
        for record in load_network_catalogue(JSON / "network.json")
    }
    assert store._count(connection, "links") == len(unique_links)
    assert store._count(connection, "emitters") == len(
        load_emitter_catalogue(JSON / "emitters.json")
    )
    assert store._count(connection, "storage_sites") == len(
        load_storage_catalogue(JSON / "storage.json")
    )
    # the transport vocabulary is seeded once, in one place
    assert [row["code"] for row in store.load_modes(connection)] == ["marine", "pipeline", "rail", "truck"]


# ------------------------------------------------------------------ identities
def test_ids_are_auto_increment_and_never_reused(database):
    _, connection = database
    first = store.load_hubs(connection)[-1]["id"]

    store.save_hubs(
        connection,
        [*store.load_hubs(connection), {**_hub_row(), "name": "Brand new hub", "id": None}],
    )
    second = [hub for hub in store.load_hubs(connection) if hub["name"] == "Brand new hub"][0]["id"]
    assert second > first

    store.save_hubs(
        connection,
        [hub for hub in store.load_hubs(connection) if hub["name"] != "Brand new hub"],
    )
    store.save_hubs(
        connection,
        [*store.load_hubs(connection), {**_hub_row(), "name": "Brand new hub again", "id": None}],
    )
    third = [
        hub for hub in store.load_hubs(connection) if hub["name"] == "Brand new hub again"
    ][0]["id"]
    assert third > second  # AUTOINCREMENT does not hand out a deleted id


def _hub_row(**overrides) -> dict:
    row = {
        "id": None,
        "name": "Hub",
        "category": "chain",
        "country": "HR",
        "x": 5074167.7,
        "y": 2587499.8,
        "elevation_m": 200.0,
    }
    row.update(overrides)
    return row


def test_a_link_must_connect_two_existing_hubs(database):
    _, connection = database
    hub = store.load_hubs(connection)[0]

    with pytest.raises(CatalogueError, match="destination hub"):
        store.save_links(
            connection,
            [
                {
                    "id": None,
                    "source_hub": hub["name"],
                    "destination_hub": "no such hub",
                    "mode": "pipeline",
                }
            ],
        )


def test_a_link_cannot_start_and_end_at_the_same_hub(database):
    _, connection = database
    hub = store.load_hubs(connection)[0]

    with pytest.raises(CatalogueError, match="same hub"):
        store.save_links(
            connection,
            [
                {
                    "id": None,
                    "source_hub": hub["name"],
                    "destination_hub": hub["name"],
                    "mode": "pipeline",
                }
            ],
        )


def test_pipeline_designs_are_linked_to_a_link(database):
    _, connection = database
    store.save_pipelines(
        connection,
        [
            {
                "id": None,
                "name": "DN300 / 150 bar",
                "diameter_m": 0.30,
                "wall_thickness_m": 0.012,
                "roughness_m": 4.5e-5,
                "material": "steel",
                "design_pressure_bar": 150.0,
                "design_temperature_c": 20.0,
            }
        ],
    )
    design = [row for row in store.load_pipelines(connection) if row["name"] == "DN300 / 150 bar"][0]
    hub = store.load_hubs(connection)[0]
    other = store.load_hubs(connection)[1]

    store.save_links(
        connection,
        [
            {
                "id": None,
                "source_hub": hub["name"],
                "destination_hub": other["name"],
                "mode": "pipeline",
                "pipeline": "DN300 / 150 bar",
            }
        ],
    )

    link = store.load_links(connection)[-1]
    assert link["pipeline_id"] == design["id"]

    with pytest.raises(CatalogueError, match="pipeline design"):
        store.save_links(
            connection,
            [
                {
                    "id": None,
                    "source_hub": hub["name"],
                    "destination_hub": other["name"],
                    "mode": "pipeline",
                    "pipeline": "no such design",
                }
            ],
        )


def test_a_duplicate_slug_gets_a_suffix(database):
    _, connection = database
    store.save_emitters(
        connection,
        [
            {"id": None, "slug": "same-name", "name": "Same name", "curve": "constant"},
            {"id": None, "slug": "same-name", "name": "Same name", "curve": "constant"},
        ],
    )

    slugs = [row["slug"] for row in store.load_emitters(connection)]
    assert slugs[-2:] == ["same-name", "same-name-2"]


# ------------------------------------------------------------------- snapshot
def test_the_snapshot_round_trips(database, tmp_path):
    _, connection = database
    snapshot = tmp_path / "json"

    store.export_snapshot(connection, snapshot)

    assert (snapshot / "emitters.json").is_file()
    assert (snapshot / "hubs.json").is_file()
    assert (snapshot / "network.json").is_file()
    assert (snapshot / "storage.json").is_file()

    emitters = json.loads((snapshot / "emitters.json").read_text(encoding="utf-8"))
    assert emitters["_meta"]["count"] == store._count(connection, "emitters")
    assert emitters["emitters"][0]["id"] == store.load_emitters(connection)[0]["slug"]

    storage = json.loads((snapshot / "storage.json").read_text(encoding="utf-8"))
    assert storage["records"][0]["well_diameter_m"] == pytest.approx(0.30)
    assert storage["records"][0]["well_number"] == 1

    links = json.loads((snapshot / "network.json").read_text(encoding="utf-8"))
    assert links["_meta"]["count"] == store._count(connection, "links")
    # the imported GIS length survives when the hubs carry no coordinates
    assert links["records"][0]["length_km"] == pytest.approx(
        load_network_catalogue(JSON / "network.json")[0].length_km
    )


def test_a_noop_save_keeps_the_link_lengths(database):
    _, connection = database
    before = [row["length_km"] for row in store.load_links(connection)]
    hubs = {row["id"]: row["name"] for row in store.load_hubs(connection)}
    rows = [
        {
            "id": row["id"],
            "source_hub": hubs[row["source_hub_id"]],
            "destination_hub": hubs[row["destination_hub_id"]],
            "mode": row["mode"],
        }
        for row in store.load_links(connection)
    ]

    store.save_links(connection, rows)

    assert [row["length_km"] for row in store.load_links(connection)] == before


# -------------------------------------------------------------------- builders
def test_hub_row_validates_the_category():
    with pytest.raises(ValueError, match="category"):
        hub_record_from_row(_hub_row(category="depot"))


def test_network_row_rejects_a_self_link():
    with pytest.raises(ValueError, match="same hub"):
        network_record_from_row(
            {"source_hub": "A", "destination_hub": "A", "mode": "pipeline"}
        )


def test_storage_row_defaults_the_well():
    record = storage_record_from_row(
        {"name": "Site", "storage_type": "DSA", "capacity_mt": 10.0, "depth_m": 1500.0}
    )
    assert record["well_diameter_m"] == pytest.approx(0.30)
    assert record["well_number"] == 1


def test_emitter_row_validates_the_curve():
    with pytest.raises(ValueError):
        emitter_record_from_row(
            {"name": "Plant", "curve": "power_law", "e0_t_per_year": None}
        )


# ---------------------------------------------------------------- the UI table
def _editor(app, key):
    """The data editor with ``key``, wherever the tab layout puts it."""

    return next(item for item in app.data_editor if item.key == key)


def _app(database):
    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()
    return app


def test_database_is_the_last_tab_with_four_grids(database):
    app = _app(database)

    assert not [item.value for item in app.exception]
    assert not [item.value for item in app.error]
    assert [tab.label for tab in app.tabs][-1] == "Database"

    frames = [frame.value for frame in app.dataframe]
    assert any("storage_options" in frame.columns for frame in frames) is False
    assert any("category" in frame.columns for frame in frames)
    assert any("source_hub" in frame.columns for frame in frames)
    assert any("storage_type" in frame.columns for frame in frames)
    assert any("industry" in frame.columns for frame in frames)
    # three Scenario editors (hubs, links, geothermal) + five Inputs + five Database
    assert len(app.data_editor) == 11
    assert not app.form


def test_the_id_column_stays_out_of_the_grid(database):
    _, connection = database
    rows = hub_database_rows()
    assert list(rows[0]) == HUB_COLUMNS
    assert rows[0]["id"] == store.load_hubs(connection)[0]["id"]


def test_a_new_hub_is_written_to_the_store(database):
    path, connection = database
    before = store._count(connection, "hubs")

    with patch.object(store, "DEFAULT_DB_PATH", path):
        app = _app(database)
        app.session_state["db_hubs_editor"] = {
            "edited_rows": {},
            "added_rows": [_hub_row(name="UI hub", category="source")],
            "deleted_rows": [],
        }
        app.button(key="db_save_database").click().run()

        assert not [item.value for item in app.exception]
        assert not [item.value for item in app.error]
        hubs = store.load_hubs(connection)

    assert len(hubs) == before + 1
    assert hubs[-1]["name"] == "UI hub"
    assert hubs[-1]["category"] == "source"
    assert any("Database saved" in str(item.value) for item in app.success)


def test_a_new_link_and_emitter_reference_the_hub(database):
    path, connection = database
    hub = next(row for row in store.load_hubs(connection) if row["name"] == "HR.CH.001")

    with patch.object(store, "DEFAULT_DB_PATH", path):
        app = _app(database)
        app.session_state["db_network_editor"] = {
            "edited_rows": {},
            "added_rows": [
                {
                    "id": None,
                    "source_hub": hub["name"],
                    "destination_hub": hub["name"],
                    "mode": "pipeline",
                }
            ],
            "deleted_rows": [],
        }
        app.button(key="db_save_database").click().run()
        assert any("same hub" in str(item.value) for item in app.error)

        app.session_state["db_network_editor"] = {
            "edited_rows": {},
            "added_rows": [
                {
                    "id": None,
                    "source_hub": hub["name"],
                    "destination_hub": "HRES002",
                    "mode": "rail",
                    "pipeline": None,
                }
            ],
            "deleted_rows": [],
        }
        app.button(key="db_save_database").click().run()
        assert not [item.value for item in app.error]

        app.session_state["db_emitters_editor"] = {
            "edited_rows": {},
            "added_rows": [
                {
                    "id": None,
                    "slug": "ui_plant",
                    "name": "UI plant",
                    "industry": "refinery",
                    "curve": "constant",
                    "emissions": 50_000.0,
                    "activation_year": 2030,
                    "implementation_probability": 1.0,
                    "hub": hub["name"],
                }
            ],
            "deleted_rows": [],
        }
        app.button(key="db_save_database").click().run()

        links = store.load_links(connection)
        emitters = store.load_emitters(connection)

    assert len(links) == 12
    assert links[-1]["mode"] == "rail"
    assert emitters[-1]["slug"] == "ui_plant"
    assert emitters[-1]["name"] == "UI plant"


def test_saving_without_edits_changes_nothing(database, tmp_path):
    path, connection = database
    snapshot = tmp_path / "json"
    store.export_snapshot(connection, snapshot)
    before = {file.name: file.read_text(encoding="utf-8") for file in snapshot.glob("*.json")}

    with patch.object(store, "DEFAULT_DB_PATH", path):
        app = _app(database)
        app.button(key="db_save_database").click().run()

        assert not [item.value for item in app.error]
        store.export_snapshot(connection, snapshot)

    assert {file.name: file.read_text(encoding="utf-8") for file in snapshot.glob("*.json")} == before
    assert any("No changes" in str(item.value) for item in app.info)


def test_the_snapshot_lives_next_to_the_store(database, tmp_path):
    """The app writes the snapshot into json/ so the engine keeps working."""

    path, connection = database
    with patch.object(store, "DEFAULT_DB_PATH", path), patch.object(
        store, "JSON_DIRECTORY", tmp_path / "json"
    ):
        store.export_snapshot(connection)
        assert (tmp_path / "json" / "emitters.json").is_file()


def test_loaders_agree_with_the_snapshot(database):
    _, connection = database
    assert len(hub_database_rows()) == store._count(connection, "hubs")
    assert len(network_database_rows()) == store._count(connection, "links")
    assert len(storage_database_rows()) == store._count(connection, "storage_sites")
    assert len(emitter_database_rows(None, 2030)) == store._count(connection, "emitters")


def test_hub_names_are_used_for_the_link_columns(database):
    rows = network_database_rows()
    names = {row["name"] for row in hub_database_rows()}
    assert rows
    assert all(row["source_hub"] in names for row in rows)
    assert all(row["destination_hub"] in names for row in rows)


def test_the_network_table_has_the_requested_columns(database):
    assert list(network_database_rows()[0]) == NETWORK_COLUMNS
    assert list(storage_database_rows()[0]) == STORAGE_COLUMNS
    assert list(emitter_database_rows(None, 2030)[0]) == DATABASE_COLUMNS


# ------------------------------------------------------- the new scenario tab
def test_the_scenario_tab_comes_first_and_owns_the_links(database):
    app = _app(database)

    assert not [item.value for item in app.exception]
    labels = [tab.label for tab in app.tabs]
    assert labels[0] == "Scenario"
    assert labels[-1] == "Database"

    # the first editor is the links table, and it still carries the route columns
    first = _editor(app, 'editor_routes').value
    for column in ("id", "name", "from_node", "to_node", "mode", "distance_km"):
        assert column in first.columns


def test_a_hub_tick_survives_one_click(database):
    """One click on "on map" must stick - it used to take two."""

    app = _app(database)
    # the first row is a hub with coordinates, so its tick is live
    assert bool(_editor(app, "editor_nodes").value.loc[0, "map"])

    # one interaction: untick the first hub
    app.session_state["editor_nodes"] = {
        "edited_rows": {0: {"map": False}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run()

    # the edit is stored before the grid is rebuilt ...
    assert not bool(app.session_state["frames"]["nodes"].loc[0, "map"])
    # ... and the rerun the app triggers shows it
    app.run()
    assert not [item.value for item in app.exception]
    assert not bool(_editor(app, "editor_nodes").value.loc[0, "map"])


def test_a_new_scenario_starts_without_links(database):
    """A new study has emitters and sinks but no network - links are what it decides."""

    app = _app(database)
    assert len(_editor(app, "editor_routes").value) > 0

    app.button(key="btn_new_scenario").click().run()

    assert not [item.value for item in app.exception]
    assert len(app.session_state["frames"]["routes"]) == 0
    assert len(app.session_state["frames"]["nodes"]) > 0


def test_delete_selected_removes_every_ticked_link(database):
    """Tick all, delete once: ten links must go, not one."""

    app = _app(database)
    before = len(_editor(app, "editor_routes").value)
    assert before > 1

    app.button(key="links_check_all").click().run()
    assert bool(_editor(app, "editor_routes").value["sel"].all())

    app.button(key="links_delete_button").click().run()

    assert not [item.value for item in app.exception]
    assert len(app.session_state["frames"]["routes"]) == 0


def test_delete_selected_leaves_the_unticked_links(database):
    app = _app(database)
    before = len(_editor(app, "editor_routes").value)

    # tick only the first row
    app.session_state["editor_routes"] = {
        "edited_rows": {0: {"sel": True}},
        "added_rows": [],
        "deleted_rows": [],
    }
    app.run()
    app.button(key="links_delete_button").click().run()

    assert not [item.value for item in app.exception]
    assert len(app.session_state["frames"]["routes"]) == before - 1


def test_delete_all_links_clears_the_table_in_one_click(database):
    app = _app(database)
    before = len(_editor(app, "editor_routes").value)
    assert before > 1

    # the button stays disabled until the deletion is confirmed
    app.checkbox(key="links_clear_confirm").check()
    app.run()
    app.button(key="links_clear_button").click().run()

    assert not [item.value for item in app.exception]
    assert len(app.session_state["frames"]["routes"]) == 0


def test_the_link_builder_explains_itself(database):
    """Clicking "New link" has to say what to do next."""

    app = _app(database)

    app.session_state["link_step"] = "inlet"
    app.run()
    assert any("inlet of the new link" in str(item.value) for item in app.info)

    app.session_state["link_step"] = "outlet"
    app.session_state["link_inlet"] = "holcim"
    app.run()
    assert any("Inlet: holcim" in str(item.value) for item in app.info)


def test_the_database_tab_offers_a_backup_and_a_restore(database):
    from streamlit_app.app import DB_BACKUP_NAME

    app = _app(database)

    downloads = list(app.download_button)
    assert len(downloads) == 1, "the catalogue needs exactly one download button"
    assert downloads[0].label == "Download database"
    # the file the user gets, as asked for by the study
    assert DB_BACKUP_NAME == "gt_ccus_db.sqlite"

    uploads = list(app.file_uploader)
    assert len(uploads) == 1, "the catalogue needs exactly one upload button"
    assert uploads[0].label == "Upload database (gt_ccus_db.sqlite)"


def test_the_scenario_tab_shows_the_hubs_first(database):
    app = _app(database)

    frames = [frame.value for frame in app.dataframe]
    hub_frames = [frame for frame in frames if "kind" in frame.columns and "links" in frame.columns]

    assert hub_frames, "the hub table belongs at the top of the Scenario tab"
    # the leading tick decides whether the hub is drawn
    assert list(hub_frames[0].columns)[:3] == ["map", "id", "name"]
    assert {"kind", "latitude", "longitude"} <= set(hub_frames[0].columns)
    # the degree is consistent with the links table
    assert hub_frames[0]["links"].sum() % 2 == 0


def test_the_links_can_be_saved_without_running(database, tmp_path, monkeypatch):
    from ccus_core.io import scenario_repository

    monkeypatch.setenv(scenario_repository.SCENARIO_DIRECTORY_ENV, str(tmp_path))
    app = _app(database)

    app.button(key="btn_save_links").click().run()

    assert not [item.value for item in app.exception]
    assert not [item.value for item in app.error]

    written = sorted(tmp_path.glob("*.json"))
    assert written, "saving the section must write the scenario file"
    saved = json.loads(written[0].read_text(encoding="utf-8"))
    scenario = saved.get("scenario", saved)
    assert scenario.get("edges"), "the saved scenario keeps its links"


def test_the_backup_button_carries_the_whole_database(database):
    """The download must be the live file, not a re-render of the tables."""

    path, _ = database
    with patch.object(store, "DEFAULT_DB_PATH", path):
        payload = store.database_bytes()

    assert payload == path.read_bytes()
    assert payload.startswith(b"SQLite format 3")


# ------------------------------------------------------- adding a catalogue link
def test_the_add_button_appends_a_candidate_link(database):
    app = _app(database)
    before = len(_editor(app, 'editor_routes').value)

    app.button(key="add_link_button").click().run()

    assert not [item.value for item in app.exception]
    after = len(_editor(app, 'editor_routes').value)
    assert after == before + 1

    added = _editor(app, 'editor_routes').value.iloc[-1]
    assert added["from_node"] and added["to_node"]
    assert added["mode"]
    # a pipeline link needs a capacity, and the row carries one
    assert added["capacity_t_per_year"] and added["capacity_t_per_year"] > 0
    assert any("Link added to the scenario" in str(item.value) for item in app.success)


def test_the_added_link_can_be_applied(database):
    """End to end: the row the button adds must survive Apply and run."""

    app = _app(database)
    app.button(key="add_link_button").click().run()
    assert not [item.value for item in app.exception]

    apply_button = next(item for item in app.button if item.label == "Apply and run")
    apply_button.click().run()

    assert not [item.value for item in app.exception]
    assert not [item.value for item in app.error]