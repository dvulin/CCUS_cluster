"""The canonical JSON format: compact, editable, and still fully documented."""

from __future__ import annotations

from pathlib import Path

import pytest

from ccus_core.io import commented_json

CLUSTER_JSON = Path(__file__).resolve().parents[1] / "inputs" / "examples" / "croatia_cluster_2025_2050.json"


def test_compact_dump_stays_below_the_readability_budget():
    scenario = commented_json.load_file(CLUSTER_JSON)
    text = commented_json.dump(scenario)
    lines = text.splitlines()
    assert len(lines) < 500, f"compact document has {len(lines)} lines"
    # one line per object: no single line explodes into an unreadable block
    assert max(len(line) for line in lines) <= 400


def test_compact_document_round_trips_including_derived_edges():
    scenario = commented_json.load_file(CLUSTER_JSON)
    reloaded = commented_json.load(commented_json.dump(scenario))

    assert len(reloaded.emitters) == len(scenario.emitters)
    assert len(reloaded.connections) == len(scenario.connections)
    # edges are derived from the connections on load, so they must come back
    assert len(reloaded.edges) == len(scenario.edges)
    assert reloaded.emitter_by_id("te-plomin").activation_year == 2028


def test_compact_document_omits_defaults_and_explains_units():
    text = commented_json.dump(commented_json.load_file(CLUSTER_JSON))
    assert '"_comments"' in text
    assert '"schema": "ccus-cluster/2.0"' in text
    # the legend documents the defaults once, instead of repeating them per sink
    assert '"storage_defaults.porosity"' in text
    assert text.count('"porosity"') <= 4  # legend + one explicit reservoir per sink
    assert '"edges"' not in text  # derived from connections


def test_verbose_style_is_still_available():
    scenario = commented_json.load_file(CLUSTER_JSON)
    verbose = commented_json.dump(scenario, style="verbose")
    assert '"unit": "year"' in verbose
    assert len(verbose.splitlines()) > 1000
    reloaded = commented_json.load(verbose)
    assert len(reloaded.emitters) == len(scenario.emitters)


def test_single_chain_example_still_loads():
    single = Path(__file__).resolve().parents[1] / "inputs" / "examples" / "ccus_cluster_v1.json"
    scenario = commented_json.load_file(single)
    assert scenario.id == "adriatic_cluster"
    assert scenario.economics is not None