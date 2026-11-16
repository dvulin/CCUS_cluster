# Skill – CCUS cluster app (GT-CCUS-graph-streamlit)

**Purpose.** Build and maintain the UI-agnostic CCUS engine (`ccus_core`) and its
Streamlit front end (`streamlit_app`).  Source: <https://github.com/dvulin/CCUS_cluster>
(branch `gt-ccs-streamlit` upstream; work happens on local `GT-CCUS-graph-streamlit`).

## 1. Layout

```
ccus_cluster/
├── ccus_core/            # engine: models/ network/ simulation/ finance/ io/ engine.py
├── engineering/          # legacy physics (MaterialBalance, VFP, Geothermal, Power, Pipeline)
├── economics/            # audited cash-flow runner (CashFlowRunner)
├── inputs/examples/      # scenarios (compact JSON) – the stored inputs
├── streamlit_app/        # app.py + i18n.py (UI only, imports ccus_core)
├── tests/                # pytest suite (no UI required)
└── docs/                 # ARCHITECTURE_ccus_core.md, whitepaper/
```

Layering rule: `engineering`/`economics` are imported **by** `ccus_core`, never the
reverse; `ccus_core` never imports Streamlit/matplotlib/tkinter/xlwings.

## 2. Commands

```powershell
$py = 'C:\Users\dvulin\anaconda3\python.exe'
& $py -m pytest tests -q              # fast suite
& $py -m pytest tests -q --runslow    # + legacy golden regression
& $py -m streamlit run streamlit_app/app.py     # → http://localhost:8501
& $py docs\whitepaper\build_whitepaper.py       # regenerate the whitepaper
```

## 3. Model cheat-sheet

| Concept | Where | Notes |
|---|---|---|
| Scenario document | `models/scenario.py` | root; `start_year`, `end_year`, `nodes`, `emitters`, `edges`, `connections`, `storage_sinks`, `geothermal_systems`, `economics`, `policy` |
| Emission curve | `models/emitter.py` | `constant`, `piecewise_linear`, `power_law` (`E0 + b·(t−t₀)^c`, `b=a·E0`), `polynomial` |
| Onboarding | `models/emitter.py` | `activation_year` or `implementation_probability` (1.0→2026, 0.5→2028, 0.1→2033) |
| Transport state | `models/edge.py` | `EdgeState` per year window; `resolve_state(year, cumulative_mass_t, fired_upgrades)` |
| Upgrades | `models/edge.py` | `InfrastructureUpgrade` with `year` and/or `cumulative_mass` trigger + lead time |
| Sinks | `models/sink.py` | `StorageSink` (+`ReservoirProperties`, defaults φ=0.20, k=100 mD, 1500 m), `geothermal_coupled`, `geothermal_start_year` |
| Policy | `models/policy.py` | EU ETS phase-out, three CO2 price paths, capture/transport/storage unit costs, Fisher relation |
| Connections | `models/connection.py` | many-to-many emitter→sink access with its own `start_year` |

## 4. Solver pipeline (year loop)

`simulation/solver.py::ChronologicalSolver.run()`:

1. emitters → captured mass (curve × capture capacity);
2. `network/routing.py` → cheapest feasible path under edge/sink capacities,
   leftovers reported as `unallocated`;
3. `simulation/reservoir.py::VariableRateReservoir` inverts `m_CO2(p)` (no physics change)
   and recomputes BHP at the *local* rate;
4. `simulation/geothermal.py` evaluates the doublet at **that year's pressure**;
5. `finance/cashflow.py` builds the `CashFlowRunner` config (CAPEX schedules, modal OPEX);
6. `finance/stakeholders.py` splits the same flows per party (emitter, transport, storage, geothermal).

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
plus `connections` rows that point at it.

**Add a transport mode** – extend `TransportMode` + `EdgeState` design (pipeline/road/marine)
and the cost rules in `finance/cashflow.py`.

**Add a hub/booster** *(planned)* – new node kind `hub` with a booster station and a
backward pressure cascade (see §7).

## 7. Known gaps (do not promise these)

* booster/**hub** nodes and per-node pressure cascade (emitter must deliver the pressure
  required by the next hub so that the storage arrives above the 10 bar minimum);
* monthly resolution (`step` is validated but only `yearly` is solved);
* real coordinates / true connectivity for the map (schematic today);
* DHF reservoir data for Ivanić / Stružec / Boksic (capacity-only sinks);
* transient thermal breakthrough and stochastic weather downtime.

## 8. Verification checklist

```powershell
& $py -m pytest tests -q --runslow     # 85 tests, ~15 s
& $py -m streamlit run streamlit_app/app.py   # then: Apply → timeline → tabs
```

Golden baseline (legacy `ScenarioRunner`): 9.10 Mt stored, 276.0935 bar final pressure,
NPV −481.6 M€ — if these move, the physics changed.