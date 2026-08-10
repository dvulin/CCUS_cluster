"""Generate docs/ekonomika.docx with editable Word equations (OMML)."""

from copy import deepcopy
from datetime import date
from html import escape
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor
from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "ekonomika.docx"
MML2OMML_PATH = Path(
    r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"
)

PAGE_WIDTH_DXA = 12240
PAGE_HEIGHT_DXA = 15840
MARGIN_DXA = 1440
CONTENT_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120
CELL_MARGINS_DXA = {"top": 80, "bottom": 80, "start": 120, "end": 120}

BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
NAVY = "0B2545"
MUTED = "667085"
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F2F4F7"
CALLOUT = "F4F6F9"
BORDER = "C7CFDA"
WHITE = "FFFFFF"
BLACK = "000000"
CAUTION = "7A5A00"


MATHML_NS = "http://www.w3.org/1998/Math/MathML"
with MML2OMML_PATH.open("rb") as stylesheet_file:
    MML_TO_OMML = etree.XSLT(etree.parse(stylesheet_file))


def xml_text(value):
    return escape(str(value), quote=False)


def mi(value, normal=False):
    variant = ' mathvariant="normal"' if normal else ""
    return f"<mi{variant}>{xml_text(value)}</mi>"


def mn(value):
    return f"<mn>{xml_text(value)}</mn>"


def mo(value):
    return f"<mo>{xml_text(value)}</mo>"


def mtext(value):
    return f"<mtext>{xml_text(value)}</mtext>"


def row(*parts):
    return "<mrow>" + "".join(parts) + "</mrow>"


def sub(base, index):
    return f"<msub>{base}{index}</msub>"


def sup(base, exponent):
    return f"<msup>{base}{exponent}</msup>"


def frac(numerator, denominator):
    return f"<mfrac>{numerator}{denominator}</mfrac>"


def fence(content, opening="(", closing=")"):
    return f'<mfenced open="{xml_text(opening)}" close="{xml_text(closing)}">{content}</mfenced>'


def root(content):
    return f"<msqrt>{content}</msqrt>"


def undersup(operator, lower, upper):
    return f"<munderover>{operator}{lower}{upper}</munderover>"


def cases(case_rows):
    table_rows = []
    for value, condition in case_rows:
        table_rows.append(
            "<mtr><mtd>"
            + value
            + "</mtd><mtd>"
            + mtext(condition)
            + "</mtd></mtr>"
        )
    return row(mo("{"), "<mtable>" + "".join(table_rows) + "</mtable>")


def idx(*parts):
    return row(*parts)


def normal(value):
    return mi(value, normal=True)


def set_run_font(run, name="Calibri", size=None, color=None, bold=None, italic=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_cell_margins(cell, margins=CELL_MARGINS_DXA):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for side, value in margins.items():
        tag = "w:start" if side == "start" else "w:end" if side == "end" else f"w:{side}"
        element = tc_mar.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            tc_mar.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def set_cell_fill(cell, color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), color)
    shd.set(qn("w:val"), "clear")


def set_cell_border(cell, color="C7CDD4", size="4"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = borders.find(qn(f"w:{edge}"))
        if element is None:
            element = OxmlElement(f"w:{edge}")
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_table_geometry(table, widths_dxa, indent_dxa=TABLE_INDENT_DXA):
    if sum(widths_dxa) != CONTENT_WIDTH_DXA:
        raise ValueError("Širine stupaca moraju dati 9360 DXA")
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr

    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(CONTENT_WIDTH_DXA))
    tbl_w.set(qn("w:type"), "dxa")

    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(indent_dxa))
    tbl_ind.set(qn("w:type"), "dxa")

    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        grid_col = OxmlElement("w:gridCol")
        grid_col.set(qn("w:w"), str(width))
        grid.append(grid_col)

    for row_obj in table.rows:
        for cell, width in zip(row_obj.cells, widths_dxa):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            set_cell_border(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def repeat_table_header(row_obj):
    tr_pr = row_obj._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_table_cell_text(cell, text, bold=False, color=BLACK, size=9, align=None):
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.08
    if align is not None:
        paragraph.alignment = align
    run = paragraph.add_run(str(text))
    set_run_font(run, size=size, color=color, bold=bold)


def add_table(doc, headers, rows, widths_dxa, numeric_columns=()):
    table = doc.add_table(rows=1, cols=len(headers))
    header_row = table.rows[0]
    for index, header in enumerate(headers):
        set_cell_fill(header_row.cells[index], LIGHT_BLUE)
        set_table_cell_text(
            header_row.cells[index],
            header,
            bold=True,
            color=NAVY,
            size=9,
            align=WD_ALIGN_PARAGRAPH.CENTER,
        )
    repeat_table_header(header_row)
    for values in rows:
        row_obj = table.add_row()
        for index, value in enumerate(values):
            alignment = (
                WD_ALIGN_PARAGRAPH.RIGHT
                if index in numeric_columns
                else WD_ALIGN_PARAGRAPH.LEFT
            )
            set_table_cell_text(
                row_obj.cells[index],
                value,
                size=8.8,
                align=alignment,
            )
    set_table_geometry(table, widths_dxa)
    after = doc.add_paragraph()
    after.paragraph_format.space_after = Pt(2)
    return table


def add_field(paragraph, instruction, display_text):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = display_text
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, text, end])
    set_run_font(run, size=9, color=MUTED)


def add_numbering_definition(doc, num_format, level_text, left=540, hanging=270):
    numbering_part = doc.part.numbering_part
    numbering = numbering_part.element
    abstract_ids = [
        int(element.get(qn("w:abstractNumId")))
        for element in numbering.findall(qn("w:abstractNum"))
    ]
    num_ids = [
        int(element.get(qn("w:numId")))
        for element in numbering.findall(qn("w:num"))
    ]
    abstract_id = max(abstract_ids, default=0) + 1
    num_id = max(num_ids, default=0) + 1

    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "singleLevel")
    abstract.append(multi)

    level = OxmlElement("w:lvl")
    level.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    fmt = OxmlElement("w:numFmt")
    fmt.set(qn("w:val"), num_format)
    text = OxmlElement("w:lvlText")
    text.set(qn("w:val"), level_text)
    justify = OxmlElement("w:lvlJc")
    justify.set(qn("w:val"), "left")
    p_pr = OxmlElement("w:pPr")
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "num")
    tab.set(qn("w:pos"), str(left))
    tabs.append(tab)
    indent = OxmlElement("w:ind")
    indent.set(qn("w:left"), str(left))
    indent.set(qn("w:hanging"), str(hanging))
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "80")
    spacing.set(qn("w:line"), "300")
    spacing.set(qn("w:lineRule"), "auto")
    p_pr.extend([tabs, indent, spacing])
    level.extend([start, fmt, text, justify, p_pr])
    abstract.append(level)
    numbering.append(abstract)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), str(abstract_id))
    num.append(abstract_ref)
    numbering.append(num)
    return num_id


