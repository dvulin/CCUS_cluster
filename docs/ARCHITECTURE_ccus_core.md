# `ccus_core` – architecture and extension notes

This document describes the UI-agnostic core added on branch `feat/ccus-core`.  It
complements [STUDY_ccus_cluster.md](STUDY_ccus_cluster.md), which documents the
*existing* `gt-ccs-streamlit` code.

## 1. Layering

```
streamlit_app/app.py      presentation only  -> imports ccus_core
ccus_core/engine.py       facade             -> ScenarioEngine.run()
ccus_core/network/        graph + routing    -> no physics, no UI
ccus_core/simulation/     solver + wrappers  -> imports engineering/*
ccus_core/finance/        cash-flow adapter  -> imports economics/*
ccus_core/io/             JSON, scenarios, workbook import, emitter catalogue, CO2 prices
ccus_core/models/         Pydantic models    -> no I/O at all
json/                     reference data for the front ends (emitters.json, CO2_prices.json)
engineering/, economics/  legacy physics and audited cash flow (unchanged)
```

Rules enforced by the test suite:

* `ccus_core` never imports `streamlit`, `matplotlib`, `tkinter` or `xlwings`;
* `engineering` and `economics` are imported *by* the core, never the reverse;
* the models accept JSON in and return JSON/DataFrame out.

## 2. Data model (`ccus_core/models`)

| Model | Purpose |
|---|---|
| `ScenarioConfig` | root document: years, nodes, emitters, edges, sinks, geothermal, economics |
| `EmissionCurve` | `constant`, `piecewise_linear` (ramp/steady/decline) or legacy `polynomial` |
| `Emitter` | onboarding year, decommissioning, gross emissions, optional `CaptureUnit` |
| `Node` / `PortHub` | graph vertices, onshore/offshore flag, berth and weather limits |
| `EdgeState` | one transport state: mode, capacity, distance, CAPEX, tariff, modal design |
| `TransportEdge` | ordered state timeline, conditional `InfrastructureUpgrade`s, and the designer's `total_distance_km` annotation (ignored by the solver) |
| `StorageSink` | capacity, reservoir properties, wells, monitoring, compressor/efficiency data |
| `GeothermalSystem` | doublet geometry, ORC/pump efficiencies, availability, OPEX |
| `EconomicsConfig` | discounting, inflation, electricity prices, CO2 price path |

## 3. Temporal state logic

`TransportEdge.resolve_state(year, cumulative_mass_t=None, fired_upgrades=None)`:

1. the planned state is the latest `EdgeState` whose `[valid_from_year,
   valid_until_year]` window contains the year;
2. every fired `InfrastructureUpgrade` contributes its `new_state` from
   `fired_year + lead_time_years`;
3. the candidate with the largest start year wins.

A `year` trigger can be evaluated inside the model.  A `cumulative_mass` trigger
cannot, because it needs the chronological history of the edge: the solver records
the firing year and passes it back through `fired_upgrades`.  This keeps the model
free of solver state (required for `st.session_state` and desktop state stores).

## 4. Routing

`RoutingEngine.route(year, supplies, sink_remaining_capacity)` allocates each
emitter's captured CO2 along the cheapest feasible path:

* cost = sum of the per-tonne tariffs of the arcs of the year;
* capacity = minimum of the explicit edge capacity, the modal design capacity
  (fleet size, vessel/weather cycle) and the residual capacity;
* residual capacities are decremented as the allocation proceeds, so an early
  emitter can starve a later one – the behaviour a cluster study must expose;
* any tonnage that cannot be routed is reported in `RoutingResult.unallocated`
  with an explanatory note.

## 5. Physics coupling

`VariableRateReservoir` reuses `engineering.MaterialBalance` unchanged:

1. `capacity_curve()` runs the legacy pressure ramp once and stores `m_CO2(p)`;
2. for a scheduled annual mass it inverts the curve, `p(t) = interp(Σm, m_CO2, p)`;
3. the BHP is recomputed with the *local* annual rate through the already
   rate-parameterised `solve_BHP_from_CO2_mass_flow`;
4. saturation and Corey permeabilities come from the existing
   `calculate_effective_saturation` / `kr_Corey`.

For the reference case (700 kt/yr, 2028-2040) this reproduces the legacy result
276.0935 bar at the end of injection – see
`tests/test_solver.py::test_reservoir_curve_matches_the_legacy_constant_rate_case`.

`GeothermalCoupling` drives `Geothermal`, `VFP` and `Power` with the annual storage
pressure and reports production flow, ORC power and pump power per year.

## 6. Finance

`build_cash_flow_config` translates the scenario plus the routed cost into the
flat configuration of the existing `economics.CashFlowRunner`:

