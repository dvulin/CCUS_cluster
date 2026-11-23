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
    "source_cluster": "Klaster ({count} emitera)",
    "source_single": "Jedan lanac (legacy, {count} emitera)",
    "source_upload": "Učitaj JSON",
    "upload_label": "JSON scenarij",
    "scenario_loaded": "Scenarij: {name}",
    "scenario_invalid": "Neispravan scenarij: {error}",
    "load_scenario": "Učitaj scenarij",
    "btn_run": "Pokreni",
    "status_ok": "Scenarij je aktualan",
    "status_dirty": "Scenarij je izmijenjen – pokreni ponovno",
    "status_idle": "Scenarij nije pokrenut",
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
    "tab_scenario": "Scenarij",
    "sec_scenario": "Scenarij",
    "scenario_horizon": "Horizont: {horizon}.",
    "sec_links": "Veze",
    "links_help": (
        "Svaka veza je jedna dionica lanca: spaja dva čvora (huba) i ima svoj način "
        "transporta, kapacitet i cijenu. Stupci 'od čvora' i 'do čvora' nude samo "
        "postojeće hubove. Novu vezu dodaješ retkom na dnu tablice, gumbom 'Dodaj vezu "
        "iz kataloga' ili klikom na dva huba na karti."
    ),
    "links_empty": (
        "Scenarij još nema veza. Dodaj jednu iz kataloga ili nacrtaj dva huba na karti."
    ),
    "links_delete_selected": "Obriši odabrano ({count})",
    "links_deleted": "Obrisano veza: {count}.",
    "links_clear_confirm": "Potvrdi: obriši svih {count} veza.",
    "links_clear_btn": "Obriši sve veze",
    "links_cleared": "Obrisano svih {count} veza.",
    "btn_new_scenario": "Novi scenarij (bez veza)",
    "new_scenario_started": (
        "Novi scenarij: mreža je prazna, dodaj veze u kartici 'Scenarij'."
    ),
    "links_connected": "Svi emiteri imaju put do skladišta.",
    "links_disconnected": (
        "{count} emiter(a) nema put do skladišta - njihova CO2 ne može biti uskladištena."
    ),
    "links_save_disconnected": (
        "Pažnja: {count} emiter(a) nije povezano sa skladištem."
    ),
    "hubs_filter_column": "Filtriraj po stupcu",
    "hubs_filter_query": "Sadrži",
    "hubs_filter_hint": "npr. HR ili hub",
    "sec_hubs": "Hubovi",
    "hubs_help": (
        "Svi hubovi ovog scenarija. Veza može spojiti samo dva porta navedena ovdje - "
        "stupci 'od čvora' i 'do čvora' nude isključivo njih."
    ),
    "hubs_no_map": (
        "{count} hub(ova) nema koordinate: {hubs}. Ne mogu se nacrtati na karti."
    ),
    "hubs_no_map_hint": (
        "Upiši latitude/longitude u tablicu hubova (stupci 'latitude' i 'longitude') "
        "ili ih dovuci iz GIS-a - tek se tada pojavljuju na karti i mogu biti krajnji "
        "hub veze."
    ),
    "check_all": "Označi sve",
    "uncheck_all": "Poništi sve",
    "links_save_confirm": "Spremi ipak (emiteri nisu povezani sa skladištem).",
    "col_scenario_hubs": {
        "map": ("na karti", "isključi da hub nestane s karte"),
        "id": ("oznaka", "id čvora iz scenarija"),
        "name": ("naziv", ""),
        "kind": ("vrsta", "emitter, junction, hub, port, storage, geothermal ili obalski terminal"),
        "latitude": ("latitude", "WGS84; prazno = nema pozicije"),
        "longitude": ("longitude", "WGS84; prazno = nema pozicije"),
        "links": ("veze", "koliko veza polazi od ili završava u ovom hubu"),
    },
    "sec_link_builder": "Nacrtaj vezu na karti",
    "link_mode": "Način transporta",
    "btn_new_link": "Nova veza",
    "btn_cancel_link": "Odustani",
    "link_pick_inlet": (
        "Klikni prvi hub na karti - to je ulaz (inlet) nove veze."
    ),
    "link_pick_outlet": (
        "Ulaz: {hub}. Sada klikni drugi hub - to je izlaz (outlet)."
    ),
    "map_follow_roads": "Prati ceste",
    "map_follow_roads_help": (
        "Za kamionske veze crta i mjeri trasu po stvarnoj cesti. Cjevovodi prate "
        "svoju izmjerenu trasu kada je GIS ima, inače zračnu liniju; željeznica i "
        "brod uvijek zračnu liniju."
    ),
    "map_show_reference": "Referentne rute",
    "map_show_reference_help": "Prikaži rute iz referentne studije (data/gis) kao pozadinu.",
    "map_show_all": "Prikaži sve hubove",
    "map_undrawn": "Nije nacrtano (hub bez koordinata): {links}.",
    "map_legend": (
        ":blue[■] cjevovod   :orange[■] kamion   :green[■] željeznica   "
        ":violet[■] brod"
    ),
    "links_details": "Koji emiteri nisu povezani",
    "link_same_hub": "Ulazni i izlazni hub moraju biti različiti.",
    "link_created": "Veza dodana: {id} ({km} km, {source}).",
    "link_km_road": "po cesti",
    "link_km_straight": "zračna linija",
    "btn_save_links": "Spremi veze u scenarij",
    "links_saved": "Veze su spremljene u scenarij '{name}'.",
    "links_save_failed": "Veze nisu spremljene: {error}",
    "sec_add_link": "Dodaj vezu iz kataloga",
    "add_link_help": (
        "Odaberi kandidatsku vezu iz baze (kartica 'Baza podataka') i dodaj je ovom "
        "scenariju. Nova veza dobiva kapacitet jednak vršnom uhvaćenom CO₂ - promijeni "
        "ga u tablici iznad. Da bi veza nosila CO₂, poveži je s emiterom i skladištem u "
        "tablici 'Povezivanja'."
    ),
    "add_link_select": "Kandidatska veza",
    "add_link_btn": "Dodaj u scenarij",
    "add_link_added": "Veza dodana u scenarij: {id}.",
    "add_link_none": "Sve kandidatske veze iz kataloga već su u ovom scenariju.",
    "links_help": (
        "Veze scenarija: svaka povezuje dva čvora (hub) i ima svoj način transporta, "
        "kapacitet i cijenu. Ovdje ih uređuješ; referentni katalog svih mogućih veza je u "
        "kartici 'Baza podataka'."
    ),
    "map_select": "Istakni vezu na karti",
    "map_none": "Scenarij nema veza.",
    "map_unavailable": (
        "Karta nije dostupna: čvorovi scenarija nemaju WGS84 koordinate. Učitaj geometriju "
        "u kartici 'Baza podataka' (stupci x/y, latitude/longitude)."
    ),
    "map_missing_hubs": (
        "Odabrani hubovi nemaju koordinate, pa se veza ne može nacrtati."
    ),
    "metric_scenario_nodes": "Čvorovi",
    "metric_scenario_links": "Veze",
    "metric_scenario_emitters": "Emiteri",
    "metric_scenario_sinks": "Skladišta",
    "sec_routes": "Rute (dionice između čvorova i hubova)",
    "col_routes": {
        "sel": ("odaberi", "označi redove za brisanje"),
        "id": ("oznaka", "jedinstvena oznaka rute"),
        "name": ("naziv", ""),
        "from_node": ("od čvora", "id čvora iz popisa"),
        "to_node": ("do čvora", "id čvora ili skladišta"),
        "mode": ("način", ""),
        "distance_km": ("L (km)", "duljina ove dionice"),
        "total_distance_km": (
            "L ukupno (km)",
            "ukupna duljina od početka ove dionice do skladišta; izračunava se, a "
            "ručno upisana vrijednost ostaje (pregazi izračun)",
        ),
        "capacity_t_per_year": ("kapacitet (t/god)", ""),
        "capex_eur": ("CAPEX (EUR)", ""),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
        "opex_eur_per_tkm": ("OPEX (EUR/t·km)", ""),
        "valid_from_year": ("od godine", ""),
    },
    "links_distance_to": "Mjeri udaljenost do skladišta",
    "links_distance_help": (
        "Stupac 'L ukupno' prikazuje koliko CO₂ još mora prijeći od početka svake "
        "dionice do odabranog skladišta, uključujući tu dionicu. Zadnja dionica koja "
        "ulazi u skladište vrijedi svoju vlastitu duljinu. Ostala skladišta su u "
        "proširenom popisu ispod tablice."
    ),
    "links_distance_all": "Udaljenost svake dionice do svih skladišta ({count})",
    "links_distance_gap": (
        "Dionice bez smjerne putanje do skladišta '{sink}': {count} – {links}."
    ),
    "links_distance_clear": "Izbriši ručno upisane udaljenosti ({count})",
    "links_distance_cleared": "Udaljenosti se ponovno računaju iz duljina dionica.",
    "connections_help": (
        "Koji emiter koju dionicu koristi i do kojeg skladišta: jedan red je jedan "
        "pristup. Emiter se bira iz tablice Emiteri, dionica iz postojećih veza, a "
        "skladište iz tablice Skladišta. Prazna dionica znači izravnu vezu "
        "emiter – skladište."
    ),
    "connections_empty": (
        "Nema još emitera ili skladišta – dodaj ih u tablicu Emiteri i Skladišta, "
        "pa zatim poveži emiter s dionicom i skladištem."
    ),
    "connections_deleted": "Obrisano povezivanja: {count}.",
    "connections_delete_selected": "Obriši označena povezivanja ({count})",
    "connections_stale": (
        "Povezivanja upućuju na nepostojeće vrijednosti: {items}. Ispravi ih prije "
        "spremanja – Apply će ih odbiti."
    ),
    "status_error": "Greška u scenariju – provjeri ulaze",
    "tab_overview": "Sažetak",
    "tab_network": "Mreža",
    "tab_reservoir": "Skladište",
    "tab_economics": "Ekonomika",
    "tab_tables": "Tablice",
    "tab_emitters": "Emiteri",
    "emitters_help": (
        "Pritisak koji emiter mora osigurati na izlazu kompresora određen je prvim hubom na "
        "njegovoj trasi; procjena je informativna dok se ne uvede kaskadni proračun tlaka po hubovima."
    ),
    "sec_compression": "Kompresija CO₂ prema prvom hubu",
    "sec_flows": "Procesi po dionicama (t/god)",
    "sec_pressures": "Tlak koji traže hubovi (kaskadni proračun)",
    "pressures_help": (
        "Tlak na zadnjem hubu je zadani (10 bar); prema uzvodno se dodaje pad tlaka svake "
        "dionice. Kada se pridruži novi emiter, zajednička dionica se preračunava za ukupni "
        "protok, a kompresiju preuzima emiter koji se zadnji priključio."
    ),
    "sec_sink_select": "Skladište",
    "flags_title": "Ograničenja skladišta",
    "flag_rate": "ograničeno deklariranom injekcijskom brzinom",
    "flag_capacity": "iskorišten je ukupni kapacitet",
    "flag_bhp": "potreban BHP iznad granice pucanja",
    "sec_sink_cum": "Kumulativno uskladišteno CO₂",
    "pie_year": "Godina prikaza",
    "pie_none": "U odabranoj godini nema troškova za prikaz.",
    "sec_tech": "Tehnička analiza",
    "sec_database": "Baza podataka",
    "tab_database": "Baza podataka",
    "database_tab_help": (
        "Referentne tablice studije: emiteri, hubovi, mreža i skladišta. Uredi ćeliju, dodaj "
        "red znakom '+' ili zalijepi blok iz Excela/LibreOffice Calc, pa klikni 'Spremi bazu'. "
        "Unosi se spremaju u json/emitters.json, json/hubs.json, json/network.json i "
        "json/storage.json; baza ne mijenja aktivni scenarij."
    ),
    "database_year": "Stupac 'emisije' prikazuje emisije za {year}. godinu.",
    "database_failed": "Baza emitera nije učitana: {error}",
    "db_sec_emitters": "Emiteri",
    "db_sec_hubs": "Hubovi",
    "db_sec_pipelines": "Cjevovodi (konstrukcija)",
    "db_sec_network": "Mreža (dionice)",
    "db_sec_storage": "Skladišta",
    "db_sec_backup": "Sigurnosna kopija i obnova",
    "db_backup_help": (
        "Cijela baza (emiteri, hubovi, mreža, skladišta) u jednoj datoteci. Preuzmi je za "
        "sigurnosnu kopiju, ili je učitaj za obnovu. Obnova prvo sprema postojeću bazu u "
        "data/backups/."
    ),
    "db_btn_download": "Preuzmi bazu",
    "db_upload_label": "Učitaj bazu (gt_ccus_db.sqlite)",
    "db_backup_missing": "Baza još ne postoji: {error}",
    "db_restore_invalid": "Datoteka nije valjana baza: {error}",
    "db_restore_summary": (
        "Datoteka sadrži: {hubs} hubova, {links} veza, {emitters} emitera, "
        "{storage} skladišta."
    ),
    "db_restore_confirm": "Razumijem da ova baza zamjenjuje cijeli katalog.",
    "db_btn_restore": "Obnovi bazu",
    "db_restore_failed": "Obnova nije uspjela: {error}",
    "db_restored": "Baza obnovljena. Sigurnosna kopija: {backup}.",
    "db_restored_no_backup": "Baza obnovljena (nije bilo prethodnje baze za kopiju).",
    "db_btn_save": "Spremi bazu",
    "db_saved": "Baza spremljena: {changes}.",
    "db_no_changes": "Nema izmjena za spremanje.",
    "db_save_failed": "Baza nije spremljena: {error}",
    "db_duplicate": "{label}: dvostruke oznake (id): {ids}.",
    "db_row": "redak",
    "db_failed_network": "Baza mreže nije učitana: {error}",
    "db_failed_storage": "Baza skladišta nije učitana: {error}",
    "db_failed_hubs": "Baza hubova nije učitana: {error}",
    "db_failed_pipelines": "Baza cjevovoda nije učitana: {error}",
    "col_pipelines": {
        "id": ("oznaka", "interna oznaka baze ( skriveno)"),
        "name": ("naziv", "npr. DN300 / 150 bar"),
        "diameter_m": ("unutarnji promjer (m)", "default 0,30 m"),
        "wall_thickness_m": ("debljina stijenke (m)", "neobavezno"),
        "roughness_m": ("hrapavost (m)", "default 4,5e-5 m"),
        "material": ("materijal", "npr. čelik, PE"),
        "design_pressure_bar": ("dizajnerski tlak (bar)", "neobavezno"),
        "design_temperature_c": ("dizajnerska T (°C)", "neobavezno"),
    },
    "col_hubs": {
        "id": ("oznaka", "interna oznaka baze ( skriveno)"),
        "name": ("naziv", ""),
        "category": (
            "kategorija",
            "source (ulaz CO2), chain (prolaz), sink (skladište), buffer, hub, port ili obalski terminal",
        ),
        "country": ("država", ""),
        "x": ("x koordinata", "x = northing (EPSG:3765)"),
        "y": ("y koordinata", "y = easting (EPSG:3765)"),
        "elevation_m": ("visina (m)", "nadmorska visina; prazno = nepoznato"),
    },
    "col_network": {
        "id": ("oznaka", "interna oznaka baze ( skriveno)"),
        "source_hub": ("polazište", "hub iz tablice Hubovi"),
        "destination_hub": ("odredište", "hub iz tablice Hubovi"),
        "mode": ("način", "pipeline, truck, rail ili marine"),
        "length_km": ("L (km)", "računa se iz koordinata hubova (samo čitanje)"),
        "pipeline": ("cjevovod", "konstrukcija iz tablice Cjevovodi (samo za način pipeline)"),
        "capex_eur": ("CAPEX (EUR)", ""),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
    },
    "col_storage": {
        "id": ("oznaka", "interna oznaka baze ( skriveno)"),
        "slug": ("slug", "statična oznaka za scenarije i rezultate"),
        "name": ("naziv", ""),
        "hub": ("hub", "sink hub iz tablice Hubovi"),
        "storage_type": ("vrsta", "DSA, DHF, DGF ili DOF"),
        "capacity_mt": ("kapacitet (Mt)", ""),
        "depth_m": ("dubina (m)", ""),
        "porosity": ("poroznost", ""),
        "permeability_m2": ("propusnost (m²)", "100 mD = 1e-13 m²"),
        "pressure_bar": ("tlak (bar)", ""),
        "temperature_c": ("temperatura (°C)", ""),
        "lithology": ("litologija", ""),
        "well_diameter_m": ("promjer bušotine (m)", "default 0,30 m"),
        "well_number": ("broj bušotina", "kapacitet injekcije ∝ broj bušotina"),
    },
    "col_database": {
        "id": ("oznaka", "interna oznaka baze ( skriveno)"),
        "slug": ("slug", "statična oznaka za scenarije i rezultate"),
        "name": ("naziv", "naziv postrojenja"),
        "industry": ("vrsta industrije", "npr. termoelektrana, cementara, rafinerija"),
        "curve": ("krivulja", "constant, power_law ili piecewise_linear"),
        "reference_year": ("ref. godina", "godina na koju se odnosi E0"),
        "e0_t_per_year": ("E0 (t/god)", "emisija u referentnoj godini"),
        "a": ("a", "linearni pad, npr. -0,03"),
        "c": ("c", "potencijski eksponent, npr. 1,5"),
        "points": ("točke", "'godina: t/god', npr. '2030: 100000, 2040: 80000'"),
        "activation_year": ("početak", "prva godina s doprinosom"),
        "implementation_probability": ("vjerojatnost CCS", "vjerojatnost provedbe CCS (0-1)"),
        "hub": ("hub", "source hub u koji ulazi CO2"),
        "emissions": (
            "emisije CO2 (t/god)",
            "konstantna stopa za krivulju constant; za power_law/piecewise se računa",
        ),
    },
    "inputs_hint": (
        "Uredi tablice, zatim klikni 'Primijeni i pokreni'. Nove emitere, pristupe i skladišta "
        "dodaješ retkom na dnu tablice (prazno polje = NaN). Referentne baze (emiteri, hubovi, "
        "mreža, skladišta) su u zadnjoj kartici 'Baza podataka'."
    ),
    "btn_apply": "Primijeni i pokreni",
    "routes_locked": (
        "Rute koje tablica ne može prikazati (više stanja ili uvjetna nadogradnja) ostaju nepromijenjene: {routes}."
    ),
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
    "sec_connections": "Povezivanje emiter → ruta → skladište",
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
        "sel": ("odaberi", "označi redove za brisanje"),
        "emitter_id": ("emiter", "id iz tablice Emiteri"),
        "route_edge_id": ("ruta", "oznaka rute iz tablice Rute (prva dionica)"),
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
    "source_cluster": "Cluster ({count} emitters)",
    "source_single": "Single chain (legacy, {count} emitters)",
    "source_upload": "Upload JSON",
    "upload_label": "JSON scenario",
    "scenario_loaded": "Scenario: {name}",
    "scenario_invalid": "Invalid scenario: {error}",
    "load_scenario": "Load scenario",
    "btn_run": "Run",
    "status_ok": "Scenario is up to date",
    "status_dirty": "Scenario changed – run again",
    "status_idle": "Scenario has not been run",
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
    "tab_scenario": "Scenario",
    "sec_scenario": "Scenario",
    "scenario_horizon": "Horizon: {horizon}.",
    "sec_links": "Links",
    "links_help": (
        "A link is one leg of the chain: it joins two nodes (hubs) and carries its "
        "transport mode, capacity and cost. The 'from node' and 'to node' columns "
        "offer the hubs that exist and nothing else. Add a link with a new row, with "
        "'Add a link from the catalogue', or by clicking two hubs on the map."
    ),
    "links_empty": (
        "This scenario has no links yet. Add one from the catalogue, or draw one by "
        "clicking two hubs on the map."
    ),
    "links_delete_selected": "Delete selected ({count})",
    "links_deleted": "Deleted {count} link(s).",
    "links_clear_confirm": "Confirm: delete all {count} links.",
    "links_clear_btn": "Delete all links",
    "links_cleared": "Deleted all {count} links.",
    "btn_new_scenario": "New scenario (no links)",
    "new_scenario_started": (
        "New scenario: the network is empty, add links in the 'Scenario' tab."
    ),
    "links_connected": "Every emitter has a path to a storage site.",
    "links_disconnected": (
        "{count} emitter(s) have no path to a storage site - their CO2 cannot be stored."
    ),
    "links_save_disconnected": (
        "Heads-up: {count} emitter(s) are not connected to a storage site."
    ),
    "hubs_filter_column": "Filter by column",
    "hubs_filter_query": "Contains",
    "hubs_filter_hint": "e.g. HR or hub",
    "sec_hubs": "Hubs",
    "hubs_help": (
        "Every hub of this scenario. A link may only join two ids listed here - the "
        "'from node' and 'to node' columns offer those and nothing else."
    ),
    "hubs_no_map": (
        "{count} hub(s) have no coordinates: {hubs}. They cannot be drawn on the map."
    ),
    "hubs_no_map_hint": (
        "Enter latitude/longitude in the hub table (the 'latitude' and 'longitude' "
        "columns) or import them from the GIS - until then the hub is not on the map "
        "and cannot be the end of a link."
    ),
    "check_all": "Check all",
    "uncheck_all": "Uncheck all",
    "links_save_confirm": "Save anyway (the emitters are not connected to a storage site).",
    "col_scenario_hubs": {
        "map": ("on map", "untick to take the hub off the map"),
        "id": ("id", "the node id used by this scenario"),
        "name": ("name", ""),
        "kind": ("kind", "emitter, junction, hub, port, storage, geothermal or offshore terminal"),
        "latitude": ("latitude", "WGS84; blank = no position"),
        "longitude": ("longitude", "WGS84; blank = no position"),
        "links": ("links", "how many links start or end at this hub"),
    },
    "sec_link_builder": "Draw a link on the map",
    "link_mode": "Transport mode",
    "btn_new_link": "New link",
    "btn_cancel_link": "Cancel",
    "link_pick_inlet": "Click the first hub on the map - that is the inlet of the new link.",
    "link_pick_outlet": "Inlet: {hub}. Now click the second hub - that is the outlet.",
    "map_follow_roads": "Follow roads",
    "map_follow_roads_help": (
        "For truck links, draw and measure the real road. Pipelines follow their "
        "surveyed route when the GIS has one, otherwise a straight line; rail and "
        "marine are always straight."
    ),
    "map_show_reference": "Reference routes",
    "map_show_reference_help": "Show the reference study's routes (data/gis) underneath.",
    "map_show_all": "Show all hubs",
    "map_undrawn": "Not drawn (a hub has no coordinates): {links}.",
    "map_legend": (
        ":blue[■] pipeline   :orange[■] truck   :green[■] rail   :violet[■] marine"
    ),
    "links_details": "Which emitters are not connected",
    "link_same_hub": "The inlet and the outlet must be two different hubs.",
    "link_created": "Link added: {id} ({km} km, {source}).",
    "link_km_road": "by road",
    "link_km_straight": "straight line",
    "btn_save_links": "Save links to the scenario",
    "links_saved": "Links saved to the scenario '{name}'.",
    "links_save_failed": "The links were not saved: {error}",
    "sec_add_link": "Add a link from the catalogue",
    "add_link_help": (
        "Pick a candidate link from the database (the 'Database' tab) and add it to this "
        "scenario. The new link gets a capacity equal to the peak captured CO2 - change it "
        "in the table above. To make it carry CO2, connect it to an emitter and a storage "
        "site in the 'Connections' table."
    ),
    "add_link_select": "Candidate link",
    "add_link_btn": "Add to scenario",
    "add_link_added": "Link added to the scenario: {id}.",
    "add_link_none": "Every candidate link of the catalogue is already in this scenario.",
    "links_help": (
        "The links of this scenario: each one joins two nodes (hubs) and carries its transport "
        "mode, capacity and cost. Edit them here; the catalogue of every candidate link is in "
        "the 'Database' tab."
    ),
    "map_select": "Highlight a link on the map",
    "map_none": "The scenario has no links.",
    "map_unavailable": (
        "No map available: the scenario nodes have no WGS84 coordinates. Load the geometry in "
        "the 'Database' tab (x/y, latitude/longitude columns)."
    ),
    "map_missing_hubs": "The selected hubs have no coordinates, so the link cannot be drawn.",
    "metric_scenario_nodes": "Nodes",
    "metric_scenario_links": "Links",
    "metric_scenario_emitters": "Emitters",
    "metric_scenario_sinks": "Storage sites",
    "sec_routes": "Routes",
    "col_routes": {
        "sel": ("select", "tick the rows to delete"),
        "id": ("id", "unique route identifier"),
        "name": ("name", ""),
        "from_node": ("from node", "node id"),
        "to_node": ("to node", "node or storage id"),
        "mode": ("mode", ""),
        "distance_km": ("L (km)", "length of this leg"),
        "total_distance_km": (
            "total L (km)",
            "distance from the start of this leg to the storage site, this leg "
            "included; calculated, and a typed value overrides it",
        ),
        "capacity_t_per_year": ("capacity (t/yr)", ""),
        "capex_eur": ("CAPEX (EUR)", ""),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
        "opex_eur_per_tkm": ("OPEX (EUR/t·km)", ""),
        "valid_from_year": ("from year", ""),
    },
    "links_distance_to": "Measure the distance to",
    "links_distance_help": (
        "The 'total L' column shows how far CO2 still has to travel from the start of "
        "each leg to the selected storage site, that leg included - so the leg that "
        "enters the site is worth its own length. The other storage sites are in the "
        "expander below the table."
    ),
    "links_distance_all": "Distance from every leg to every storage site ({count})",
    "links_distance_gap": (
        "Legs with no directed path to storage site '{sink}': {count} – {links}."
    ),
    "links_distance_clear": "Discard typed distances ({count})",
    "links_distance_cleared": "Distances are calculated from the leg lengths again.",
    "connections_help": (
        "Which emitter uses which leg, and to which storage site: one row is one "
        "access. The emitter comes from the Emitters table, the leg from the links "
        "that exist, the storage site from the Storage table. A blank leg means a "
        "direct emitter-to-storage access."
    ),
    "connections_empty": (
        "No emitters or storage sites yet - add them in the Emitters and Storage "
        "tables, then connect an emitter to a leg and a storage site."
    ),
    "connections_deleted": "Deleted connections: {count}.",
    "connections_delete_selected": "Delete selected connections ({count})",
    "connections_stale": (
        "Connections point at values that no longer exist: {items}. Fix them before "
        "saving - Apply will refuse them."
    ),
    "status_error": "Scenario error – check the inputs",
    "tab_overview": "Summary",
    "tab_network": "Network",
    "tab_reservoir": "Storage",
    "tab_economics": "Economics",
    "tab_tables": "Tables",
    "tab_emitters": "Emitters",
    "emitters_help": (
        "The discharge pressure an emitter must deliver is set by the first hub on its route; "
        "instructive only until the hub-to-hub pressure cascade is implemented."
    ),
    "sec_compression": "CO2 compression towards the first hub",
    "sec_flows": "Flows by leg (t/yr)",
    "sec_pressures": "Pressure required at each hub (cascade)",
    "pressures_help": (
        "The last hub is fixed at the default 10 bar; every leg upstream adds its friction "
        "loss. When a new emitter joins, the shared leg is recomputed for the total flow and "
        "the last emitter to join carries the compression."
    ),
    "sec_sink_select": "Storage site",
    "flags_title": "Storage constraints",
    "flag_rate": "limited by the declared injection rate",
    "flag_capacity": "total capacity used up",
    "flag_bhp": "required BHP above the fracture limit",
    "sec_sink_cum": "Cumulative stored CO2",
    "pie_year": "Year to display",
    "pie_none": "No costs to display in the selected year.",
    "sec_tech": "Technical analysis",
    "sec_database": "Database",
    "tab_database": "Database",
    "database_tab_help": (
        "The reference tables of the study: emitters, hubs, network and storage. Edit a cell, "
        "add a row with '+', or paste a block from Excel/LibreOffice Calc, then click 'Save "
        "database'. Entries are stored in json/emitters.json, json/hubs.json, "
        "json/network.json and json/storage.json; the database does not change the active "
        "scenario."
    ),
    "database_year": "The 'emissions' column shows {year}.",
    "database_failed": "Emitter database could not be loaded: {error}",
    "db_sec_emitters": "Emitters",
    "db_sec_hubs": "Hubs",
    "db_sec_pipelines": "Pipelines (design)",
    "db_sec_network": "Network (links)",
    "db_sec_storage": "Storage sites",
    "db_sec_backup": "Backup and restore",
    "db_backup_help": (
        "The whole database (emitters, hubs, network, storage) in one file. Download it as a "
        "backup, or upload it to restore. A restore first copies the current database to "
        "data/backups/."
    ),
    "db_btn_download": "Download database",
    "db_upload_label": "Upload database (gt_ccus_db.sqlite)",
    "db_backup_missing": "There is no database yet: {error}",
    "db_restore_invalid": "This is not a valid database: {error}",
    "db_restore_summary": (
        "The file holds {hubs} hubs, {links} links, {emitters} emitters, "
        "{storage} storage sites."
    ),
    "db_restore_confirm": "I understand this replaces the whole catalogue.",
    "db_btn_restore": "Restore database",
    "db_restore_failed": "The restore failed: {error}",
    "db_restored": "Database restored. Backup: {backup}.",
    "db_restored_no_backup": "Database restored (there was no previous one to copy).",
    "db_btn_save": "Save database",
    "db_saved": "Database saved: {changes}.",
    "db_no_changes": "No changes to save.",
    "db_save_failed": "The database was not saved: {error}",
    "db_duplicate": "{label}: duplicate ids: {ids}.",
    "db_row": "row",
    "db_failed_network": "Network database could not be loaded: {error}",
    "db_failed_storage": "Storage database could not be loaded: {error}",
    "db_failed_hubs": "Hub database could not be loaded: {error}",
    "db_failed_pipelines": "Pipeline database could not be loaded: {error}",
    "col_pipelines": {
        "id": ("id", "database key (hidden)"),
        "name": ("name", "e.g. DN300 / 150 bar"),
        "diameter_m": ("inner diameter (m)", "default 0.30 m"),
        "wall_thickness_m": ("wall thickness (m)", "optional"),
        "roughness_m": ("roughness (m)", "default 4.5e-5 m"),
        "material": ("material", "e.g. steel, PE"),
        "design_pressure_bar": ("design pressure (bar)", "optional"),
        "design_temperature_c": ("design temperature (°C)", "optional"),
    },
    "col_hubs": {
        "id": ("id", "database key (hidden)"),
        "name": ("name", ""),
        "category": (
            "category",
            "source (CO2 enters), chain (transit), sink (storage), buffer, hub, port or offshore terminal",
        ),
        "country": ("country", ""),
        "x": ("x coordinate", "x = northing (EPSG:3765)"),
        "y": ("y coordinate", "y = easting (EPSG:3765)"),
        "elevation_m": ("elevation (m)", "above sea level; blank = unknown"),
    },
    "col_network": {
        "id": ("id", "database key (hidden)"),
        "source_hub": ("source hub", "a hub from the Hubs table"),
        "destination_hub": ("destination hub", "a hub from the Hubs table"),
        "mode": ("mode", "pipeline, truck, rail or marine"),
        "length_km": ("L (km)", "derived from the hub coordinates (read-only)"),
        "pipeline": ("pipeline", "a design from the Pipelines table (pipeline links only)"),
        "capex_eur": ("CAPEX (EUR)", ""),
        "opex_eur_per_t": ("OPEX (EUR/t)", ""),
    },
    "col_storage": {
        "id": ("id", "database key (hidden)"),
        "slug": ("slug", "stable reference for scenarios and results"),
        "name": ("name", ""),
        "hub": ("hub", "a sink hub from the Hubs table"),
        "storage_type": ("type", "DSA, DHF, DGF or DOF"),
        "capacity_mt": ("capacity (Mt)", ""),
        "depth_m": ("depth (m)", ""),
        "porosity": ("porosity", ""),
        "permeability_m2": ("permeability (m²)", "100 mD = 1e-13 m²"),
        "pressure_bar": ("pressure (bar)", ""),
        "temperature_c": ("temperature (°C)", ""),
        "lithology": ("lithology", ""),
        "well_diameter_m": ("well diameter (m)", "default 0.30 m"),
        "well_number": ("number of wells", "injection capacity scales with the well count"),
    },
    "col_database": {
        "id": ("id", "database key (hidden)"),
        "slug": ("slug", "stable reference for scenarios and results"),
        "name": ("name", "plant name"),
        "industry": ("industry type", "e.g. power plant, cement works, refinery"),
        "curve": ("curve", "constant, power_law or piecewise_linear"),
        "reference_year": ("ref. year", "year E0 refers to"),
        "e0_t_per_year": ("E0 (t/yr)", "emission in the reference year"),
        "a": ("a", "linear decline, e.g. -0.03"),
        "c": ("c", "power exponent, e.g. 1.5"),
        "points": ("points", "'year: t/yr', e.g. '2030: 100000, 2040: 80000'"),
        "activation_year": ("start year", "first year with a contribution"),
        "implementation_probability": ("CCS probability", "implementation probability (0-1)"),
        "hub": ("hub", "the source hub the CO2 enters"),
        "emissions": (
            "CO2 emissions (t/yr)",
            "the constant rate for a constant curve; derived for power_law / piecewise",
        ),
    },
    "inputs_hint": (
        "Edit the tables, then click 'Apply and run'. Add emitters, connections and storage sites "
        "as a new row at the bottom (blank cell = NaN). The reference catalogues (emitters, hubs, "
        "network, storage) live in the last tab, 'Database'."
    ),
    "btn_apply": "Apply and run",
    "routes_locked": (
        "Routes the table cannot express (a state timeline or a conditional upgrade) are kept unchanged: {routes}."
    ),
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
    "sec_connections": "Link emitter → route → storage",
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
        "sel": ("select", "tick the rows to delete"),
        "emitter_id": ("emitter", "id from the Emitters table"),
        "route_edge_id": ("route", "route id from the Routes table (first leg)"),
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