def apply_numbering(paragraph, num_id):
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        p_pr.append(num_pr)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_id_element = OxmlElement("w:numId")
    num_id_element.set(qn("w:val"), str(num_id))
    num_pr.extend([ilvl, num_id_element])


def add_bullet(doc, text, bullet_num_id, bold_lead=None):
    paragraph = doc.add_paragraph()
    apply_numbering(paragraph, bullet_num_id)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = 1.25
    if bold_lead and text.startswith(bold_lead):
        lead = paragraph.add_run(bold_lead)
        set_run_font(lead, bold=True, color=NAVY)
        body = paragraph.add_run(text[len(bold_lead):])
        set_run_font(body)
    else:
        run = paragraph.add_run(text)
        set_run_font(run)
    return paragraph


def add_numbered(doc, text, decimal_num_id):
    paragraph = doc.add_paragraph()
    apply_numbering(paragraph, decimal_num_id)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.line_spacing = 1.25
    run = paragraph.add_run(text)
    set_run_font(run)
    return paragraph


def add_body(doc, text, bold_lead=None, italic=False):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.25
    if bold_lead and text.startswith(bold_lead):
        lead = paragraph.add_run(bold_lead)
        set_run_font(lead, bold=True, color=NAVY)
        body = paragraph.add_run(text[len(bold_lead):])
        set_run_font(body, italic=italic)
    else:
        run = paragraph.add_run(text)
        set_run_font(run, italic=italic)
    return paragraph


def add_callout(doc, label, text, color=NAVY):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(5)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.left_indent = Pt(6)
    paragraph.paragraph_format.right_indent = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.15
    p_pr = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), CALLOUT)
    p_pr.append(shading)
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:space"), "4")
        border.set(qn("w:color"), BORDER)
        borders.append(border)
    p_pr.append(borders)
    label_run = paragraph.add_run(label + " ")
    set_run_font(label_run, bold=True, color=color, size=10.5)
    text_run = paragraph.add_run(text)
    set_run_font(text_run, color=BLACK, size=10.5)


def add_equation(doc, math_body, caption, number):
    mathml = etree.fromstring(
        f'<math xmlns="{MATHML_NS}" display="block">{math_body}</math>'.encode("utf-8")
    )
    transformed = MML_TO_OMML(mathml)
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.keep_with_next = True
    paragraph._p.append(deepcopy(transformed.getroot()))
    caption_paragraph = doc.add_paragraph()
    caption_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption_paragraph.paragraph_format.space_before = Pt(0)
    caption_paragraph.paragraph_format.space_after = Pt(6)
    caption_paragraph.paragraph_format.keep_together = True
    caption_run = caption_paragraph.add_run(f"E{number}. {caption}")
    set_run_font(caption_run, size=9, color=MUTED, italic=True)
    return number + 1


