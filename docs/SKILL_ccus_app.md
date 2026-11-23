# Skill – CCUS cluster app (GT-CCUS-graph-streamlit)

**Purpose.** Build and maintain the UI-agnostic CCUS engine (`ccus_core`) and its
Streamlit front end (`streamlit_app`).  Source: <https://github.com/dvulin/CCUS_cluster>
(upstream branch `gt-ccs-streamlit`; work happens on local `GT-CCUS-graph-streamlit`).

## 1. Layout

```
ccus_cluster/
├── ccus_core/            # engine
│   ├── models/           # Pydantic data model (no I/O, no UI)
│   ├── network/          # graph, routing, hub pressure cascade
│   ├── simulation/       # solver, reservoir, geothermal, pressures, adapters
│   ├── finance/          # cash-flow adapter, per-stakeholder statements
│   ├── io/               # compact JSON, scenarios, catalogues (SQLite), CO2 prices
│   └── engine.py         # ScenarioEngine facade
├── engineering/          # legacy physics (MaterialBalance, VFP, Geothermal, Power, Pipeline)
├── economics/            # audited cash-flow runner
├── inputs/examples/      # stored scenarios (JSON)
├── streamlit_app/        # app.py + i18n.py + map_layers.py (UI only)
├── tests/                # pytest suite (no UI needed)
└── docs/                 # architecture, skill, whitepaper, tools_used.txt
```

Layering rule: `engineering`/`economics` are imported **by** `ccus_core`, never the
reverse; `ccus_core` never imports Streamlit/matplotlib/tkinter/xlwings.

## 2. Commands

```powershell
$py = 'C:\Users\dvulin\anaconda3\python.exe'
& $py -m pytest tests -q              # fast suite (312 tests)
& $py -m pytest tests -q --runslow    # + legacy golden regression
& $py -m streamlit run streamlit_app/app.py     # → http://localhost:8501
& $py docs\whitepaper\build_whitepaper.py       # regenerate the whitepaper
```

## 3. Model cheat-sheet

| Concept | Where | Notes |
|---|---|---|
| Scenario document | `models/scenario.py` | `start_year`, `end_year`, `nodes`, `emitters`, `edges`, `connections`, `storage_sinks`, `geothermal_systems`, `economics`, `policy` |
| Emission curve | `models/emitter.py` | `constant`, `piecewise_linear`, `power_law` (`E0 + b·(t−t₀)^c`, `b=a·E0`), `polynomial` |
| Onboarding | `models/emitter.py` | `activation_year` or `implementation_probability` (1.0→2026, 0.5→2028, 0.1→2033) |
| Transport state | `models/edge.py` | `EdgeState` per year window; `resolve_state(year, cumulative_mass_t, fired_upgrades)` |
| Upgrades | `models/edge.py` | `InfrastructureUpgrade` with `year` and/or `cumulative_mass` trigger + lead time |
| Sinks | `models/sink.py` | `StorageSink` (+`ReservoirProperties`, defaults φ=0.20, k=100 mD, 1500 m), `geothermal_coupled`, `geothermal_start_year` |
| Policy | `models/policy.py` | EU ETS phase-out, three CO2 price paths, capture/transport/storage unit costs, Fisher relation |
| CO2 prices | `json/CO2_prices.json`, `io/co2_prices.py` | the three price scenarios as an editable yearly series (2025-2050); loaded into `policy.prices` and into a preset `economics.price_path` that omits `values_eur_per_t`. Missing file → workbook defaults; malformed file → `Co2PriceFileError` |
| Connections | `models/connection.py` | many-to-many emitter→sink access with its own `start_year` |

## 4. Solver pipeline (year loop)

`simulation/solver.py::ChronologicalSolver.run()`:

1. emitters → captured mass (curve × capture capacity);
2. `network/routing.py` → cheapest feasible path under edge/sink capacities,
   leftovers reported as `unallocated`;
3. `simulation/reservoir.py::VariableRateReservoir` inverts `m_CO2(p)` (no physics change)
   and recomputes BHP at the *local* rate;
3b. `network/pressure.py` + `simulation/pressures.py` → hub pressure cascade
    `p[i] = p[i+1] + dp_i(flow_i)` from the 10 bar storage target upwards;
4. `simulation/geothermal.py` evaluates the doublet at **that year's pressure**;
5. `finance/cashflow.py` builds the `CashFlowRunner` config (CAPEX schedules, modal OPEX);
6. `finance/stakeholders.py` splits the same flows per party (emitter, transport,
   storage, geothermal) and exposes per-entity timeseries.

## 5. Conventions

* Canonical input: **compact JSON** with a `_comments` legend (≤500 lines for 14 emitters).
* Money in EUR, mass in t CO2, pressure in bar, power in kW, energy in MWh (8766 h/yr).
* All engineering classes are stateless per call; time lives in the solver/DataFrames.
* Croatian UI strings live in `streamlit_app/i18n.py` (`hr`/`en`), never inline.
* Anything added to `ccus_core` needs a test in `tests/` (pytest, no UI).

