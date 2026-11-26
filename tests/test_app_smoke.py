"""Language-agnostic smoke test of the Streamlit presentation layer."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py"
RUN_LABELS = ("Apply", "Primijeni")
STATUS_PREFIXES = (
    "Scenario is up to date",
    "Scenario changed",
    "Scenario has not been run",
    "Scenario error",
    "Scenarij je aktualan",
    "Scenarij je izmijenjen",
    "Scenarij nije pokrenut",
)


def _banner(app):
    """The status banner text, whichever status widget it was rendered with."""

    for kind in ("success", "warning", "info", "error"):
        for element in getattr(app, kind, []):
            if str(element.value).startswith(STATUS_PREFIXES):
                return str(element.value)
    return None


def _metric(app, prefix: str):
    """Value of the first metric whose label starts with ``prefix``."""

    for metric in app.metric:
        if str(metric.label).startswith(prefix):
            return str(metric.value)
    return None


def test_database_tab_lists_the_whole_catalogue():
    """The Database tab (last) shows every catalogue emitter in an editable table."""

    from ccus_core.io import load_emitter_catalogue

    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()

    assert not [item.value for item in app.exception]
    assert not [item.value for item in app.error]
    assert [tab.label for tab in app.tabs][-1] == "Database"

    records = load_emitter_catalogue()
    tables = [
        frame.value
        for frame in app.dataframe
        if hasattr(frame, "value") and "industry" in list(frame.value.columns)
    ]
    assert tables, "the Database table must be rendered"
    assert len(tables[0]) == len(records)
    assert list(tables[0]["slug"]) == [record.id for record in records]
    # the catalogue is editable: one grid per table and one save button for all
    assert any(button.label.startswith("Save database") for button in app.button)
    assert not app.form


def test_source_option_reports_the_real_emitter_count():
    """K16: the radio label must describe the file that is actually loaded."""

    from streamlit_app.app import DEFAULT_CLUSTER
    from streamlit_app.i18n import strings

    app = AppTest.from_file(str(APP), default_timeout=300)
    app.run()

    count = len(DEFAULT_CLUSTER and __import__("ccus_core").io.load_file(DEFAULT_CLUSTER).emitters)
    labels = app.radio[0].options
    assert labels[0] == strings("en")["source_cluster"].format(count=count)
    # the stale label promised 14 emitters for a 3-emitter file
    assert "14" not in labels[0]
    assert app.radio[0].value == "cluster"


def test_apply_without_edits_keeps_the_reported_numbers():
    """Apply must be lossless: zero edits, zero change in NPV."""

    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()
    run_button = next(button for button in app.button if button.label.startswith(RUN_LABELS))
    run_button.click().run()
    npv_after_run = _metric(app, "NPV")
    assert npv_after_run is not None

    apply_button = next(button for button in app.button if button.label.startswith("Apply"))
    apply_button.click().run()

    assert not [item.value for item in app.exception]
    assert _metric(app, "NPV") == npv_after_run


def test_banner_is_truthful_after_apply_without_any_edit():
    """NEW-02: the banner must not lag one interaction behind the Apply click.

    Before the fix the banner was written above the tab bodies, so the rerun that
    handled the Apply click still described the state *before* the click and only
    the next unrelated rerun showed "Scenario changed - run again" although nothing
    had changed.
    """

    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()
    assert _banner(app) == "Scenario has not been run"

    run_button = next(button for button in app.button if button.label.startswith(RUN_LABELS))
    run_button.click().run()
    assert _banner(app) == "Scenario is up to date"

    apply_button = next(
        button for button in app.button if button.label.startswith("Apply")
    )
    apply_button.click().run()

    assert not [item.value for item in app.exception]
    assert _banner(app) == "Scenario is up to date"
    # an unrelated rerun (a slider move in the browser) must not flip the banner
    app.run()
    assert _banner(app) == "Scenario is up to date"


def test_app_renders_the_configuration_tables():
    app = AppTest.from_file(str(APP), default_timeout=300)
    app.run()

    assert not [item.value for item in app.exception]
    assert any("CCUS cluster" in title.value for title in app.title)
    # the stakeholder tables are the entry point of the UI
    assert len(app.dataframe) >= 4
    assert any(button.label.startswith(RUN_LABELS) for button in app.button)


def test_app_defaults_to_english():
    app = AppTest.from_file(str(APP), default_timeout=300)
    app.run()

    assert not [item.value for item in app.exception]
    # the language picker is keyed: the Database forms add more selectboxes
    assert app.selectbox(key="language").value == "en"
    assert any(button.label.startswith("Apply") for button in app.button)


def test_app_runs_the_engine_and_shows_results():
    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()
    run_button = next(button for button in app.button if button.label.startswith(RUN_LABELS))
    run_button.click().run()

    assert not [item.value for item in app.exception]
    assert app.slider, "the timeline slider must appear once a result exists"
    assert app.slider[0].label in {"Vremenska os", "Timeline"}
    assert any("NPV" in metric.label for metric in app.metric)