* **CAPEX placement has one source of truth**: `capex_schedules()` returns the
  per-block, per-year CAPEX map (`capture`, `transport`, `storage`, `compressor`,
  `geothermal`) clamped to the ledger horizon.  The consolidated cash flow and the
  per-stakeholder statements both call it, so a euro of CAPEX can never be booked in
  two different years or counted twice.  Every asset is booked **once**:
  * a planned `EdgeState` in its `valid_from_year`,
  * an `InfrastructureUpgrade` in `fired_year + lead_time_years` **and only when the
    trigger actually fires** (`upgrade_capex_by_edge()`); a mass trigger that never
    fires books nothing,
  * a capture plant, a sink or a doublet in its commissioning year.
* **monitoring is an annual rate**: `monitoring_cost_by_sink()` charges
  `rate × years` per sink - `..._during_injection_eur_per_year` while the site
  injects and `..._after_injection_eur_per_year` from the last injection year to
  `monitoring_end_year`, which is **required** as soon as a monitoring rate is set.
  A pre-summed cluster total is never passed to the runner (it would be multiplied
  by every year of the ledger).
* **transport OPEX** follows the routed modal cost of each year;
* inflation escalation, discounting, cumulative NPV, IRR and the without-CCS
  counterfactual are computed by the audited `CashFlowRunner`.

## 7. Solver output

`SimulationResult` holds:

| Attribute | Content |
|---|---|
| `routing` | `list[RoutingResult]` – one per year (allocations, edge flows, sink injections, `rate_limited_sinks`, `capacity_limited_sinks`) |
| `reservoir` | `{sink_id: DataFrame}` – annual pressure, saturation, BHP, `bhp_above_limit`, `capacity_limited` |
| `geothermal` | `{system_id: DataFrame}` – annual flow, ORC/pump power, availability factors |
| `ledger` | annual technical ledger consumed by the cash-flow model |
| `cash_flow` | annual cash flow with NPV/IRR columns |
| `kpis` | stored/routed/unallocated CO2, NPV, IRR, PV revenues and costs, `rate_limited_sinks`, `capacity_limited_sinks`, `bhp_limited_sinks` |
| `fired_upgrades` | `edge_id → {upgrade_id: year the trigger fired}` – the chronological bookkeeping the finance layer needs |
| `edge_cumulative_mass` | `edge_id → t` shipped, used to evaluate mass triggers |
| `to_dict()` | JSON-safe summary (used by external state managers) |

`year_snapshot(result, year)` returns the per-year view consumed by the timeline
slider and the map.

### 7.1 Compressor power and injection limits

* the compressor power of **every active sink is summed** (each site has its own
  injection skid); `compressor_power_kw` is the authoritative column and
  `compressor_peak_kw` remains as a deprecated alias for the legacy ledger readers;
* `StorageSink.max_injection_rate_t_per_year` caps the annual injection of a sink
  independently of its pore volume and is enforced inside the router
  (`RoutingEngine.route(sink_injection_limits=…)`); a sink stopped by its rate cap is
  reported in `rate_limited_sinks`, never confused with an empty reservoir;
* a BHP above the fracture limit (`reservoir.maximum_pressure_bar`) sets
  `bhp_above_limit` per year and `kpis["bhp_limited_sinks"]`.

## 8. Tests

```
pytest tests -q              # 131 tests, < 20 s
pytest tests -q --runslow    # adds the legacy ScenarioRunner golden regression
```

| File | Covers |
|---|---|
| `test_emitter_model.py` | staggered onboarding, ramp/decline, capture limits, validation |
| `test_edge_model.py` | truck→pipeline switch, tariff switch, lead time, mass trigger, marine/road capacity |
| `test_routing.py` | undersized edge, mid-run upgrade, offshore bottleneck, multi-hop tariff, sink exhaustion |
| `test_scenario_model.py` | graph validation, duplicate ids, price paths, cash-flow config mapping |
| `test_solver.py` | physics equivalence with the legacy model, end-to-end run, timeline snapshot, example JSON |
| `test_fix_numbers.py` | monitoring `rate × years`, mass-triggered upgrade CAPEX once, compressor sum, per-sink rate caps, BHP/capacity flags |
| `test_geothermal_coupling.py` | engine-side doublet, one electricity credit, real pump efficiency, availability derating |
| `test_stakeholders.py` | Σ stakeholder net = consolidated net per year, CAPEX once, upgrade CAPEX, reference scenarios |
| `test_json_format.py` | compact dump/load, quoted numeric keys, upgrades and designs survive, stale derived edges |
| `test_scenario_repository.py` | save/load/list/delete confined to the scenario directory |
| `test_app_layer.py` | Apply round-trip (upgrades, states, node locations, reservoirs) and the refusal path |
| `test_legacy_oracle.py` | golden regression of `services.ScenarioRunner` (slow) |

## 9. Emission-change model, onboarding and policy (from the cluster workbook)

### 9.1 Emission curve

`EmissionCurve` gained the thesis curve ``kind="power_law"``::

    E(t) = max(0, E0 + b * (t - t0)**c),   b = a * E0

