# Tool inventory – ccus-ui-tester

Every tool the UI test session uses, where it lives, which version it was built against,
and the one-line command that proves it works. `preflight.py` runs all the checks marked
**(preflight)** automatically.

Paths assume Windows 11 and PowerShell. `<PROJECT>` = `C:\sestan_test_app\gt-ccus-graph-streamlit`
(override with `--project` or the environment variable `CCUS_PROJECT_ROOT`).
`<SKILL_DIR>` = the folder that contains this skill's `SKILL.md`.

## 1. Python environment

| Item | Value | Check |
|---|---|---|
| Interpreter | `%USERPROFILE%\anaconda3\python.exe` (Anaconda base; reference 3.11.5; minimum 3.10) | `& $py --version` **(preflight)** |
| Set once per shell | `$py = "$env:USERPROFILE\anaconda3\python.exe"` | – |
| pip | `& $py -m pip` | `& $py -m pip --version` |
| UTF-8 console | `$env:PYTHONUTF8 = "1"` (set by `run_headless.ps1` and `start_app.py`) | – |

If the project uses another environment (venv, conda env), put its `python.exe` into
`scripts\tester_config.json` → `"python"` and use the same path for `$py`.

### Required packages **(preflight)**

| Package | Minimum | Reference | Install |
|---|---|---|---|
| streamlit | 1.40 | 1.67.0 | `& $py -m pip install "streamlit>=1.40"` |
| pandas | 2.0 | – | `& $py -m pip install pandas` |
| numpy | 1.24 | – | `& $py -m pip install numpy` |
| scipy | 1.10 | – | `& $py -m pip install scipy` |
| pydantic | 2.0 | 2.x | `& $py -m pip install "pydantic>=2"` |
| CoolProp | 6.4 | – | `& $py -m pip install CoolProp` |
| matplotlib | 3.7 | – | `& $py -m pip install matplotlib` |
| openpyxl | 3.1 | – | `& $py -m pip install openpyxl` |

All of them are listed in `<PROJECT>\requirements.txt`: `& $py -m pip install -r requirements.txt`.

### Optional packages

| Package | Purpose | Install |
|---|---|---|
| pytest (reference 9.2.0) | project test suite `& $py -m pytest tests -q` | `& $py -m pip install pytest` |
| pytest-playwright | scripted browser tests (not needed for the agent) | `& $py -m pip install pytest-playwright; & $py -m playwright install chromium` |

## 2. The application under test

| Item | Value |
|---|---|
| Entry point | `<PROJECT>\streamlit_app\app.py` |
| Start (managed) | `& $py "<SKILL_DIR>\scripts\start_app.py" --fresh` |
| Start (manual) | `cd <PROJECT>; & $py -m streamlit run streamlit_app/app.py --server.port 8501 --server.headless true` |
| URL | `http://localhost:8501` (health: `http://localhost:8501/_stcore/health` → `ok`) |
| Stop | `& $py "<SKILL_DIR>\scripts\stop_app.py"` |
| Log | `<PROJECT>\test-reports\ui\streamlit.log` |

Always start with `python -m streamlit` from `<PROJECT>`: `-m` puts the project folder on
`sys.path`, otherwise `import ccus_core` fails inside the app.

### Environment variables

| Variable | Set by | Meaning |
|---|---|---|
| `GT_CCS_SCENARIO_DIRECTORY` | `start_app.py`, `apptest_runner.py` | folder for Save/Load/Delete in the UI; tests use `<PROJECT>\test-reports\ui\scenarios` |
| `CCUS_PROJECT_ROOT` | you (optional) | project root when scripts are run from elsewhere |
| `PYTHONUTF8`, `PYTHONIOENCODING` | scripts | Croatian characters in console and logs |

## 3. Node.js, DeepSeek Harness and the browser

| Item | Value | Check |
|---|---|---|
| Node.js | `^22.19.0 \|\| >=24.0.0` (DSH requirement; Playwright MCP needs ≥18) | `node --version` **(preflight)** |
| npx | ships with Node.js | `npx --version` **(preflight)** |
| DeepSeek Harness | `@deepseek-ai/dsh` (built against 0.2.2-rc.1); Web UI `npx @deepseek-ai/dsh web` → `http://127.0.0.1:3080` | `npx @deepseek-ai/dsh --version` |
| DSH home | `%USERPROFILE%\.dsh` (user skills in `.dsh\skills`) | `dir $env:USERPROFILE\.dsh` |
| Playwright MCP | `@playwright/mcp@0.0.85`, mounted by `cordis.patch.yml` as server `ccus-browser` | `npx -y @playwright/mcp@0.0.85 --help` |
| Browser | Microsoft Edge (`--browser msedge`), `%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe` | **(preflight)** |

