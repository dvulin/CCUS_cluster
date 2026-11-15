"""User-interface strings for the Streamlit layer (Croatian and English).

The module is pure data: UTF-8 literals, no Streamlit import, so it can be reused
by any front end.  ``strings(language)`` returns the dictionary for ``hr`` or
``en``; missing keys fall back to Croatian so a new string can never break a page.
"""

from __future__ import annotations

from typing import Any

HR: dict[str, Any] = {
    "page_title": "CCUS cluster",
    "app_title": "CCUS cluster – dinamični emiteri i multimodalni transport",
    "language": "Jezik",
    "sidebar_scenario": "Scenarij",
    "sidebar_source": "Izvor",
    "source_cluster": "Klaster (14 emitera)",
    "source_single": "Jedan lanac (legacy)",
    "source_upload": "Učitaj JSON",
    "upload_label": "JSON scenarij",
    "scenario_loaded": "Scenarij: {name}",
    "scenario_invalid": "Neispravan scenarij: {error}",
    "load_scenario": "Učitaj scenarij",
    "tab_inputs": "Ulazi",
    "tab_overview": "Sažetak",
    "tab_network": "Mreža",
    "tab_reservoir": "Skladište",
    "tab_economics": "Ekonomika",
    "tab_tables": "Tablice",
    "inputs_hint": (
        "Uredi tablice, zatim klikni 'Primijeni i pokreni'. Nove emitere, pristupe i skladišta "
        "dodaješ retkom na dnu tablice (prazno polje = NaN)."
    ),
    "btn_apply": "Primijeni i pokreni",
    "applied_ok": "Scenarij je osvježen.",
    "scenario_invalid_short": "Scenarij nije valjan: {error}",
    "info_start": "Uredi tablice i klikni 'Primijeni i pokreni', ili pokreni postojeći scenarij.",
    "slider_time": "Vremenska os",
    "econ_start": "Početna godina",
    "econ_end": "Završna godina",
    "econ_discount": "Diskontna stopa",
    "econ_inflation": "Inflacija",
    "metric_captured": "Usječeno CO₂ (t)",
    "metric_routed": "Rutirano (t)",
    "metric_injected": "Utisnuto (t)",
    "metric_stored": "Pohranjeno ukupno (t)",
    "metric_npv": "NPV (EUR)",
    "metric_irr": "IRR",
    "metric_pv_revenue": "PV prihodi (EUR)",
    "metric_pv_cost": "PV troškovi (EUR)",
    "sec_emitters": "Emiteri",
    "sec_connections": "Pristupi emiter → skladište",
    "sec_sinks": "Skladišta (DSA / DHF)",
    "sec_geothermal": "Geotermalni sustavi",
    "sec_economics": "Ekonomika",
    "sec_ledger": "Godišnji tehnički bilten",
    "sec_edges": "Usmjerenja u odabranoj godini",
    "sec_sink_detail": "Skladište",
    "sec_routes": "Rute",
    "download_ledger": "Preuzmi tehnički bilten (CSV)",
    "file_ledger": "ccus_ledger.csv",
    "col_emitters": {
        "id": ("id", "slug: mala slova, bez razmaka"),
        "name": ("naziv", ""),
        "activation_year": ("početak", "prva godina doprinosa"),
        "implementation_probability": ("vjerojatnost", "1.0 = 2026., 0.5 = 2028., 0.1 = 2033."),
        "curve": ("krivulja", ""),
        "e0_t_per_year": ("E0 (t/god)", "emisija u referentnoj godini"),
        "a": ("a", "linearni pad, npr. -0,03"),
        "c": ("c", "potencijski eksponent, npr. 1,5"),
        "constant_t_per_year": ("konstantno (t/god)", ""),
        "capture_capacity_t_per_year": ("capture kapacitet (t/god)", "0 = bez ograničenja"),
        "capture_capex_eur": ("capture CAPEX (EUR)", ""),
        "capture_opex_eur_per_t": ("capture OPEX (EUR/t)", ""),
    },
    "col_connections": {
        "emitter_id": ("emiter", "id iz tablice Emiteri"),
        "sink_id": ("skladište", "id iz tablice Skladišta"),
        "start_year": ("od godine", "nezavisno po paru"),
        "end_year": ("do godine", "prazno = do kraja"),
        "mode": ("način", ""),
        "distance_km": ("L (km)", ""),
        "capacity_t_per_year": ("kapacitet (t/god)", ""),
        "capex_eur": ("CAPEX (EUR)", "naplaćuje se u startnoj godini"),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
        "opex_eur_per_tkm": ("OPEX (EUR/t·km)", ""),
    },
    "col_sinks": {
        "id": ("id", ""),
        "name": ("naziv", ""),
        "type": ("tip", ""),
        "capacity_t": ("kapacitet (t)", ""),
        "depth_m": ("dubina (m)", "default 1500 m"),
        "porosity": ("poroznost", "default 0,20"),
        "permeability_m2": ("propusnost (m²)", "default 100 mD = 1e-13 m²"),
        "commissioning_year": ("od godine", ""),
        "capex_eur": ("CAPEX (EUR)", ""),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
        "monitoring_cost_during_injection_eur_per_year": ("monitoring (EUR/god) – injekcija", ""),
        "monitoring_cost_after_injection_eur_per_year": ("monitoring (EUR/god) – nakon", ""),
    },
    "col_geothermal": {
        "id": ("id", ""),
        "name": ("naziv", ""),
        "sink_id": ("skladište", "dublet na tom skladištu"),
        "d_doublet_m": ("razmak para (m)", ""),
        "reservoir_temperature_c": ("T ležišta (°C)", ""),
        "eta_orc": ("η ORC", ""),
        "p_out_bar": ("p izlaza ORC (bar)", ""),
        "t_out_c": ("T izlaza ORC (°C)", ""),
        "operation_start_year": ("od godine", ""),
        "operation_end_year": ("do godine", ""),
        "capex_eur": ("CAPEX (EUR)", ""),
        "fixed_opex_eur_per_year": ("OPEX (EUR/god)", ""),
    },
}