``a`` is the linear decline rate (-0.02 … -0.05), ``c`` the power-law exponent
(1.5).  `net_zero_year()` returns the first year the curve reaches zero
(Plomin 2036, Zagreb 2037 in the workbook).  The other curve families
(`constant`, `piecewise_linear`, `polynomial`) are unchanged.

### 9.2 Onboarding from the implementation probability

The workbook uses a CCS implementation probability per emitter
(1.0 / 0.5 / 0.1).  `ScenarioConfig.onboarding_years` maps it to the first
contributing year (default `1.0 → 2026`, `0.9 → 2027`, `0.5 → 2028`,
`0.1 → 2033`).  An emitter may declare either `activation_year` or
`implementation_probability`; the validator resolves the year and then applies the
usual consistency checks (decommissioning, capture commissioning).

### 9.3 Policy block

`PolicyConfig` (optional on the scenario) carries:

| Block | Content |
|---|---|
| `ets` | free-allocation phase-out: 50 % (2025), 47.5 %, 42.5 %, 32.5 %, 17.5 %, 0 % (2030) |
| `prices` | three CO2 price scenarios 2025-2050 (optimistic / conservative / pessimistic) |
| `capture` | CAPEX/OPEX per tonne by technology (PI 100, NI 75, OXY 90 EUR/t; OPEX 30/40/25/20) + oxygen plant CAPEX |
| `transport` | 0.7 EUR/(t·km); OPEX 15 EUR/t up to 45 km, ``22*ln(L) - 80`` above |
| `storage` | injection CAPEX/OPEX per tonne |
| `financial` | real rate, inflation, Fisher nominal rate (6 % / 6 % → 12.36 %) |

When a policy block is present, the without-CCS counterfactual uses **taxable**
emissions (gross × (1 − free share)) instead of gross emissions.

### 9.4 Canonical JSON input (compact, editable, documented)

`ccus_core.io.commented_json` reads and writes the scenario document. The default
`style="compact"` keeps **one block per line** while it fits in 320 characters
and moves the prose into a `_comments` legend at the top of the file:

```json
{
  "schema": "ccus-cluster/2.0",
  "_format": "compact: one block per line; units and explanations in _comments",
  "_comments": { "emitters[].activation_year": "year - first year the emitter can contribute", "…": "…" },
  "scenario": {
    "start_year": 2025,
    "emitters": [
      {"id": "nexe", "name": "NEXE", "node_id": "nexe-gate", "activation_year": 2028,
       "gross_emissions": {"kind": "power_law", "e0_t_per_year": 1118203.087, "reference_year": 2025, "a": -0.03, "c": 1.5}}
    ],
    "connections": [ {"emitter_id": "nexe", "sink_id": "ivanic", "start_year": 2028, "mode": "pipeline", "distance_km": 22.0} ]
  }
}
```

The 14-emitter / 3-sink cluster example is **189 lines** (previously 4 000+).
Defaults are omitted (`exclude_defaults=True`).  ``edges`` are **always** written:
they carry the state timeline, the conditional upgrades, the modal designs and the
``geometry_id``, none of which a connection can express - dropping them would lose
data.  ``connections`` stay in the document as the many-to-many access list, and a
stored edge that a connection fully defines (single state, no upgrade, capacity
declared) is refreshed from that connection on load, so an edited connection can
never leave a stale capacity behind.  The loader still accepts plain JSON and the
older `style="verbose"` records (`value`/`unit`/`comment` per leaf), which remain
available for archival.  Dict keys are always quoted: ``points`` is keyed by year and
``onboarding_years`` by probability, so a bare ``{2030: …}`` would not be valid JSON
(`test_json_format.py::test_numeric_keys_are_quoted_so_the_document_is_valid_json`).

### 9.5 Workbook import (one way, Excel → JSON)

`ccus_core.io.excel_import.build_scenario()` reads `razrada scenarija`,
`emissions-change` and `storage` with a small standard-library XLSX reader
(`openpyxl` cannot open this particular workbook because of its stylesheet) and
returns a `ScenarioConfig`.  The result for the supplied workbook is committed as
`inputs/examples/croatia_cluster_2025_2050.json` (14 emitters, 14 single-leg
edges, 3 sinks: Ivanić 5.5 Mt, Stružec 1.7 Mt, Boksić 13.7 Mt).

The import is deliberately a *starting point*: each emitter keeps the single leg
from the workbook, so once a sink is full the excess CO2 is reported as
`unallocated` until extra edges are added.

### 9.6 Many-to-many access and default reservoirs

`ScenarioConfig.connections` holds `EmitterSinkConnection` objects, one per
emitter→sink access:

* many sinks per emitter (several connections, different `sink_id`),
* many emitters per sink (several connections, same `sink_id`),
* an independent `start_year` per pair, so each emitter can join a given storage
  system in its own year.

The validator expands every connection into a directed `TransportEdge` with a
single `EdgeState` (`valid_from_year = start_year`, optional `end_year`), and
refuses duplicates or unknown references.  The workbook import produces
connections rather than edges.

