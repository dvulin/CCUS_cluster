# GT-CCUS — CO₂ cluster calculator

A Python engine and a Streamlit calculator for techno-economic CO₂ cluster studies:
capture, transport by pipeline, truck, rail or ship, injection and geological storage,
with a geothermal doublet, a hub pressure cascade and a cash-flow model that reports
consolidated **and** per-stakeholder NPV/IRR.

The repository holds two entry points:

| Entry point | What it is |
|---|---|
| [`streamlit_app/app.py`](streamlit_app/app.py) | **The calculator.** Scenario designer (hubs, links, connections), input tables, result tabs and the reference-data catalogue. |
| [`app.py`](app.py) | **The original single-chain demo.** Kept runnable and used as the reference the golden regression compares against. |

![CI](https://github.com/dvulin/CCUS_cluster/actions/workflows/ci.yml/badge.svg?branch=gt-ccs-streamlit)

---

## Requirements

* Python 3.11 or newer
* Node.js 18+ — only for the optional architecture map ([Floorplan](#floorplan-architecture-map))

## Install

```powershell
cd C:\Users\dvulin\Documents\DSH\sestan_diplomski\ccus_cluster
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run the calculator

```powershell
python -m streamlit run streamlit_app\app.py
```

Then open <http://localhost:8501>.

Use `python -m streamlit` rather than the `streamlit.exe` shim: with `-m` the
repository root is on the import path, so `ccus_core` resolves. The first tab,
**Scenario**, is the designer — hubs → links → connections → *Save links to the
scenario*.

## Run the tests

```powershell
pytest tests -q --runslow
```

345 tests, about 80 seconds. `--runslow` is required: the golden regression and the
AppTest smoke checks are marked slow.

**Golden baseline** (legacy demo, 2027–2050): 9.10 Mt stored, 276.0935 bar final
storage pressure, NPV −481.6 M€. If those move, the physics changed.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) installs the dependencies and
runs the full suite on every push to `main`, `gt-ccs-streamlit` and
`GT-CCUS-graph-streamlit`, and on every pull request. The badge above reflects the
latest run on `gt-ccs-streamlit`.

## Layout

```
ccus_core/          the engine — models, network, simulation, finance, io, geo
  models/           Pydantic scenario document (no I/O, no UI, no solver)
  network/          graph, routing, hub pressure cascade, connectivity, distance
  simulation/       solver, variable-rate reservoir, geothermal, pressure table
  finance/          cash-flow adapter, per-stakeholder statements
  io/               commented JSON, named scenarios, SQLite catalogue, CO2 prices
  geo/              EPSG:3765, EP/TF route parsing, distances
  engine.py         ScenarioEngine: JSON in → SimulationResult out
streamlit_app/      app.py, i18n.py, map_layers.py (UI only)
engineering/        legacy physics, imported by ccus_core
economics/          audited cash-flow model, imported by ccus_core
services/           the legacy demo runner (ScenarioRunner)
inputs/, outputs/   the legacy demo's scenario store and result exports
json/               the committed snapshot the engine reads
data/gis/           extracted GIS routes and hubs (read-only)
data/ccus.sqlite3   the live catalogue (git-ignored, rebuilt from json/)
tests/              pytest suite, including the legacy golden regression
docs/               ARCHITECTURE_ccus_core.md, SKILL_ccus_app.md
floorplan/          generated architecture map (git-ignored, see below)
```

`ccus_core` never imports a UI toolkit, and `models/` imports neither pandas nor the
solver. `engineering/` and `economics/` are imported **by** `ccus_core`, never the
reverse.

## Reference data: catalogue and snapshot

* `data/ccus.sqlite3` — the live catalogue of candidate emitters, hubs, transport
  links, pipeline designs and storage sites. **Git-ignored.**
* `json/*.json` — the git-diffable snapshot the engine reads. **Committed.**
* Every successful *Save database* writes SQLite in one transaction and then
  regenerates the snapshot. Deleting the database and reopening the app rebuilds an
  identical catalogue from the snapshot.
* The **Database** tab can download the whole file as `gt_ccus_db.sqlite` and restore
  it later; a restore copies the current database into `data/backups/` first, so it
  can always be undone.

A scenario is **not** stored in the database: it is a JSON document under
`inputs/scenarios/`.

## Floorplan (architecture map)

`floorplan/` holds an interactive map of the codebase — every part, file and screen
with a plain-language name and a one-line description. It is **generated and kept out
of git** (the folder carries its own `.gitignore`), so a fresh clone has no map until
it is generated.

**Generate or update it** — run the `floorplan` skill in your coding agent
(`/floorplan` in Claude Code, `$floorplan` in Codex), or ask for the floorplan to be
made or updated. The agent writes `floorplan/architecture.json` and
`floorplan/descriptions/*.json`; `graph.json` and `index.html` are generated from
them.

**Show it** (needs Node.js 18+), from the repository root:

```powershell
node floorplan\serve.mjs
```

It prints the address (default <http://127.0.0.1:4378>, or the next free port) and
opens your browser. The **Ask** bar answers questions about the code through the
Claude Code or Codex CLI installed on the machine.

| Task | Command |
|---|---|
| Show the map | `node floorplan\serve.mjs` |
| Print the address without opening a browser | `node floorplan\serve.mjs --no-open` |
| Stop the server | `node floorplan\serve.mjs --stop` |
| Open the static map only (no Ask bar) | `start floorplan\index.html` |
| Re-scan after code changes | `node <skill>\scripts\refresh.mjs .` |

The server stops itself two hours after the last tab closes. The map is a snapshot:
after changing code, re-scan (or ask for an update) and open tabs reload in place.

## Scope

Monthly solver steps, transient thermal breakthrough, stochastic downtime, offshore
wells, a redesign of the Streamlit shell, GIS/OSM publishing and anything that changes
the physics or the audited cash flow are out of scope. GIS data is read-only; no
network access is needed for the analysis — the basemap tiles and the optional OSRM
road lookup are the only online elements.

## Licence

See [LICENSE](LICENSE).