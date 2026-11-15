"""Streamlit presentation layer for the CCUS cluster engine.

The UI is deliberately thin: it imports :mod:`ccus_core` and nothing else from the
project.  All physics, routing and financial logic lives in the engine, so this
module can be replaced (desktop app, Excel add-in, notebook) without touching the
model code.

The configuration tab edits the whole stakeholder set â€” emitters, their emission
curves, every emitterâ†’sink access and every storage site â€” through editable
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

from ccus_core import ScenarioEngine, ScenarioConfig, year_snapshot  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = REPOSITORY_ROOT / "inputs" / "examples" / "ccus_cluster_v1.json"
DEFAULT_CLUSTER = REPOSITORY_ROOT / "inputs" / "examples" / "croatia_cluster_2025_2050.json"

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
    """Draw the transport graph of one year (nodes, edges, flow width)."""

    positions: dict[str, tuple[float, float]] = {}
    for node in scenario.nodes:
        if node.location.latitude is not None and node.location.longitude is not None:
            positions[node.id] = (float(node.location.longitude), float(node.location.latitude))

    missing = [node.id for node in scenario.nodes if node.id not in positions]
    for index, node_id in enumerate(missing):
        positions[node_id] = (16.0 + 0.35 * index, 45.6 - 0.35 * index)

    figure, axis = plt.subplots(figsize=(8.2, 5.6))
    for edge in snapshot.edges:
        start = positions.get(edge["from_node"])
        end = positions.get(edge["to_node"])
        if start is None or end is None:
            continue
        width = 1.0 + 4.0 * min(1.0, float(edge["flow_t"]) / 500_000.0)
        axis.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            color=MODE_COLOURS.get(edge["mode"] or "", "#999999"),
            linewidth=width,
            alpha=0.35 if not edge["active"] else 0.9,
            zorder=1,
        )

    for node in scenario.nodes:
        longitude, latitude = positions[node.id]
        sink = next((item for item in snapshot.sinks if item["node_id"] == node.id), None)
        emitter = next((item for item in snapshot.emitters if item["node_id"] == node.id), None)
        if sink is not None:
            marker, size, colour = "s", 130.0, "#d62728"
        elif emitter is not None:
            marker, size, colour = "o", 90.0, "#333333"
        else:
            marker, size, colour = "^", 70.0, "#7f7f7f"
        axis.scatter([longitude], [latitude], marker=marker, s=size, color=colour, edgecolor="white", linewidth=0.8, zorder=2)
        axis.annotate(node.name, (longitude, latitude), fontsize=7, xytext=(4, 4), textcoords="offset points")

    handles = [
        plt.Line2D([0], [0], color=colour, linewidth=3, label=label)
        for mode, colour in MODE_COLOURS.items()
        if any(edge["mode"] == mode for edge in snapshot.edges)
        for label in [MODE_LABELS.get(mode, mode)]
    ]
    if handles:
        axis.legend(handles=handles, fontsize=7, loc="lower left", frameon=False)
    axis.set_xlabel("Geografska duĹľina")
    axis.set_ylabel("Geografska Ĺˇirina")
    axis.set_title(f"Transportna mreĹľa, {snapshot.year}.")
    axis.grid(alpha=0.2)
    figure.tight_layout()
    return figure


def snapshot_frame(rows: list[dict]):
    import pandas as pd

    return pd.DataFrame(rows)


# --------------------------------------------------------------------- app
def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="CCUS cluster", layout="wide")
    st.title("CCUS cluster â€“ dinamiÄŤni emiteri i multimodalni transport")

    with st.sidebar:
        st.header("Scenarij")
        source = st.radio(
            "Izvor",
            ["Klaster (14 emitera)", "Jedan lanac (legacy)", "UÄŤitaj JSON"],
            index=0,
        )
        if source == "Klaster (14 emitera)":
            payload = DEFAULT_CLUSTER
        elif source == "Jedan lanac (legacy)":
            payload = DEFAULT_SCENARIO
        else:
            uploaded = st.file_uploader("JSON scenarij", type=["json"])
            payload = uploaded.getvalue() if uploaded is not None else DEFAULT_CLUSTER
        try:
            base_scenario = load_scenario(payload)
            st.success(f"Scenarij: {base_scenario.name}")
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            st.error(f"NevrjeÄ‘an scenarij: {exc}")
            return

        if st.button("UÄŤitaj scenarij"):
            st.session_state["frames"] = scenario_to_frames(base_scenario)
            st.session_state["base"] = base_scenario.model_dump()
            st.session_state.pop("result", None)
            st.rerun()

    frames = st.session_state.get("frames")
    if frames is None:
        frames = scenario_to_frames(base_scenario)
        st.session_state["frames"] = frames
        st.session_state["base"] = base_scenario.model_dump()
    base = st.session_state.get("base")
    base_scenario = ScenarioConfig.model_validate(base) if base else base_scenario

    inputs_tab, overview, network, reservoir, economics, tables = st.tabs(
        ["Ulazi", "SaĹľetak", "MreĹľa", "SkladiĹˇte", "Ekonomika", "Tablice"]
    )

    with inputs_tab:
        st.caption(
            "Uredi tablice, zatim klikni 'Primijeni i pokreni'. Nove emitere, pristupe i skladiĹˇta "
            "dodajeĹˇ u redak na dnu tablice (prazno polje = NaN)."
        )
        frames["emitters"] = st.data_editor(
            frames["emitters"],
            num_rows="dynamic",
            width="stretch",
            key="editor_emitters",
        )
        frames["connections"] = st.data_editor(
            frames["connections"],
            num_rows="dynamic",
            width="stretch",
            key="editor_connections",
        )
        frames["sinks"] = st.data_editor(
            frames["sinks"],
            num_rows="dynamic",
            width="stretch",
            key="editor_sinks",
        )
        frames["geothermal"] = st.data_editor(
            frames["geothermal"],
            num_rows="dynamic",
            width="stretch",
            key="editor_geothermal",
        )

        st.markdown("#### Ekonomika")
        column_a, column_b, column_c, column_d = st.columns(4)
        start_year = column_a.number_input("PoÄŤetna godina", 2000, 2100, int(base_scenario.start_year))
        end_year = column_b.number_input("ZavrĹˇna godina", 2000, 2100, int(base_scenario.end_year))
        discount = column_c.number_input(
            "Diskontna stopa", 0.0, 0.5,
            float(base_scenario.economics.discount_rate) if base_scenario.economics else 0.05, 0.005,
        )
        inflation = column_d.number_input(
            "Inflacija", 0.0, 0.5,
            float(base_scenario.economics.inflation_rate) if base_scenario.economics else 0.05, 0.005,
        )

        if st.button("Primijeni i pokreni", type="primary"):
            try:
                scenario = frames_to_scenario(base_scenario, frames)
                scenario = scenario.model_copy(
                    update={
                        "start_year": int(start_year),
                        "end_year": int(end_year),
                        "economics": scenario.economics.model_copy(
                            update={"start_year": int(start_year), "end_year": int(end_year),
                                    "discount_rate": float(discount), "inflation_rate": float(inflation)}
                        ) if scenario.economics else None,
                    }
                )
                st.session_state["result"] = ScenarioEngine(scenario).run()
                st.session_state["scenario"] = scenario
                st.session_state["base"] = scenario.model_dump()
                st.success("Scenarij je osvjeĹľen.")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                st.session_state.pop("result", None)
                st.error(f"Scenarij nije valjan: {exc}")

    result = st.session_state.get("result")
    if result is None:
        st.info("Uredi tablice i klikni 'Primijeni i pokreni', ili pokreni postojeÄ‡i scenarij.")
        return

    active_scenario = st.session_state.get("scenario", base_scenario)
    years = active_scenario.years()
    year = st.slider("Vremenska os", min(years), max(years), min(years), step=1)
    snapshot = year_snapshot(result, year)

    with overview:
        columns = st.columns(4)
        columns[0].metric("UsjeÄŤeno COâ‚‚ (t)", f"{snapshot.totals['captured_t']:,.0f}")
        columns[1].metric("Rutirano (t)", f"{snapshot.totals['routed_t']:,.0f}")
        columns[2].metric("Utisnuto (t)", f"{snapshot.totals['injected_t']:,.0f}")
        columns[3].metric("Pohranjeno ukupno (t)", f"{snapshot.totals['stored_t']:,.0f}")
        st.markdown("#### Emiteri")
        st.dataframe(snapshot_frame(snapshot.emitters), width="stretch")
        st.markdown("#### GodiĹˇnji tehniÄŤki bilten")
        st.dataframe(result.ledger, width="stretch")

    with network:
        st.pyplot(build_map_figure(snapshot, active_scenario), width="stretch")
        st.markdown("#### Usmjerenja u odabranoj godini")
        st.dataframe(snapshot_frame(snapshot.edges), width="stretch")

    with reservoir:
        for sink_id, frame in result.reservoir.items():
            st.markdown(f"#### {sink_id}")
            st.line_chart(frame.set_index("year")[["pressure_bar", "bhp_bar"]])
            st.dataframe(frame, width="stretch")

    with economics:
        if result.cash_flow is not None:
            columns = st.columns(4)
            columns[0].metric("NPV (EUR)", f"{result.kpis.get('npv_eur') or 0.0:,.0f}")
            columns[1].metric("IRR", f"{(result.kpis.get('irr') or 0.0) * 100:.2f} %")
            columns[2].metric("PV prihodi (EUR)", f"{result.kpis.get('pv_revenues_eur') or 0.0:,.0f}")
            columns[3].metric("PV troĹˇkovi (EUR)", f"{result.kpis.get('pv_costs_eur') or 0.0:,.0f}")
            st.line_chart(result.cash_flow.set_index("year")[["net_cash_flow", "cumulative_npv"]])
            st.dataframe(result.cash_flow, width="stretch")

    with tables:
        st.markdown("#### Rute")
        st.dataframe(result.routing_frame(), width="stretch")
        st.download_button(
            "Preuzmi tehniÄŤki bilten (CSV)",
            result.ledger.to_csv(index=False).encode("utf-8"),
            file_name="ccus_ledger.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()