`storage_defaults` (`ReservoirDefaults`) supplies the physics for newly declared
sites: **porosity 0.20, permeability 100 mD (1e-13 m²), depth 1500 m**, with
25 km² area, 150 m thickness, 150 bar reference pressure and the 0.18 bar/m
fracture gradient.  Every sink without explicit `reservoir` gets this model, so
pressure, BHP and the injection limit exist for any DSA/DHF the user adds.

### 9.7 Per-stakeholder economics

`ccus_core.finance.stakeholders` splits **the same consolidated cash flow** into
per-party statements (emitter, transport operator, storage operator, geothermal
operator).  Every consolidated line item is attributed to exactly one party:

| Consolidated line | Attributed to |
|---|---|
| `capture_capex` | each emitter, in its capture commissioning year |
| `capture_opex` | emitters, pro-rata by captured mass |
| `transport_capex` | each transport operator, per state/fired upgrade year |
| `transport_opex` | transport operators, pro-rata by the tariff of the arcs they carry |
| `compressor_capex` / `compressor_opex` | the storage operator running the skid |
| `storage_capex` / `storage_opex` | each storage operator (per sink, by injected mass) |
| `geothermal_capex` / `geothermal_opex` | the geothermal operator (fixed part + ORC share) |
| `monitoring` | each storage operator, `rate × years` per phase |
| `electricity_purchase` | the storage operator (compressor and pump load) |
| `electricity_revenue` | the geothermal operator (ORC export) |
| `co2_value` | the emitters, pro-rata by delivered mass |
| `cost_inflation_adjustment` | every party, pro-rata by its own base cost |

With these conventions every transfer cancels on consolidation, so

    sum(stakeholder net cash flow) == consolidated net cash flow

holds **for every year and for the total** - asserted in
`test_stakeholders.py` for the solver scenario, for an edge with a triggered
upgrade, and for all three shipped example scenarios.  ``stakeholder_summary()``
returns ``year × stakeholder → net_cash_flow_eur``.

### 9.8 Simultaneous geothermal and CO2 storage

Every storage sink carries ``geothermal_coupled``.  When the flag is set, the
**engine** creates the doublet - ``ensure_coupled_doublets()`` in
``ccus_core.simulation.geothermal`` runs in ``ScenarioEngine.__init__`` and in the
solver, is idempotent, and never overrides an explicit ``GeothermalSystem`` at the
same node.  The UI no longer invents one, so a coupled site has exactly one doublet
and its CAPEX is counted once.  The coupling is evaluated once per year against that
year's storage pressure (see §5):

* the produced mass flow is derated by the **well availability**
  (``min(production_well_availability, injection_well_availability)``);
* the ORC output is derated by ``orc_availability`` and the reinjection pump load by
  ``pump_availability``, so ``orc_gross_mwh``/``gt_pump_mwh`` in the ledger are the
  annual energies, not the nameplate ones;
* the pump power is the electricity needed to lift the water from the surface
  facility pressure (``p_out_bar``) to the injection bottomhole pressure, using the
  **real pump efficiency of the sink** (``StorageSink.eta_gt_injection_pump``), not a
  hard-coded constant;
* ``net_power_kw = orc - pump`` is what the ledger turns into export/import, so one
  kilowatt-hour is credited exactly once (export and import are mutually exclusive
  per year - asserted in ``test_geothermal_coupling.py``).

### 9.9 Named scenarios and geothermal start year

`ccus_core.io.scenario_repository` stores whole scenarios as ``<name>.json`` in
``inputs/scenarios`` (overridable with ``GT_CCS_SCENARIO_DIRECTORY``):
``next_default_name()`` proposes ``scenario_001``, ``scenario_002``, …, names are
validated, writes are atomic and an existing name is never overwritten unless
``overwrite=True``.  **Loading and deleting are confined to the scenario directory**:
``scenario_path()`` rejects a name with ``..``, a separator or an absolute path
outside the directory, so a scenario name can never reach an arbitrary file.

Every storage sink can declare ``geothermal_coupled`` **and**
``geothermal_start_year``; when the flag is set without an explicit geothermal
system, a default doublet is created from that year onwards.  The coupling is
evaluated once per year against that year's storage pressure (see §5).

### 9.10 Hub (booster) nodes – planned

Accepted for the next iteration:

* a new node kind **hub** that carries a booster/compressor station (pressure
  boost, CAPEX, OPEX, availability);
* explicit distances **emitter → hub**, **hub → hub** and **hub → storage**;
* a **backward pressure cascade**: every emitter must deliver CO2 at the pressure
  required at the next hub.  For the first hub in a chain that requirement is the
  pressure needed to arrive at the storage site with a positive pressure above the
  default minimum (10 bar).  Each hub between emitter and storage adds its own
  boost, so the required delivery pressure decreases along the chain.

Until this exists, edges carry no pressure state and the map is schematic only.

