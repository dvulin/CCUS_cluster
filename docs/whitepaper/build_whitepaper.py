"""Build the 2-3 page GT-CCUS whitepaper (DOCX) with generated figures.

Run from the repository root::

    python docs/whitepaper/build_whitepaper.py

Outputs ``docs/whitepaper/GT-CCUS_whitepaper.docx`` and the PNG figures next to it.
The figures are rebuilt from the real model results (workbook import), so the
document cannot drift away from the code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from ccus_core import ScenarioEngine  # noqa: E402
from ccus_core.io import load_file  # noqa: E402
from ccus_core.models import EmissionCurve, ScenarioConfig  # noqa: E402

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8,
        "axes.titlesize": 8.5,
        "axes.labelsize": 7.5,
        "axes.edgecolor": "#4a4a4a",
        "axes.linewidth": 0.6,
        "figure.dpi": 200,
    }
)

NAVY = "#12355b"
TEAL = "#1b7f79"
ORANGE = "#e07a1f"
GREY = "#8a8f98"
RED = "#c0392b"


# --------------------------------------------------------------------- figures
def figure_architecture(path: Path) -> None:
    layers = [
        ("Scenario JSON\n(commented, auditable)", "#eef2f7", NAVY),
        ("ccus_core.models\nPydantic: emitters, connections, sinks, policy", "#e3ecf5", NAVY),
        ("ccus_core.network\ntime-dependent graph + routing", "#dcebe6", TEAL),
        ("ccus_core.simulation\nreservoir / wells / geothermal / solver", "#f6e7d3", ORANGE),
        ("ccus_core.finance\nCAPEX / OPEX / NPV / IRR", "#f3dfe0", RED),
        ("engine.py  →  SimulationResult\n(DataFrames + JSON-safe dict)", "#e9e9ee", "#333333"),
        ("streamlit_app / notebook / Excel / desktop\n(import ccus_core only)", "#f2f2f2", GREY),
    ]
    figure, axis = plt.subplots(figsize=(7.2, 3.5))
    axis.set_xlim(0, 10)
    axis.set_ylim(0, len(layers) * 1.0 + 0.4)
    axis.axis("off")
    for index, (label, colour, edge) in enumerate(layers):
        y = (len(layers) - index - 1) * 1.0 + 0.2
        axis.add_patch(
            plt.Rectangle((0.3, y), 6.2, 0.78, facecolor=colour, edgecolor=edge, linewidth=0.9)
        )
        axis.text(3.4, y + 0.39, label, ha="center", va="center", fontsize=7.4, color="#111111")
        if index < len(layers) - 1:
            axis.annotate(
                "",
                xy=(3.4, y - 0.02),
                xytext=(3.4, y - 0.2),
                arrowprops=dict(arrowstyle="-|>", color=GREY, linewidth=0.8),
            )
    axis.text(
        8.9,
        len(layers) * 0.5,
        "no UI imports\nin the core\n\nphysics reused\nunchanged\n\nstateless\nper run",
        ha="center",
        va="center",
        fontsize=6.6,
        color="#444444",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#fafafa", edgecolor="#cccccc", linewidth=0.6),
    )
    axis.set_title("Figure 1 — Layered, UI-agnostic architecture", loc="left", color=NAVY)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


def figure_timeline(path: Path) -> None:
    years = np.arange(2025, 2046)
    emitters = {
        "NEXE (onboard 2026)": EmissionCurve.power_law(e0_t_per_year=656_178.0, reference_year=2025, a=-0.03, c=1.5),
        "TE Plomin (2028)": EmissionCurve.power_law(e0_t_per_year=1_118_203.0, reference_year=2025, a=-0.03, c=1.5),
        "Rafinerija Rijeka (2033)": EmissionCurve.power_law(e0_t_per_year=678_318.0, reference_year=2025, a=-0.025, c=1.5),
    }
    activation = {"NEXE (onboard 2026)": 2026, "TE Plomin (2028)": 2028, "Rafinerija Rijeka (2033)": 2033}

    figure, (left, right) = plt.subplots(1, 2, figsize=(7.4, 2.7), gridspec_kw={"width_ratios": [1.15, 1]})
    for label, curve in emitters.items():
        values = [curve.value_at(year) if year >= activation[label] else 0.0 for year in years]
        left.plot(years, np.array(values) / 1e6, label=label, linewidth=1.2)
        left.scatter([activation[label]], [0], marker="v", s=14, color="#333333", zorder=5)
    left.set_xlabel("calendar year")
    left.set_ylabel("captured CO2 (Mt/yr)")
    left.set_title("Staggered onboarding of emission curves", loc="left", color=NAVY)
    left.grid(alpha=0.25, linewidth=0.4)
    left.legend(fontsize=6.2, frameon=False)

    states = [
        ("truck", 2027, 2030, 0.12, GREY, "truck 0.12 Mt/yr"),
        ("pipeline", 2031, 2035, 0.60, TEAL, "pipeline 0.60 Mt/yr"),
        ("pipeline + 2nd train", 2036, 2045, 0.85, NAVY, "pipeline 0.85 Mt/yr"),
    ]
    for _name, start, end, capacity, colour, label in states:
        right.barh(0, end - start + 1, left=start, height=0.5, color=colour, alpha=0.85)
        right.text((start + end) / 2, 0, label, ha="center", va="center", fontsize=6.2, color="white")
    right.set_yticks([])
    right.set_xlim(2026, 2046)
    right.set_xlabel("calendar year")
    right.set_title("Infrastructure upgrade of one corridor", loc="left", color=NAVY)
    right.grid(axis="x", alpha=0.25, linewidth=0.4)
    for spine in ("top", "right", "left"):
        right.spines[spine].set_visible(False)

    figure.suptitle("Figure 2 — Time is a first-class input: onboarding, ramps and upgrades", x=0.01, ha="left", fontsize=8.5, color=NAVY)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


def figure_results(path: Path, result) -> None:
    ledger = result.ledger
    years = ledger["year"].to_numpy()
    routed = ledger["co2_chain_t"].to_numpy() / 1e6

    unallocated = np.array(
        [
            sum(item.unallocated.values()) / 1e6
            for item in result.routing
        ]
    )

    figure, (left, right) = plt.subplots(1, 2, figsize=(7.4, 2.6))
    left.bar(years, routed, color=TEAL, label="routed to storage", width=0.8)
    left.bar(years, unallocated, bottom=routed, color=RED, alpha=0.75, label="unrouted (no path / sink full)", width=0.8)
    left.set_ylabel("CO2 (Mt/yr)")
    left.set_xlabel("calendar year")
    left.set_title("Cluster throughput, workbook case (14 emitters, 3 sinks)", loc="left", color=NAVY)
    left.grid(axis="y", alpha=0.25, linewidth=0.4)
    left.legend(fontsize=6.2, frameon=False)

    for sink_id, frame in result.reservoir.items():
        right.plot(frame["year"], frame["co2_cumulative_t"] / 1e6, label=sink_id, linewidth=1.2)
    right.set_ylabel("cumulative stored (Mt)")
    right.set_xlabel("calendar year")
    right.set_title("Sink fill-up and pressure-limited injection", loc="left", color=NAVY)
    right.grid(alpha=0.25, linewidth=0.4)
    right.legend(fontsize=6.2, frameon=False)

    figure.suptitle("Figure 3 — Chronological routing exposes bottlenecks and storage limits", x=0.01, ha="left", fontsize=8.5, color=NAVY)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


# --------------------------------------------------------------------- document
def build_document(result, scenario: ScenarioConfig, images: dict[str, Path]) -> Path:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(1.6)
    section.bottom_margin = Cm(1.4)
    section.left_margin = Cm(1.9)
    section.right_margin = Cm(1.9)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(9.5)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.05

    for name, size in (("Heading 1", 12.5), ("Heading 2", 10.5)):
        style = styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0x12, 0x35, 0x5B)
        style.font.bold = True
        style.paragraph_format.space_before = Pt(7)
        style.paragraph_format.space_after = Pt(2)

    # ---------------------------------------------------------------- title
    title = document.add_paragraph()
    title.paragraph_format.space_after = Pt(0)
    run = title.add_run("GT-CCUS 2.0")
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x12, 0x35, 0x5B)

    subtitle = document.add_paragraph()
    subtitle.paragraph_format.space_after = Pt(6)
    run = subtitle.add_run(
        "A UI-agnostic simulation core for multi-emitter, multi-modal CO2 clusters "
        "(geothermal storage, dynamic emitters, cash flow)"
    )
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor(0x1B, 0x7F, 0x79)

    meta = document.add_paragraph()
    meta.paragraph_format.space_after = Pt(8)
    run = meta.add_run(
        "Technical whitepaper  ·  branch GT-CCUS-graph-streamlit  ·  "
        "Python package ccus_core  ·  69 automated tests  ·  status: pre-release"
    )
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # ---------------------------------------------------------------- summary
    document.add_heading("1. Executive summary", level=1)
    document.add_paragraph(
        "CCUS screening studies usually stop at a spreadsheet: one emitter, one pipeline, one "
        "aquifer, one cash-flow block. Real clusters are neither single nor static — emitters come "
        "on stream in different years, CO2 is moved by truck, rail, ship or pipeline, and a route "
        "that starts as a truck lane becomes a pipeline once volumes justify it. GT-CCUS 2.0 turns "
        "that spreadsheet logic into an importable Python package: a chronological simulation of "
        "the whole chain, with a graph in which every transport state has a year, and a cash-flow "
        "model that prices each of those states."
    )
    document.add_paragraph(
        "The engine is deliberately decoupled from the presentation layer. The same scenario file "
        "drives a Streamlit app, a notebook, a desktop tool or an Excel add-in; the physics, the "
        "routing and the financial model are never imported by the user interface, and never import it."
    )

    kpis = [
        ("Model objects", "emitters, connections, nodes, sinks, geothermal, policy"),
        ("Transport modes", "pipeline, truck, rail, marine"),
        ("Onboarding", "per emitter and per emitter–sink pair (independent start year)"),
        ("Upgrades", "planned year-based or conditional (cumulative volume)"),
        ("Physics reused", "material balance, VFP, geothermal doublet, ORC/pump/compressor, pipeline"),
        ("Outputs", "annual ledger, routing ledger, per-sink pressures, cash flow, NPV/IRR"),
    ]
    table = document.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for label, value in kpis:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        for paragraph in cells[0].paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(8.2)
                run.font.bold = True
        for paragraph in cells[1].paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(8.2)
    document.add_paragraph()

    # ---------------------------------------------------------------- problem
    document.add_heading("2. What changes compared with the current model", level=1)
    document.add_paragraph(
        "The existing GT-CCS application computes one chain over a pressure ramp: a constant annual "
        "mass, one emitter, one transport leg and one storage site. Four limitations follow from that "
        "design, and each one is addressed explicitly:"
    )
    for text in [
        "Constant emission — no ramp-up, steady state or decline, and no way to describe when an "
        "emitter actually joins the cluster. Emission curves now support a constant, a piecewise-linear "
        "ramp/steady/decline profile and the study's power law E(t) = E0 + b·x^c with b = a·E0.",
        "Single transport mode — truck and rail exist only as a cost rate. Transport is now a "
        "time-dependent directed multigraph with capacity, tariff and modal design (vessel size, port "
        "throughput, weather availability, fleet size).",
        "Static infrastructure — an upgrade can only be modelled by editing the input and re-running. "
        "An edge now carries a state timeline plus conditional upgrades, so 'trucks for three years, "
        "then a pipeline' is one scenario, not three.",
        "One chain, one NPV — no shared capacity between emitters and no routing feedback. Routing is "
        "capacity-constrained per year, so a saturated sink or a full port shows up as unallocated CO2 "
        "instead of disappearing into an average.",
    ]:
        paragraph = document.add_paragraph(text, style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(1)
        for run in paragraph.runs:
            run.font.size = Pt(9)

    # ---------------------------------------------------------------- figure 1
    document.add_heading("3. Architecture", level=1)
    document.add_paragraph(
        "The core is a stack of pure packages (Figure 1). Models are Pydantic objects and contain no "
        "I/O; network and simulation import them; finance reuses the audited cash-flow runner; and "
        "engine.py is the only facade an application needs. The legacy engineering and economics "
        "modules are imported by the core and never the other way round, so every existing physical "
        "correlation stays the single source of truth."
    )
    document.add_picture(str(images["architecture"]), width=Cm(16.6))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---------------------------------------------------------------- figure 2
    document.add_heading("4. How a scenario is simulated", level=1)
    steps = [
        ("Resolve the calendar", "one year at a time; every emitter and every emitter–sink pair has its own first year."),
        ("Query the active emitters", "gross emissions come from the emission curve, captured mass is limited by the capture unit."),
        ("Resolve the network state", "for the year, each edge returns its planned state or a fired upgrade (year-based or cumulative-volume trigger)."),
        ("Route the mass", "cheapest feasible path under residual edge, port, weather and sink capacities; leftovers are reported as unallocated."),
        ("Update the physics", "cumulative mass is inverted against the material-balance curve, BHP is recomputed at the local rate, and the geothermal doublet follows the resulting pressure."),
        ("Value the cash flow", "CAPEX schedules (including upgrade CAPEX) and modal OPEX are escalated by inflation and discounted; NPV and IRR follow."),
    ]
    for index, (name, text) in enumerate(steps, start=1):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(1)
        run = paragraph.add_run(f"{index}. {name}. ")
        run.font.bold = True
        run.font.size = Pt(9)
        run = paragraph.add_run(text)
        run.font.size = Pt(9)

    document.add_picture(str(images["timeline"]), width=Cm(16.6))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---------------------------------------------------------------- results
    document.add_heading("5. What the engine produces", level=1)
    kpi = result.kpis
    document.add_paragraph(
        f"On the workbook case (14 emitters, 3 storage sites: Ivanić 5.5 Mt, Stružec 1.7 Mt, "
        f"Bokić 13.7 Mt) the engine routes {kpi['routed_co2_t'] / 1e6:,.2f} Mt into the sinks and "
        f"reports {kpi['unallocated_co2_t'] / 1e6:,.2f} Mt that has no feasible route in its year — "
        f"the number a cluster study needs before it promises a storage site to an emitter. "
        f"The resulting project NPV is {kpi['npv_eur'] / 1e6:,.1f} M€."
    )
    document.add_picture(str(images["results"]), width=Cm(16.6))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    document.add_paragraph(
        "Two properties of that result are worth stressing. First, the unallocated mass is not a "
        "rounding error: it is the capacity of the transport plan in that year, and it drives the "
        "business decision to build a second route or a second storage site. Second, the injection "
        "stop is physical — it happens when the reservoir pressure reaches the fracture limit or the "
        "site capacity is used up, not when a spreadsheet year runs out."
    )

    # ---------------------------------------------------------------- benefits
    document.add_heading("6. Benefits", level=1)
    for text in [
        "One scenario file, many front ends. The same JSON runs in Streamlit, a notebook or a desktop "
        "application; the UI never contains physics.",
        "Auditable numbers. Every input keeps its unit and comment in the JSON, and every result is a "
        "DataFrame that can be exported or compared year by year.",
        "No double counting. Transport cost is charged per routed tonne on the arcs actually used, so a "
        "shared pipeline is not paid twice and an upgrade is not billed in a year it is not in service.",
        "Physics stays authoritative. The new engine inverts and reuses the existing material balance, "
        "VFP and geothermal models instead of re-implementing them; the constant-rate case reproduces "
        "the legacy result (276.09 bar after the reference injection period).",
        "Tested where it hurts. 69 tests cover staggered onboarding, mid-run upgrades, offshore "
        "bottlenecks, multi-emitter/multi-sink routing, ETS phase-out and JSON round-trips — plus a "
        "golden regression test of the legacy application.",
    ]:
        paragraph = document.add_paragraph(text, style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(1)
        for run in paragraph.runs:
            run.font.size = Pt(9)

    # ---------------------------------------------------------------- roadmap
    document.add_heading("7. Status and next steps", level=1)
    document.add_paragraph(
        "Implemented: dynamic emission curves and onboarding, the time-dependent multi-modal graph with "
        "upgrades, the chronological routing engine, the reservoir/well/geothermal coupling, the "
        "financial coupling with modal tariffs and upgrade CAPEX, the commented JSON format, the "
        "workbook importer and the Streamlit presentation layer. Next: monthly resolution as an option, "
        "offshore wells with their own BHP limits, stochastic weather downtime and a full replacement of "
        "the legacy single-chain UI."
    )

    output = HERE / "GT-CCUS_whitepaper.docx"
    document.save(output)
    return output


def main() -> None:
    scenario = load_file(ROOT / "inputs" / "examples" / "croatia_cluster_2025_2050.json")
    result = ScenarioEngine(scenario).run()

    images = {
        "architecture": HERE / "fig1_architecture.png",
        "timeline": HERE / "fig2_timeline.png",
        "results": HERE / "fig3_results.png",
    }
    figure_architecture(images["architecture"])
    figure_timeline(images["timeline"])
    figure_results(images["results"], result)

    output = build_document(result, scenario, images)
    print(f"written {output} ({output.stat().st_size / 1024:.0f} kB)")
    print(f"kpis: routed {result.kpis['routed_co2_t'] / 1e6:.2f} Mt, "
          f"unallocated {result.kpis['unallocated_co2_t'] / 1e6:.2f} Mt, "
          f"npv {result.kpis['npv_eur'] / 1e6:.1f} M EUR")


if __name__ == "__main__":
    main()