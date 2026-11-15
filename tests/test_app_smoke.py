"""End-to-end smoke test of the Streamlit presentation layer."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py"


def test_app_renders_without_exceptions():
    app = AppTest.from_file(str(APP), default_timeout=180)
    app.run()

    assert not [item.value for item in app.exception]
    assert any("CCUS cluster" in title.value for title in app.title)
    assert any(button.label.startswith("Pokreni") for button in app.button)


def test_app_runs_the_engine_and_shows_results():
    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()
    run_button = next(button for button in app.button if button.label.startswith("Pokreni"))
    run_button.click().run()

    assert not [item.value for item in app.exception]
    # the timeline slider only exists after a successful run
    assert app.slider, "the timeline slider must appear once a result exists"
    assert app.slider[0].label == "Vremenska os"
    assert any("NPV" in metric.label for metric in app.metric)