## 6. Recipes

**Add an emitter** – new row in the UI *Emitters* table (id, name, start year, curve,
E0/a/c, capture capacity/CAPEX/OPEX) or an object in the JSON `emitters` list.

**Add a sink** – *Skladišta* table (capacity, depth, φ, k, CAPEX, OPEX, monitoring),
plus `connections` rows (or `edges` through hubs) that point at it.

**Add a hub** – a junction node with a booster station; legs *emitter → hub*,
*hub → hub*, *hub → storage* are plain edges with `distance_km` and a pipeline design.
The cascade in `network/pressure.py` then returns the required pressure at every node.

**Add a transport mode** – extend `TransportMode` + `EdgeState` design
(pipeline/road/marine) and the cost rules in `finance/cashflow.py`.

**Compression duty** – the emitter that joined last carries the shared trunk; the
pressure table shows why (`simulation/pressures.py`).

## 7. The user interface

Tabs, in order: **Scenario**, Inputs, Emitters, Summary, Network, Storage, Economics,
Tables, Database.

**Standing rules for this app:**

* **A new scenario has no links.** The emitters and the sinks are the brief; the
  network is what the study decides. Use *New scenario (no links)* in the sidebar.
  Loading a saved scenario still brings its links back.
* **A hub needs coordinates to count.** Without latitude/longitude it is not drawn,
  not tickable, not offered as a link end, and cannot be added as a new hub.

* **Scenario** (first) is what the study *is*, ordered as the study is:
  1. **Hubs** - an editable grid: a leading **on map** tick, id, name, kind,
     latitude, longitude, degree. `+` adds a hub (give it coordinates and it appears
     on the map); unticking takes it off the map without deleting it; deleting the
     row is refused while a link, emitter or sink still uses the hub. Any column can
     be filtered, and the filter is merged back so hidden rows are never deleted.
     **Check all / Uncheck all** ticks the whole column at once.
  2. **Links** - the links table. `from node` / `to node` are selectboxes over the
     hubs that exist, never free text. One row = one leg between two hubs. The leading
     tick column is a **selection**: **Check all** ticks every row, **Delete selected
     (N)** removes exactly those, and **Delete all links** clears the table behind a
     confirmation. An empty table says so instead of looking broken, and is a
     legitimate state to save.
     The **`total_distance_km`** column answers "how far is the CO2 still from the
     storage site on this leg?". It is measured against the storage site chosen in
     *Measure the distance to* above the grid (default: the sink the most connections
     point at), and the convention is
     `total(leg) = length(leg) + total(next leg towards the sink)` - so the leg that
     enters the site is worth its own length, and the first leg of a chain carries the
     full emitter → storage distance. A leg with no directed path to that sink stays
     blank and is named in a warning. A leg reaching several sinks shows the selected
     one and lists every other one in the expander *Distance from every leg to every
     storage site*; the values are never averaged. The column is calculated while the
     topology is unchanged, **written into the scenario on save** (`TransportEdge.total_distance_km`),
     and a value the user types becomes an override that survives later recalculation
     - *Discard typed distances (N)* puts every row back under calculation.
  3. **Connections** - emitter → route → sink, one row per access. All three are
     selectboxes (emitters, the links that exist, storage sites); a blank route means a
     direct emitter-to-storage access. The leading tick selects rows for **Delete
     selected (N)**. This is the many-to-many business object the solver expands into
     directed edges, and it is edited here - next to the legs it points at - not in
     `Inputs`. An id that no longer exists stays visible and is reported; Apply
     refuses it (D7).
  4. **Add a link from the catalogue** - the bridge to the *candidate* catalogue,
     which stays in `Database`. Labels name both hubs with category and country
     (`HR.CH.001 (chain, HR) → HRCH003 (chain) · pipeline · 27.06 km`), and a hub the
     scenario does not have is marked "new hub".
  5. **Draw a link on the map** - *New link*, click the inlet hub, click the outlet
     hub; the row appears in the table and on the map. The length is a great-circle
     estimate and stays editable for a GIS measurement. Chaining (A-B then B-C) is
     the router's job, not extra UI.
  6. **Save links to the scenario** - validates through `frames_to_scenario` and
     writes the scenario file, without running the chain. A disconnected scenario
     asks for one confirmation ("Save anyway") rather than being refused.

  The candidate catalogue answers "which corridors exist"; a scenario answers "which
  ones am I building". Links live here and not in `Database` because a network
  belongs to one scenario.
* **A tick needs one click, not two.** A `st.data_editor` keeps its own widget
  state, so the grid used to show the old values until the next interaction.
  `_finish_edit` drops the widget key and reruns whenever an edit changed the frame,
  which is what makes a checkbox stick on the first click.
* **The Scenario tab is laid out tight.** Each table's controls sit on one toolbar
  row (collapsed labels), the connectivity check is a single line with the details in
  an expander, and *New link* prints the instruction for the next click.