EN: dict[str, Any] = {
    "page_title": "CCUS cluster",
    "app_title": "CCUS cluster – dynamic emitters and multi-modal transport",
    "language": "Language",
    "sidebar_scenario": "Scenario",
    "sidebar_source": "Source",
    "source_cluster": "Cluster (14 emitters)",
    "source_single": "Single chain (legacy)",
    "source_upload": "Upload JSON",
    "upload_label": "JSON scenario",
    "scenario_loaded": "Scenario: {name}",
    "scenario_invalid": "Invalid scenario: {error}",
    "load_scenario": "Load scenario",
    "tab_inputs": "Inputs",
    "tab_overview": "Summary",
    "tab_network": "Network",
    "tab_reservoir": "Storage",
    "tab_economics": "Economics",
    "tab_tables": "Tables",
    "inputs_hint": (
        "Edit the tables, then click 'Apply and run'. Add emitters, connections and storage sites "
        "as a new row at the bottom (blank cell = NaN)."
    ),
    "btn_apply": "Apply and run",
    "applied_ok": "Scenario updated.",
    "scenario_invalid_short": "Scenario is invalid: {error}",
    "info_start": "Edit the tables and click 'Apply and run', or run the existing scenario.",
    "slider_time": "Timeline",
    "econ_start": "Start year",
    "econ_end": "End year",
    "econ_discount": "Discount rate",
    "econ_inflation": "Inflation",
    "metric_captured": "Captured CO₂ (t)",
    "metric_routed": "Routed (t)",
    "metric_injected": "Injected (t)",
    "metric_stored": "Stored total (t)",
    "metric_npv": "NPV (EUR)",
    "metric_irr": "IRR",
    "metric_pv_revenue": "PV revenues (EUR)",
    "metric_pv_cost": "PV costs (EUR)",
    "sec_emitters": "Emitters",
    "sec_connections": "Emitter → storage access",
    "sec_sinks": "Storage sites (DSA / DHF)",
    "sec_geothermal": "Geothermal systems",
    "sec_economics": "Economics",
    "sec_ledger": "Annual technical ledger",
    "sec_edges": "Movements in the selected year",
    "sec_sink_detail": "Storage site",
    "sec_routes": "Routes",
    "download_ledger": "Download technical ledger (CSV)",
    "file_ledger": "ccus_ledger.csv",
    "col_emitters": {
        "id": ("id", "slug: lower case, no spaces"),
        "name": ("name", ""),
        "activation_year": ("start", "first year of contribution"),
        "implementation_probability": ("probability", "1.0 = 2026, 0.5 = 2028, 0.1 = 2033"),
        "curve": ("curve", ""),
        "e0_t_per_year": ("E0 (t/yr)", "emission in the reference year"),
        "a": ("a", "linear decline, e.g. -0.03"),
        "c": ("c", "power exponent, e.g. 1.5"),
        "constant_t_per_year": ("constant (t/yr)", ""),
        "capture_capacity_t_per_year": ("capture capacity (t/yr)", "0 = unlimited"),
        "capture_capex_eur": ("capture CAPEX (EUR)", ""),
        "capture_opex_eur_per_t": ("capture OPEX (EUR/t)", ""),
    },
    "col_connections": {
        "emitter_id": ("emitter", "id from the Emitters table"),
        "sink_id": ("storage", "id from the Storage table"),
        "start_year": ("from year", "independent per pair"),
        "end_year": ("to year", "blank = until the end"),
        "mode": ("mode", ""),
        "distance_km": ("L (km)", ""),
        "capacity_t_per_year": ("capacity (t/yr)", ""),
        "capex_eur": ("CAPEX (EUR)", "charged in the start year"),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
        "opex_eur_per_tkm": ("OPEX (EUR/t·km)", ""),
    },
    "col_sinks": {
        "id": ("id", ""),
        "name": ("name", ""),
        "type": ("type", ""),
        "capacity_t": ("capacity (t)", ""),
        "depth_m": ("depth (m)", "default 1500 m"),
        "porosity": ("porosity", "default 0.20"),
        "permeability_m2": ("permeability (m²)", "default 100 mD = 1e-13 m²"),
        "commissioning_year": ("from year", ""),
        "capex_eur": ("CAPEX (EUR)", ""),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
        "monitoring_cost_during_injection_eur_per_year": ("monitoring (EUR/yr) – injection", ""),
        "monitoring_cost_after_injection_eur_per_year": ("monitoring (EUR/yr) – after", ""),
    },
    "col_geothermal": {
        "id": ("id", ""),
        "name": ("name", ""),
        "sink_id": ("storage", "doublet at that site"),
        "d_doublet_m": ("doublet spacing (m)", ""),
        "reservoir_temperature_c": ("reservoir T (°C)", ""),
        "eta_orc": ("η ORC", ""),
        "p_out_bar": ("ORC outlet p (bar)", ""),
        "t_out_c": ("ORC outlet T (°C)", ""),
        "operation_start_year": ("from year", ""),
        "operation_end_year": ("to year", ""),
        "capex_eur": ("CAPEX (EUR)", ""),
        "fixed_opex_eur_per_year": ("OPEX (EUR/yr)", ""),
    },
}

LANGUAGES = {"hr": HR, "en": EN}


def strings(language: str) -> dict[str, Any]:
    """Return the string table for ``language`` (fallback: Croatian)."""

    return LANGUAGES.get(str(language).lower(), HR)


def text(language: str, key: str, **kwargs: object) -> str:
    """Return one translated string, formatted with ``kwargs`` when given."""

    value = strings(language).get(key, HR.get(key, key))
    if kwargs and isinstance(value, str) and "{" in value:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value
    return value if isinstance(value, str) else str(value)


__all__ = ["HR", "EN", "LANGUAGES", "strings", "text"]