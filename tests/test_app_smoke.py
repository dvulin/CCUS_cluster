"""Language-agnostic smoke test of the Streamlit presentation layer."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py"
RUN_LABELS = ("Apply", "Primijeni")


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
    assert app.selectbox[0].value == "en"
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