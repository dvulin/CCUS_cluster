"""Emitter database: the catalogue the UI offers before a scenario is defined."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccus_core.io import DEFAULT_CATALOGUE_PATH, load_emitter_catalogue
from ccus_core.io.emitter_catalogue import EmitterRecord

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_catalogue_loads():
    records = load_emitter_catalogue()

    assert records, "the bundled emitter database must not be empty"
    assert all(isinstance(record, EmitterRecord) for record in records)
    # ids are unique and the file order is kept
    ids = [record.id for record in records]
    assert len(ids) == len(set(ids))
    assert ids == [record.id for record in load_emitter_catalogue()]


def test_catalogue_records_carry_the_data_the_study_needs():
    record = load_emitter_catalogue()[0]

    assert record.name
    assert record.curve.kind in {"constant", "piecewise_linear", "power_law", "polynomial"}
    assert record.emissions_in(record.reference_year) > 0.0
    # the industry type is part of the database so the UI can show and group it
    assert isinstance(record.industry, str) and record.industry.strip()


def test_emissions_follow_the_curve_and_the_onboarding_year():
    record = next(
        item for item in load_emitter_catalogue() if item.activation_year is not None
    )
    before = record.emissions_in(record.activation_year - 1)
    after = record.emissions_in(record.activation_year)

    assert record.available_emissions(record.activation_year - 1) == 0.0
    assert record.available_emissions(record.activation_year) == pytest.approx(after)
    assert before >= 0.0


def test_every_catalogue_entry_has_an_industry():
    """The Database column must be filled; gaps are a data bug, not a display case."""

    records = load_emitter_catalogue()
    missing = [record.id for record in records if not (record.industry or "").strip()]

    assert not missing, f"industry missing for: {missing}"
    # a small, reusable vocabulary keeps the column groupable
    assert len({record.industry for record in records}) <= 15


def test_a_catalogue_file_can_be_supplied(tmp_path):
    payload = {
        "emitters": [
            {
                "id": "test_plant",
                "name": "Test plant",
                "industry": "cement works",
                "curve": {"kind": "constant", "constant_t_per_year": 250_000.0},
                "activation_year": 2030,
                "implementation_probability": 1.0,
            }
        ]
    }
    path = tmp_path / "emitters.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    records = load_emitter_catalogue(path)
    assert len(records) == 1
    assert records[0].industry == "cement works"
    assert records[0].emissions_in(2035) == pytest.approx(250_000.0)


def test_a_broken_catalogue_is_reported(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"emitters": [{"name": "no id"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="id"):
        load_emitter_catalogue(path)


def test_default_path_points_at_the_repository_catalogue():
    assert DEFAULT_CATALOGUE_PATH.name == "emitters.json"
    assert DEFAULT_CATALOGUE_PATH.is_file()