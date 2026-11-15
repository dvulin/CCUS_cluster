"""Streamlit presentation layer for the CCUS cluster engine.

The UI is deliberately thin: it imports :mod:`ccus_core` and nothing else from the
project.  All physics, routing and financial logic lives in the engine, so this
module can be replaced (desktop app, Excel add-in, notebook) without touching the
model code.

Run with::

    streamlit run streamlit_app/app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ccus_core import ScenarioEngine, ScenarioConfig, year_snapshot  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = REPOSITORY_ROOT / "inputs" / "examples" / "ccus_cluster_v1.json"

MODE_COLOURS = {
    "pipeline": "#1f77b4",
    "truck": "#ff7f0e",
    "rail": "#2ca02c",
    "marine": "#17becf",
}

MODE_LABELS = {
    "pipeline": "Cjevovod",
    "truck": "Kamion",
    "rail": "Željeznica",
    "marine": "Brod",
}


# --------------------------------------------------------------------- data
def load_scenario(payload: bytes | str | Path) -> ScenarioConfig:
    """Validate a JSON scenario from a path, a string or an uploaded file."""

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, (str, Path)) and not str(payload).lstrip().startswith("{"):
        payload = Path(payload).read_text(encoding="utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    return ScenarioConfig.model_validate(payload)


def apply_overrides(scenario: ScenarioConfig, overrides: dict) -> ScenarioConfig:
    """Return a copy of ``scenario`` with UI overrides applied."""

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
            if profile["kind"] == "constant":
                profile["constant_t_per_year"] = value
            else:
                # a non-constant profile is flattened to the requested value so the
                # slider has a predictable effect on ramp scenarios too
                profile["points"] = {int(year): value for year in profile["points"]}
    if "discount_rate" in overrides and payload.get("economics"):
        payload["economics"]["discount_rate"] = float(overrides["discount_rate"])
    if "end_year" in overrides:
        payload["end_year"] = int(overrides["end_year"])
        if payload.get("economics"):
            payload["economics"]["end_year"] = max(
                int(payload["economics"]["start_year"]), int(overrides["end_year"])
            )
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
        axis.scatter(
            [longitude],
            [latitude],
            marker=marker,
            s=size,
            color=colour,
            edgecolor="white",
            linewidth=0.8,
            zorder=2,
        )
        axis.annotate(node.name, (longitude, latitude), fontsize=7, xytext=(4, 4), textcoords="offset points")

    handles = [
        plt.Line2D([0], [0], color=colour, linewidth=3, label=label)
        for mode, colour in MODE_COLOURS.items()
        if any(edge["mode"] == mode for edge in snapshot.edges)
        for label in [MODE_LABELS.get(mode, mode)]
    ]
    if handles:
        axis.legend(handles=handles, fontsize=7, loc="lower left", frameon=False)
    axis.set_xlabel("Geografska dužina")
    axis.set_ylabel("Geografska širina")
    axis.set_title(f"Transportna mreža, {snapshot.year}.")
    axis.grid(alpha=0.2)
    figure.tight_layout()
    return figure


def build_routing_frame(result):
    return result.routing_frame()


# --------------------------------------------------------------------- app
def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="CCUS cluster", layout="wide")
    st.title("CCUS cluster – dinamični emiteri i multimodalni transport")

    with st.sidebar:
        st.header("Scenarij")
        source = st.radio("Izvor", ["Primjer iz repozitorija", "Učitaj JSON"], index=0)
        if source == "Primjer iz repozitorija":
            payload: bytes | str | Path = DEFAULT_SCENARIO
        else:
            uploaded = st.file_uploader("JSON scenarij", type=["json"])
            payload = uploaded.getvalue() if uploaded is not None else DEFAULT_SCENARIO
        try:
            scenario = load_scenario(payload)
            st.success(f"Scenarij: {scenario.name}")
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            st.error(f"Nevrjeđan scenarij: {exc}")
            return

        with st.expander("Uredi ključne ulaze", expanded=False):
            activation = {
                emitter.id: st.number_input(
                    f"Početak – {emitter.name}",
                    min_value=scenario.start_year,
                    max_value=scenario.end_year,
                    value=int(emitter.activation_year),
                    step=1,
                )
                for emitter in scenario.emitters
            }
            emissions = {
                emitter.id: st.number_input(
                    f"Emisije (t/god) – {emitter.name}",
                    min_value=0.0,
                    value=float(emitter.gross_emissions.value_at(scenario.end_year) or 0.0),
                    step=10_000.0,
                )
                for emitter in scenario.emitters
            }
            discount = st.number_input(
                "Diskontna stopa", 0.0, 0.5, float(scenario.economics.discount_rate if scenario.economics else 0.05), 0.005
            )
            if st.button("Primijeni izmjene"):
                scenario = apply_overrides(
                    scenario,
                    {
                        "activation_year": activation,
                        "emission_t_per_year": emissions,
                        "discount_rate": discount,
                    },
                )
                st.session_state["scenario_payload"] = scenario.model_dump()
                st.rerun()

    st.caption(
        f"Čvorovi: {len(scenario.nodes)} · usmjerivači: {len(scenario.edges)} · "
        f"skladišta: {len(scenario.storage_sinks)} · geotermalni sustavi: {len(scenario.geothermal_systems)}"
    )

    if st.button("Pokreni proračun", type="primary"):
        with st.spinner("Rješavanje cjelokupne vremenske osi…"):
            st.session_state["result"] = ScenarioEngine(scenario).run()
            st.session_state["scenario"] = scenario

    result = st.session_state.get("result")
    active_scenario = st.session_state.get("scenario", scenario)
    if result is None:
        st.info("Pokreni proračun za prikaz rezultata.")
        return

    years = active_scenario.years()
    year = st.slider("Vremenska os", min(years), max(years), min(years), step=1)
    snapshot = year_snapshot(result, year)

    overview, network, reservoir, economics, tables = st.tabs(
        ["Sažetak", "Mreža", "Skladište", "Ekonomika", "Tablice"]
    )

    with overview:
        columns = st.columns(4)
        columns[0].metric("Usječeno CO₂ (t)", f"{snapshot.totals['captured_t']:,.0f}")
        columns[1].metric("Rutirano (t)", f"{snapshot.totals['routed_t']:,.0f}")
        columns[2].metric("Utisnuto (t)", f"{snapshot.totals['injected_t']:,.0f}")
        columns[3].metric("Pohranjeno ukupno (t)", f"{snapshot.totals['stored_t']:,.0f}")

        st.markdown("#### Emiteri")
        st.dataframe(snapshot_frame(snapshot.emitters), width="stretch")
        st.markdown("#### Godišnji tehnički bilten")
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
            columns[3].metric("PV troškovi (EUR)", f"{result.kpis.get('pv_costs_eur') or 0.0:,.0f}")
            st.line_chart(result.cash_flow.set_index("year")[["net_cash_flow", "cumulative_npv"]])
            st.dataframe(result.cash_flow, width="stretch")

    with tables:
        st.markdown("#### Rute")
        st.dataframe(build_routing_frame(result), width="stretch")
        st.download_button(
            "Preuzmi tehnički bilten (CSV)",
            result.ledger.to_csv(index=False).encode("utf-8"),
            file_name="ccus_ledger.csv",
            mime="text/csv",
        )


def snapshot_frame(rows: list[dict]) -> "object":
    import pandas as pd

    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()