### 9.10 Hub (booster) nodes and the pressure cascade

* `ccus_core/network/pressure.py` solves the chain backwards from the storage hub
  (``p_precompression``, default 10 bar): ``p[i] = p[i+1] + dp_i(flow_i)`` with the
  same Darcy–Weisbach/Haaland model as `engineering.Pipeline`.
* Flows are aggregated per **path** (shared legs carry the sum of the emitters on
  them), so adding an emitter raises the required upstream pressure — the
  recalculation the cluster study needs.
* `ccus_core/simulation/pressures.py` returns the annual table
  (`year × leg × p_in/p_out/dp`) and the compression duty follows the convention
  that the emitter which joined last carries the shared trunk.

Remaining: hub nodes as a first-class kind with a *booster station* (it can only
lower the required upstream pressure, never raise it), and buffer storage for
batch modes (ship, truck, rail), where continuous delivery is impossible.

### 9.11 Apply without data loss (Streamlit)

The Inputs tables own a few columns per entity, not the whole study.
`frames_to_scenario()` therefore **patches the base scenario** instead of rebuilding
it from scratch:

* nodes are never rebuilt - coordinates and port data survive Apply;
* emitters keep their `node_id`, decommissioning, notes, capture technology and
  availability; the tables only overwrite the columns they show;
* sinks keep the rest of the reservoir description (area, thickness, temperature,
  reference pressure, `injection_well`); the Storage table only overwrites depth,
  porosity and permeability, and a blank year cell keeps the base year
  (`_optional_year_or`) so a monitoring window cannot be dropped by accident;
* a route row that still matches what the table showed keeps the **whole edge**
  (state timeline, conditional upgrades, modal designs, `geometry_id`);
* a route row that was **edited** while its edge carries more than the table can
  express (a second state or an upgrade) is **refused** with an explicit error
  naming the route, instead of silently flattening it;
* `total_distance_km` is an annotation, not a transport state: it is patched onto a
  kept edge (so a route with upgrades can carry it without being flattened) and is
  never part of `_route_signature`, so writing it can never turn an untouched route
  into an "edited" one;
* connections and geothermal rows keep every field the table does not show.

`test_app_layer.py` asserts the round-trip (identical scenario after
tables → scenario), the preservation of locations/reservoirs/monitoring windows and
the refusal path.  `test_designer_connections.py` adds the connections grid (the
`sel` tick is not data), the distance column and the override rules.

### 9.12 Numbers that must reconcile (review checklist)

| Invariant | Where |
|---|---|
| Σ stakeholder net = consolidated net, per year and total | `test_stakeholders.py` |
| monitoring charged `rate × years`, never a pre-summed total | `test_fix_numbers.py` |
| every asset CAPEX booked once, upgrades only when they fire | `test_fix_numbers.py`, `test_stakeholders.py` |
| compressor power summed over active sinks | `test_fix_numbers.py` |
| per-sink injection-rate cap enforced and reported | `test_fix_numbers.py` |
| BHP above the fracture limit and exhausted capacity flagged | `test_fix_numbers.py` |
| one electricity credit per kWh (export XOR import) | `test_geothermal_coupling.py` |
| JSON round-trip identical, numeric keys quoted | `test_json_format.py` |
| repository load/delete confined to its directory | `test_scenario_repository.py` |
| CO2 price file loaded, validated and editable | `test_co2_prices.py` |
| catalogue backup / validated restore | `test_database_backup.py` |
| candidate link added to a scenario | `test_add_link.py`, `test_database_tab.py` |
| hubs only, hub-to-hub links, save | `test_link_builder.py`, `test_database_tab.py` |
| filter / map tick / add & remove a hub | `test_hub_table.py` |
| every emitter reaches a storage site | `test_connectivity.py` |
| Scenario tab first, Database last | `test_database_tab.py` |

### 9.13 Emitter database (catalogue of candidate emitters)

A scenario models the emitters that *take part*; a study starts from the catalogue of
all candidate plants of a region.  The catalogue lives in `json/emitters.json` and is
read by `ccus_core/io/emitter_catalogue.py` (no UI imports, so any front end can use
it):

```json
{
  "id": "te-plomin",
  "name": "TE PLOMIN",
  "industry": "thermal power plant",
  "curve": {"kind": "power_law", "reference_year": 2025,
            "e0_t_per_year": 1118203.087, "a": -0.03, "c": 1.5, "b": -33546.09},
  "implementation_probability": 0.5,
  "activation_year": 2028,
  "reference_sink_id": "ivanic"
}
```

* `load_emitter_catalogue(path=None)` returns `EmitterRecord` objects in file order;
  `record.emissions_in(year)` evaluates the curve, `record.available_emissions(year)`
  applies the onboarding year.
* The bundled catalogue holds the **14 emitters of the workbook import** with their
  emission curves, implementation probability, start year and reference sink.  The
  industry type is not part of the workbook, so it was inferred from the plant names
  (TE → thermal power plant, TE-TO → cogeneration, *cementara* → cement works,
  *rafinerija* → oil refinery, …) and flagged with a `notes` entry where the name is
  not conclusive (`nexe`).
