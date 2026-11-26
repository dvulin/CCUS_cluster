"""Streamlit-level checks for the save/load flow (isolated scenario directory)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from ccus_core.io import load_scenario_file, save_scenario

APP = Path(__file__).resolve().parents[1] / "streamlit_app" / "app.py"


def _button(app, label: str):
    """Exact-label button lookup: "Load" is not "Load scenario"."""

    return next(button for button in app.button if button.label == label)


def _success_texts(app):
    return [str(item.value) for item in app.success]


@pytest.fixture
def isolated_repository(tmp_path, monkeypatch):
    """Keep saved scenarios out of the repository during the test."""

    monkeypatch.setenv("GT_CCS_SCENARIO_DIRECTORY", str(tmp_path))
    return tmp_path


def test_save_reports_success_and_writes_the_file(isolated_repository):
    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()

    app.session_state["scenario_name"] = "my_case"
    app.run()
    _button(app, "Run").click().run()

    _button(app, "Save").click().run()

    assert not [item.value for item in app.exception]
    assert not [item.value for item in app.error]
    assert any("my_case" in text for text in _success_texts(app))
    assert (isolated_repository / "my_case.json").is_file()


def test_load_confirms_and_becomes_the_scenario_that_run_uses(isolated_repository):
    """After Load, Run must compute the loaded file - not the source radio payload."""

    from ccus_core.io import commented_json
    from ccus_core.models import ScenarioConfig

    source = commented_json.load_file(
        Path(__file__).resolve().parents[1] / "inputs" / "examples" / "ccus_cluster_v1.json"
    )
    loaded_document = source.model_copy(update={"name": "Loaded from the repository"})
    save_scenario(loaded_document, "loaded_case", directory=isolated_repository)

    app = AppTest.from_file(str(APP), default_timeout=600)
    app.run()

    # pick the saved scenario and load it
    app.selectbox(key="saved_choice").set_value("loaded_case").run()
    _button(app, "Load").click().run()

    assert not [item.value for item in app.exception]
    assert not [item.value for item in app.error]
    assert any("loaded_case" in text for text in _success_texts(app))
    assert app.session_state["active_name"] == "loaded_case"
    active = ScenarioConfig.model_validate(app.session_state["active_scenario"])
    assert active.name == "Loaded from the repository"

    # and Run computes that document
    _button(app, "Run").click().run()
    assert not [item.value for item in app.exception]
    assert app.session_state["scenario"].name == "Loaded from the repository"