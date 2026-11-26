---
name: ccus-ui-tester
description: Test the GT-CCUS Streamlit calculator (streamlit_app/app.py) together with a human tester. Preflights every tool, starts the app in an isolated scenario folder, drives or guides the browser through scripted stories, compares what the UI shows with engine reference values and invariants, and writes a dated test report.
whenToUse: The user asks to test, check, verify, demo or accept the CCUS / GT-CCS Streamlit UI, run UI test stories, compare UI numbers with the ccus_core engine, reproduce a UI bug, or prepare a UI test report.
---

# ccus-ui-tester – human-in-the-loop UI testing for the CCUS cluster app

You test the **presentation layer** of the project: the Streamlit app in
`streamlit_app/app.py`, which sits on the UI-agnostic engine `ccus_core`. Engine numbers
are checked by scripts (the *oracle*); your job in the browser is to confirm that what a
person enters reaches the engine and that what the engine returns is shown faithfully,
understandably and without errors.

`<SKILL_DIR>` below means the folder this SKILL.md was loaded from (DSH reports it as the
skill's resource base). `<PROJECT>` is the project root, the folder that contains
`ccus_core/` and `streamlit_app/` (default `C:\sestan_test_app\gt-ccus-graph-streamlit`).

## Golden rules

1. **Never edit source code, example inputs or saved scenarios.** You only create files
   under `<PROJECT>\test-reports\ui\`. Report defects; do not fix them.
2. **Isolate.** Always start the app with `scripts/start_app.py`; it points
   `GT_CCS_SCENARIO_DIRECTORY` to `test-reports\ui\scenarios`, so Save/Delete in the UI
   cannot touch `inputs\scenarios`. Never use the UI Delete button on a name that also
   exists as a file in `<PROJECT>` (known issue K12 deletes the wrong file).
3. **The human decides.** Follow `MASTERPROMPT.md` (in this folder): announce each step,
   ask at every checkpoint, never guess a visual judgment the human should make.
4. **Evidence for every verdict:** expected value (oracle or story), observed value
   (snapshot text or human answer), screenshot path when relevant.
5. **Known vs new.** Compare every failure with `references/known-issues.md`; tag it
   `K..` or mark it `NEW`.

## Tools (full inventory with versions and check commands: `references/tools.md`)

| Tool | Where | Used for |
|---|---|---|
| Python 3.10+ with the project packages | default `%USERPROFILE%\anaconda3\python.exe` (reference 3.11.5) | scripts, Streamlit, engine |
| Streamlit | `& $py -m streamlit` (always `-m`, from `<PROJECT>`) | the app under test |
| Node.js + npx | on PATH; DSH needs `^22.19.0 \|\| >=24` | DSH runtime, Playwright MCP |
| Playwright MCP `@playwright/mcp@0.0.85` | mounted by this plugin as server `ccus-browser` | browser automation: tools `mcp__ccus-browser__browser_*` |
| Microsoft Edge | preinstalled on Windows 11 | browser used by Playwright MCP (`--browser msedge`) |
| PowerShell | Windows PowerShell 5.1 or 7 | shell used by DSH on Windows |

### Scripts (`<SKILL_DIR>\scripts\`, configuration in `tester_config.json`)

| Script | What it does | Output |
|---|---|---|
| `preflight.py [--run]` | checks Python, packages, project files, example scenarios, Node/npx, Edge, port | `test-reports\ui\preflight.json` |
| `make_inputs.py` | writes valid, small and broken JSON inputs for the stories | `test-reports\ui\inputs\*.json` |
| `oracle.py [--scenario X] [--year Y]` | runs the engine; prints the UI strings to expect and invariants I01–I10, W01–W03 | `test-reports\ui\oracle_<X>.json` |
| `apptest_runner.py [--only A0n]` | headless UI checks A01–A08 with Streamlit AppTest (no browser, ~30 s) | `test-reports\ui\apptest_<time>.md/.json` |
| `start_app.py [--fresh] [--port N]` | starts the app headless on 8501, isolated, waits for health | `test-reports\ui\app_state.json`, `streamlit.log` |
| `stop_app.py` | stops the app started by `start_app.py` | – |
| `run_headless.ps1` | preflight → make_inputs → oracle → AppTest in one go | all of the above |

Command pattern (PowerShell, working directory `<PROJECT>`):

```powershell
$py = "$env:USERPROFILE\anaconda3\python.exe"     # or the path preflight reported
& $py "<SKILL_DIR>\scripts\preflight.py" --run
```

## Workflow

1. **Agree the session with the human** (MASTERPROMPT §2): mode A (you drive the
   browser), mode B (human drives, you guide) or mixed; which stories; language HR/EN.
2. **Preflight:** `preflight.py --run`. Stop on any `[FAIL]` and tell the human the exact
   fix command printed next to it.
3. **Reference values:** `make_inputs.py`, then `oracle.py` (all scenarios, or
   `--scenario cluster --year <slider year>` for the year you will look at). Keep the
   printed `UI <year>:` lines and economics strings at hand: these are the expected UI texts.
4. **Headless pass (optional but fast):** `apptest_runner.py`. Anything it already shows
   need not be repeated by hand; the human stories then focus on what AppTest cannot see
   (layout, charts, wording, real mouse/keyboard behaviour, file dialogs).
5. **Start the app:** `start_app.py --fresh`; open the printed URL
   (`http://localhost:8501`) with `mcp__ccus-browser__browser_navigate`, or ask the human
   to open it.
6. **Run the stories** in `stories/` (index below) step by step with the human.
7. **Report:** fill `references/report-template.md` into
   `test-reports\ui\report_<YYYYMMDD_HHMM>.md`; attach screenshots from
   `test-reports\ui\playwright\`.
8. **Clean up:** `stop_app.py`. Leave all reports in place.

## Driving Streamlit with Playwright MCP (mode A)

* Start every page interaction with `browser_snapshot`; act on element references from
  the latest snapshot only (they change after every Streamlit rerun).
* After a click that triggers a rerun (Pokreni/Run, Primijeni i pokreni/Apply and run,
  Spremi/Save, Učitaj/Load, slider, language), wait: `browser_wait_for` with
  `textGone` = `Running...` or, simpler, `time` = 3, then snapshot again.
* Widgets are found by accessible name (labels in `references/ui-map.md`): radio
  "Izvor/Source", buttons "Pokreni/Run", "Primijeni i pokreni/Apply and run", slider
  "Vremenska os/Timeline", tabs "Ulazi … Tablice".
* **File upload:** select source "Učitaj JSON/Upload JSON", click "Browse files", then
  `browser_file_upload` with an **absolute** path under `<PROJECT>`
  (e.g. `<PROJECT>\test-reports\ui\inputs\valid_croatia.json`). Playwright MCP only reads
  files under its workspace root (the DSH working directory). After the upload, click
  "Učitaj scenarij/Load scenario" (known issue K21: tables do not refresh by themselves).
* **Editable tables** (st.data_editor, a canvas grid with an accessible row structure):
  click the cell, type the value, press Enter, then confirm in a snapshot that the cell
  text changed. If the cell cannot be reached, switch that step to mode B (ask the human
  to edit it) or upload a prepared JSON instead. Never type into the grid blind.
* **Metrics** are read from the snapshot text (label followed by value, e.g.
  `NPV (EUR) -919,875,061`). Overview metrics depend on the slider year: set the slider
  first (focus it, then `browser_press_key` ArrowRight/End) and compare with the oracle
  line for that year.
* **Charts** (matplotlib map and pie, Streamlit line/bar charts) are images or canvas: take
  `browser_take_screenshot` and ask the human for the visual judgment.
* Red error boxes (`stAlertContainer`) and Python tracebacks (`stException`) are always
  findings; copy their text into the report.

## Stories (`stories/`)

| ID | Story | Typical duration |
|---|---|---|
| S01 | Load the default scenario and run it; numbers match the oracle | 5 min |
| S02 | "Apply and run" without edits must not change results | 5 min |
| S03 | Edit tables (emitter, connection, sink) and see the effect | 10 min |
| S04 | Save → list → load → (no delete) in the isolated folder | 5 min |
| S05 | Upload JSON (valid, small) and switch sources | 5 min |
| S06 | Language switch HR ↔ EN: labels change, numbers and state do not | 5 min |
| S07 | Invalid inputs and error messages | 10 min |
| S08 | Timeline, tabs, charts, download: readability and consistency | 10 min |

## References

* `MASTERPROMPT.md` – session protocol for any AI model with a human tester.
* `references/tools.md` – every tool, path, version, install and check command.
* `references/ui-map.md` – sidebar, tabs, tables, labels (HR/EN), what the UI can and cannot edit.
* `references/invariants.md` – oracle checks, tolerances and what each failure means.
* `references/known-issues.md` – K01–K21 from the code review, with the story that exposes each.
* `references/report-template.md` – report layout and severity scale.
