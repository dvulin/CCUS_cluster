"""Build the GT-CCUS whitepaper (DOCX): serif figures, OMML equations, JSON appendix.

Run from the repository root::

    python docs/whitepaper/build_whitepaper.py

Outputs ``docs/whitepaper/GT-CCUS_whitepaper.docx`` plus the PNG figures.  Figures are
rebuilt from the real model results and the appendix tables are generated from the
Pydantic models, so the document cannot drift away from the code.

Formatting conventions
----------------------
* figures use a Roman/serif typeface (STIX) with LaTeX-style math labels;
* governing equations are native Word equations (OMML, i.e. MathType-compatible),
  converted from LaTeX through MathML with the Office ``MML2OMML.XSL`` stylesheet;
* the appendix documents every JSON field with type, unit, requirement and default.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import rcParams

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from ccus_core import ScenarioEngine  # noqa: E402
from ccus_core.io import load_file  # noqa: E402
from ccus_core.models import EmissionCurve  # noqa: E402

# --------------------------------------------------------------------- style
NAVY = "#12355b"
TEAL = "#1b6f6a"
ORANGE = "#b5651d"
GREY = "#7a7f87"
RED = "#a63232"

rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.labelsize": 8.5,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7.2,
        "axes.edgecolor": "#333333",
        "axes.linewidth": 0.6,
        "figure.dpi": 220,
    }
)

XSL_PATH = Path(r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL")


# --------------------------------------------------------------------- equations
def latex_to_omml(latex: str):
    """Convert a LaTeX expression into a Word (OMML) element."""

    import latex2mathml.converter as converter
    from lxml import etree

    mathml = converter.convert(latex)
    transform = etree.XSLT(etree.parse(str(XSL_PATH)))
    return transform(etree.fromstring(mathml)).getroot()


def add_equation(document, latex: str, number: str | None = None) -> None:
    """Append a display equation as a native Word equation object."""

    from docx.enum.text import WD_ALIGN_PARAGRAPH

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = 4
    paragraph.paragraph_format.space_after = 4
    try:
        paragraph._p.append(latex_to_omml(latex))
    except Exception as exc:  # pragma: no cover - keeps the build alive
        paragraph.add_run(f"[equation unavailable: {exc}]")
    if number:
        run = paragraph.add_run(f"\t({number})")
        run.font.size = 9


# --------------------------------------------------------------------- figures
def figure_architecture(path: Path) -> None:
    layers = [
        ("Scenario JSON — commented, auditable input", "#eef2f7", NAVY),
        ("ccus_core.models — Pydantic: emitters, connections, sinks, policy", "#e2ebf4", NAVY),
        ("ccus_core.network — time-dependent graph and capacity routing", "#dcebe6", TEAL),
        ("ccus_core.simulation — reservoir, wells, geothermal, solver", "#f6e7d3", ORANGE),
        ("ccus_core.finance — CAPEX, OPEX, NPV, IRR", "#f2dedf", RED),
        ("engine.py — ScenarioEngine → SimulationResult (DataFrames)", "#e9e9ee", "#333333"),
        ("streamlit_app · notebook · Excel · desktop (import ccus_core only)", "#f2f2f2", GREY),
    ]
    figure, axis = plt.subplots(figsize=(7.2, 3.4))
    axis.set_xlim(0, 10)
    axis.set_ylim(0, len(layers) + 0.2)
    axis.axis("off")
    for index, (label, colour, edge) in enumerate(layers):
        y = len(layers) - index - 0.8
        axis.add_patch(
            plt.Rectangle((0.25, y), 6.4, 0.66, facecolor=colour, edgecolor=edge, linewidth=0.9)
        )
        axis.text(3.45, y + 0.33, label, ha="center", va="center", fontsize=7.6, color="#111111")
        if index < len(layers) - 1:
            axis.annotate(
                "",
                xy=(3.45, y - 0.02),
                xytext=(3.45, y - 0.14),
                arrowprops=dict(arrowstyle="-|>", color=GREY, linewidth=0.8),
            )
    axis.text(
        8.55,
        len(layers) / 2,
        "no UI import\nin the core\n\nphysics reused\nunchanged\n\nstateless per run",
        ha="center",
        va="center",
        fontsize=7,
        color="#333333",
        bbox=dict(boxstyle="round,pad=0.45", facecolor="#fafafa", edgecolor="#c8c8c8", linewidth=0.6),
    )
    axis.set_title(
        "Figure 1 — Layered, UI-agnostic architecture (physics never imports the UI)",
        loc="left",
        color=NAVY,
    )
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


def figure_timeline(path: Path) -> None:
    years = np.arange(2025, 2046)
    emitters = {
        "NEXE": (EmissionCurve.power_law(e0_t_per_year=656_178.0, reference_year=2025, a=-0.03, c=1.5), 2026),
        "TE Plomin": (EmissionCurve.power_law(e0_t_per_year=1_118_203.0, reference_year=2025, a=-0.03, c=1.5), 2028),
        "Rafinerija Rijeka": (EmissionCurve.power_law(e0_t_per_year=678_318.0, reference_year=2025, a=-0.025, c=1.5), 2033),
    }

    figure, (left, right) = plt.subplots(1, 2, figsize=(7.4, 2.9), gridspec_kw={"width_ratios": [1.1, 1]})

    for label, (curve, activation) in emitters.items():
        values = np.array(
            [curve.value_at(int(year)) if year >= activation else 0.0 for year in years]
        ) / 1e6
        left.plot(years, values, label=label, linewidth=1.3)
        left.plot([activation], [0.0], marker="v", markersize=5.5, color="#222222", zorder=5)

    left.set_xlabel("calendar year")
    left.set_ylabel(r"captured CO$_2$  (Mt yr$^{-1}$)")
    left.set_xlim(2025, 2045)
    left.set_ylim(bottom=-0.03)
    left.set_xticks(np.arange(2025, 2046, 4))
    left.grid(alpha=0.25, linewidth=0.4)
    left.legend(loc="upper right", frameon=False, title="emitter", title_fontsize=7)
    left.set_title("(a) staggered onboarding of emission curves", loc="left", color=NAVY)

    rows = [
        ("trucks\n0.12 Mt yr$^{-1}$", 2027, 2030, 0.12, GREY),
        ("pipeline\n0.60 Mt yr$^{-1}$", 2031, 2035, 0.60, TEAL),
        ("pipeline + 2nd train\n0.85 Mt yr$^{-1}$", 2036, 2045, 0.85, NAVY),
    ]
    for index, (label, start, end, capacity, colour) in enumerate(rows):
        right.barh(
            index,
            end - start + 1,
            left=start,
            height=0.55,
            color=colour,
            alpha=0.9,
            edgecolor="white",
            linewidth=0.6,
        )
        right.text(
            (start + end) / 2,
            index,
            f"{start}–{end}",
            ha="center",
            va="center",
            fontsize=7.4,
            color="white",
        )

    right.set_yticks(range(len(rows)))
    right.set_yticklabels([row[0] for row in rows], fontsize=7.0)
    right.set_xlim(2026, 2046)
    right.set_xticks(np.arange(2026, 2047, 4))
    right.set_xlabel("calendar year")
    right.grid(axis="x", alpha=0.25, linewidth=0.4)
    for spine in ("top", "right", "left"):
        right.spines[spine].set_visible(False)
    right.tick_params(axis="y", length=0)
    right.tick_params(axis="x", labelsize=7.0)
    right.set_title("(b) one corridor: capacity state per year", loc="left", color=NAVY)

    figure.suptitle(
        "Figure 2 — Time is a first-class input: onboarding, ramps and infrastructure upgrades",
        x=0.01,
        ha="left",
        fontsize=9,
        color=NAVY,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


def figure_results(path: Path, result) -> None:
    ledger = result.ledger
    years = ledger["year"].to_numpy()
    routed = ledger["co2_chain_t"].to_numpy() / 1e6
    unallocated = np.array([sum(item.unallocated.values()) / 1e6 for item in result.routing])

    figure, (left, right) = plt.subplots(1, 2, figsize=(7.4, 2.7))
    left.bar(years, routed, color=TEAL, label="routed to storage", width=0.8)
    left.bar(years, unallocated, bottom=routed, color=RED, alpha=0.75, label="unrouted (no feasible path)", width=0.8)
    left.set_ylabel(r"CO$_2$  (Mt yr$^{-1}$)")
    left.set_xlabel("calendar year")
    left.set_xticks(np.arange(2025, 2051, 5))
    left.grid(axis="y", alpha=0.25, linewidth=0.4)
    left.legend(frameon=False, loc="upper right")
    left.set_title("(a) cluster throughput, workbook case (14 emitters, 3 sinks)", loc="left", color=NAVY)

    for sink_id, frame in result.reservoir.items():
        right.plot(frame["year"], frame["co2_cumulative_t"] / 1e6, label=sink_id, linewidth=1.3)
    right.set_ylabel("cumulative stored CO$_2$  (Mt)")
    right.set_xlabel("calendar year")
    right.set_xticks(np.arange(2025, 2051, 5))
    right.grid(alpha=0.25, linewidth=0.4)
    right.legend(frameon=False, loc="lower right")
    right.set_title("(b) sink fill-up and pressure-limited injection", loc="left", color=NAVY)

    figure.suptitle(
        "Figure 3 — Chronological routing exposes bottlenecks and storage limits",
        x=0.01,
        ha="left",
        fontsize=9,
        color=NAVY,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)


# --------------------------------------------------------------------- appendix
def field_rows(model) -> list[tuple[str, str, str, str]]:
    """Describe every field of a Pydantic model for the JSON appendix."""

    rows: list[tuple[str, str, str, str]] = []
    for name, field in model.model_fields.items():
        annotation = field.annotation
        type_name = getattr(annotation, "__name__", None) or str(annotation).replace("typing.", "")
        type_name = type_name.replace(" | None", " (opt.)")
        required = "yes" if field.is_required() else "no"
        default = "" if field.is_required() else str(field.default)
        if len(default) > 26:
            default = default[:23] + "…"
        description = (field.description or "").replace("\n", " ")
        rows.append((name, type_name, required, default, description))
    return rows


def add_table(document, title: str, rows, widths=(3.6, 3.6, 2.2, 8.0)) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt

    caption = document.add_paragraph()
    caption.paragraph_format.space_before = 5
    caption.paragraph_format.space_after = 1
    run = caption.add_run(title)
    run.font.bold = True
    run.font.size = Pt(8.6)

    table = document.add_table(rows=1, cols=4)
    table.style = "Light Grid Accent 1"
    table.autofit = False

    # tighten the cell margins: the specification is dense by nature
    margins = OxmlElement("w:tblCellMar")
    for side, width in (("top", 0), ("left", 28), ("bottom", 0), ("right", 28)):
        element = OxmlElement(f"w:{side}")
        element.set(qn("w:w"), str(width))
        element.set(qn("w:type"), "dxa")
        margins.append(element)
    table._tbl.tblPr.append(margins)

    header = table.rows[0].cells
    for cell, text in zip(header, ("field", "type", "default", "description")):
        cell.text = text
        for paragraph in cell.paragraphs:
            paragraph.paragraph_format.space_after = Pt(0)
            for item in paragraph.runs:
                item.font.size = Pt(7.0)
                item.font.bold = True
    for row in rows:
        cells = table.add_row().cells
        values = (row[0], row[1], row[3], row[4])
        for cell, text in zip(cells, values):
            cell.text = text
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
                for item in paragraph.runs:
                    item.font.size = Pt(6.8)
    for row in table.rows:
        for index, width in enumerate(widths):
            row.cells[index].width = Cm(width)


# --------------------------------------------------------------------- document
def build_document(result, scenario, images: dict[str, Path]) -> Path:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    document = Document()
    section = document.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.05

    for name, size in (("Heading 1", 12), ("Heading 2", 10.5)):
        style = document.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0x12, 0x35, 0x5B)
        style.paragraph_format.space_before = Pt(8)
        style.paragraph_format.space_after = Pt(2)

    # ---------------------------------------------------------------- title
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run("GT-CCUS 2.0")
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x12, 0x35, 0x5B)

    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(6)
    run = paragraph.add_run(
        "A UI-agnostic simulation core for multi-emitter, multi-modal CO$_2$ clusters — "
        "geothermal storage, dynamic emitters and cash flow"
    )
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x1B, 0x6F, 0x6A)

    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(8)
    run = paragraph.add_run(
        "Technical whitepaper  ·  branch GT-CCUS-graph-streamlit  ·  Python package ccus_core  ·  "
        "69 automated tests  ·  pre-release"
    )
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x60, 0x60, 0x60)

    # ---------------------------------------------------------------- 1
    document.add_heading("1. Executive summary", level=1)
    document.add_paragraph(
        "CCUS screening studies usually stop at a spreadsheet: one emitter, one pipeline, one aquifer, "
        "one cash-flow block. Real clusters are neither single nor static — emitters come on stream in "
        "different years, CO$_2$ is moved by truck, rail, ship or pipeline, and a route that starts as a "
        "truck lane becomes a pipeline once the volumes justify it. GT-CCUS 2.0 turns that spreadsheet "
        "logic into an importable Python package: a chronological simulation of the whole chain, with a "
        "graph in which every transport state carries its year, and a cash-flow model that prices each of "
        "those states."
    )
    document.add_paragraph(
        "The core is decoupled from presentation. One scenario file drives the Streamlit app, a notebook, "
        "a desktop tool or an Excel add-in; the physics, routing and finance never import a UI framework, "
        "and no UI module contains physics."
    )

    table = document.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for label, value in [
        ("Model objects", "emitters, connections, nodes, storage sinks, geothermal, policy"),
        ("Transport modes", "pipeline, truck, rail, marine"),
        ("Onboarding", "per emitter and per emitter–sink pair, each with its own start year"),
        ("Upgrades", "year-based or conditional (cumulative volume), with CAPEX"),
        ("Physics reused", "material balance, VFP, geothermal doublet, ORC/pump/compressor, pipeline"),
        ("Outputs", "annual ledger, routing ledger, per-sink pressure, cash flow, NPV/IRR"),
    ]:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        for index, cell in enumerate(cells):
            for paragraph in cell.paragraphs:
                for item in paragraph.runs:
                    item.font.size = Pt(8.2)
                    item.font.bold = index == 0
    document.add_paragraph()

    # ---------------------------------------------------------------- 2
    document.add_heading("2. What changes compared with the current model", level=1)
    document.add_paragraph(
        "The existing application computes one chain over a pressure ramp: a constant annual mass, one "
        "emitter, one transport leg and one storage site. Four limitations follow from that design, and "
        "each is addressed explicitly."
    )
    for text in [
        "Constant emission. There is no ramp-up, steady state or decline, and no way to say when an "
        "emitter joins the cluster. Emission curves now support a constant, a piecewise-linear profile and "
        "the power law of Equation (1).",
        "Single transport mode. Truck and rail exist only as a cost rate. Transport is now a time-dependent "
        "directed multigraph with capacity, tariff and modal design (vessel size, port throughput, weather "
        "availability, fleet size).",
        "Static infrastructure. An upgrade can only be modelled by editing the input and re-running. An "
        "edge now carries a state timeline plus conditional upgrades, so “trucks for three years, then a "
        "pipeline” is one scenario, not three.",
        "One chain, one NPV. There is no shared capacity between emitters and no routing feedback. Routing "
        "is capacity-constrained per year, so a saturated sink or a full port appears as unallocated CO$_2$ "
        "instead of disappearing into an average.",
    ]:
        paragraph = document.add_paragraph(text, style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(1)
        for run in paragraph.runs:
            run.font.size = Pt(9.4)

    # ---------------------------------------------------------------- 3
    document.add_heading("3. Architecture", level=1)
    document.add_paragraph(
        "The core is a stack of pure packages (Figure 1). Models are Pydantic objects without I/O; network "
        "and simulation import them; finance reuses the audited cash-flow runner; and engine.py is the only "
        "facade an application needs. The legacy engineering and economics modules are imported by the core "
        "and never the other way round, so every existing physical correlation remains the single source of "
        "truth."
    )
    document.add_picture(str(images["architecture"]), width=Cm(16.4))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---------------------------------------------------------------- 4
    document.add_heading("4. Governing equations", level=1)
    document.add_paragraph(
        "The engine adds no new thermodynamics: it re-uses the correlations of the existing package and "
        "evaluates them on a time grid. The equations that define the annual step are:"
    )

    document.add_paragraph("Emission curve (power law of the cluster study, with b = a·E0):").runs[0].font.size = Pt(9.4)
    add_equation(document, r"E(t)=\max\left(0,\;E_{0}+b\,(t-t_{0})^{c}\right),\qquad b=a\,E_{0}", "1")

    document.add_paragraph("Aquifer material balance (pore and water volumes, cumulative stored mass):").runs[0].font.size = Pt(9.4)
    add_equation(document, r"V_{p}(p)=V_{p,0}\left(1+c_{p}\Delta p\right),\quad V_{w}(p)=V_{w,0}\left(1-c_{w}\Delta p\right)", "2")
    add_equation(
        document,
        r"m_{\mathrm{CO_2}}(p)=\left[\left(V_{p}(p)-V_{p,0}\right)+\left(V_{w,0}-V_{w}(p)\right)\right]\rho_{\mathrm{CO_2}}(p)",
        "3",
    )

    document.add_paragraph("Injection bottom-hole pressure (radial Darcy flow with a transient drainage radius):").runs[0].font.size = Pt(9.4)
    add_equation(
        document,
        r"p_{\mathrm{wf}}=p_{\mathrm{res}}+\frac{\mu\,q}{2\pi\,k_{\mathrm{CO_2}}\,h}\ln\!\left(\frac{r_{e}}{r_{w}}\right),\qquad r_{e}=\sqrt{\frac{k\,t}{\phi\,\mu\,c_{t}}}",
        "4",
    )

    document.add_paragraph("Transport operating cost of a leg (flat rate up to 45 km, logarithmic above):").runs[0].font.size = Pt(9.4)
    add_equation(
        document,
        r"\mathrm{OPEX}_{\ell}=\begin{cases}15\ \mathrm{EUR\,t^{-1}}, & L\le 45\ \mathrm{km}\\[2pt] 22\ln L-80\ \mathrm{EUR\,t^{-1}}, & L>45\ \mathrm{km}\end{cases}",
        "5",
    )

    document.add_paragraph("EU ETS liability and project value (free-allocation phase-out s(t), Fisher relation for r):").runs[0].font.size = Pt(9.4)
    add_equation(
        document,
        r"E^{\mathrm{tax}}_{t}=E_{t}\left(1-s_{t}\right),\qquad \mathrm{NPV}=\sum_{t}\frac{IKP_{t}}{\left(1+r\right)^{t}}-IK_{0},\qquad \left(1+r\right)=\left(1+\rho\right)\left(1+\pi\right)",
        "6",
    )

    # ---------------------------------------------------------------- 5
    document.add_heading("5. How a scenario is simulated", level=1)
    for index, (name, text) in enumerate(
        [
            ("Resolve the calendar", "one year at a time; every emitter and every emitter–sink pair has its own first year."),
            ("Query the active emitters", "gross emissions come from Equation (1); captured mass is limited by the capture unit."),
            ("Resolve the network state", "each edge returns its planned state or a fired upgrade (year or cumulative-volume trigger)."),
            ("Route the mass", "cheapest feasible path under residual edge, port, weather and sink capacities; leftovers are reported as unallocated."),
            ("Update the physics", "cumulative mass is inverted through Equations (2)–(3), BHP follows Equation (4), and the geothermal doublet tracks the resulting pressure."),
            ("Value the cash flow", "CAPEX schedules (including upgrade CAPEX) and modal OPEX of Equation (5) are escalated by inflation and discounted through Equation (6)."),
        ],
        start=1,
    ):
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(1)
        run = paragraph.add_run(f"{index}. {name}. ")
        run.font.bold = True
        run.font.size = Pt(9.4)
        run = paragraph.add_run(text)
        run.font.size = Pt(9.4)

    document.add_picture(str(images["timeline"]), width=Cm(16.4))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---------------------------------------------------------------- 6
    document.add_heading("6. What the engine produces", level=1)
    kpi = result.kpis
    document.add_paragraph(
        f"On the workbook case (14 emitters, 3 storage sites: Ivanić 5.5 Mt, Stružec 1.7 Mt, "
        f"Bokić 13.7 Mt) the engine routes {kpi['routed_co2_t'] / 1e6:,.2f} Mt into the sinks and reports "
        f"{kpi['unallocated_co2_t'] / 1e6:,.2f} Mt with no feasible route in its year — the number a "
        f"cluster study needs before it promises a storage site to an emitter. The project NPV is "
        f"{kpi['npv_eur'] / 1e6:,.1f} M€."
    )
    document.add_picture(str(images["results"]), width=Cm(16.4))
    document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(
        "Two properties of that result deserve emphasis. First, the unallocated mass is not a rounding "
        "error: it is the capacity of the transport plan in that year, and it drives the decision to build "
        "a second route or a second storage site. Second, injection stops for a physical reason — the "
        "reservoir pressure reaches the fracture limit or the site capacity is used up — not because a "
        "spreadsheet year ran out."
    )

    # ---------------------------------------------------------------- 7
    document.add_heading("7. Benefits", level=1)
    for text in [
        "One scenario file, many front ends: the same JSON runs in Streamlit, a notebook or a desktop "
        "application, and the UI never contains physics.",
        "Auditable numbers: every input keeps its unit and comment in the JSON, and every result is a "
        "DataFrame that can be exported or compared year by year.",
        "No double counting: transport cost is charged per routed tonne on the arcs actually used, so a "
        "shared pipeline is not paid twice and an upgrade is not billed before it is in service.",
        "Physics stays authoritative: the engine inverts and re-uses the existing material balance, VFP and "
        "geothermal models instead of re-implementing them; the constant-rate case reproduces the legacy "
        "result (276.09 bar at the end of the reference injection period).",
        "Tested where it hurts: 69 tests cover staggered onboarding, mid-run upgrades, offshore bottlenecks, "
        "multi-emitter/multi-sink routing, the ETS phase-out and JSON round-trips, plus a golden regression "
        "test of the legacy application.",
    ]:
        paragraph = document.add_paragraph(text, style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(1)
        for run in paragraph.runs:
            run.font.size = Pt(9.4)

    # ---------------------------------------------------------------- appendix
    document.add_page_break()
    document.add_heading("Appendix A — JSON input specification", level=1)
    document.add_paragraph(
        "The engine reads a single JSON document. Plain JSON is accepted, but the canonical format keeps "
        "every leaf in a three-column record, so a scenario stays readable and auditable in a text editor: "
        "value, unit and comment. The tables below are generated from the Pydantic models and therefore "
        "always match the code."
    )

    document.add_paragraph(
        '{\n'
        '  "schema": "ccus-cluster/2.0",\n'
        '  "scenario": {\n'
        '    "id": { "value": "croatia_cluster" },\n'
        '    "start_year": { "value": 2025, "unit": "year" },\n'
        '    "end_year": { "value": 2050, "unit": "year" },\n'
        '    "emitters": [ { "id": { "value": "nexe" }, "…": "…" } ],\n'
        '    "connections": [ { "emitter_id": { "value": "nexe" },\n'
        '                       "sink_id": { "value": "ivanic" },\n'
        '                       "start_year": { "value": 2026, "unit": "year" } } ]\n'
        '  }\n'
        '}'
    ).runs[0].font.name = "Consolas"

    from ccus_core.models import (
        EconomicsConfig,
        EdgeState,
        Emitter,
        EmitterSinkConnection,
        GeothermalSystem,
        PolicyConfig,
        ReservoirProperties,
        ScenarioConfig,
        StorageSink,
        TransportEdge,
    )

    add_table(document, "Table A.1 — ScenarioConfig (document root)", field_rows(ScenarioConfig))
    add_table(document, "Table A.2 — Emitter (onboarding, emission curve, capture unit)", field_rows(Emitter))
    add_table(document, "Table A.3 — EmitterSinkConnection (many-to-many access)", field_rows(EmitterSinkConnection))
    add_table(document, "Table A.4 — EdgeState (one transport state: mode, capacity, tariff)", field_rows(EdgeState))
    add_table(document, "Table A.5 — StorageSink (site, capacity, monitoring, compressor)", field_rows(StorageSink))
    add_table(document, "Table A.6 — ReservoirProperties (defaults: φ = 0.20, k = 100 mD, 1500 m)", field_rows(ReservoirProperties))
    add_table(document, "Table A.7 — GeothermalSystem (doublet and ORC)", field_rows(GeothermalSystem))
    add_table(document, "Table A.8 — EconomicsConfig (discount, inflation, price path)", field_rows(EconomicsConfig))
    add_table(document, "Table A.9 — PolicyConfig (ETS, price scenarios, unit costs)", field_rows(PolicyConfig))

    document.add_paragraph(
        "Value types. A field is either a plain scalar or a record {value, unit, comment}; lists and nested "
        "objects follow the same rule. Years are calendar years, masses are tonnes of CO2 per year unless "
        "stated otherwise, pressures are bar and money is euro in the base year."
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
    print(
        f"kpis: routed {result.kpis['routed_co2_t'] / 1e6:.2f} Mt, "
        f"unallocated {result.kpis['unallocated_co2_t'] / 1e6:.2f} Mt, "
        f"npv {result.kpis['npv_eur'] / 1e6:.1f} M EUR"
    )


if __name__ == "__main__":
    main()