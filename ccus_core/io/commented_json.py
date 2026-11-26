"""Human-readable JSON input/output with column-aligned key / value / comment.

The engine accepts plain JSON, but the *canonical* on-disk format keeps every
leaf value in a three-column record so a scenario stays auditable in a text
editor::

    "start_year": {
      "value": 2025,
      "unit": "year",
      "comment": "first year of the emission and price series"
    }

Loading is tolerant: plain scalars, these records and nested combinations all
resolve to the value.  Dumping wraps the leaves again and adds the unit/comment
columns from the registry below.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccus_core.models import ScenarioConfig

from .co2_prices import PRICE_SCENARIO_NAMES, load_price_scenarios

RECORD_KEYS = {"value", "unit", "comment"}

# leaf path (dotted) -> (unit, comment)
FIELD_METADATA: dict[str, tuple[str | None, str | None]] = {
    "scenario.id": (None, "stable identifier used by the solver and the UI"),
    "scenario.name": (None, "human readable scenario name"),
    "scenario.start_year": ("year", "first year of the simulation horizon"),
    "scenario.end_year": ("year", "last year of the simulation horizon"),
    "scenario.step": (None, "solver step: yearly (monthly is not implemented yet)"),
    "emitters[].id": (None, "slug: lower-case, no spaces"),
    "emitters[].name": (None, "emitter name as printed in the reports"),
    "emitters[].node_id": (None, "network node where the captured CO2 enters the graph"),
    "emitters[].activation_year": ("year", "first year with a contribution; derived from the probability when omitted"),
    "emitters[].implementation_probability": ("-", "CCS implementation probability: 1.0, 0.9, 0.5, 0.1 ..."),
    "emitters[].decommission_year": ("year", "last year of operation"),
    "emitters[].gross_emissions.kind": (None, "constant | piecewise_linear | polynomial | power_law"),
    "emitters[].gross_emissions.e0_t_per_year": ("t CO2/year", "E(0): emission at the reference year (power_law)"),
    "emitters[].gross_emissions.reference_year": ("year", "E(0) reference year and x = 0 point"),
    "emitters[].gross_emissions.a": ("-", "linear decline rate (thesis: -0.02 ... -0.05)"),
    "emitters[].gross_emissions.b": ("t CO2/year", "b = a * E(0) when omitted"),
    "emitters[].gross_emissions.c": ("-", "power-law exponent (thesis: 1.5)"),
    "emitters[].gross_emissions.constant_t_per_year": ("t CO2/year", "flat emission rate"),
    "emitters[].gross_emissions.points": ("t CO2/year", "year -> emission control points"),
    "emitters[].capture.capacity_t_per_year": ("t CO2/year", "capture nameplate capacity"),
    "emitters[].capture.capex_eur": ("EUR", "capture CAPEX"),
    "emitters[].capture.opex_eur_per_t": ("EUR/t CO2", "capture OPEX per tonne"),
    "emitters[].capture.commissioning_year": ("year", "capture plant commissioning year"),
    "connections[].emitter_id": (None, "emitter that wants CO2 transport"),
    "connections[].sink_id": (None, "storage site it can reach"),
    "connections[].start_year": ("year", "first year this access may be used (independent per pair)"),
    "connections[].end_year": ("year", "last year this access may be used"),
    "connections[].mode": (None, "pipeline | truck | rail | marine"),
    "connections[].distance_km": ("km", "route length"),
    "connections[].capacity_t_per_year": ("t CO2/year", "design capacity of this access"),
    "connections[].capex_eur": ("EUR", "CAPEX charged in start_year"),
    "connections[].opex_eur_per_t": ("EUR/t CO2", "flat tariff"),
    "connections[].opex_eur_per_tkm": ("EUR/(t CO2 km)", "distance tariff"),
    "storage_defaults.porosity": ("-", "default porosity for new DSA/DHF sites (0.20)"),
    "storage_defaults.permeability_m2": ("m2", "default permeability (100 mD = 1e-13 m2)"),
    "storage_defaults.top_depth_m": ("m", "default reservoir depth (1500 m)"),
    "edges[].id": (None, "slug"),
    "edges[].from_node": (None, "start node id"),
    "edges[].to_node": (None, "end node id"),
    "edges[].states[].mode": (None, "pipeline | truck | rail | marine"),
    "edges[].states[].valid_from_year": ("year", "first year of this transport state"),
    "edges[].states[].valid_until_year": ("year", "last year of this transport state"),
    "edges[].states[].capacity_t_per_year": ("t CO2/year", "design capacity"),
    "edges[].states[].distance_km": ("km", "route length"),
    "edges[].states[].capex_eur": ("EUR", "state CAPEX (charged in valid_from_year)"),
    "edges[].states[].opex_eur_per_t": ("EUR/t CO2", "flat tariff"),
    "edges[].states[].opex_eur_per_tkm": ("EUR/(t CO2 km)", "distance tariff"),
    "storage_sinks[].id": (None, "slug"),
    "storage_sinks[].name": (None, "site name"),
    "storage_sinks[].node_id": (None, "graph node of the site"),
    "storage_sinks[].capacity_t": ("t CO2", "nominal storage capacity"),
    "storage_sinks[].commissioning_year": ("year", "first year the site can accept CO2"),
    "storage_sinks[].capex_eur": ("EUR", "site CAPEX"),
    "storage_sinks[].opex_eur_per_t": ("EUR/t CO2", "injection OPEX per tonne"),
    "storage_sinks[].depth_m": ("m", "reservoir depth"),
    "economics.start_year": ("year", "first year of the cash flow"),
    "economics.end_year": ("year", "last year of the cash flow"),
    "economics.capex_start_year": ("year", "year of the first investment"),
    "economics.discount_rate": ("-", "real discount rate"),
    "economics.inflation_rate": ("-", "cost escalation rate"),
}


def unwrap(value: Any) -> Any:
    """Resolve ``{value, unit, comment}`` records into plain Python values."""

    if isinstance(value, dict):
        if set(value) <= RECORD_KEYS and "value" in value:
            return value["value"]
        return {key: unwrap(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [unwrap(item) for item in value]
    return value


def load(text: str) -> ScenarioConfig:
    """Parse a scenario document (commented or plain) into a model."""

    return from_payload(json.loads(text))


def from_payload(payload: Any) -> ScenarioConfig:
    """Validate a plain or commented JSON payload into a :class:`ScenarioConfig`."""

    payload = unwrap(payload)
    if not isinstance(payload, dict):
        raise ValueError("a scenario document must be a JSON object")
    return ScenarioConfig.model_validate(_lift_document(payload))


def load_file(path: str | Path) -> ScenarioConfig:
    return load(Path(path).read_text(encoding="utf-8"))


def _lift_document(payload: dict) -> dict:
    """Accept both the flat ``ScenarioConfig`` shape and the documented layout."""

    if "scenario" in payload and isinstance(payload["scenario"], dict):
        flat = dict(payload["scenario"])
        for section in ("emitters", "edges", "connections", "nodes", "storage_sinks", "geothermal_systems", "economics", "policy", "onboarding_years"):
            if section in payload:
                flat[section] = payload[section]
        payload = flat
    return _apply_price_file(payload)


def _price_scenarios() -> dict:
    """The CO2 price scenarios in force (``json/CO2_prices.json`` or the defaults)."""

    return load_price_scenarios()


def _preset_price_path(path: dict, scenarios: dict) -> dict:
    """A preset price path (``conservative``) with its series taken from the file."""

    resolved = dict(path)
    scenario = scenarios[str(path["mode"])]
    resolved.setdefault("start_year", int(scenario.start_year))
    resolved["values_eur_per_t"] = list(scenario.values_eur_per_t)
    return resolved


def _apply_price_file(payload: dict) -> dict:
    """Supply CO2 price series that the document leaves to ``json/CO2_prices.json``.

    Two places accept the file:

    * ``policy.prices`` - a scenario that carries a ``policy`` block but no prices;
    * ``economics.price_path`` - a preset (``optimistic`` / ``conservative`` /
      ``pessimistic``) without ``values_eur_per_t``, which otherwise had to repeat
      the whole 26-year series inline.

    The models never read the file themselves - they stay free of I/O - so the
    prices are resolved once, here, while the document is still a plain dict.  A
    missing file falls back to the workbook defaults; a malformed one raises
    :class:`~ccus_core.io.co2_prices.Co2PriceFileError` instead of being ignored.
    """

    scenarios = _price_scenarios()
    if not scenarios:
        return payload

    payload = dict(payload)

    policy = payload.get("policy")
    if isinstance(policy, dict) and not policy.get("prices"):
        policy = dict(policy)
        policy["prices"] = {
            name: scenario.model_dump() for name, scenario in scenarios.items()
        }
        payload["policy"] = policy

    economics = payload.get("economics")
    if isinstance(economics, dict):
        path = economics.get("price_path")
        if (
            isinstance(path, dict)
            and path.get("mode") in PRICE_SCENARIO_NAMES
            and not path.get("values_eur_per_t")
        ):
            economics = dict(economics)
            economics["price_path"] = _preset_price_path(path, scenarios)
            payload["economics"] = economics

    return payload


def _wrap(value: Any, path: str = "") -> Any:
    if isinstance(value, dict):
        return {key: _wrap(item, f"{path}.{key}" if path else key) for key, item in value.items()}
    if isinstance(value, list):
        return [_wrap(item, f"{path}[]") for item in value]
    record: dict[str, Any] = {"value": value}
    unit, comment = FIELD_METADATA.get(path, (None, None))
    if unit is None and comment is None and path.startswith("scenario."):
        # registry keys for nested sections are written without the root prefix
        unit, comment = FIELD_METADATA.get(path[len("scenario.") :], (None, None))
    if unit is not None:
        record["unit"] = unit
    if comment is not None:
        record["comment"] = comment
    return record


def _render_key(key: Any) -> str:
    """Render a dict key as a JSON string.

    Model keys are not always strings: ``EmissionCurve.points`` is keyed by year and
    ``ScenarioConfig.onboarding_years`` by probability, so ``json.dumps(key)`` would
    emit the bare literal ``2030``/``1.0`` and produce a document that is not valid
    JSON.  Every key is therefore quoted; pydantic coerces ``"2030"`` back to ``int``.
    """

    if isinstance(key, str):
        return json.dumps(key, ensure_ascii=False)
    if isinstance(key, bool) or key is None:
        return json.dumps(str(key))
    if isinstance(key, (int, float)):
        # 2030 -> "2030", 1.0 -> "1.0" (a float key must keep its decimal point)
        return json.dumps(repr(key) if isinstance(key, float) else str(key))
    return json.dumps(str(key), ensure_ascii=False)


def _render(value: Any, level: int, indent: int, inline_limit: int) -> str:
    """Compact JSON renderer: a block stays on one line while it fits."""

    pad = " " * (indent * level)
    inner = " " * (indent * (level + 1))

    if isinstance(value, dict):
        compact = (
            "{"
            + ", ".join(
                f"{_render_key(key)}: {_render(item, 0, indent, inline_limit)}"
                for key, item in value.items()
            )
            + "}"
        )
        if len(compact) <= inline_limit:
            return compact
        items = [
            f"{inner}{_render_key(key)}: {_render(item, level + 1, indent, inline_limit)}"
            for key, item in value.items()
        ]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"

    if isinstance(value, list):
        rendered = [_render(item, 0, indent, inline_limit) for item in value]
        compact = "[" + ", ".join(rendered) + "]"
        if len(compact) <= inline_limit:
            return compact
        items = [f"{inner}{item}" for item in (_render(item, level + 1, indent, inline_limit) for item in value)]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"

    return json.dumps(value, ensure_ascii=False)


def _legend() -> dict[str, str]:
    """``key -> "unit — comment"`` for every documented field."""

    legend: dict[str, str] = {}
    for key, (unit, comment) in FIELD_METADATA.items():
        if comment is None:
            continue
        text = comment.replace("—", "-")
        legend[key] = f"{unit} - {text}" if unit and unit != "-" else text
    return legend


def dump(scenario: ScenarioConfig, *, style: str = "compact", indent: int = 2, inline_limit: int = 320) -> str:
    """Render a scenario as JSON.

    ``style="compact"`` (default) keeps one block per line while it fits in
    ``inline_limit`` characters, which keeps a 14-emitter cluster well below 500
    lines.  ``style="verbose"`` writes the older three-column ``value``/``unit``/
    ``comment`` records for every leaf.
    """

    payload = scenario.model_dump(exclude_none=True, exclude_defaults=True)
    # `edges` is never dropped: it carries the state timeline, the upgrades, the
    # modal designs and the geometry id, none of which a connection can express.
    # The connections stay in the document as the (many-to-many) access list.
    if style == "verbose":
        payload = scenario.model_dump(exclude_none=True)
        body = {"schema": "ccus-cluster/2.0", "scenario": _wrap(payload, "scenario")}
        return json.dumps(body, indent=indent, ensure_ascii=False) + "\n"

    body: dict[str, Any] = {
        "schema": "ccus-cluster/2.0",
        "_format": (
            "compact: one block per line; units and explanations in _comments; "
            "edges are authoritative for the state timeline and the upgrades"
        ),
        "_comments": _legend(),
        "scenario": payload,
    }
    return _render(body, 0, indent, inline_limit) + "\n"


def dump_file(
    scenario: ScenarioConfig,
    path: str | Path,
    *,
    style: str = "compact",
    indent: int = 2,
    inline_limit: int = 320,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump(scenario, style=style, indent=indent, inline_limit=inline_limit), encoding="utf-8")
    return target