### Playwright MCP settings used by the plugin

```
npx -y @playwright/mcp@0.0.85 --browser msedge --isolated --viewport-size 1600x1000
    --output-dir test-reports/ui/playwright --console-level warning --timeout-action 15000
```

* `--isolated` – fresh in-memory browser profile per session (no cookies or cache carry over).
* `--output-dir` – screenshots and saved snapshots land in `<PROJECT>\test-reports\ui\playwright`
  when DSH runs in `<PROJECT>`.
* Uploads (`browser_file_upload`) only read files under the workspace root (the DSH working
  directory); keep inputs in `<PROJECT>\test-reports\ui\inputs`.
* Without Edge: replace `msedge` by `chrome`, or remove `--browser` and run
  `npx playwright install chromium` once.

### Browser tools the agent uses (server `ccus-browser`)

| Tool | Use |
|---|---|
| `mcp__ccus-browser__browser_navigate` | open `http://localhost:8501` |
| `mcp__ccus-browser__browser_snapshot` | read the page as an accessibility tree (labels, values, element refs) |
| `mcp__ccus-browser__browser_click` | buttons, tabs, radio options, table cells |
| `mcp__ccus-browser__browser_type` / `browser_press_key` | text inputs, numbers, table cells, slider keys |
| `mcp__ccus-browser__browser_select_option` | dropdowns when exposed as native selects |
| `mcp__ccus-browser__browser_file_upload` | JSON upload after clicking "Browse files" |
| `mcp__ccus-browser__browser_wait_for` | wait for text to appear/disappear or for N seconds |
| `mcp__ccus-browser__browser_take_screenshot` | evidence and visual checks |
| `mcp__ccus-browser__browser_console_messages` | front-end errors |
| `mcp__ccus-browser__browser_find` | search the snapshot text (e.g. "NPV") |

## 4. Project scripts (relative to the project root)

| Path | Used for |
|---|---|
| `streamlit_app/app.py` | app under test |
| `streamlit_app/i18n.py` | all HR/EN labels (source of truth for `ui-map.md`) |
| `ccus_core/engine.py` | `ScenarioEngine`, `year_snapshot` (used by the oracle) |
| `ccus_core/io/commented_json.py` | load/dump of scenario JSON |
| `ccus_core/io/scenario_repository.py` | Save/Load/Delete behind the sidebar |
| `inputs/examples/cluster_three_emitters.json` | default source "Klaster" |
| `inputs/examples/ccus_cluster_v1.json` | source "Jedan lanac (legacy)" |
| `inputs/examples/croatia_cluster_2025_2050.json` | 14-emitter upload test |
| `tests/test_app_smoke.py` | existing AppTest smoke test |

## 5. Skill scripts (`<SKILL_DIR>\scripts\`)

| Script | Purpose |
|---|---|
| `tester_config.json` | paths, port, scenario aliases, tolerances (edit here, not in the scripts) |
| `_common.py` | shared helpers: project root discovery, report folders, quiet engine runs |
| `preflight.py` | environment check |
| `make_inputs.py` | test input files |
| `oracle.py` | expected UI values and invariants |
| `apptest_runner.py` | headless UI checks A01–A08 |
| `start_app.py` / `stop_app.py` | isolated app lifecycle |
| `run_headless.ps1` | one-command headless pass |

## 6. Outputs (all under `<PROJECT>\test-reports\ui\`)

| File / folder | Content |
|---|---|
| `preflight.json` | environment check results |
| `oracle_<scenario>.json` | KPIs, expected UI strings, invariant results |
| `apptest_<time>.md/.json` | headless check results |
| `inputs\` | generated test inputs |
| `scenarios\` | scenarios saved from the UI during tests |
| `playwright\` | screenshots and snapshots from the browser |
| `streamlit.log`, `app_state.json` | app log and process state |
| `report_<time>.md` | the session report (written by the agent) |

Consider adding `test-reports/` to `.gitignore`.