* The **Database** tab (the last tab) renders the catalogues as four *editable* tables -
  emitters, hubs, links, storage sites - with one **Save database** button. A row is added
  with the grid's `+` button, by pasting a block from Excel/LibreOffice Calc, or by deleting
  a row. The store is SQLite (`data/ccus.sqlite3`, rebuilt from the JSON snapshot when
  missing): integer auto-increment ids that the grid hides, a foreign key from a link to
  the two hubs it connects, unique slugs and checked vocabularies. Saving writes the
  database in one transaction and regenerates the JSON snapshot under `json/`, which is what
  the engine reads; the snapshot is the git-diffable artefact. Columns the table does not
  own (WGS84 coordinates, the derived length of a link, the emissions of a non-constant
  curve) are computed, so saving an untouched table is a no-op. Transport modes belong to
  the links, and a link's capacity is a result of the network calculation, not an input.
  Each transport mode has its own specifics table (`pipelines` today: diameter, wall
  thickness, roughness, material, design p/T) referenced by `links.pipeline_id`.
* The same pattern covers the other reference tables: `json/hubs.json` (candidate
  collection/booster hubs), `json/network.json` (candidate transport links with
  geometry) and `json/storage.json` (storage sites with geology), read and written by
  `ccus_core/io/catalogue.py` (`HubRecord`, `NetworkRecord`, `StorageRecord`) and stored by
  `ccus_core/io/sqlite_catalogue.py`.

### 9.14 CO2 price scenarios (`json/CO2_prices.json`)

The three price paths of the study (optimistic, conservative, pessimistic) were Python
constants, so a reviewer had to read `ccus_core/models/policy.py` to know what a tonne
of CO2 costs in 2035. They are now ordinary reviewed data: one price per year, in
`json/CO2_prices.json`, read by `ccus_core/io/co2_prices.py`.

```json
{
  "_meta": {"schema": "gt-ccus-co2-prices/1.0", "unit": "EUR/t CO2",
            "start_year": 2025, "years": 26, "scenarios": ["optimistic", "..."]},
  "years": [2025, 2026, "...", 2050],
  "scenarios": {
    "optimistic":   [63.64, 93.99, "..."],
    "conservative": [63.64, 68.08, "..."],
    "pessimistic":  [63.64, 42.59, "..."]
  }
}
```

* `load_price_scenarios(path=None)` returns `{name: Co2PriceScenario}`. A **missing**
  file falls back to the built-in workbook values (`DEFAULT_PRICE_SCENARIOS`), so a
  fresh checkout and every existing test behave exactly as before. A **malformed** file
  raises `Co2PriceFileError` - silently pricing a cluster with numbers nobody reviewed
  would be worse than stopping.
* The three presets must all be present, `years` must be sorted and unique, and every
  scenario needs exactly one price per year: `PricePath.mode` and
  `PolicyConfig.selected_price_scenario` only accept those three names.
* `GT_CCS_CO2_PRICES` points at a different file; `save_price_scenarios()` writes one
  back atomically (used by the tests and by any future editor).
* The models never read the file. The series is resolved once, in
  `ccus_core/io/commented_json.py`, while the document is still a plain dict, in two
  places:
  * `policy.prices` - filled when a scenario carries a `policy` block without prices;
  * `economics.price_path` - a preset without `values_eur_per_t`, so
    `"price_path": {"mode": "conservative"}` now works and takes its 26 values from the
    file instead of repeating them in every scenario.
* A scenario opts in by naming a preset. The bundled examples keep their explicit
  `price_path` (custom or with inline values) and are therefore **not** re-priced by the
  file, which is what keeps the legacy golden regression valid. Because the shipped
  series equals the model defaults, `dump()` still omits `policy` for the bundled
  scenarios; the prices appear in a saved scenario only after the file is edited.
* `test_co2_prices.py` covers the file, the fallback, the validation rules, the
  round-trip and a real run whose NPV moves when a price is doubled.

### 9.15 Backup and restore of the catalogue

`data/ccus.sqlite3` is git-ignored and holds every catalogue edit, and the JSON
snapshot is only regenerated when the Database tab saves.  Until this existed there was
no backup at all: the only way back was to delete the database and let it rebuild from
the snapshot, which loses every edit made after the last save.  `ccus_core/io/sqlite_catalogue.py`
therefore owns four functions, and the Database tab is a thin caller:

| Function | Purpose |
|---|---|
| `database_bytes(path=None)` | the raw file, for the download button |
| `inspect_database(data)` | validate an uploaded file before it is allowed anywhere near the live one |
| `backup_database(path=None, directory=None)` | timestamped copy into `data/backups/`, so a restore is itself reversible |
| `restore_database(data, path=None, backup=True)` | validate → copy aside → replace atomically → refresh the JSON snapshot |

