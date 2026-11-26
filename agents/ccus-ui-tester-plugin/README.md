# CCUS UI tester – DSH bundle

Installs two rows into the current DSH profile so the `ccus-ui-tester` skill can do
its job:

| Row | Package | What it provides |
|---|---|---|
| `ccus-browser` | `@deepseek-ai/dsh-mcp-client` | Playwright MCP server `ccus-browser` → tools `mcp__ccus-browser__browser_*` (Edge, isolated profile) |
| `skill-ccus-ui-tester` | `@deepseek-ai/dsh-skill-filesystem` | second local skill root at rank 300 (custom) pointing to `skills/` in this bundle, so the skill is discovered without copying it into `~/.dsh/skills` |

Registering a second `@deepseek-ai/dsh-skill-filesystem` row is supported: each row
uses its own `providerName` and the registry merges the roots, so the shipped
`filesystem` provider (project and user skills) keeps working unchanged.

The skill itself (`SKILL.md`, `MASTERPROMPT.md`, `references/`, `stories/`, `scripts/`)
lives in `skills/ccus-ui-tester/` inside this bundle. It is a copy of the authored
original in `agents/ccus-ui-tester`, which stays the source of truth:

```powershell
robocopy "<repo>\agents\ccus-ui-tester" "<this bundle>\skills\ccus-ui-tester" /MIR
```

Re-copy after editing the original; skill bodies are re-read on every load, so no
restart is needed for body edits (the bundle's patch file itself is unchanged).

## Launch conditions

* **Working directory.** Run DSH with the CCUS project root (the folder holding
  `ccus_core/` and `streamlit_app/`) as its working directory: `browser_file_upload`
  only reads files under the DSH working directory, and the generated test inputs live
  under `<PROJECT>\test-reports\ui\inputs`. `--output-dir` is pinned to an absolute
  `C:\Users\dvulin\Documents\DSH\sestan_diplomski\ccus_cluster\test-reports\ui\playwright`
  in `cordis.patch.yml`, because a stdio MCP child resolves a *relative* output dir
  against its own home directory instead of the DSH working directory (measured: a
  relative `test-reports/ui/playwright` landed in `C:\Users\dvulin\`). Edit that one
  line if the project moves.
* Node.js `^22.19.0 || >=24` on `PATH` (Playwright MCP runs through `npx`), and
  Microsoft Edge installed.
* `failOnStartupError: true`: the row refuses to activate if the server cannot
  start (missing Edge, failed `npx` download), which is visible instead of silent.
  The symptom of a *stale* connection is older tooling: after a config edit, check
  that a screenshot really lands in `<PROJECT>\test-reports\ui\playwright`.

## Locale

`locale/en.json` and `locale/hr.json` supply the Plugin Manager title and description
(`meta.title`, `meta.description`).

## Verified after installation

* Both rows activate; the bundle lists as `@local/ccus-ui-tester-plugin` v1.0.0 in
  the profile (`package.json` `dsh.profile.bundles`, dependency
  `link:.../agents/ccus-ui-tester-plugin`).
* The skill appears in the session catalog as `ccus-ui-tester` and loads with its
  resource base `agents\ccus-ui-tester-plugin\skills\ccus-ui-tester`.
* `mcp__ccus-browser__browser_*` tools register and work; a screenshot written during
  verification landed in `test-reports\ui\playwright`.
* `preflight.py --project <PROJECT>` → `READY: 0 required item(s) failed`;
  `oracle.py --scenario cluster` → reference strings and invariants.

## Do not point the browser tools at the DSH Web GUI itself

`dsh web` prints one startup URL whose `?token=` query mints an **authority-bound,
HMAC-signed cookie** (`dsh-auth-<hash of host:port>`, 30-day `Max-Age`) that
authorizes the SPA index. Everything else — `/api`, WebSocket, `/_stcore` — needs the
same cookie, and a page without it gets `401 dsh web authentication required; reopen
the URL printed by dsh web`.

So navigating `mcp__ccus-browser__browser_*` to `http://127.0.0.1:<dsh port>/` is a
dead end: Playwright's isolated profile has no such cookie, the request returns 401,
and repeated attempts only stack up. It does **not** invalidate the cookie of the
browser tab a human is already using, so the running GUI stays usable; but the printed
token lives only in the memory of the `dsh web` process (a `WeakMap`, never written to
disk), so a token cannot be recovered afterwards. Only the `dsh web` terminal has it.

Consequences:

* The browser tools exist to drive the **app under test** (`http://localhost:8501`),
  never the Harness UI.
* If a Harness page is ever needed, open the tokenized URL from the `dsh web` terminal
  in a normal browser; do not ask the automation browser to authenticate.
* If the printed token is lost, the only fix is to restart `dsh web` (the terminal is
  the single source of the URL) — nothing in `.dsh` can re-mint it.