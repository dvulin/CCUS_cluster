"""Import the cluster workbook (``.xlsx``) into the canonical JSON scenario.

The workbook is the *source of context*, the JSON is the *stored input*.  This
module is the one-way bridge between them; it never writes to the workbook.

Expected sheets and columns (as published in ``CCS TABLICE 2015-2022 example.xlsx``):

``razrada scenarija``
    row 27 = header, rows 29+ = one emitter per row:
    C name | D emissions (kt) | E p-CCS | F start year | G capture technology |
    H construction | I quantity | J transport mode | K distance (km) |
    L transport mode 2 | M distance 2 | N sink | O type | P capacity (Mt) | Q depth (m)

``emissions-change``
    row 9 = years (I..AI), rows 10+ = one emitter per row:
    D p-CCS | E name | F a | G b | H c | I.. emission per year (t)

``storage``
    rows 8+ = storage site list: B type | C name | D class | E fluid | F onshore |
    G formation | H depth (m) | I capacity (Mt)
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from ccus_core.models import (
    EconomicsConfig,
    EmissionCurve,
    Emitter,
    GeoLocation,
    Node,
    NodeKind,
    PipelineDesign,
    PolicyConfig,
    RoadDesign,
    ScenarioConfig,
    StorageSink,
    StorageType,
    TransportEdge,
    TransportMode,
)

MODE_CODES = {
    "cijev": TransportMode.PIPELINE,
    "cjevovod": TransportMode.PIPELINE,
    "vlak": TransportMode.RAIL,
    "zeljeznica": TransportMode.RAIL,
    "kamion": TransportMode.TRUCK,
    "cestovni": TransportMode.TRUCK,
    "brod": TransportMode.MARINE,
}

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """ASCII slug, stable for the Croatian diacritics used in the workbook."""

    folded = (
        name.replace("č", "c").replace("ć", "c").replace("ž", "z").replace("š", "s").replace("đ", "d")
    )
    slug = SLUG_RE.sub("-", folded.lower()).strip("-")
    return slug[:48].strip("-")


def _cell(row: list[Any], index: int) -> Any:
    return row[index] if index < len(row) else None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _rows(path: str | Path, sheet: str) -> dict[int, list[Any]]:
    """Read one sheet as ``{excel row number: values indexed by column}``.

    ``openpyxl`` refuses this workbook because of its stylesheet, so the sheet XML
    is parsed directly.  Rows are keyed by their real Excel number, so a sheet
    with empty leading rows does not shift the columns.
    """

    return _XlsxReader(path).sheet(sheet)


class _XlsxReader:
    """Minimal read-only XLSX reader (sheet XML + shared strings)."""

    def __init__(self, path: str | Path):
        import zipfile

        self._zip = zipfile.ZipFile(str(path))
        self._shared = self._read_shared_strings()

    def close(self) -> None:
        self._zip.close()

    def _read_shared_strings(self) -> list[str]:
        import xml.etree.ElementTree as ET

        name = "xl/sharedStrings.xml"
        if name not in self._zip.namelist():
            return []
        root = ET.fromstring(self._zip.read(name))
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        return [
            "".join(node.text or "" for node in item.iter(f"{ns}t"))
            for item in root.findall(f"{ns}si")
        ]

    def sheet(self, sheet_name: str) -> dict[int, list[Any]]:
        import xml.etree.ElementTree as ET

        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

        workbook = ET.fromstring(self._zip.read("xl/workbook.xml"))
        relationships = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        targets = {item.get("Id"): item.get("Target") for item in relationships}

        part = None
        for item in workbook.iter(f"{ns}sheet"):
            if item.get("name") == sheet_name:
                target = targets.get(item.get(f"{rel_ns}id"), "")
                target = target.lstrip("/")
                part = target if target.startswith("xl/") else f"xl/{target}"
                break
        if part is None:
            raise KeyError(f"sheet '{sheet_name}' not found")

        root = ET.fromstring(self._zip.read(part))
        rows: dict[int, list[Any]] = {}
        for row in root.iter(f"{ns}row"):
            row_number = int(row.get("r", "0") or 0)
            values: list[Any] = []
            for cell in row.findall(f"{ns}c"):
                index = _column_index(cell.get("r", "A1"))
                while len(values) <= index:
                    values.append(None)
                values[index] = _cell_value(cell, self._shared, ns)
            rows[row_number] = values
        return rows


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    index = 0
    for character in letters.upper():
        index = index * 26 + (ord(character) - ord("A") + 1)
    return max(index - 1, 0)


def _cell_value(cell, shared: list[str], ns: str) -> Any:
    kind = cell.get("t")
    if kind == "s":
        node = cell.find(f"{ns}v")
        return shared[int(node.text)] if node is not None and node.text else ""
    if kind == "inlineStr":
        node = cell.find(f"{ns}is")
        if node is None:
            return ""
        return "".join(part.text or "" for part in node.iter(f"{ns}t"))
    node = cell.find(f"{ns}v")
    if node is None or node.text is None:
        return None
    text = node.text
    if kind in (None, "n"):
        try:
            return float(text)
        except ValueError:
            return text
    return text


def _parse_scenario_sheet(rows: dict[int, list[Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row_number in sorted(rows):
        if row_number < 29:
            continue
        row = rows[row_number]
        name = _text(_cell(row, 2))
        emissions_kt = _number(_cell(row, 3))
        probability = _number(_cell(row, 4))
        if not name or emissions_kt is None:
            if records:
                # the emitter block ends here; below it the sheet holds the
                # CAPEX/OPEX summary, which has a different column meaning
                break
            continue
        if probability is not None and not 0.0 <= probability <= 1.0:
            break
        records.append(
            {
                "name": name,
                "emissions_kt": emissions_kt,
                "probability": probability,
                "activation_year": _number(_cell(row, 5)),
                "technology": _text(_cell(row, 6)).upper(),
                "transport_mode": _text(_cell(row, 9)),
                "distance_km": _number(_cell(row, 10)),
                "sink": _text(_cell(row, 13)),
                "sink_type": _text(_cell(row, 14)).upper(),
                "sink_capacity_mt": _number(_cell(row, 15)),
                "sink_depth_m": _number(_cell(row, 16)),
            }
        )
    return records


def _parse_emission_change(rows: dict[int, list[Any]]) -> dict[str, dict[str, Any]]:
    """Return ``{slug: {a, b, c, e0, reference_year}}`` from ``emissions-change``."""

    result: dict[str, dict[str, Any]] = {}
    for row_number in sorted(rows):
        if row_number < 10:
            continue
        row = rows[row_number]
        name = _text(_cell(row, 4))
        if not name:
            continue
        a = _number(_cell(row, 5))
        b = _number(_cell(row, 6))
        c = _number(_cell(row, 7))
        e0 = _number(_cell(row, 8))
        if e0 is None or a is None or b is None or c is None:
            # rows 27+ repeat the table without a/b/c; the first (canonical)
            # block wins
            continue
        result.setdefault(
            slugify(name),
            {
                "a": a,
                "b": b,
                "c": c,
                "e0_t_per_year": e0,
                "reference_year": 2025,
            },
        )
    return result


def _parse_storage_sheet(rows: dict[int, list[Any]]) -> dict[str, dict[str, Any]]:
    sites: dict[str, dict[str, Any]] = {}
    for row_number in sorted(rows):
        if row_number < 8:
            continue
        row = rows[row_number]
        name = _text(_cell(row, 2))
        capacity = _number(_cell(row, 8))
        if not name or capacity is None:
            continue
        sites[slugify(name)] = {
            "name": name,
            "type": _text(_cell(row, 1)).upper(),
            "depth_m": _number(_cell(row, 7)),
            "capacity_mt": capacity,
        }
    return sites


def build_scenario(workbook: str | Path) -> ScenarioConfig:
    """Build a :class:`ScenarioConfig` from the cluster workbook."""

    scenario_rows = _parse_scenario_sheet(_rows(workbook, "razrada scenarija"))
    if not scenario_rows:
        raise ValueError("no emitter rows found in 'razrada scenarija'")
    curves = _parse_emission_change(_rows(workbook, "emissions-change"))
    sites = _parse_storage_sheet(_rows(workbook, "storage"))

    sinks: dict[str, StorageSink] = {}
    nodes: list[Node] = []
    edges: list[TransportEdge] = []
    emitters: list[Emitter] = []

    for record in scenario_rows:
        emitter_id = slugify(record["name"])
        node_id = f"{emitter_id}-gate"
        nodes.append(
            Node(
                id=node_id,
                name=record["name"],
                kind=NodeKind.EMITTER,
                location=GeoLocation(onshore=True),
            )
        )

        curve = curves.get(emitter_id, {})
        e0 = curve.get("e0_t_per_year") or record["emissions_kt"] * 1000.0
        gross = EmissionCurve.power_law(
            e0_t_per_year=e0,
            reference_year=int(curve.get("reference_year") or 2025),
            a=float(curve.get("a") or -0.025),
            c=float(curve.get("c") or 1.5),
            b=curve.get("b"),
        )
        technology = record["technology"] or "NI"
        activation = int(record["activation_year"]) if record["activation_year"] else None
        emitters.append(
            Emitter(
                id=emitter_id,
                name=record["name"],
                node_id=node_id,
                activation_year=activation,
                implementation_probability=record["probability"],
                gross_emissions=gross,
            )
        )

        sink_key = slugify(record["sink"] or "storage")
        sink = sinks.get(sink_key)
        if sink is None:
            site = sites.get(sink_key, {})
            capacity_t = float(record["sink_capacity_mt"] or site.get("capacity_mt") or 1.0) * 1e6
            sink = StorageSink(
                id=sink_key,
                node_id=f"{sink_key}-site",
                name=record["sink"] or site.get("name") or sink_key,
                storage_type=StorageType.DHF if "DHF" in (record["sink_type"] or "") else StorageType.DSA,
                capacity_t=capacity_t,
                commissioning_year=2026,
                capex_eur=0.0,
                opex_eur_per_t=10.0,
                notes=(
                    "capacity-only: reservoir properties are not part of the workbook"
                ),
            )
            sinks[sink_key] = sink
            nodes.append(
                Node(id=sink.node_id, name=sink.name, kind=NodeKind.STORAGE, location=GeoLocation(onshore=True))
            )

        mode = MODE_CODES.get(
            (record["transport_mode"] or "cijev").lower(),
            TransportMode.PIPELINE,
        )
        distance = float(record["distance_km"] or 0.0)
        edges.append(
            TransportEdge(
                id=f"{emitter_id}-to-{sink_key}",
                name=f"{record['name']} → {sink.name}",
                from_node=node_id,
                to_node=sink.node_id,
                states=[
                    _edge_state(mode, distance, e0)
                ],
            )
        )

    return ScenarioConfig(
        id="croatia_cluster",
        name="Croatian coastal and central CCS cluster (workbook import)",
        start_year=2025,
        end_year=2050,
        nodes=nodes,
        emitters=emitters,
        edges=edges,
        storage_sinks=list(sinks.values()),
        policy=PolicyConfig(),
        economics=EconomicsConfig(
            start_year=2025,
            end_year=2050,
            capex_start_year=2026,
            discount_rate=0.06,
            inflation_rate=0.06,
            price_path={"mode": "custom", "custom": {"function": "linear", "p0_eur_per_t": 63.64, "linear_growth_eur_per_t_per_year": 3.0}},
        ),
        notes=(
            "Imported from the cluster workbook. Costs follow the thesis unit rates; "
            "edges are single-leg placeholders until the multi-modal network is edited."
        ),
    )


def _edge_state(mode: TransportMode, distance_km: float, e0: float):
    from ccus_core.models import EdgeState

    common = {
        "mode": mode,
        "valid_from_year": 2025,
        "capacity_t_per_year": max(e0, 1.0),
        "distance_km": max(distance_km, 0.1),
        "opex_eur_per_t": 15.0 if distance_km <= 45.0 else 22.0 * math.log(distance_km) - 80.0,
        "capex_eur": 0.7 * e0 * max(distance_km, 0.1),
    }
    if mode is TransportMode.PIPELINE:
        common["pipeline"] = PipelineDesign(inner_diameter_m=0.30, inlet_pressure_bar=150.0, inlet_temperature_c=20.0)
    elif mode in (TransportMode.TRUCK, TransportMode.RAIL):
        common["road"] = RoadDesign(
            vehicle_capacity_t=25.0 if mode is TransportMode.TRUCK else 60.0,
            trips_per_vehicle_per_day=2.0,
            working_days_per_year=250.0,
            fleet_size=max(1, math.ceil(e0 / (25.0 * 2.0 * 250.0))),
        )
    return EdgeState(**common)