A restore replaces *everything*, so `inspect_database` refuses anything that is not
unambiguously this application's catalogue: the SQLite signature, `PRAGMA integrity_check`,
every table in `REQUIRED_TABLES`, and a `schema_version` equal to `SCHEMA_VERSION`.  The
replacement is written to a temporary file in the same directory and moved into place, so
an interrupted restore cannot leave a half-written catalogue behind.  `test_database_backup.py`
covers the happy path, the three rejections and the "an invalid restore leaves the database
alone" invariant.

### 9.16 The Scenario tab: hubs, links and the map

A transport link belongs to one scenario, not to the study: two studies of the same
region rarely ship the same network.  The links are therefore edited in the **Scenario**
tab (the first one), which is ordered as the study is:

1. **Hubs** - the "who exists" table: a leading **on map** tick, id, name, kind,
   latitude, longitude and the number of links that touch each hub.  It is editable
   and filterable on any column; the filter is merged back, so what it hides is
   never deleted.  Ticking a hub off removes it from the map only; deleting its row
   removes the node, which is refused while a link, emitter, sink or geothermal
  system still uses it.
2. **Links** - the links table.  `from node` and `to node` are **selectboxes over
   the hubs that exist**, not free text: a link that names a hub the scenario does
   not have would create a phantom node.  A link is one *leg* of the chain - it
   joins two hubs - and each row can be removed with *Delete the selected link*.
   The **`total_distance_km`** column (next to `distance_km`) is the distance from
   the start of that leg to the selected storage site, this leg included; see
   §9.16.2 for the convention, the multi-sink expander and the typed override.
3. **Connections** - emitter → route → sink, the many-to-many access table the solver
   expands into directed edges.  It is edited here, next to the legs it points at,
   rather than in `Inputs`, so a study is wired up in one place: hubs → legs → who
   uses which leg.  All three selectors offer only what exists (emitters, the current
   links, storage sites), a blank route means a direct emitter-to-storage access, and
   the leading tick selects rows for *Delete selected (N)*.
4. **Add a link from the catalogue** - the bridge to the *candidate* catalogue, which
   stays in `Database`.  Each entry is labelled with both hubs, their category and
   country (`HR.CH.001 (chain, HR) → HRCH003 (chain) · pipeline · 27.06 km`), and a
   hub the scenario does not have is marked "new hub" - a bare `HRES002` tells the
   reader nothing.
5. **Draw a link on the map** - click *New link*, click the inlet hub, click the
   outlet hub.  Streamlit reruns per click: the first click stores the inlet and
   enlarges it, the second appends the row.  Chaining is left to the router, which
   already enumerates paths across several edges (A-B plus B-C carries A to C).
   The length starts as the great-circle estimate between the two hubs and stays
   editable, so a GIS measurement can replace it.
6. **Save links to the scenario** - validates the section through
   `frames_to_scenario` and writes the scenario file without running the chain.

The map draws **every link** of the section and says where each line came from:

| Source | When | Example |
|---|---|---|
| `route` | the link's two hubs match a route of `data/gis/routes.geojson` | 27.06 km surveyed polyline |
| `road` | mode *truck* - the OSRM demo server's driving geometry | 161 km of real road, cached |
| `straight` | everything else (rail, marine, or no match) | the direct line between the hubs |

Lines are **coloured by transport mode** (pipeline blue, truck orange, rail green,
marine violet) and a pipeline is drawn thicker than a lane of trucks, with a legend
under the chart. Two traps are worth recording:

* **Widths must be pixels, passed as a literal.** pydeck turns any Python string into
  a JS expression, so `line_width_units="pixels"` serialises as `@@=pixels`, evaluates
  to `undefined` and silently restores deck's default (metres, scaled by zoom) - which
  drew a 1.6 km link as a 400 px band across the whole chart. `pydeck.types.String`
  keeps it a literal. A test pins the difference.
* **A short link is invisible nationally.** Two hubs 2 km apart are half a pixel at
  zoom 6.4, so the map frames the pair it was just asked to connect
  (`_focus_view`: zoom 12 for a short hop, 6.4 for a long one, *Show all hubs* to go
  back). Measured on the rendered canvas, that link is now 97 px long, 9 px thick,
  horizontal.

The road lookup is a presentation detail in `streamlit_app/map_layers.py`, never in
`ccus_core`: it has a 6 s timeout, a module-level cache so a rerun never asks twice,
and a missing network simply falls back to the straight line. A link whose endpoint has
no WGS84 coordinates cannot be drawn at all - the map names those links instead of
leaving them out silently.

**The distance follows the line that is drawn.** A truck link with *Follow roads* on
stores the length of the road polyline (`road_length_km`, the sum of its segments), not
the crow-flies distance - the two differ by ~43 % on the Ivanić leg (172 km straight,
247 km by road) and the cost model charges per km. The flash message names the source
("by road" / "straight line") so the number is never ambiguous, and a pipeline link
always keeps the straight line unless the GIS has a surveyed route for that pair.

