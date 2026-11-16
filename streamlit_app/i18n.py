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
    "save_section": "Spremanje scenarija",
    "save_name": "Naziv scenarija",
    "btn_save": "Spremi",
    "saved_ok": "Scenarij spremljen: {name}",
    "save_failed": "Scenarij nije spremljen: {error}",
    "select_saved": "Snimljeni scenariji",
    "btn_load": "Učitaj",
    "btn_delete": "Obriši",
    "confirm_delete": "Potvrdi brisanje",
    "deleted_ok": "Scenarij obrisan: {name}",
    "loaded_ok": "Scenarij učitan: {name}",
    "no_saved": "Nema snimljenih scenarija.",
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
    "slider_help": (
        "Odabir godine mijenja samo prikaz (mapu, tablice, tlakove); proračun se izvrši jednom "
        "za cijelu vremensku os."
    ),
    "econ_start": "Početna godina",
    "econ_end": "Završna godina",
    "econ_discount": "Diskontna stopa",
    "econ_inflation": "Inflacija",
    "metric_captured": "Uhvaćeno CO₂ (t)",
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
    "sec_ledger": "Godišnji tehnički sažetak",
    "cum_cost": "Kumulativni trošak po kategorijama",
    "cum_cost_note": "Kumulativni iznos troškova po kategorijama (nominalno, bez diskontiranja).",
    "pie_last": "Struktura troškova – zadnja godina analize",
    "entity_select": "Ekonomika pojedinog sudionika",
    "entity_capex": "CAPEX",
    "entity_opex": "OPEX",
    "entity_transfers": "Prijenosi (tarife plaćene / naplaćene)",
    "entity_net": "Neto tijek novca",
    "entity_npv": "NPV sudionika",
    "entity_empty": "Nema podataka za odabranog sudionika.",
    "sec_edges": "Usmjerenja u odabranoj godini",
    "sec_sink_detail": "Skladište",
    "sec_routes": "Rute",
    "col_help": "Opis stupaca",
    "net_help": (
        "Šematski prikaz mreže (TODO: prave koordinate i stvarna povezanost); debljina linije = "
        "protok, strelica = smjer toka."
    ),
    "sec_stakeholders": "Ekonomika po sudionicima",
    "stakeholders_help": (
        "Tarife su po principu potpunog odražavanja troškova (bez marže): emiter plaća prijevoz i "
        "utiskivanje, a operateri ih naplaćuju – stoga se prijenosi poništavaju pri konsolidaciji."
    ),
    "stakeholders_detail": "Pojedinosti po stavkama (CAPEX, OPEX, tarife, prihod)",
    "download_ledger": "Preuzmi tehnički sažetak (CSV)",
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
        "geothermal_coupled": ("geotermalni dublet", "istovremeni CCS i geotermalni rad na istom skladištu"),
        "geothermal_start_year": ("početak geotermalne", "prva godina rada geotermalnog dubleta"),
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
    "save_section": "Save scenario",
    "save_name": "Scenario name",
    "btn_save": "Save",
    "saved_ok": "Scenario saved: {name}",
    "save_failed": "Scenario was not saved: {error}",
    "select_saved": "Saved scenarios",
    "btn_load": "Load",
    "btn_delete": "Delete",
    "confirm_delete": "Confirm deletion",
    "deleted_ok": "Scenario deleted: {name}",
    "loaded_ok": "Scenario loaded: {name}",
    "no_saved": "No saved scenarios yet.",
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
    "slider_help": (
        "The slider only changes the view (map, tables, pressures); the run is computed once "
        "for the whole horizon."
    ),
    "econ_start": "Start year",
    "econ_end": "End year",
    "econ_discount": "Discount rate",
    "econ_inflation": "Inflation",
    "metric_captured": "Captured CO2 (t)",
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
    "sec_ledger": "Annual technical summary",
    "cum_cost": "Cumulative cost by category",
    "cum_cost_note": "Cumulative cost per category (nominal, undiscounted).",
    "pie_last": "Cost structure – last analysis year",
    "entity_select": "Economics of a single stakeholder",
    "entity_capex": "CAPEX",
    "entity_opex": "OPEX",
    "entity_transfers": "Transfers (tariffs paid / collected)",
    "entity_net": "Net cash flow",
    "entity_npv": "Stakeholder NPV",
    "entity_empty": "No data for the selected stakeholder.",
    "sec_edges": "Movements in the selected year",
    "sec_sink_detail": "Storage site",
    "sec_routes": "Routes",
    "col_help": "Column descriptions",
    "net_help": (
        "Schematic view (TODO: real coordinates and true connectivity); line width = flow, "
        "arrow = direction."
    ),
    "sec_stakeholders": "Economics by stakeholder",
    "stakeholders_help": (
        "Tariffs are cost-reflective (no margin): emitters pay transport and injection, operators "
        "collect them, so transfers cancel on consolidation."
    ),
    "stakeholders_detail": "Line-item detail (CAPEX, OPEX, tariffs, revenue)",
    "download_ledger": "Download technical summary (CSV)",
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
        "geothermal_coupled": ("geothermal doublet", "run geothermal and CO2 storage at the same site"),
        "geothermal_start_year": ("geothermal start", "first year of geothermal operation"),
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