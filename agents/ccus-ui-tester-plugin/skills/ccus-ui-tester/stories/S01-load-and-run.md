# S01 – Load the default scenario and run it

**Goal:** the default source loads, runs without errors, and the shown numbers equal the
engine oracle.
**Covers:** A01, A02 · known issues K05, K16, K18
**Preconditions:** app started with `start_app.py --fresh`; `oracle.py --scenario cluster`
was run (expected values below are from 2026-11-16; always use the fresh oracle output).

| # | Action | Expected | Evidence |
|---|---|---|---|
| 1 | Open `http://localhost:8501` | Title "CCUS cluster – dinamični emiteri i multimodalni transport"; sidebar source "Klaster (14 emitera)" selected; green "Scenarij: Tri emitera – …"; info "Scenarij nije pokrenut" | snapshot |
| 2 | HUMAN CHECK: "The source says 14 emitters, the loaded scenario says three. Which one is right for you?" | human answer recorded (K16) | answer |
| 3 | Click **Pokreni** in the sidebar; wait for the rerun | green "Scenarij je aktualan"; slider "Vremenska os" appears (2027–2045); no red box | snapshot |
| 4 | Open tab **Ekonomika** | NPV `-919,875,061`, IRR `0.00 %`, PV prihodi `978,183,300`, PV troškovi `-1,898,058,362` (oracle `economics`) | snapshot |
| 5 | Open tab **Sažetak** (slider still at 2027) | four metrics `0` (K18) | snapshot |
| 6 | HUMAN CHECK: "Is it clear to you that these numbers are for the year 2027 only?" | answer (K18) | answer |
| 7 | Move the slider to **2030**, then to **2045** | 2030: captured `1,947,416`, routed `1,947,416`, injected `1,947,416`, stored `4,089,750`; 2045: captured `179,639`, routed `0`, injected `0`, stored `17,324,235` | snapshot ×2 |
| 8 | HUMAN CHECK at 2045: "Captured 179,639 t but routed 0 t – where does that CO2 go? Does the UI tell you?" | the UI shows no unallocated amount (K05); record the human's reading | answer |
| 9 | Screenshot of tab **Mreža** at 2030 | map renders; legend readable | screenshot |

**Pass:** steps 1, 3, 4, 7 match the oracle exactly and no error box appears. Steps 2, 6, 8
are judgments recorded as HUMAN-OK / FAIL.