Both tables lead with a **tick column**.  On the hubs it is *on map* (a view
switch); on the links and the connections it is a plain **selection** - tick ten
rows, press *Delete selected (10)*, and ten rows go, exactly like a file manager.
All three have **Check all / Uncheck all**, so the whole table can be selected or
cleared in one click, and *Delete all links* stays as the one-action shortcut
behind a confirmation.  An empty links table is a legitimate state and says so.

A hub **without WGS84 coordinates cannot be shown and cannot be linked**: the tick is
forced off in the hub table, the hub is not offered as a link end, and a *new* hub
without latitude/longitude is refused outright. (An existing link that already targets
such a hub keeps its value, so the table never invalidates stored data.)

A **new scenario starts with an empty network** - the emitters and the sinks are the
brief, the links are what the study decides. Loading a saved scenario brings its links
back.

`Database` keeps the catalogue of *candidate* links - the reference table a scenario
is built from - alongside the emitters, hubs, pipelines and storage sites.

### 9.16.1 Is every emitter connected?

`ccus_core/network/connectivity.py` answers the question the solver can only answer
at the end: `unreachable_emitters(scenario)` walks the link graph from each emitter's
node and reports every emitter that reaches no storage site, with the reason ("no
link starts at X", "no path from X to a storage hub", "the scenario has no storage
sink").  The Scenario tab shows the report, and *Save links to the scenario* asks for a
single confirmation before writing a disconnected scenario - parking one mid-study is
legitimate, silently re-pricing one is not.

### 9.16.2 How far is the CO2 from the storage site?

`connectivity.py::distance_to_sinks(scenario)` runs a reverse Dijkstra from every
storage node over the directed link graph and returns
`{edge_id: {sink_id: km}}`.  The convention is the one the designer displays:

```
total(leg) = length(leg) + total(next leg towards the sink)
```

so a chain `emitter → L2 → L3 → sink` reports `d(L1)+d(L2)+d(L3)` on the first leg,
`d(L2)+d(L3)` on the second, and `d(L3)` on the leg that enters the sink - the first
leg therefore carries the full emitter → storage distance.  A leg with **no directed
path** to a sink is *absent* from the mapping rather than reported as zero: "no path"
and "zero distance" are different statements.  A bidirectional leg reports the cheaper
of its two directions, because CO2 may enter it either way.

Two storage sites are never collapsed into an average: the Scenario tab measures
against the site selected in *Measure the distance to* (default: the sink the most
connections point at) and lists every other reachable site in an expander.
`TransportEdge.total_distance_km` stores what the designer wrote - calculated, or a
typed override - and the solver never reads it, so the annotation cannot move a KPI
(`test_designer_connections.py::test_the_distance_column_never_moves_the_physics`).

The map uses a `ScatterplotLayer` for the hubs rather than a `GeoJsonLayer`: its
radius is a real pixel size and its picking is what
`st.pydeck_chart(on_select="rerun")` reports back.  Every layer declares an `id`,
because the selection is keyed by layer; the hub layer's data carries the node id, so
a click maps straight back to a hub.  A hub without WGS84 coordinates is left out of
the map entirely rather than drawn at `0, 0`.

### 9.17 From a candidate link to a scenario link

The two levels are bridged by **Add a link from the catalogue** in the Scenario tab:

1. `_candidate_links(routes)` lists the catalogue links whose (source, destination, mode)
   triple is not in the scenario yet, each with a readable label.
2. `route_row_from_candidate(...)` turns the chosen one into a `ROUTE_COLUMNS` row:
   the id is a slug of `source-destination-mode`, suffixed `-2`, `-3`, … while it is
   taken; `valid_from_year` is the start of the horizon; CAPEX/OPEX and the length come
   from the catalogue.
3. The row is appended to `frames["routes"]`, so the links table and the map show it at
   once and a **connection** can route an emitter through it.

The capacity is the one thing the catalogue cannot supply, and a pipeline state without
an explicit capacity is refused by `EdgeState.effective_capacity_t_per_year`. The new row
therefore gets `_suggested_capacity()` - the peak captured mass over the horizon, with a
1000 t/yr floor - and the user corrects it in the table. `test_add_link.py` covers the
row, the id collisions, Apply, and the empty-scenario floor; `test_database_tab.py`
covers the button itself and a full Apply-and-run afterwards.

## 10. What is deliberately not done yet

* monthly resolution (the solver is yearly; `ScenarioConfig.step` accepts `monthly`
  but no solver consumes it yet);
* transient thermal breakthrough in the annual geothermal estimate;
* stochastic weather downtime (deterministic availability factor only);
* offshore injection wells and their BHP limits (the offshore sink is capacity-only
  until a reservoir is attached);
* a full UI rewrite of `app.py`: the legacy app remains the reference UI, the new
  `streamlit_app/` is the target.