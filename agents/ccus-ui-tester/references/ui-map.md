# UI map – CCUS cluster Streamlit app

Source of truth: `streamlit_app/app.py` (layout) and `streamlit_app/i18n.py` (labels).
Labels are given as **HR / EN**. The default language is Croatian.

## Sidebar (top to bottom)

| Element | Type | Label HR / EN | Notes |
|---|---|---|---|
| Language | selectbox (key `language`) | Jezik / Language | Hrvatski, English. Switching currently discards results (K19). |
| Source | radio | Izvor / Source | options below |
| – option 1 | | Klaster (14 emitera) / Cluster (14 emitters) | loads `inputs/examples/cluster_three_emitters.json` (**3** emitters; K16) |
| – option 2 | | Jedan lanac (legacy) / Single chain (legacy) | loads `inputs/examples/ccus_cluster_v1.json` |
| – option 3 | | Učitaj JSON / Upload JSON | shows a file uploader "JSON scenarij / JSON scenario" |
| Status line | success / error | Scenarij: {name} / Scenario: {name}; Neispravan scenarij: … / Invalid scenario: … | |
| Run | button (primary) | Pokreni / Run | runs the **file** scenario, resets the tables (edits are lost) |
| Load scenario | button | Učitaj scenarij / Load scenario | copies the source into the tables; needed after an upload (K21) |
| Save section | subheader | Spremanje scenarija / Save scenario | |
| Scenario name | text input (key `scenario_name`) | Naziv scenarija / Scenario name | default `scenario_001`, `scenario_002`, … |
| Save | button | Spremi / Save | writes `<name>.json` to `GT_CCS_SCENARIO_DIRECTORY` |
| Saved scenarios | selectbox (key `saved_choice`) | Snimljeni scenariji / Saved scenarios | only when files exist; otherwise "Nema snimljenih scenarija. / No saved scenarios yet." |
| Load | button | Učitaj / Load | loads the selected saved scenario into the tables |
| Confirm deletion | checkbox | Potvrdi brisanje / Confirm deletion | reveals Delete |
| Delete | button | Obriši / Delete | deletes the saved file (see K12 – do not use with names that match project files) |

## Main page

Title: "CCUS cluster – dinamični emiteri i multimodalni transport" / "CCUS cluster – dynamic
emitters and multi-modal transport". Status banner: "Scenarij nije pokrenut / Scenario has
not been run", "Scenarij je aktualan / Scenario is up to date", "Scenarij je izmijenjen –
pokreni ponovno / Scenario changed – run again".

### Tabs

| # | HR | EN | Content |
|---|---|---|---|
| 1 | Ulazi | Inputs | 4 editable tables + economics inputs + "Primijeni i pokreni / Apply and run" |
| 2 | Emiteri | Emitters | compression towards the first hub (table), captured CO2 bar chart |
| 3 | Sažetak | Summary | 4 metrics for the slider year, emitter table, annual ledger |
| 4 | Mreža | Network | schematic map (matplotlib image), edges table, hub pressures table + chart, flows chart + table, reservoir pressure chart |
| 5 | Skladište | Storage | storage site selectbox, cumulative stored (expander), pressure/BHP chart per site |
| 6 | Ekonomika | Economics | 4 metrics, cash-flow chart and table, stakeholder table + chart, cumulative cost, cost pie (year selectbox), per-entity economics |
| 7 | Tablice | Tables | routes table, "Preuzmi tehnički sažetak (CSV) / Download ledger (CSV)" |

The timeline slider "Vremenska os / Timeline" appears under the tabs after a run. It starts
at the **first** year, where most overview metrics are 0; move it before comparing values.

### Metrics

| Tab | HR | EN | Oracle key | Depends on slider |
|---|---|---|---|---|
| Sažetak | Uhvaćeno CO₂ (t) | Captured CO2 (t) | `metric_captured` | yes |
| Sažetak | Rutirano (t) | Routed (t) | `metric_routed` | yes |
| Sažetak | Utisnuto (t) | Injected (t) | `metric_injected` | yes |
| Sažetak | Pohranjeno ukupno (t) | Stored total (t) | `metric_stored` | yes (cumulative to that year) |
| Ekonomika | NPV (EUR) | NPV (EUR) | `metric_npv` | no |
| Ekonomika | IRR | IRR | `metric_irr` | no (shown as `0.00 %` when undefined) |
| Ekonomika | PV prihodi (EUR) | PV revenues (EUR) | `metric_pv_revenue` | no |
| Ekonomika | PV troškovi (EUR) | PV costs (EUR) | `metric_pv_cost` | no |

Number format: thousands separator `,`, no decimals (e.g. `-919,875,061`).

### Editable tables (tab Ulazi / Inputs)

Rows can be added at the bottom of each table ("+" row) and deleted with the row checkbox.
Headers:

**Emiteri / Emitters** – id, naziv/name, početak/start (activation year),
vjerojatnost/probability, krivulja/curve (`constant`, `power_law`, `piecewise_linear`),
E0 (t/god)/E0 (t/yr), a, c, konstantno (t/god)/constant (t/yr),
capture kapacitet (t/god)/capture capacity (t/yr), capture CAPEX (EUR), capture OPEX (EUR/t).

**Pristupi emiter → skladište / Connections** – emiter/emitter, skladište/storage,
od godine/from year, do godine/to year, način/mode (`pipeline`, `truck`, `rail`, `marine`),
L (km), kapacitet (t/god)/capacity (t/yr), CAPEX (EUR), OPEX (EUR/t), OPEX (EUR/t·km).
Empty for the default "Klaster" and "Jedan lanac" sources (they use hub edges, not
connections).

**Skladišta (DSA / DHF) / Storage** – id, naziv/name, tip/type (DSA, DHF),
geotermalni dublet/geothermal doublet (checkbox), početak geotermalne/geothermal start,
kapacitet (t)/capacity (t), dubina (m)/depth (m), poroznost/porosity,
propusnost (m²)/permeability (m²), od godine/from year, CAPEX (EUR), OPEX (EUR/t),
monitoring (EUR/god) – injekcija / injection, monitoring (EUR/god) – nakon / after.

**Geotermalni sustavi / Geothermal systems** – id, naziv/name, skladište/storage,
razmak para (m)/doublet spacing (m), T ležišta (°C)/reservoir T (°C), η ORC,
p izlaza ORC (bar)/ORC outlet p (bar), T izlaza ORC (°C)/ORC outlet T (°C),
od godine/from year, do godine/to year, CAPEX (EUR), OPEX (EUR/god)/OPEX (EUR/yr).

**Ekonomika / Economics** (number inputs) – Početna godina/Start year,
Završna godina/End year, Diskontna stopa/Discount rate, Inflacija/Inflation.

## What the UI cannot edit (use JSON upload)

Hub nodes and multi-leg edges, infrastructure upgrades (year / cumulative-mass triggers),
marine and road designs, pipeline diameters, reservoir area/thickness/temperature, policy
block (ETS, price paths, unit costs), CO2 price path, node locations. Pressing
"Primijeni i pokreni" rebuilds the scenario from the tables only and **drops** all of these
(K08).

## Stable selectors (for Playwright, if needed)

Prefer accessible names from the snapshot. Streamlit test ids present in the front end:
`stSidebar`, `stTab`, `stSlider`, `stMetricLabel`, `stMetricValue`, `stDataFrame`,
`stDataFrameGlideDataEditor`, `stFileUploaderDropzoneInput`, `stAlertContainer`,
`stException`, `stStatusWidget` (shows "Running..." during a rerun), `stApp`.