* **Two pydeck traps.** `line_width_units` must be `pydeck.types.String("pixels")` —
  a plain string becomes the JS expression `@@=pixels`, which is `undefined`, so deck
  silently falls back to metres and draws huge bands. And a link shorter than a pixel
  needs the map to zoom to it (`_focus_view`), or it is simply not visible.
* **Connectivity**: `ccus_core/network/connectivity.py::unreachable_emitters` walks
  the link graph from each emitter's node and reports the ones that reach no storage
  site, with the reason. The Scenario tab shows the report and Save refuses to write
  a disconnected scenario.
* **Distance to storage**: `connectivity.py::distance_to_sinks` runs a reverse
  Dijkstra from every storage node over the directed link graph and returns
  `{edge_id: {sink_id: km}}` for the whole scenario, so the same function serves the
  designer's column, its multi-sink expander and any report. It is pure graph
  analysis - no solver, no UI - and `TransportEdge.total_distance_km` only stores
  what the designer wrote; the solver never reads it.
* **Map picking**: the hub layer is a `ScatterplotLayer` (a real pixel radius and the
  picking `st.pydeck_chart(on_select="rerun")` reports), every layer declares an `id`
  because the selection is keyed by layer, and the layer data carries the node id.
  A hub without WGS84 coordinates is left off the map rather than drawn at 0, 0.
  The links layer draws every link, coloured by transport mode (pipeline blue,
  truck orange, rail green, marine violet) with a legend. Each line is drawn twice -
  a pale casing under a thick coloured core - so it stays legible over the basemap
  and over the reference routes. A line follows the GIS polyline when the hubs match
  a surveyed route, the road when the mode is truck (OSRM demo server, cached, 6 s
  timeout) and the direct line otherwise. With *Follow roads* on, a truck link also
  **stores** the road length, not the crow-flies one - they differ by ~43 % on a real
  leg, and costs are per km. The road lookup is presentation-only - `ccus_core` stays
  offline - and a missing network falls back to the straight line.
  A link whose endpoint has no coordinates is not drawn, and the map names it.
  **Note**: a long-running `streamlit run` does not always reload `map_layers.py` -
  after editing it, restart the server, or the map keeps the old layer code and
  clicks appear to do nothing.
* **Database** holds the reference catalogues (emitters, hubs, pipelines, candidate
  links, storage) plus **Backup and restore**: *Download database* returns the whole
  `data/ccus.sqlite3` as `gt_ccus_db.sqlite`, and the uploader restores one. A restore
  validates the file (SQLite signature, `integrity_check`, required tables, schema
  version), copies the current database to `data/backups/` and only then replaces it,
  then regenerates the JSON snapshot. Nothing else in the repository holds the
  catalogue: the database is git-ignored, so without that download there is no copy.
* All UI text goes through `streamlit_app/i18n.py` (Croatian and English); add a key to
  both dictionaries.

## 8. Known gaps (do not promise these)

* hub as a **first-class node kind with a real booster station** (CAPEX/OPEX, and the
  ability to *raise* pressure, not only to consume it);
* **buffer storage** for batch modes (ship, truck, rail) where continuous delivery
  is impossible;
* monthly resolution (`step` is validated but only `yearly` is solved);
* real coordinates / true connectivity for the map (schematic today);
* DHF reservoir data for Ivanić / Stružec / Boksic (capacity-only sinks);
* transient thermal breakthrough and stochastic weather downtime.

## 9. Verification checklist

```powershell
& $py -m pytest tests -q --runslow     # 344 tests, ~80 s
& $py -m streamlit run streamlit_app/app.py   # then: Apply → timeline → tabs
```

Golden baseline (legacy `ScenarioRunner`): 9.10 Mt stored, 276.0935 bar final pressure,
NPV −481.6 M€ — if these move, the physics changed.

## 10. Fix plan status (numbers and data loss)

The seven P1 items are implemented and each has the regression test that would have
caught it (see `docs/ARCHITECTURE_ccus_core.md` §9.12 for the invariant table):

| # | Fix | Test |
|---|---|---|
| 1 | monitoring charged `rate × years` per phase, `monitoring_end_year` required | `test_fix_numbers.py` |
| 2 | stakeholder CAPEX booked once; Σ stakeholder net = consolidated net | `test_stakeholders.py` |
| 3 | upgrade CAPEX only when the trigger fires (solver passes `fired_upgrades` + mass) | `test_fix_numbers.py` |
| 4 | Apply round-trips edges (states, upgrades, designs, node locations) or refuses | `test_app_layer.py` |
| 5 | JSON: quoted keys, edges kept, stale derived edges refreshed, load/delete confined | `test_json_format.py`, `test_scenario_repository.py` |
| 6 | compressor power summed, per-sink rate caps, BHP/capacity flags | `test_fix_numbers.py` |
| 7 | engine-created doublet, one electricity credit, real pump efficiency + availability | `test_geothermal_coupling.py` |
| 8 | CO2 price scenarios live in `json/CO2_prices.json`, not in Python | `test_co2_prices.py` |

Tools and absolute paths: `docs/tools_used.txt`.