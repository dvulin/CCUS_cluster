"""Streamlit presentation layer for the CCUS cluster engine.

The UI is deliberately thin: it imports :mod:`ccus_core` and nothing else from the
project.  All physics, routing and financial logic lives in the engine, so this
module can be replaced (desktop app, Excel add-in, notebook) without touching the
model code.

The configuration tab edits the whole stakeholder set — emitters, their emission
curves, every emitter→sink access and every storage site — through editable
tables, so the UI stays as expressive as the JSON without asking the user to edit
JSON by hand.

Run with::

    streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ccus_core import ScenarioEngine, ScenarioConfig, year_snapshot  # noqa: E402

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0
HOURS_PER_YEAR = 8766.0

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = REPOSITORY_ROOT / "inputs" / "examples" / "ccus_cluster_v1.json"
DEFAULT_CLUSTER = REPOSITORY_ROOT / "inputs" / "examples" / "cluster_three_emitters.json"

MODE_COLOURS = {
    "pipeline": "#1f77b4",
    "truck": "#ff7f0e",
    "rail": "#2ca02c",
    "marine": "#17becf",
}

MODE_LABELS = {
    "pipeline": "Cjevovod",
    "truck": "Kamion",
    "rail": "Ĺ˝eljeznica",
    "marine": "Brod",
}


# --------------------------------------------------------------------- helpers
def _number(value, default: float = 0.0) -> float:
    if value is None or isinstance(value, str) and not value.strip():
        return default
    try:
        if isinstance(value, float) and math.isnan(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value, default: int = 0) -> int:
    return int(round(_number(value, float(default))))


def _optional_year(value, default: int):
    """Return an int for a year cell, or ``None`` when the cell is empty."""

    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none"}:
        return None
    return int(round(float(value)))


def _text(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


# --------------------------------------------------------------------- data
def load_scenario(payload: bytes | str | Path):
    """Validate a JSON scenario from a path, a string or an uploaded file."""

    from ccus_core.io import commented_json

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, (str, Path)) and not str(payload).lstrip().startswith("{"):
        payload = Path(payload).read_text(encoding="utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    return commented_json.from_payload(payload)


def apply_overrides(scenario: ScenarioConfig, overrides: dict) -> ScenarioConfig:
    """Return a copy of ``scenario`` with simple scalar overrides applied."""

    payload = scenario.model_dump()
    for emitter in payload["emitters"]:
        activation_override = overrides.get("activation_year", {}).get(emitter["id"])
        if activation_override is not None:
            emitter["activation_year"] = int(activation_override)
            capture = emitter.get("capture")
            if capture is not None and capture["commissioning_year"] < emitter["activation_year"]:
                capture["commissioning_year"] = emitter["activation_year"]

        if emitter["id"] in overrides.get("emission_t_per_year", {}):
            value = float(overrides["emission_t_per_year"][emitter["id"]])
            profile = emitter["gross_emissions"]
            kind = profile.get("kind")
            if kind == "constant":
                profile["constant_t_per_year"] = value
            elif kind == "power_law":
                profile["e0_t_per_year"] = value
            elif kind == "piecewise_linear" and profile.get("points"):
                profile["points"] = {int(year): value for year in profile["points"]}
            else:
                profile["kind"] = "constant"
                profile["constant_t_per_year"] = value
                profile.pop("points", None)

    if "discount_rate" in overrides and payload.get("economics"):
        payload["economics"]["discount_rate"] = float(overrides["discount_rate"])
    if "end_year" in overrides:
        payload["end_year"] = int(overrides["end_year"])
        if payload.get("economics"):
            payload["economics"]["end_year"] = max(
                int(payload["economics"]["start_year"]), int(overrides["end_year"])
            )

    upgrade_year = overrides.get("upgrade_year", {})
    upgrade_threshold = overrides.get("upgrade_threshold", {})
    for edge in payload.get("edges", []):
        for upgrade in edge.get("upgrades", []):
            if upgrade["id"] in upgrade_year:
                upgrade["trigger"]["year"] = int(upgrade_year[upgrade["id"]])
                if upgrade["trigger"]["kind"] == "cumulative_mass":
                    upgrade["trigger"]["kind"] = "both"
            if upgrade["id"] in upgrade_threshold:
                threshold = float(upgrade_threshold[upgrade["id"]])
                upgrade["trigger"]["threshold_t"] = threshold
                if threshold > 0.0 and upgrade["trigger"]["kind"] == "year":
                    upgrade["trigger"]["kind"] = "both"
    return ScenarioConfig.model_validate(payload)


# --------------------------------------------------------------------- frames
EMITTER_COLUMNS = [
    "id",
    "name",
    "activation_year",
    "implementation_probability",
    "curve",
    "e0_t_per_year",
    "a",
    "c",
    "constant_t_per_year",
    "capture_capacity_t_per_year",
    "capture_capex_eur",
    "capture_opex_eur_per_t",
]

CONNECTION_COLUMNS = [
    "emitter_id",
    "sink_id",
    "start_year",
    "end_year",
    "mode",
    "distance_km",
    "capacity_t_per_year",
    "capex_eur",
    "opex_eur_per_t",
    "opex_eur_per_tkm",
]

SINK_COLUMNS = [
    "id",
    "name",
    "type",
    "geothermal_coupled",
    "geothermal_start_year",
    "capacity_t",
    "depth_m",
    "porosity",
    "permeability_m2",
    "commissioning_year",
    "capex_eur",
    "opex_eur_per_t",
    "monitoring_cost_during_injection_eur_per_year",
    "monitoring_cost_after_injection_eur_per_year",
]

GEOTHERMAL_COLUMNS = [
    "id",
    "name",
    "sink_id",
    "d_doublet_m",
    "reservoir_temperature_c",
    "eta_orc",
    "p_out_bar",
    "t_out_c",
    "operation_start_year",
    "operation_end_year",
    "capex_eur",
    "fixed_opex_eur_per_year",
]


def scenario_to_frames(scenario: ScenarioConfig) -> dict[str, "object"]:
    """Flatten a scenario into the editable tables of the UI."""

    import pandas as pd

    emitters = []
    for emitter in scenario.emitters:
        curve = emitter.gross_emissions
        capture = emitter.capture
        emitters.append(
            {
                "id": emitter.id,
                "name": emitter.name,
                "activation_year": emitter.activation_year,
                "implementation_probability": emitter.implementation_probability,
                "curve": curve.kind,
                "e0_t_per_year": curve.e0_t_per_year,
                "a": curve.a,
                "c": curve.c,
                "constant_t_per_year": curve.constant_t_per_year,
                "capture_capacity_t_per_year": capture.capacity_t_per_year if capture else None,
                "capture_capex_eur": capture.capex_eur if capture else None,
                "capture_opex_eur_per_t": capture.opex_eur_per_t if capture else None,
            }
        )

    connections = []
    for connection in scenario.connections:
        state = connection.state()
        connections.append(
            {
                "emitter_id": connection.emitter_id,
                "sink_id": connection.sink_id,
                "start_year": connection.start_year,
                "end_year": connection.end_year,
                "mode": state.mode.value,
                "distance_km": connection.distance_km,
                "capacity_t_per_year": connection.capacity_t_per_year,
                "capex_eur": connection.capex_eur,
                "opex_eur_per_t": connection.opex_eur_per_t,
                "opex_eur_per_tkm": connection.opex_eur_per_tkm,
            }
        )

    sinks = []
    for sink in scenario.storage_sinks:
        reservoir = sink.reservoir
        sinks.append(
            {
                "id": sink.id,
                "name": sink.name,
                "type": sink.storage_type.value,
                "geothermal_coupled": sink.geothermal_coupled,
                "geothermal_start_year": sink.geothermal_start_year,
                "capacity_t": sink.capacity_t,
                "depth_m": reservoir.top_depth_m if reservoir else None,
                "porosity": reservoir.porosity if reservoir else None,
                "permeability_m2": reservoir.permeability_m2 if reservoir else None,
                "commissioning_year": sink.commissioning_year,
                "capex_eur": sink.capex_eur,
                "opex_eur_per_t": sink.opex_eur_per_t,
                "monitoring_cost_during_injection_eur_per_year": sink.monitoring_cost_during_injection_eur_per_year,
                "monitoring_cost_after_injection_eur_per_year": sink.monitoring_cost_after_injection_eur_per_year,
            }
        )

    geothermal = []
    for system in scenario.geothermal_systems:
        geothermal.append(
            {
                "id": system.id,
                "name": system.name,
                "sink_id": scenario.storage_sinks[0].id if scenario.storage_sinks else None,
                "d_doublet_m": system.d_doublet_m,
                "reservoir_temperature_c": system.reservoir_temperature_c,
                "eta_orc": system.eta_orc,
                "p_out_bar": system.p_out_bar,
                "t_out_c": system.t_out_c,
                "operation_start_year": system.operation_start_year,
                "operation_end_year": system.operation_end_year,
                "capex_eur": system.capex_eur,
                "fixed_opex_eur_per_year": system.fixed_opex_eur_per_year,
            }
        )

    return {
        "emitters": pd.DataFrame(emitters, columns=EMITTER_COLUMNS),
        "connections": pd.DataFrame(connections, columns=CONNECTION_COLUMNS),
        "sinks": pd.DataFrame(sinks, columns=SINK_COLUMNS),
        "geothermal": pd.DataFrame(geothermal, columns=GEOTHERMAL_COLUMNS),
    }


def frames_to_scenario(base: ScenarioConfig, frames: dict) -> ScenarioConfig:
    """Rebuild a validated scenario from the edited tables."""

    import pandas as pd

    from ccus_core.models import (
        CaptureUnit,
        EconomicsConfig,
        Emitter,
        EmitterSinkConnection,
        EmissionCurve,
        GeothermalSystem,
        GeoLocation,
        Node,
        NodeKind,
        ReservoirProperties,
        StorageSink,
        StorageType,
    )

    start_year = int(base.start_year)
    end_year = int(base.end_year)

    nodes: list[Node] = []
    emitters: list[Emitter] = []
    for row in frames["emitters"].to_dict("records"):
        emitter_id = _text(row.get("id"))
        if not emitter_id:
            continue
        node_id = f"{emitter_id}-gate"
        nodes.append(Node(id=node_id, name=_text(row.get("name"), emitter_id), kind=NodeKind.EMITTER, location=GeoLocation(onshore=True)))

        kind = _text(row.get("curve"), "constant")
        if kind == "power_law":
            curve = EmissionCurve.power_law(
                e0_t_per_year=_number(row.get("e0_t_per_year"), 1.0),
                reference_year=start_year,
                a=_number(row.get("a"), 0.0),
                c=_number(row.get("c"), 1.5),
            )
        elif kind == "piecewise_linear":
            existing = next((e.gross_emissions for e in base.emitters if e.id == emitter_id), None)
            curve = existing if existing is not None else EmissionCurve.constant(_number(row.get("constant_t_per_year"), 0.0))
        else:
            curve = EmissionCurve.constant(_number(row.get("constant_t_per_year"), 0.0))

        capacity = _number(row.get("capture_capacity_t_per_year"), 0.0)
        capture = None
        if capacity > 0.0:
            capture = CaptureUnit(
                name=f"{emitter_id} capture",
                capacity_t_per_year=capacity,
                capex_eur=_number(row.get("capture_capex_eur"), 0.0),
                opex_eur_per_t=_number(row.get("capture_opex_eur_per_t"), 0.0),
                commissioning_year=int(row.get("activation_year") or start_year),
            )

        emitters.append(
            Emitter(
                id=emitter_id,
                name=_text(row.get("name"), emitter_id),
                node_id=node_id,
                activation_year=int(row.get("activation_year") or start_year),
                implementation_probability=(
                    None if row.get("implementation_probability") is None or pd.isna(row.get("implementation_probability"))
                    else _number(row.get("implementation_probability"))
                ),
                gross_emissions=curve,
                capture=capture,
            )
        )

    sink_ids: list[str] = []
    sinks: list[StorageSink] = []
    for row in frames["sinks"].to_dict("records"):
        sink_id = _text(row.get("id"))
        if not sink_id:
            continue
        sink_ids.append(sink_id)
        node_id = f"{sink_id}-site"
        nodes.append(Node(id=node_id, name=_text(row.get("name"), sink_id), kind=NodeKind.STORAGE, location=GeoLocation(onshore=True)))
        reservoir = ReservoirProperties(
            area_m2=25e6,
            effective_thickness_m=150.0,
            porosity=_number(row.get("porosity"), 0.20),
            permeability_m2=_number(row.get("permeability_m2"), 1.0e-13),
            top_depth_m=_number(row.get("depth_m"), 1500.0),
            temperature_c=60.0,
            reference_pressure_bar=150.0,
            pressure_step_bar=0.5,
        )
        sinks.append(
            StorageSink(
                id=sink_id,
                node_id=node_id,
                name=_text(row.get("name"), sink_id),
                storage_type=StorageType(_text(row.get("type"), "DSA").upper()),
                geothermal_coupled=bool(row.get("geothermal_coupled") or False),
                geothermal_start_year=_optional_year(
                    row.get("geothermal_start_year"), start_year
                ),
                capacity_t=_number(row.get("capacity_t"), 1.0),
                reservoir=reservoir,
                commissioning_year=_integer(row.get("commissioning_year"), start_year),
                capex_eur=_number(row.get("capex_eur"), 0.0),
                opex_eur_per_t=_number(row.get("opex_eur_per_t"), 0.0),
                monitoring_cost_during_injection_eur_per_year=_number(
                    row.get("monitoring_cost_during_injection_eur_per_year"), 0.0
                ),
                monitoring_cost_after_injection_eur_per_year=_number(
                    row.get("monitoring_cost_after_injection_eur_per_year"), 0.0
                ),
            )
        )

    connections = []
    for row in frames["connections"].to_dict("records"):
        emitter_id = _text(row.get("emitter_id"))
        sink_id = _text(row.get("sink_id"))
        if not emitter_id or not sink_id:
            continue
        connections.append(
            EmitterSinkConnection(
                emitter_id=emitter_id,
                sink_id=sink_id,
                start_year=_integer(row.get("start_year"), start_year),
                end_year=None if pd.isna(row.get("end_year")) else _integer(row.get("end_year"), end_year),
                mode=_text(row.get("mode"), "pipeline"),
                distance_km=_number(row.get("distance_km"), 0.0),
                capacity_t_per_year=_number(row.get("capacity_t_per_year"), 0.0) or None,
                capex_eur=_number(row.get("capex_eur"), 0.0),
                opex_eur_per_t=_number(row.get("opex_eur_per_t"), 0.0),
                opex_eur_per_tkm=_number(row.get("opex_eur_per_tkm"), 0.0),
            )
        )

    geothermal = []
    sink_node = {sink.id: sink.node_id for sink in sinks}
    for row in frames["geothermal"].to_dict("records"):
        system_id = _text(row.get("id"))
        if not system_id:
            continue
        sink_id = _text(row.get("sink_id")) or (sink_ids[0] if sink_ids else None)
        if sink_id is None or sink_id not in sink_node:
            continue
        geothermal.append(
            GeothermalSystem(
                id=system_id,
                node_id=sink_node[sink_id],
                name=_text(row.get("name"), system_id),
                d_doublet_m=_number(row.get("d_doublet_m"), 1500.0),
                reservoir_temperature_c=_number(row.get("reservoir_temperature_c"), 150.0),
                eta_orc=_number(row.get("eta_orc"), 0.2),
                p_out_bar=_number(row.get("p_out_bar"), 10.0),
                t_out_c=_number(row.get("t_out_c"), 35.0),
                rw_production_m=0.15,
                rw_injection_m=0.15,
                h_ref_production_m=1500.0,
                h_ref_injection_m=1500.0,
                operation_start_year=_integer(row.get("operation_start_year"), start_year),
                operation_end_year=_integer(row.get("operation_end_year"), end_year),
                capex_eur=_number(row.get("capex_eur"), 0.0),
                fixed_opex_eur_per_year=_number(row.get("fixed_opex_eur_per_year"), 0.0),
            )
        )

    # every coupled sink must end up with a geothermal doublet, even if the user only
    # ticked the box in the storage table
    covered = {system.node_id for system in geothermal}
    for sink in sinks:
        if not sink.geothermal_coupled or sink.node_id in covered:
            continue
        geothermal.append(
            GeothermalSystem(
                id=f"{sink.id}-doublet",
                node_id=sink.node_id,
                name=f"{sink.name} doublet",
                d_doublet_m=1500.0,
                reservoir_temperature_c=sink.reservoir.temperature_c if sink.reservoir else 150.0,
                eta_orc=0.20,
                p_out_bar=10.0,
                t_out_c=35.0,
                rw_production_m=0.15,
                rw_injection_m=0.15,
                h_ref_production_m=sink.reservoir.top_depth_m if sink.reservoir else 1500.0,
                h_ref_injection_m=sink.reservoir.top_depth_m if sink.reservoir else 1500.0,
                operation_start_year=int(
                    sink.geothermal_start_year or sink.commissioning_year or start_year
                ),
                operation_end_year=end_year,
                capex_eur=50_000_000.0,
                fixed_opex_eur_per_year=1_500_000.0,
            )
        )

    economics = base.economics
    payload = {
        "id": base.id,
        "name": base.name,
        "start_year": start_year,
        "end_year": end_year,
        "nodes": [node.model_dump() for node in nodes],
        "emitters": [emitter.model_dump() for emitter in emitters],
        "connections": [connection.model_dump() for connection in connections],
        "storage_sinks": [sink.model_dump() for sink in sinks],
        "geothermal_systems": [system.model_dump() for system in geothermal],
        "economics": economics.model_dump() if economics else None,
        "policy": base.policy.model_dump() if base.policy else None,
        "storage_defaults": base.storage_defaults.model_dump(),
        "onboarding_years": base.onboarding_years,
    }
    return ScenarioConfig.model_validate(payload)


# --------------------------------------------------------------------- charts
def build_map_figure(snapshot, scenario: ScenarioConfig):
    """Draw a schematic of the transport network for one year.

    The layout is layered by graph distance (emitters on the left, storage on the
    right) so the figure reads as a network rather than a scatter plot.  This is a
    schematic: coordinates come from the scenario when present, otherwise from the
    layered layout.  Line width encodes the routed mass, the arrow the direction.
    """

    plt.rcParams["font.family"] = ["DejaVu Sans", "Arial", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    # ---------------------------------------------------------------- layers
    emitter_nodes = {emitter.node_id for emitter in scenario.emitters}
    sink_nodes = {sink.node_id for sink in scenario.storage_sinks}
    adjacency: dict[str, list[str]] = {}
    for edge in snapshot.edges:
        adjacency.setdefault(edge["from_node"], []).append(edge["to_node"])
        if edge.get("bidirectional"):
            adjacency.setdefault(edge["to_node"], []).append(edge["from_node"])

    layer: dict[str, int] = {node: 0 for node in emitter_nodes}
    queue = list(emitter_nodes)
    while queue:
        current = queue.pop(0)
        for neighbour in adjacency.get(current, []):
            if neighbour not in layer:
                layer[neighbour] = layer[current] + 1
                queue.append(neighbour)
    for node_id in scenario.nodes and [node.id for node in scenario.nodes] or []:
        layer.setdefault(node_id, max(layer.values(), default=0) + 1)

    grouped: dict[int, list[str]] = {}
    for node_id, depth in layer.items():
        grouped.setdefault(depth, []).append(node_id)

    positions: dict[str, tuple[float, float]] = {}
    for depth in sorted(grouped):
        members = sorted(grouped[depth])
        for index, node_id in enumerate(members):
            node = next((item for item in scenario.nodes if item.id == node_id), None)
            latitude = node.location.latitude if node else None
            longitude = node.location.longitude if node else None
            if latitude is not None and longitude is not None:
                positions[node_id] = (float(longitude), float(latitude))
            else:
                offset = (index - (len(members) - 1) / 2.0) * 0.9
                positions[node_id] = (float(depth), offset)

    # ---------------------------------------------------------------- edges
    figure, axis = plt.subplots(figsize=(8.6, 4.8))
    max_flow = max([float(edge["flow_t"]) for edge in snapshot.edges] or [1.0])

    for edge in snapshot.edges:
        start = positions.get(edge["from_node"])
        end = positions.get(edge["to_node"])
        if start is None or end is None:
            continue
        flow = float(edge["flow_t"])
        width = 0.8 + 3.2 * (flow / max_flow if max_flow else 0.0)
        colour = MODE_COLOURS.get(edge["mode"] or "", "#999999")
        if edge["active"]:
            axis.annotate(
                "",
                xy=(end[0], end[1]),
                xytext=(start[0], start[1]),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=colour,
                    linewidth=width,
                    alpha=0.9,
                    shrinkA=6,
                    shrinkB=6,
                ),
            )
        # inactive edges are not drawn at all: a thin line would suggest a
            # connection that does not exist in that year
        elif False:
            pass
        if flow > 0.0:
            axis.text(
                (start[0] + end[0]) / 2.0,
                (start[1] + end[1]) / 2.0,
                f"{flow / 1000.0:,.0f} kt",
                fontsize=6,
                color="#222222",
                ha="center",
                va="bottom",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.75),
            )

    # ---------------------------------------------------------------- nodes
    for node in scenario.nodes:
        if node.id not in positions:
            continue
        x, y = positions[node.id]
        is_sink = node.id in sink_nodes
        is_port = node.kind.value in {"port", "offshore_terminal"}
        if is_sink:
            marker, size, colour = "s", 120.0, "#c0392b"
        elif is_port:
            marker, size, colour = "^", 90.0, "#2980b9"
        elif node.id in emitter_nodes:
            marker, size, colour = "o", 80.0, "#2c3e50"
        else:
            marker, size, colour = "D", 60.0, "#7f8c8d"
        axis.scatter([x], [y], marker=marker, s=size, color=colour, edgecolor="white", linewidth=0.8, zorder=3)
        axis.annotate(node.name, (x, y), fontsize=6.8, xytext=(5, 5), textcoords="offset points")

    handles = [
        plt.Line2D([0], [0], color=colour, linewidth=3, label=MODE_LABELS.get(mode, mode))
        for mode, colour in MODE_COLOURS.items()
        if any(edge["mode"] == mode for edge in snapshot.edges)
    ]
    handles += [
        plt.Line2D([0], [0], marker="o", color="none", markerfacecolor="#2c3e50", markersize=7, label="Emiter"),
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#c0392b", markersize=7, label="Skladište"),
        plt.Line2D([0], [0], marker="^", color="none", markerfacecolor="#2980b9", markersize=7, label="Luka"),
    ]
    if handles:
        axis.legend(handles=handles, fontsize=6.5, loc="lower left", frameon=False, ncol=2)
    axis.set_xlabel("Sloj u mreži (0 = emiteri)")
    axis.set_ylabel("Pozicija unutar sloja")
    axis.set_title(f"Transportna mreža, {snapshot.year}.")
    axis.grid(alpha=0.18, linewidth=0.4)
    figure.tight_layout()
    return figure


def snapshot_frame(rows: list[dict]):
    import pandas as pd

    return pd.DataFrame(rows)


# --------------------------------------------------------------------- app


def main() -> None:
    import streamlit as st

    try:  # package import (tests) or script import (streamlit run)
        from .i18n import strings
    except ImportError:  # pragma: no cover - script execution
        from i18n import strings

    st.set_page_config(page_title="CCUS cluster", layout="wide")

    if "language" not in st.session_state:
        st.session_state["language"] = "hr"
    t = strings(st.session_state["language"])
    st.title(t["app_title"])

    with st.sidebar:
        st.header("CCUS cluster")
        language = st.selectbox(
            t.get("language", "Jezik"),
            ["hr", "en"],
            format_func=lambda code: {"hr": "Hrvatski", "en": "English"}[code],
            index=["hr", "en"].index(st.session_state["language"]),
            key="language",
        )
        t = strings(st.session_state["language"])

        st.subheader(t["sidebar_scenario"])
        source = st.radio(
            t["sidebar_source"],
            [t["source_cluster"], t["source_single"], t["source_upload"]],
            index=0,
        )
        if source == t["source_cluster"]:
            payload = DEFAULT_CLUSTER
        elif source == t["source_single"]:
            payload = DEFAULT_SCENARIO
        else:
            uploaded = st.file_uploader(t["upload_label"], type=["json"])
            payload = uploaded.getvalue() if uploaded is not None else DEFAULT_CLUSTER

        if st.session_state.get("active_source") != source:
            st.session_state["active_source"] = source
            st.session_state.pop("frames", None)
            st.session_state.pop("result", None)
            st.session_state.pop("scenario", None)

        try:
            base_scenario = load_scenario(payload)
            st.success(t["scenario_loaded"].format(name=base_scenario.name))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            st.error(t["scenario_invalid"].format(error=exc))
            return

        if st.button(t["btn_run"], type="primary"):
            try:
                st.session_state["result"] = ScenarioEngine(base_scenario).run()
                st.session_state["scenario"] = base_scenario
                st.session_state["frames"] = scenario_to_frames(base_scenario)
                st.session_state["base"] = base_scenario.model_dump()
                st.session_state["last_run_fingerprint"] = _fingerprint(base_scenario)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                st.error(t["save_failed"].format(error=exc))

        if st.button(t["load_scenario"]):
            st.session_state["frames"] = scenario_to_frames(base_scenario)
            st.session_state["base"] = base_scenario.model_dump()
            st.session_state.pop("result", None)
            st.rerun()


    with st.sidebar:
        from ccus_core.io import (
            delete_scenario,
            list_scenarios,
            load_scenario_file,
            next_default_name,
            save_scenario,
        )

        st.subheader(t["save_section"])
        default_name = st.session_state.get("scenario_name") or next_default_name()
        name = st.text_input(t["save_name"], value=default_name, key="scenario_name")

        scenario_to_save = None
        if st.session_state.get("frames") is not None:
            try:
                scenario_to_save = frames_to_scenario(base_scenario, st.session_state["frames"])
            except Exception:  # noqa: BLE001 - the editor may be mid-edit
                scenario_to_save = None
        if scenario_to_save is None:
            scenario_to_save = base_scenario

        if st.button(t["btn_save"]):
            try:
                path = save_scenario(scenario_to_save, name)
                st.session_state["scenario_name"] = path.stem
                st.success(t["saved_ok"].format(name=path.stem))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                st.error(t["save_failed"].format(error=exc))

        saved = list_scenarios()
        if saved:
            choice = st.selectbox(
                t["select_saved"],
                [record.name for record in saved],
                key="saved_choice",
            )
            if st.button(t["btn_load"]):
                try:
                    loaded = load_scenario_file(choice)
                    st.session_state["frames"] = scenario_to_frames(loaded)
                    st.session_state["base"] = loaded.model_dump()
                    st.session_state.pop("result", None)
                    st.success(t["loaded_ok"].format(name=choice))
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 - surfaced to the user
                    st.error(t["save_failed"].format(error=exc))
            if st.checkbox(t["confirm_delete"], key="confirm_delete"):
                if st.button(t["btn_delete"]):
                    try:
                        delete_scenario(choice)
                        st.success(t["deleted_ok"].format(name=choice))
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001 - surfaced to the user
                        st.error(t["save_failed"].format(error=exc))
        else:
            st.caption(t["no_saved"])

    frames = st.session_state.get("frames")
    if frames is None:
        frames = scenario_to_frames(base_scenario)
        st.session_state["frames"] = frames
        st.session_state["base"] = base_scenario.model_dump()
    base = st.session_state.get("base")
    base_scenario = ScenarioConfig.model_validate(base) if base else base_scenario

    result = st.session_state.get("result")
    if result is None:
        st.info(t["status_idle"])
    elif st.session_state.get("last_run_fingerprint") == _fingerprint(base_scenario):
        st.success(t["status_ok"])
    else:
        st.warning(t["status_dirty"])

    (
        inputs_tab,
        emitters_tab,
        overview,
        network,
        reservoir,
        economics,
        tables,
    ) = st.tabs(
        [
            t["tab_inputs"],
            t["tab_emitters"],
            t["tab_overview"],
            t["tab_network"],
            t["tab_reservoir"],
            t["tab_economics"],
            t["tab_tables"],
        ]
    )

    with inputs_tab:
        st.caption(t["inputs_hint"])

        st.markdown(f"#### {t['sec_emitters']}")
        frames["emitters"] = st.data_editor(
            frames["emitters"],
            num_rows="dynamic",
            width="stretch",
            key="editor_emitters",
            column_config=_column_config(st, t["col_emitters"], frames["emitters"].columns, number=True, text={"id", "name"}),
        )

        _column_help(st, t["col_help"], t["col_emitters"], frames["emitters"].columns)

        st.markdown(f"#### {t['sec_connections']}")
        frames["connections"] = st.data_editor(
            frames["connections"],
            num_rows="dynamic",
            width="stretch",
            key="editor_connections",
            column_config=_column_config(
                st,
                t["col_connections"],
                frames["connections"].columns,
                number=True,
                text={"emitter_id", "sink_id"},
                select={"mode": ["pipeline", "truck", "rail", "marine"]},
            ),
        )

        _column_help(st, t["col_help"], t["col_connections"], frames["connections"].columns)

        st.markdown(f"#### {t['sec_sinks']}")
        frames["sinks"] = st.data_editor(
            frames["sinks"],
            num_rows="dynamic",
            width="stretch",
            key="editor_sinks",
            column_config=_column_config(
                st,
                t["col_sinks"],
                frames["sinks"].columns,
                number=True,
                text={"id", "name"},
                select={"type": ["DSA", "DHF"]},
                checkbox={"geothermal_coupled"},
            ),
        )

        _column_help(st, t["col_help"], t["col_sinks"], frames["sinks"].columns)

        st.markdown(f"#### {t['sec_geothermal']}")
        frames["geothermal"] = st.data_editor(
            frames["geothermal"],
            num_rows="dynamic",
            width="stretch",
            key="editor_geothermal",
            column_config=_column_config(
                st,
                t["col_geothermal"],
                frames["geothermal"].columns,
                number=True,
                text={"id", "name", "sink_id"},
            ),
        )

        _column_help(st, t["col_help"], t["col_geothermal"], frames["geothermal"].columns)

        st.markdown(f"#### {t['sec_economics']}")
        column_a, column_b, column_c, column_d = st.columns(4)
        start_year = column_a.number_input(t["econ_start"], 2000, 2100, int(base_scenario.start_year))
        end_year = column_b.number_input(t["econ_end"], 2000, 2100, int(base_scenario.end_year))
        discount = column_c.number_input(
            t["econ_discount"],
            0.0,
            0.5,
            float(base_scenario.economics.discount_rate) if base_scenario.economics else 0.05,
            0.005,
        )
        inflation = column_d.number_input(
            t["econ_inflation"],
            0.0,
            0.5,
            float(base_scenario.economics.inflation_rate) if base_scenario.economics else 0.05,
            0.005,
        )

        if st.button(t["btn_apply"], type="primary"):
            try:
                scenario = frames_to_scenario(base_scenario, frames)
                scenario = scenario.model_copy(
                    update={
                        "start_year": int(start_year),
                        "end_year": int(end_year),
                        "economics": scenario.economics.model_copy(
                            update={
                                "start_year": int(start_year),
                                "end_year": int(end_year),
                                "discount_rate": float(discount),
                                "inflation_rate": float(inflation),
                            }
                        )
                        if scenario.economics
                        else None,
                    }
                )
                st.session_state["result"] = ScenarioEngine(scenario).run()
                st.session_state["scenario"] = scenario
                st.session_state["base"] = scenario.model_dump()
                st.success(t["applied_ok"])
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                st.session_state.pop("result", None)
                st.error(t["scenario_invalid_short"].format(error=exc))

    result = st.session_state.get("result")
    if result is None:
        st.info(t["info_start"])
        return

    active_scenario = st.session_state.get("scenario", base_scenario)
    years = active_scenario.years()
    year = st.slider(t["slider_time"], min(years), max(years), min(years), step=1)
    st.caption(t["slider_help"])
    snapshot = year_snapshot(result, year)

    with emitters_tab:
        st.markdown(f"### {t['sec_compression']}")
        st.caption(t["emitters_help"])
        rows = []
        for emitter in active_scenario.emitters:
            series = {
                int(row.year): float(row.co2_chain_t)
                for row in result.ledger.itertuples(index=False)
            }
            captured = [emitter.captured_emissions(year) for year in years]
            peak_year = years[int(max(range(len(captured)), key=lambda index: captured[index]))]
            peak = max(captured) if captured else 0.0
            first_edge = next(
                (edge for edge in active_scenario.edges if edge.from_node == emitter.node_id),
                None,
            )
            state = first_edge.resolve_state(peak_year) if first_edge else None
            inlet_pressure = float(state.pipeline.inlet_pressure_bar) if state and state.pipeline else float("nan")
            distance = float(state.distance_km) if state else 0.0
            sink = None
            if first_edge is not None:
                node_id = first_edge.to_node
                sink = next((s for s in active_scenario.storage_sinks if s.node_id == node_id), None)
            rate_kg_s = peak * 1000.0 / SECONDS_PER_YEAR
            power_kw = 0.0
            if sink is not None and rate_kg_s > 0.0:
                power_kw = _compressor_power_kw(sink, rate_kg_s, inlet_pressure)
            rows.append(
                {
                    "emitter": emitter.name,
                    "activation_year": emitter.activation_year,
                    "peak_t_per_year": round(peak, 0),
                    "first_hub": first_edge.to_node if first_edge else "–",
                    "distance_km": round(distance, 1),
                    "design_inlet_pressure_bar": round(inlet_pressure, 1),
                    "compression_power_kw": round(power_kw, 1),
                    "compression_mwh_per_year": round(power_kw * HOURS_PER_YEAR / 1000.0, 1),
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch")

        st.markdown(f"#### {t['sec_tech']}")
        chart_data = {}
        for item in snapshot.emitters:
            chart_data[item["id"]] = item["captured_t"]
        yearly = pd.DataFrame(
            {
                "year": years,
                **{
                    emitter.id: [emitter.captured_emissions(year) for year in years]
                    for emitter in active_scenario.emitters
                },
            }
        ).set_index("year")
        st.bar_chart(yearly / 1e6)

    with overview:
        columns = st.columns(4)
        columns[0].metric(t["metric_captured"], f"{snapshot.totals['captured_t']:,.0f}")
        columns[1].metric(t["metric_routed"], f"{snapshot.totals['routed_t']:,.0f}")
        columns[2].metric(t["metric_injected"], f"{snapshot.totals['injected_t']:,.0f}")
        columns[3].metric(t["metric_stored"], f"{snapshot.totals['stored_t']:,.0f}")
        st.markdown(f"#### {t['sec_emitters']}")
        st.dataframe(snapshot_frame(snapshot.emitters), width="stretch")
        st.markdown(f"#### {t['sec_ledger']}")
        st.dataframe(result.ledger, width="stretch")

    with network:
        st.pyplot(build_map_figure(snapshot, active_scenario), width="stretch")
        st.caption(t["net_help"])
        st.markdown(f"#### {t['sec_edges']}")
        st.dataframe(snapshot_frame(snapshot.edges), width="stretch")

        st.markdown(f"#### {t['sec_flows']}")
        flows = (
            result.routing_frame()
            .pivot_table(index="year", columns="path", values="quantity_t", aggfunc="sum")
            .fillna(0.0)
        )
        st.bar_chart(flows / 1e6)
        st.dataframe(flows, width="stretch")

        pressure_frames = [frame for frame in result.reservoir.values()]
        if pressure_frames:
            pressures = pressure_frames[0][["year", "pressure_bar", "bhp_bar"]]
            for frame in pressure_frames[1:]:
                pressures = pressures.merge(
                    frame[["year", "pressure_bar", "bhp_bar"]].rename(
                        columns={"pressure_bar": "pressure_bar", "bhp_bar": "bhp_bar"}
                    ),
                    on="year",
                    how="outer",
                )
            st.line_chart(pressures.set_index("year"))


    with reservoir:

        sink_options = list(result.reservoir.keys())
        if sink_options:
            chosen = st.selectbox(t["sec_sink_select"], sink_options, key="sink_choice")
            frame = result.reservoir[chosen]
            with st.expander(t["sec_sink_cum"], expanded=False):
                st.line_chart(frame.set_index("year")[["co2_cumulative_t"]])
                st.dataframe(frame, width="stretch")
        for sink_id, frame in result.reservoir.items():
            st.markdown(f"**{sink_id}**")
            st.line_chart(frame.set_index("year")[["pressure_bar", "bhp_bar"]])


    with economics:
        if result.cash_flow is not None:
            columns = st.columns(4)
            columns[0].metric(t["metric_npv"], f"{result.kpis.get('npv_eur') or 0.0:,.0f}")
            columns[1].metric(t["metric_irr"], f"{(result.kpis.get('irr') or 0.0) * 100:.2f} %")
            columns[2].metric(t["metric_pv_revenue"], f"{result.kpis.get('pv_revenues_eur') or 0.0:,.0f}")
            columns[3].metric(t["metric_pv_cost"], f"{result.kpis.get('pv_costs_eur') or 0.0:,.0f}")
            st.line_chart(result.cash_flow.set_index("year")[["net_cash_flow", "cumulative_npv"]])
            st.dataframe(result.cash_flow, width="stretch")

        from ccus_core.finance import build_stakeholder_table, stakeholder_summary

        st.markdown(f"#### {t['sec_stakeholders']}")
        st.caption(t["stakeholders_help"])
        table = build_stakeholder_table(active_scenario, result)
        summary = stakeholder_summary(table)
        st.dataframe(summary, width="stretch")
        if not summary.empty:
            st.bar_chart(summary.pivot(index="year", columns="stakeholder", values="net_cash_flow_eur"))
        with st.expander(t["stakeholders_detail"], expanded=False):
            st.dataframe(table, width="stretch")

        # ------------------------------------------------ cumulative cost
        from ccus_core.finance import (
            cost_breakdown_for_year,
            cumulative_costs,
            entity_index,
            entity_statement,
        )

        st.markdown(f"#### {t['cum_cost']}")
        cumulative = cumulative_costs(result.cash_flow)
        cost_columns = [column for column in cumulative.columns if column not in {"year", "total"}]
        st.line_chart(cumulative.set_index("year")[cost_columns])
        st.caption(t["cum_cost_note"])

        # ------------------------------------------------ cost pie (last year)
        st.markdown(f"#### {t['pie_last']}")
        pie_year = st.selectbox(
            t["pie_year"],
            list(reversed([int(year) for year in result.cash_flow["year"]])),
            index=0,
            key="pie_year",
        )
        breakdown = cost_breakdown_for_year(result.cash_flow, int(pie_year))
        if len(breakdown) >= 2:
            labels = list(breakdown)
            values = [breakdown[key] for key in labels]
            figure, axis = plt.subplots(figsize=(5.6, 3.4))
            axis.pie(
                values,
                labels=labels,
                autopct="%1.1f%%",
                startangle=90,
                counterclock=False,
                textprops={"fontsize": 7.5},
                colors=plt.get_cmap("tab20").colors[: len(labels)],
            )
            axis.set_title(f"{t['pie_last']} ({int(pie_year)}.)")
            figure.tight_layout()
            st.pyplot(figure, width="stretch")
            plt.close(figure)
        else:
            st.info(t["pie_none"])

        # ------------------------------------------------ per-entity economics
        st.markdown(f"#### {t['entity_select']}")
        entities = entity_index(active_scenario)
        if entities:
            labels = [entity["label"] for entity in entities]
            choice = st.selectbox(t["entity_select"], labels, key="entity_choice")
            entity = next(item for item in entities if item["label"] == choice)
            statement = entity_statement(
                table,
                entity["stakeholder"],
                entity["id"],
                discount_rate=float(active_scenario.economics.discount_rate) if active_scenario.economics else None,
            )
            if statement["years"]:
                totals = statement["totals"]
                columns = st.columns(4)
                columns[0].metric(t["entity_capex"], f"{totals.get('capex', 0.0):,.0f} EUR")
                columns[1].metric(t["entity_opex"], f"{totals.get('opex', 0.0):,.0f} EUR")
                columns[2].metric(t["entity_transfers"], f"{totals.get('tariff_paid', 0.0) + totals.get('tariff_collected', 0.0):,.0f} EUR")
                columns[3].metric(t["entity_net"], f"{totals.get('net', 0.0):,.0f} EUR")
                if statement["npv"] is not None:
                    st.metric(t["entity_npv"], f"{statement['npv']:,.0f} EUR")

                entity_frame = pd.DataFrame(
                    {
                        "year": statement["years"],
                        **{line: statement["items"][line] for line in statement["items"]},
                        "net": statement["net_by_year"],
                    }
                ).set_index("year")
                st.dataframe(entity_frame, width="stretch")
                st.line_chart(entity_frame[["net"]])
                cumulative_net = entity_frame["net"].cumsum().rename("cumulative")
                st.line_chart(cumulative_net)
            else:
                st.info(t["entity_empty"])


    with tables:
        st.markdown(f"#### {t['sec_routes']}")
        st.dataframe(result.routing_frame(), width="stretch")
        st.download_button(
            t["download_ledger"],
            result.ledger.to_csv(index=False).encode("utf-8-sig"),
            file_name=t["file_ledger"],
            mime="text/csv; charset=utf-8",
        )


def _compressor_power_kw(sink, rate_kg_s: float, p_out_bar: float) -> float:
    """CO2 compressor power (kW) required to reach ``p_out_bar`` for one sink."""

    if rate_kg_s <= 0.0 or p_out_bar != p_out_bar:
        return 0.0
    try:
        from engineering import Power

        from ccus_core.simulation.adapters import power_inputs_for_sink

        power = Power(power_inputs_for_sink(sink, rate_kg_s), None)
        return float(
            power.calculate_compression_power(
                fluid="CO2",
                p_in_bar=float(sink.compressor_inlet_pressure_bar),
                p_out_bar=float(p_out_bar),
                t_in_C=float(sink.compressor_inlet_temperature_c),
                m_dot=float(rate_kg_s),
            )
        )
    except Exception:  # noqa: BLE001 - never break the UI on a power estimate
        return 0.0


def _column_help(st, title: str, labels: dict, columns) -> None:
    """Expandable list of column descriptions, so the headers can stay short."""

    rows = "\n".join(
        f"| `{column}` | {labels.get(column, (column, ''))[1] or '–'} |" for column in columns
    )
    with st.expander(title, expanded=False):
        st.markdown(f"| Stupac | Opis |\n|---|---|\n{rows}")


def _fingerprint(scenario: ScenarioConfig) -> str:
    """Short, stable hash of a scenario document (used for the dirty indicator)."""

    import hashlib

    payload = scenario.model_dump_json()
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _column_config(st, labels: dict, columns, *, number: bool, text: set[str], select: dict | None = None, checkbox: set[str] | None = None):
    """Build a ``column_config`` mapping from the translation table."""

    select = select or {}
    checkbox = checkbox or {}
    config = {}
    for column in columns:
        label, help_text = labels.get(column, (column, ""))
        if column in checkbox:
            config[column] = st.column_config.CheckboxColumn(label, help=help_text or None)
        elif column in select:
            config[column] = st.column_config.SelectboxColumn(label, options=select[column], help=help_text or None)
        elif column in text:
            config[column] = st.column_config.TextColumn(label, help=help_text or None)
        elif number:
            config[column] = st.column_config.NumberColumn(label, help=help_text or None)
        else:
            config[column] = st.column_config.Column(label, help=help_text or None)
    return config


if __name__ == "__main__":
    main()