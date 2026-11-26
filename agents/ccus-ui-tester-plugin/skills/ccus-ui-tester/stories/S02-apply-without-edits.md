# S02 – "Primijeni i pokreni" without any edit must not change the results

**Goal:** the table round trip is lossless; the status banner is correct.
**Covers:** A03, I09 · known issues K08, K14

| # | Action | Expected | Evidence |
|---|---|---|---|
| 1 | Fresh page, source "Klaster", click **Pokreni**, slider → last year (2045) | stored `17,324,235`; NPV `-919,875,061` | snapshot |
| 2 | Tab **Ulazi**: look at the four tables without changing anything | Emiteri 3 rows; Pristupi **0 rows** (the scenario uses hub edges) | snapshot |
| 3 | HUMAN CHECK: "The connections table is empty although the network has 7 transport edges. Would you expect to see them here?" | answer | answer |
| 4 | Click **Primijeni i pokreni** (bottom of Ulazi) | "Scenarij je osvježen."; results identical to step 1 | snapshot |
| 5 | Slider → 2045; read stored and NPV | **expected** unchanged; **known**: stored `0`, NPV `-645,438,134` (K08) | snapshot |
| 6 | Read the status banner | expected "Scenarij je aktualan"; known: "Scenarij je izmijenjen – pokreni ponovno" (K14) | snapshot |
| 7 | Repeat 1–6 with source "Jedan lanac (legacy)" | same rule; known: stored `9,634,400` → `0` | snapshot |
| 8 | Repeat 1–6 with upload `test-reports\ui\inputs\valid_croatia.json` (+ "Učitaj scenarij") | stored `7,875,204` unchanged (connections-only scenario survives) | snapshot |

**Pass:** steps 5 and 6 unchanged for all three sources.