def configure_styles(doc):
    styles = doc.styles
    normal_style = styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal_style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal_style.font.size = Pt(11)
    normal_style.font.color.rgb = RGBColor.from_string(BLACK)
    normal_style.paragraph_format.space_before = Pt(0)
    normal_style.paragraph_format.space_after = Pt(6)
    normal_style.paragraph_format.line_spacing = 1.25

    heading_tokens = {
        "Heading 1": (16, BLUE, 18, 10),
        "Heading 2": (13, BLUE, 14, 7),
        "Heading 3": (12, DARK_BLUE, 10, 5),
    }
    for style_name, (size, color, before, after) in heading_tokens.items():
        style = styles[style_name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    if "Equation Caption" not in [style.name for style in styles]:
        equation_style = styles.add_style("Equation Caption", WD_STYLE_TYPE.PARAGRAPH)
        equation_style.font.name = "Calibri"
        equation_style.font.size = Pt(9)
        equation_style.font.italic = True
        equation_style.font.color.rgb = RGBColor.from_string(MUTED)


def configure_section(section):
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    header = section.header
    header_paragraph = header.paragraphs[0]
    header_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header_paragraph.paragraph_format.space_after = Pt(0)
    header_run = header_paragraph.add_run("GT-CCS | Integrirana ekonomika")
    set_run_font(header_run, size=9, color=MUTED)

    footer = section.footer
    footer_paragraph = footer.paragraphs[0]
    footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer_run = footer_paragraph.add_run("Stranica ")
    set_run_font(footer_run, size=9, color=MUTED)
    add_field(footer_paragraph, " PAGE ", "1")


def add_cover(doc):
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(64)

    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_after = Pt(16)
    run = kicker.add_run("TEHNIČKI REFERENTNI IZVJEŠTAJ")
    set_run_font(run, size=10.5, color=CAUTION, bold=True)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(10)
    run = title.add_run("Ekonomika integriranog GT-CCS modela")
    set_run_font(run, name="Calibri Light", size=28, color=NAVY, bold=True)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(28)
    run = subtitle.add_run(
        "Povezivanje skladištenja CO₂, geotermalne energije i godišnjeg novčanog toka"
    )
    set_run_font(run, size=14, color=DARK_BLUE)

    metadata = doc.add_paragraph()
    metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER
    metadata.paragraph_format.space_after = Pt(6)
    run = metadata.add_run("Projekt: CCUS_cluster / GT-CCS Streamlit")
    set_run_font(run, size=10.5, color=MUTED, bold=True)

    metadata = doc.add_paragraph()
    metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER
    metadata.paragraph_format.space_after = Pt(6)
    run = metadata.add_run("Status: implementirano stanje nakon tehničko-ekonomske integracije")
    set_run_font(run, size=10, color=MUTED)

    metadata = doc.add_paragraph()
    metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER
    metadata.paragraph_format.space_after = Pt(72)
    run = metadata.add_run(f"Datum dokumenta: {date.today().strftime('%d.%m.%Y.')}")
    set_run_font(run, size=10, color=MUTED)

    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.paragraph_format.space_after = Pt(0)
    run = note.add_run(
        "Sve jednadžbe u dokumentu ugrađene su kao uređivi Word Equation objekti."
    )
    set_run_font(run, size=10, color=NAVY, italic=True)

    doc.add_page_break()


def build_document():
    doc = Document()
    configure_styles(doc)
    configure_section(doc.sections[0])
    bullet_num_id = add_numbering_definition(doc, "bullet", "•")
    decimal_num_id = add_numbering_definition(doc, "decimal", "%1.")

    doc.core_properties.title = "Ekonomika integriranog GT-CCS modela"
    doc.core_properties.subject = "Povezivanje tehničkog modela i godišnjeg novčanog toka"
    doc.core_properties.author = "GT-CCS projekt"
    doc.core_properties.keywords = "GT-CCS, CO2, geotermija, ekonomika, novčani tok"

    add_cover(doc)

    equation_number = 1

    doc.add_heading("1. Svrha, opseg i trenutačni status", level=1)
    add_body(
        doc,
        "Ovaj dokument opisuje sve dogovorene promjene kojima su dotad odvojeni inženjerski i ekonomski dijelovi spojeni u jedan godišnji tehničko-ekonomski tok. Polazište ekonomike više nisu ručno zadani godišnji nizovi, nego izračunata masa uskladištenog CO₂, snage kompresora, ORC-a i geotermalne pumpe te kalendarski životni vijek sustava.",
    )
    add_callout(
        doc,
        "Aktivno stanje.",
        "Godišnji novčani tok povezan je s tehničkim rezultatima. Troškovi se uvećavaju za inflaciju prije diskontiranja, a aktivni rezultat uključuje PV, NPV, IRR i scenarij bez CCS-a.",
    )
    add_body(
        doc,
        "Predznaci su jedinstveni: prihodi i vrijednost CO₂ pozitivni su, a CAPEX, OPEX, monitoring i kupnja električne energije negativni. Postojeće fizikalne jednadžbe skladištenja, bušotina, geotermije i snage nisu promijenjene.",
    )

    doc.add_heading("2. Dogovorene arhitekturne promjene", level=1)
    changes = [
        "Jedna autoritativna godišnja količina CO₂ vrijedi za hvatanje, transport, utiskivanje i verificirano skladištenje.",
        "Uvedene su zasebne godine početka ekonomskog razdoblja, početka ulaganja, početka i kraja utiskivanja, kraja rada geotermalnog sustava te kraja monitoringa.",
        "Tehnički nizovi pretvaraju se u godišnju tehničku tablicu mase, energije i aktivnih životnih faza.",
        "ORC prvo pokriva geotermalnu pumpu i kompresor CO₂; višak se prodaje, a manjak kupuje.",
        "CAPEX i OPEX hvatanja, transporta, kompresora, skladištenja i geotermalnog sustava vode se odvojeno.",
        "Monitoring tijekom utiskivanja i nakon prestanka utiskivanja ima dva zasebna godišnja ulaza i može trajati nakon utiskivanja.",
        "Nazivna snaga kompresora izvodi se kao najveća potrebna snaga u tehničkom nizu; CAPEX kompresora ostaje korisnički ulaz, a ne korelacija.",
        "Transport podržava cjevovod, cestovni i željeznički način. Horizontalni pad tlaka cjevovoda još nije izračunat.",
        "Geotermalni sustav može raditi nakon prestanka utiskivanja CO₂.",
        "Ekonomski modeli koriste kompoziciju; aktivni CashFlowRunner ne nasljeđuje klase emitera, transporta ili skladišta iz stare klase Economics.",
        "Streamlit prikazuje godišnju tehničku tablicu, godišnji novčani tok, energetsku bilancu i cijenu CO₂.",
    ]
    for change in changes:
        add_bullet(doc, change, bullet_num_id)

    doc.add_heading("2.1. Aktivni moduli i odgovornosti", level=2)
    module_rows = [
        ("inputs/io_endpoints.py", "Učitavanje JSON-a, sinkronizacija mase CO₂, jedinice i validacija životnog vijeka, troškova, učinkovitosti, raspoloživosti i transporta."),
        ("services/scenario_runner.py", "Jedini orkestrator: pokreće fiziku, određuje operativni kraj, gradi godišnji tehnički niz, cijenu CO₂ i novčani tok."),
        ("services/engineering_economics_adapter.py", "Pretvara tehničke DataFrameove iz proteklog vremena u kalendarske godišnje mase, MWh, nazivnu snagu i aktivne faze."),
        ("economics/cost_models.py", "Neovisni modeli CAPEX-a, OPEX-a, monitoringa, električne energije i vrijednosti CO₂."),
        ("economics/cash_flow_runner.py", "Sastavlja komponentne stavke, inflacijski prilagođen nominalni tok, diskontirani tok, NPV, IRR i scenarij bez CCS-a."),
        ("economics/price_scenarios.py", "Gradi odabranu zadanu ili prilagođenu godišnju putanju cijene CO₂."),
        ("engineering/transport.py", "Konfiguracija transportne dionice; fizikalna jednadžba horizontalnog pada tlaka namjerno je blokirana do potvrde."),
        ("app.py", "Korisnički unos, validacijske poruke, grafikoni, KPI-jevi i tablični prikaz rezultata."),
    ]
    add_table(doc, ["Datoteka", "Uloga u integraciji"], module_rows, [2900, 6460])

    doc.add_heading("3. Jedinstvena količina CO₂ i vremenski ugovor", level=1)
    add_body(
        doc,
        "Autoritativni ulaz je emitter_emissions_annual. Zbog kompatibilnosti postoje i m_dot_annual u kt/god te transport_flow_rate u t/god, ali se pri svakom unosu strogo sinkroniziraju. Godišnji tehnički niz zatim izvodi stvarno uskladištenu količinu iz materijalne bilance.",
    )
    equation_number = add_equation(
        doc,
        row(
            sub(mi("M"), idx(normal("captured"), mo(","), mi("y"))),
            mo("="),
            sub(mi("M"), idx(normal("transported"), mo(","), mi("y"))),
            mo("="),
            sub(mi("M"), idx(normal("injected"), mo(","), mi("y"))),
            mo("="),
            sub(mi("M"), idx(normal("stored"), mo(","), mi("y"))),
            mo("="),
            sub(mi("M"), idx(normal("chain"), mo(","), mi("y"))),
        ),
        "Jedinstvena godišnja količina CO₂ kroz cijeli lanac.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(
            normal("emitter_emissions_annual"),
            mo("="),
            mn("1000"),
            mo("·"),
            normal("m_dot_annual"),
            mo("="),
            normal("transport_flow_rate"),
        ),
        "Sinkronizacija JSON aliasa; m_dot_annual je u kt/god, ostale dvije vrijednosti u t/god.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("τ"), mi("y")), mo("="), mi("y"), mo("−"), sub(mi("y"), idx(normal("CCS"), mo(","), normal("start")))),
        "Preslikavanje kalendarske godine u proteklo vrijeme tehničkog modela.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("T"), normal("plan")), mo("="), sub(mi("y"), normal("inj,end")), mo("−"), sub(mi("y"), normal("inj,start")), mo("+"), mn("1")),
        "Planirano trajanje utiskivanja; obje krajnje kalendarske godine uključene su u proračun.",
        equation_number,
    )

    doc.add_heading("3.1. Operativni kraj utiskivanja", level=2)
    add_body(
        doc,
        "Utiskivanje završava na najranijem od tri ruba: planiranom kraju, dosegnutom nazivnom kapacitetu skladišta ili geomehaničkom rubu. Ako tehnički niz završi ranije, servis vraća hrvatsku napomenu s razlogom.",
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("p"), normal("max")), mo("="), sub(mi("G"), normal("frac")), mo("·"), sub(mi("h"), normal("top"))),
        "Dopušteni tlak izveden iz gradijenta tlaka frakturiranja i dubine vrha ležišta.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("T"), normal("inj")), mo("="), normal("min"), fence(row(sub(mi("T"), normal("plan")), mo(","), sub(mi("T"), normal("capacity")), mo(","), sub(mi("T"), normal("geomech"))))),
        "Stvarno trajanje utiskivanja u aktivnom scenariju.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(
            sup(sub(mi("p"), normal("storage")), mo("*")),
            fence(mi("τ")),
            mo("="),
            cases(
                [
                    (row(sub(mi("p"), normal("storage")), fence(mi("τ"))), "0 ≤ τ ≤ T_inj"),
                    (row(sub(mi("p"), normal("storage")), fence(sub(mi("T"), normal("inj")))), "T_inj < τ ≤ T_GT"),
                ]
            ),
        ),
        "Tlak ležišta za nastavak geotermalnog rada: nakon utiskivanja drži se završna vrijednost.",
        equation_number,
    )
    add_callout(
        doc,
        "Pretpostavka nakon utiskivanja.",
        "Konstantan tlak koristi se zato što model pretpostavlja jednaku proizvodnju i ponovno utiskivanje geotermalne vode, odnosno nulti neto volumni učinak geotermalnog dubleta. Relaksacija tlaka i prostorni tok nisu modelirani.",
    )

    doc.add_heading("4. Godišnja tehnička tablica za ekonomiku", level=1)
    add_body(
        doc,
        "Adapter čita kumulativnu masu iz mbal_df, snagu kompresora iz vfp_co2_df te ORC i pumpnu snagu iz vfp_gt_df. Nizovi se linearno interpoliraju na granice kalendarskih godina. Ne provodi se ekstrapolacija nepostojećih tehničkih podataka.",
    )
    equation_number = add_equation(
        doc,
        row(
            sub(mi("M"), idx(normal("chain"), mo(","), mi("y"))),
            mo("="),
            sup(mn("10"), mn("6")),
            fence(row(sub(mi("M"), normal("stored")), fence(sub(mi("τ"), normal("end"))), mo("−"), sub(mi("M"), normal("stored")), fence(sub(mi("τ"), normal("start")))), opening="[", closing="]"),
        ),
        "Godišnja masa CO₂: razlika kumulativne mase; tehnički niz mase je u Mt, rezultat u tonama.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("M"), idx(normal("cum"), mo(","), mi("y"))), mo("="), sup(mn("10"), mn("6")), mo("·"), sub(mi("M"), normal("stored")), fence(sub(mi("τ"), normal("end")))),
        "Kumulativno uskladišteni CO₂ na kraju kalendarske godine.",
        equation_number,
    )

    doc.add_heading("4.1. Pretvorba snage u godišnju energiju", level=2)
    equation_number = add_equation(
        doc,
        row(
            sub(mi("E"), idx(mi("i"), mo(","), mi("y"))),
            mo("="),
            frac(mn("8766"), mn("1000")),
            undersup(mo("∫"), sub(mi("τ"), normal("start")), sub(mi("τ"), normal("end"))),
            sub(mi("P"), mi("i")),
            fence(mi("τ")),
            mi("dτ"),
        ),
        "Kontinuirana definicija energije komponente i u MWh, pri čemu je snaga u kW, a vrijeme u godinama.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(
            sub(mi("E"), idx(mi("i"), mo(","), mi("y"))),
            mo("≈"),
            mn("8.766"),
            undersup(mo("∑"), mi("j"), mi("n")),
            frac(
                row(
                    sub(mi("P"), idx(mi("i"), mo(","), mi("j"))),
                    mo("+"),
                    sub(mi("P"), idx(mi("i"), mo(","), mi("j"), mo("+"), mn("1"))),
                ),
                mn("2"),
            ),
            fence(row(sub(mi("τ"), idx(mi("j"), mo("+"), mn("1"))), mo("−"), sub(mi("τ"), mi("j")))),
        ),
        "Numerička trapezna integracija koja se stvarno primjenjuje u adapteru.",
        equation_number,
    )
    add_body(
        doc,
        "Isti postupak daje orc_gross_mwh, gt_pump_mwh i co2_compressor_mwh. Faktor 8766 odgovara 365,25 dana godišnje, a faktor 1000 pretvara kWh u MWh.",
    )

    doc.add_heading("4.2. Električna bilanca sustava", level=2)
    equation_number = add_equation(
        doc,
        row(sub(mi("P"), normal("system")), mo("="), sub(mi("P"), normal("ORC")), mo("−"), sub(mi("P"), normal("GT,pump")), mo("−"), sub(mi("P"), normal("CO₂,comp"))),
        "Trenutačna izlazna snaga integriranog sustava.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(
            sub(mi("E"), idx(normal("export"), mo(","), mi("y"))),
            mo("="),
            mn("8.766"),
            undersup(mo("∫"), sub(mi("τ"), normal("start")), sub(mi("τ"), normal("end"))),
            normal("max"),
            fence(row(sub(mi("P"), normal("system")), mo(","), mn("0"))),
            mi("dτ"),
        ),
        "Prodana električna energija: integral samo pozitivnog dijela bilance.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(
            sub(mi("E"), idx(normal("import"), mo(","), mi("y"))),
            mo("="),
            mn("8.766"),
            undersup(mo("∫"), sub(mi("τ"), normal("start")), sub(mi("τ"), normal("end"))),
            normal("max"),
            fence(row(mo("−"), sub(mi("P"), normal("system")), mo(","), mn("0"))),
            mi("dτ"),
        ),
        "Kupljena električna energija: integral apsolutne vrijednosti negativnog dijela bilance.",
        equation_number,
    )
    add_body(
        doc,
        "Ako linearno interpolirana snaga promijeni predznak unutar intervala, adapter određuje nultočku i odvojeno integrira pozitivni i negativni trokut. Time se izbjegava međusobno poništavanje izvoza i uvoza unutar iste godine.",
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("P"), normal("compressor,nameplate")), mo("="), sub(normal("max"), mi("y")), fence(sub(mi("P"), idx(normal("compressor,peak"), mo(","), mi("y"))))),
        "Nazivna snaga kompresora: najveća izračunata potrebna snaga.",
        equation_number,
    )

    doc.add_heading("4.3. Raspoloživost i radni sati", level=2)
    equation_number = add_equation(
        doc,
        row(sub(mi("H"), mi("i")), mo("="), mn("8766"), mo("·"), sub(mi("A"), mi("i"))),
        "Evidentirani raspoloživi sati komponente i; A_i je u rasponu od 0 do 1.",
        equation_number,
    )
    add_callout(
        doc,
        "Važno ograničenje.",
        "Raspoloživosti kompresora, ORC-a i triju bušotina postoje u JSON ugovoru i iz njih se izvode raspoloživi sati, ali još ne mijenjaju protok, energiju ni masu. Za to treba potvrditi kako se godišnja masa raspoređuje u kraće on-stream vrijeme i kako se kombiniraju raspoloživosti opreme.",
        color=CAUTION,
    )

    doc.add_heading("4.4. Stupci godišnje tehničke tablice", level=2)
    ledger_rows = [
        ("year", "godina", "Kalendarska godina ekonomike."),
        ("co2_chain_t", "t CO₂/god", "Jedinstvena godišnja količina kroz aktivni CCS lanac."),
        ("co2_stored_cumulative_t", "t CO₂", "Kumulativno verificirano uskladištena masa."),
        ("orc_gross_mwh", "MWh", "Bruto ORC energija."),
        ("gt_pump_mwh", "MWh", "Energija geotermalne utisne pumpe."),
        ("co2_compressor_mwh", "MWh", "Energija kompresora ili pumpe CO₂."),
        ("electricity_export_mwh", "MWh", "Višak energije raspoloživ za prodaju."),
        ("electricity_import_mwh", "MWh", "Manjak energije koji se kupuje."),
        ("compressor_peak_kw", "kW", "Najveća potrebna snaga kompresora u godini."),
        ("injection_active", "True/False", "Aktivnost hvatanja, transporta, kompresora i skladištenja."),
        ("geothermal_active", "True/False", "Aktivnost geotermalnog sustava."),
        ("monitoring_active", "True/False", "Aktivnost monitoringa od početka CCS-a do zadane krajnje godine."),
        ("injection_stop_note", "tekst", "Razlog ranijeg kraja zbog kapaciteta, geomehanike ili nedostatka niza."),
    ]
    add_table(doc, ["Stupac", "Jedinica", "Značenje"], ledger_rows, [2700, 1500, 5160])

    doc.add_heading("5. Ekonomski model i predznaci", level=1)
    add_body(
        doc,
        "CashFlowRunner prima validiranu godišnju tehničku tablicu i ekonomske ulaze. Svaka komponenta vraća zaseban godišnji niz. Troškovni ulazi unose se kao pozitivni iznosi, a model im pri knjiženju dodjeljuje negativan predznak.",
    )
    equation_number = add_equation(
        doc,
        row(
            sub(mi("CF"), idx(mi("i"), mo(","), mi("y"))),
            mo("<"),
            mn("0"),
            mo("⇒"),
            normal("trošak"),
            mo(";"),
            sub(mi("CF"), idx(mi("i"), mo(","), mi("y"))),
            mo(">"),
            mn("0"),
            mo("⇒"),
            normal("prihod"),
        ),
        "Konvencija predznaka svih komponentnih stavki.",
        equation_number,
    )

    doc.add_heading("5.1. CAPEX", level=2)
    equation_number = add_equation(
        doc,
        row(
            sub(mi("CAPEX"), idx(mi("i"), mo(","), mi("y"))),
            mo("="),
            cases(
                [
                    (row(mo("−"), sub(mi("C"), idx(mi("i"), normal(",CAPEX")))), "y = y_CAPEX,i"),
                    (mn("0"), "inače"),
                ]
            ),
        ),
        "Jednokratni CAPEX komponente i. Aktivni ravni JSON koristi economics_ccs_start_year kao zajedničku godinu ulaganja.",
        equation_number,
    )
    add_body(
        doc,
        "Runner dodatno podržava zasebnu capex_year ili godišnji capex_schedule_eur u ugniježđenoj konfiguraciji, ali Streamlit ogledni JSON trenutačno koristi jednu zajedničku godinu ulaganja.",
    )

    doc.add_heading("5.2. Opća OPEX jednadžba", level=2)
    equation_number = add_equation(
        doc,
        row(
            sub(mi("OPEX"), idx(mi("i"), mo(","), mi("y"))),
            mo("="),
            mo("−"),
            fence(row(sub(mi("Q"), idx(mi("i"), mo(","), mi("y"))), mo("·"), sub(mi("c"), idx(mi("i"), mo(","), mi("y"))), mo("+"), sub(mi("I"), idx(mi("i"), mo(","), mi("y"))), mo("·"), sub(mi("F"), idx(mi("i"), mo(","), mi("y"))))),
        ),
        "Opći OPEX: varijabilni trošak količine ili energije plus fiksni godišnji OPEX samo dok je komponenta aktivna.",
        equation_number,
    )
    add_body(
        doc,
        "Q_i,y je tehnička količina (t CO₂ ili MWh), c_i,y je varijabilna tarifa, I_i,y je binarni indikator aktivnosti, a F_i,y je fiksni godišnji OPEX.",
    )

    doc.add_heading("5.3. Hvatanje CO₂", level=2)
    equation_number = add_equation(
        doc,
        row(sub(mi("OPEX"), idx(normal("capture"), mo(","), mi("y"))), mo("="), mo("−"), sub(mi("M"), idx(normal("chain"), mo(","), mi("y"))), mo("·"), sub(mi("c"), normal("capture,t"))),
        "Aktivni varijabilni trošak hvatanja po toni CO₂.",
        equation_number,
    )
    add_body(doc, "CAPEX hvatanja dolazi iz emitter_capex, a varijabilni OPEX iz emitter_opex_per_ton.")

    doc.add_heading("5.4. Transport CO₂", level=2)
    equation_number = add_equation(
        doc,
        row(sub(mi("OPEX"), idx(normal("pipeline"), mo(","), mi("y"))), mo("="), mo("−"), sub(mi("M"), idx(normal("chain"), mo(","), mi("y"))), mo("·"), sub(mi("c"), normal("pipeline,t"))),
        "OPEX transporta cjevovodom; koristi isključivo tarifu u EUR/t CO₂.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("OPEX"), idx(normal("road/rail"), mo(","), mi("y"))), mo("="), mo("−"), sub(mi("M"), idx(normal("chain"), mo(","), mi("y"))), mo("·"), sub(mi("c"), normal("tkm")), mo("·"), sub(mi("L"), normal("transport"))),
        "OPEX cestovnog ili željezničkog transporta u EUR/(t CO₂·km); nema dvostrukog obračuna tarife po toni.",
        equation_number,
    )
    add_body(
        doc,
        "Transport mode određuje koja se jednadžba primjenjuje. CAPEX transporta knjiži se zasebno. Duljina, promjer, hrapavost i broj koljena postoje kao ulazi za budući fizikalni proračun cjevovoda.",
    )

    doc.add_heading("5.5. Kompresor CO₂", level=2)
    equation_number = add_equation(
        doc,
        row(
            sub(mi("OPEX"), idx(normal("compressor"), mo(","), mi("y"))),
            mo("="),
            mo("−"),
            fence(
                row(
                    sub(mi("E"), idx(normal("compressor"), mo(","), mi("y"))),
                    mo("·"),
                    sub(mi("c"), normal("compressor,MWh")),
                    mo("+"),
                    sub(mi("I"), idx(normal("inj"), mo(","), mi("y"))),
                    mo("·"),
                    sub(mi("F"), idx(normal("compressor"), mo(","), mi("y"))),
                )
            ),
        ),
        "Komponentni OPEX kompresora: opcionalna tarifa po MWh plus fiksni godišnji OPEX tijekom utiskivanja.",
        equation_number,
    )
    add_body(
        doc,
        "Trošak kupljene električne energije kompresora ne knjiži se ponovno u compressor_opex, nego kroz zajedničku električnu bilancu. Time se izbjegava dvostruko računanje energije. CAPEX kompresora je izravan ulaz.",
    )

    doc.add_heading("5.6. Skladištenje CO₂", level=2)
    equation_number = add_equation(
        doc,
        row(sub(mi("OPEX"), idx(normal("storage"), mo(","), mi("y"))), mo("="), mo("−"), sub(mi("M"), idx(normal("chain"), mo(","), mi("y"))), mo("·"), sub(mi("c"), normal("storage,t"))),
        "Godišnji OPEX skladištenja po stvarno uskladištenoj toni CO₂.",
        equation_number,
    )
    add_body(
        doc,
        "Nazivni kapacitet skladišta sada je operativni rub. Ako se dosegne prije planirane krajnje godine i prije geomehaničke granice, utiskivanje prestaje i sve CCS varijabilne stavke nakon toga postaju nula.",
    )

    doc.add_heading("5.7. Geotermalni sustav", level=2)
    equation_number = add_equation(
        doc,
        row(
            sub(mi("OPEX"), idx(normal("GT"), mo(","), mi("y"))),
            mo("="),
            mo("−"),
            fence(
                row(
                    sub(mi("E"), idx(normal("ORC,gross"), mo(","), mi("y"))),
                    mo("·"),
                    sub(mi("c"), normal("GT,MWh")),
                    mo("+"),
                    sub(mi("I"), idx(normal("GT"), mo(","), mi("y"))),
                    mo("·"),
                    sub(mi("F"), idx(normal("GT"), mo(","), mi("y"))),
                )
            ),
        ),
        "Komponentni OPEX geotermalnog sustava; aktivan je do geothermal_operation_end_year.",
        equation_number,
    )
    add_body(
        doc,
        "Prihod geotermije ne računa se iz bruto ORC energije. Prodaje se samo electricity_export_mwh nakon oduzimanja geotermalne pumpe i kompresora CO₂.",
    )

    doc.add_heading("5.8. Monitoring", level=2)
    equation_number = add_equation(
        doc,
        row(
            sub(mi("MON"), mi("y")),
            mo("="),
            mo("−"),
            cases(
                [
                    (sub(mi("C"), normal("during")), "monitoring aktivan i utiskivanje aktivno"),
                    (sub(mi("C"), normal("after")), "monitoring aktivan nakon utiskivanja"),
                    (mn("0"), "monitoring nije aktivan"),
                ]
            ),
        ),
        "Godišnji monitoring tijekom i nakon utiskivanja.",
        equation_number,
    )
    add_body(
        doc,
        "Monitoring počinje s CCS radom i može završiti nakon prestanka utiskivanja. Dva troška u početnom scenariju mogu biti jednaka, ali ostaju zasebni ulazi zbog kasnije analize odgovornosti i monitoringa nakon zatvaranja lokacije.",
    )

    doc.add_heading("5.9. Električna energija", level=2)
    equation_number = add_equation(
        doc,
        row(sub(mi("R"), idx(normal("electricity"), mo(","), mi("y"))), mo("="), sub(mi("E"), idx(normal("export"), mo(","), mi("y"))), mo("·"), sub(mi("p"), idx(normal("sell"), mo(","), mi("y")))),
        "Prihod od prodaje viška električne energije.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("C"), idx(normal("electricity"), mo(","), mi("y"))), mo("="), mo("−"), sub(mi("E"), idx(normal("import"), mo(","), mi("y"))), mo("·"), sub(mi("p"), idx(normal("buy"), mo(","), mi("y")))),
        "Trošak kupnje nedostajuće električne energije.",
        equation_number,
    )

    doc.add_heading("5.10. Vrijednost CO₂ i cjenovni scenariji", level=2)
    equation_number = add_equation(
        doc,
        row(sub(mi("R"), idx(normal("CO₂"), mo(","), mi("y"))), mo("="), sub(mi("M"), idx(normal("chain"), mo(","), mi("y"))), mo("·"), sub(mi("p"), idx(normal("CO₂"), mo(","), mi("y")))),
        "Pozitivna godišnja vrijednost CO₂ za količinu u aktivnom CCS lancu.",
        equation_number,
    )
    add_body(
        doc,
        "Korisnik bira pesimistični, konzervativni ili optimistični niz, ili izrađuje vlastiti scenarij. Zadani nizovi počinju u co2_price_start_year; nakon posljednje dostupne cijene zadržava se posljednja vrijednost.",
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("p"), normal("linear")), fence(mi("τ")), mo("="), sub(mi("p"), mn("0")), mo("+"), mi("a"), mo("·"), mi("τ")),
        "Prilagođena linearna putanja cijene CO₂.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(
            sub(mi("p"), normal("log")),
            fence(mi("τ")),
            mo("="),
            sub(mi("p"), mn("0")),
            mo("+"),
            mi("a"),
            mo("·"),
            normal("ln"),
            fence(row(mn("1"), mo("+"), mi("b"), mo("·"), mi("τ"))),
        ),
        "Prilagođena logaritamska putanja cijene CO₂; b mora biti veći od nule.",
        equation_number,
    )
    equation_number = add_equation(
        doc,
        row(sub(mi("p"), normal("power")), fence(mi("τ")), mo("="), sub(mi("p"), mn("0")), mo("+"), mi("a"), mo("·"), sup(mi("τ"), mi("c"))),
        "Prilagođena potencijska putanja cijene CO₂; eksponent c mora biti veći od nule.",
        equation_number,
    )

    doc.add_heading("5.11. Ukupni godišnji novčani tok", level=2)
    equation_number = add_equation(
        doc,
        row(
            sub(mi("CF"), mi("y")),
            mo("="),
            undersup(mo("∑"), mi("i"), normal("all line items")),
            sub(mi("CF"), idx(mi("i"), mo(","), mi("y"))),
        ),
        "Ukupni nediskontirani godišnji novčani tok kao zbroj svih komponentnih stavki.",
        equation_number,
    )
    line_item_rows = [
        ("capture_capex / capture_opex", "Hvatanje CO₂"),
        ("transport_capex / transport_opex", "Odabrani način transporta"),
        ("compressor_capex / compressor_opex", "Kompresor CO₂"),
        ("storage_capex / storage_opex", "Utiskivanje i skladištenje"),
        ("geothermal_capex / geothermal_opex", "Geotermalni sustav"),
        ("monitoring", "Monitoring tijekom i nakon utiskivanja"),
        ("electricity_revenue", "Prodaja viška energije"),
        ("electricity_purchase", "Kupnja manjka energije"),
        ("co2_value", "Pozitivna vrijednost količine CO₂ u lancu"),
        ("net_cash_flow", "Zbroj svih prethodnih stavki"),
    ]
    add_table(doc, ["Stupac novčanog toka", "Ekonomsko značenje"], line_item_rows, [3500, 5860])

    doc.add_heading("6. Ulazni parametri aktivne integracije", level=1)
    add_body(
        doc,
        "Sljedeća tablica prikazuje ključne vrijednosti oglednog main_inputs.json. Nulte vrijednosti nisu procjena stvarnog troška; one znače da stavka postoji u modelu, ali za demonstracijski scenarij još nije kalibrirana.",
    )
    input_rows = [
        ("economics_start_year", "2027", "godina", "Početak godišnje ekonomske tablice"),
        ("economics_end_year", "2050", "godina", "Kraj ekonomske tablice"),
        ("economics_ccs_start_year", "2028", "godina", "Zajednička godina ulaganja"),
        ("ccs_injection_start_year", "2028", "godina", "Početak utiskivanja i geotermije"),
        ("ccs_injection_end_year", "2040", "godina", "Posljednja planirana godina utiskivanja"),
        ("geothermal_operation_end_year", "2050", "godina", "Posljednja godina rada geotermije"),
        ("ccs_monitoring_end_year", "2050", "godina", "Posljednja godina monitoringa"),
        ("emitter_emissions_annual", "716.000", "t CO₂/god", "Autoritativna godišnja količina"),
        ("emitter_capex", "447.245.393,63", "EUR", "CAPEX hvatanja"),
        ("emitter_opex_per_ton", "25,00", "EUR/t CO₂", "OPEX hvatanja"),
        ("transport_mode", "pipeline", "-", "Cjevovod"),
        ("transport_distance_km", "50", "km", "Duljina transportne dionice"),
        ("transport_capex", "25.000.000", "EUR", "CAPEX transporta"),
        ("transport_opex_per_ton", "15,00", "EUR/t CO₂", "OPEX cjevovoda"),
        ("storage_capacity", "9.308.000", "t CO₂", "Nazivni operativni kapacitet"),
        ("storage_capex", "150.000.000", "EUR", "CAPEX skladištenja"),
        ("storage_opex_per_ton", "10,00", "EUR/t CO₂", "OPEX skladištenja"),
        ("compressor_capex", "0", "EUR", "Nekalibrirani demonstracijski ulaz"),
        ("compressor_annual_opex", "0", "EUR/god", "Nekalibrirani demonstracijski ulaz"),
        ("geothermal_capex", "0", "EUR", "Nekalibrirani demonstracijski ulaz"),
        ("geothermal_annual_opex", "0", "EUR/god", "Nekalibrirani demonstracijski ulaz"),
        ("monitoring_annual_cost_during_injection", "0", "EUR/god", "Nekalibrirani demonstracijski ulaz"),
        ("monitoring_annual_cost_after_injection", "0", "EUR/god", "Nekalibrirani demonstracijski ulaz"),
        ("electricity_buy_price", "100", "EUR/MWh", "Demonstracijski ulaz"),
        ("electricity_sell_price", "80", "EUR/MWh", "Demonstracijski ulaz"),
        ("economics_co2_price_mode", "conservative", "-", "Odabrana cjenovna putanja CO₂"),
        ("economics_interest_rate", "0,05", "-", "Nominalna diskontna stopa"),
        ("economics_inflation_rate", "0,05", "-", "Inflacija troškova prije diskontiranja"),
    ]
    add_table(doc, ["JSON ključ", "Vrijednost", "Jedinica", "Uloga"], input_rows, [2900, 1500, 1400, 3560], numeric_columns=(1,))

    doc.add_heading("7. Ogledni integrirani rezultat", level=1)
    add_body(
        doc,
        "Zadani scenarij koristi 716.000 t CO₂ godišnje od 2028. do 2040. i geotermalni rad do 2050. U trenutnom izračunu ORC pokriva pumpu i kompresor u svim godinama, pa nema uvoza električne energije.",
    )
    result_rows = [
        ("Ukupno uskladišteni CO₂", "9,308", "Mt"),
        ("Konačni tlak skladišta", "278,399", "bar"),
        ("Najveći CO₂ BHP", "333,846", "bar"),
        ("Nazivna snaga kompresora", "1.299,970", "kW"),
        ("Bruto ORC energija", "542.244,428", "MWh"),
        ("Energija geotermalne pumpe", "17.383,068", "MWh"),
        ("Energija kompresora CO₂", "140.446,721", "MWh"),
        ("Prodana/raspoloživa energija", "384.414,638", "MWh"),
        ("Kupljena energija", "0", "MWh"),
    ]
    add_table(doc, ["Tehnički pokazatelj", "Vrijednost", "Jedinica"], result_rows, [5100, 2300, 1960], numeric_columns=(1,))

    cash_rows = [
        ("CAPEX hvatanja", "-447.245.393,63", "EUR"),
        ("OPEX hvatanja", "-232.700.000,00", "EUR"),
        ("CAPEX transporta", "-25.000.000,00", "EUR"),
        ("OPEX transporta", "-139.620.000,00", "EUR"),
        ("CAPEX skladištenja", "-150.000.000,00", "EUR"),
        ("OPEX skladištenja", "-93.080.000,00", "EUR"),
        ("Vrijednost CO₂", "+840.584.000,00", "EUR"),
        ("Ostale aktivne stavke", "0,00", "EUR"),
        ("Ukupni nediskontirani novčani tok", "-247.061.393,63", "EUR"),
    ]
    add_table(doc, ["Zbroj kroz razdoblje 2027.-2050.", "Vrijednost", "Jedinica"], cash_rows, [5300, 2300, 1760], numeric_columns=(1,))
    add_callout(
        doc,
        "Tumačenje rezultata.",
        "Nulta ekonomska vrijednost električne energije, kompresorskog CAPEX/OPEX-a, geotermalnog CAPEX/OPEX-a i monitoringa posljedica je nultih zadanih ulaza. Fizička energija postoji i vidljiva je u tehničkoj tablici.",
    )

    doc.add_heading("8. Validacije i zaštita od nekonzistentnih scenarija", level=1)
    validations = [
        "Masa hvatanja, transporta i utiskivanja mora odgovarati autoritativnom emitter_emissions_annual.",
        "Mora vrijediti: početak ekonomike ≤ početak ulaganja ≤ početak utiskivanja ≤ kraj utiskivanja ≤ kraj ekonomike.",
        "Kraj geotermalnog rada i kraj monitoringa ne smiju biti prije kraja utiskivanja ni nakon kraja ekonomike.",
        "Učinkovitosti i raspoloživosti moraju biti veće od nule i manje ili jednake jedan.",
        "Početni tlak ležišta ne smije biti veći od dopuštenog tlaka izvedenog iz gradijenta tlaka frakturiranja.",
        "CAPEX, OPEX, cijene, duljine, hrapavost i broj koljena ne smiju biti negativni.",
        "Cjevovod zahtijeva geometriju i OPEX po toni; cestovni i željeznički transport zahtijevaju OPEX po toni i kilometru.",
        "Tehnička tablica odbija negativne energije, duple godine, prazne vrijednosti i energiju izvan aktivne životne faze.",
        "CAPEX godina mora biti unutar ekonomskog horizonta; ne mogu se istodobno zadati jednokratni CAPEX i CAPEX raspored.",
        "CO₂ cjenovni niz mora sadržavati konačne nenegativne vrijednosti.",
    ]
    for validation in validations:
        add_bullet(doc, validation, bullet_num_id)

    doc.add_heading("9. Što još nije implementirano", level=1)
    pending = [
        "Povrat ulaganja kao zaseban pokazatelj razdoblja povrata još nije uveden; PV, NPV, IRR, inflacija troškova i diskontiranje aktivni su u CashFlowRunneru.",
        "Horizontalni pad tlaka i energija transportnog cjevovoda. Klasa Transport i pripadni ulazi postoje, ali Darcy-Weisbachova jednadžba, korelacija koeficijenta trenja i koeficijenti koljena čekaju zasebne potvrde.",
        "Primjena raspoloživosti na on-stream protok, BHP, snagu i energiju. Trenutačno se samo evidentiraju raspoloživost i izvedeni sati.",
        "E_eff je ulaz i opisna pretpostavka, ali još nije aktivno uključen u jednadžbe materijalne bilance. Njegovo uključivanje zahtijeva zasebnu potvrdu jednadžbe.",
        "Fizikalni model transporta kamionom ili željeznicom nije uveden; za te načine aktivan je samo CAPEX i OPEX po toni-kilometru.",
        "Više emitera, više transportnih dionica i više skladišta nisu dio trenutačnog minimalnog integriranog scenarija.",
    ]
    for item in pending:
        add_bullet(doc, item, bullet_num_id)

    doc.add_heading("10. Lokalno pokretanje i provjera", level=1)
    steps = [
        'U PowerShellu aktivirati okruženje: & "C:/webdev/CCUS_cluster/CCUS_cluster/.gt_ccs_venv/Scripts/Activate.ps1"',
        'Pokrenuti testove: python -m unittest discover -s tests -p "test_*.py" -v',
        "Pokrenuti Streamlit: python -m streamlit run app.py",
        "U kartici Ekonomika provjeriti godišnju količinu CO₂, energetsku bilancu i neto godišnji novčani tok.",
        "U kartici Tablice provjeriti annual_technical_ledger i annual_cash_flow_df.",
    ]
    for step in steps:
        add_numbered(doc, step, decimal_num_id)
    add_body(doc, "Završna automatizirana provjera integracije: 34 testa prolaze, a Streamlit test izvršava zadani scenarij bez iznimki.")

    source_heading = doc.add_heading("11. Izvori implementiranog opisa", level=1)
    source_heading.paragraph_format.page_break_before = True
    source_rows = [
        ("Ulazni ugovor", r"C:\sestan_test_app\inputs\io_endpoints.py"),
        ("Ogledni scenarij", r"C:\sestan_test_app\inputs\examples\main_inputs.json"),
        ("Orkestracija", r"C:\sestan_test_app\services\scenario_runner.py"),
        ("Godišnje poravnanje", r"C:\sestan_test_app\services\engineering_economics_adapter.py"),
        ("Troškovni modeli", r"C:\sestan_test_app\economics\cost_models.py"),
        ("Novčani tok", r"C:\sestan_test_app\economics\cash_flow_runner.py"),
        ("Cijena CO₂", r"C:\sestan_test_app\economics\price_scenarios.py"),
        ("Streamlit sučelje", r"C:\sestan_test_app\app.py"),
        ("Evidencija promjena", r"C:\sestan_test_app\changelog.txt"),
    ]
    add_table(doc, ["Područje", "Aktivna datoteka"], source_rows, [2500, 6860])

    add_callout(
        doc,
        "Status jednadžbi.",
        f"Dokument sadrži {equation_number - 1} uređivih Word Equation jednadžbi. One opisuju trenutačno implementirani tehničko-ekonomski tok i jasno odvajaju aktivne izračune od otvorenih dijelova.",
    )

    # Posljednji prazni odlomak služi kao razmak iza callout-tablice, ali u Wordu
    # može prijeći na zasebnu praznu stranicu. Na kraju dokumenta nije potreban.
    if doc.paragraphs and not doc.paragraphs[-1].text:
        last_paragraph = doc.paragraphs[-1]._element
        last_paragraph.getparent().remove(last_paragraph)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT_PATH)
    return OUTPUT_PATH


if __name__ == "__main__":
    path = build_document()
    print(path)
