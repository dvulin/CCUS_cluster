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
ccus_core/models/         Pydantic models    -> no I/O at all
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
| `TransportEdge` | ordered state timeline plus conditional `InfrastructureUpgrade`s |
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

* CAPEX is placed with `capex_schedule_eur` (per-year map), which is how upgrade
  CAPEX (truck → pipeline) enters the cash flow;
* transport OPEX follows the routed modal cost of each year;
* inflation escalation, discounting, cumulative NPV, IRR and the without-CCS
  counterfactual are computed by the audited `CashFlowRunner`.

## 7. Solver output

`SimulationResult` holds:

| Attribute | Content |
|---|---|
| `routing` | `list[RoutingResult]` – one per year (allocations, edge flows, sink injections) |
| `reservoir` | `{sink_id: DataFrame}` – annual pressure, saturation, BHP |
| `geothermal` | `{system_id: DataFrame}` – annual flow, ORC/pump power |
| `ledger` | annual technical ledger consumed by the cash-flow model |
| `cash_flow` | annual cash flow with NPV/IRR columns |
| `kpis` | stored/routed/unallocated CO2, NPV, IRR, PV revenues and costs |
| `to_dict()` | JSON-safe summary (used by external state managers) |

`year_snapshot(result, year)` returns the per-year view consumed by the timeline
slider and the map.

## 8. Tests

```
pytest tests -q              # 42 tests, < 10 s
pytest tests -q --runslow    # adds the legacy ScenarioRunner golden regression
```

| File | Covers |
|---|---|
| `test_emitter_model.py` | staggered onboarding, ramp/decline, capture limits, validation |
| `test_edge_model.py` | truck→pipeline switch, tariff switch, lead time, mass trigger, marine/road capacity |
| `test_routing.py` | undersized edge, mid-run upgrade, offshore bottleneck, multi-hop tariff, sink exhaustion |
| `test_scenario_model.py` | graph validation, duplicate ids, price paths, cash-flow config mapping |
| `test_solver.py` | physics equivalence with the legacy model, end-to-end run, timeline snapshot, example JSON |
| `test_app_layer.py` | UI data functions only (no Streamlit import) |
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
Defaults are omitted (`exclude_defaults=True`) and derived `edges` are not
written when `connections` are present — they are rebuilt on load. The loader
still accepts plain JSON and the older `style="verbose"` records
(`value`/`unit`/`comment` per leaf), which remain available for archival. regenerate the annotated form; the unit and comment columns come
from `FIELD_METADATA`.

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

`ccus_core.finance.stakeholders` splits the same physical flows into per-party
statements (emitter, transport operator, storage operator, geothermal operator):

* the emitter pays the transport tariff of every arc it uses and the injection
  tariff of its sink;
* the transport operator collects the transport tariffs and carries the edge
  CAPEX/OPEX;
* the storage operator collects the injection tariffs and carries CAPEX/OPEX and
  monitoring;
* the geothermal operator carries CAPEX/OPEX and earns the net electricity result.

Tariffs are cost-reflective by default (no margin), so every transfer cancels on
consolidation and the sum of the stakeholder statements reconciles with the
consolidated cash flow. ``stakeholder_summary()`` returns ``year × stakeholder →
net_cash_flow_eur``.

### 9.8 Simultaneous geothermal and CO2 storage

Every storage sink carries ``geothermal_coupled``.  When the flag is set, the
solver/UI ensures a doublet exists for that site (a default one is created when no
explicit ``GeothermalSystem`` is defined), so the storage pressure produced by CO2
injection drives the geothermal balance in the same year.

### 9.9 Named scenarios and geothermal start year

`ccus_core.io.scenario_repository` stores whole scenarios as ``<name>.json`` in
``inputs/scenarios`` (overridable with ``GT_CCS_SCENARIO_DIRECTORY``):
``next_default_name()`` proposes ``scenario_001``, ``scenario_002``, …, names are
validated, writes are atomic and an existing name is never overwritten unless
``overwrite=True``.

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

## 10. What is deliberately not done yet

* monthly resolution (the solver is yearly; `ScenarioConfig.step` accepts `monthly`
  but no solver consumes it yet);
* transient thermal breakthrough in the annual geothermal estimate;
* stochastic weather downtime (deterministic availability factor only);
* offshore injection wells and their BHP limits (the offshore sink is capacity-only
  until a reservoir is attached);
* a full UI rewrite of `app.py`: the legacy app remains the reference UI, the new
  `streamlit_app/` is the target.