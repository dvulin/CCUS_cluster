# S05 – Upload a JSON scenario and switch sources

**Goal:** an uploaded file becomes the active scenario everywhere (status, tables, results).
**Covers:** A05 · known issues K05, K21
**Inputs:** `test-reports\ui\inputs\valid_croatia.json`, `valid_small_two_emitters.json`

| # | Action | Expected | Evidence |
|---|---|---|---|
| 1 | Source "Učitaj JSON"; Browse files → `valid_croatia.json` | green "Scenarij: Croatian coastal and central CCS cluster (workbook import)" | snapshot |
| 2 | Tab Ulazi, count rows of Emiteri | expected 14; known: still the previous scenario's rows until **Učitaj scenarij** is clicked (K21) | snapshot |
| 3 | Click **Učitaj scenarij**, then **Pokreni**; slider → 2028, then 2050 | 2028: captured `3,756,694`, routed `3,691,701`; 2050: stored `7,875,204`; NPV `-342,751,882` | snapshot |
| 4 | HUMAN CHECK: "About 15 Mt (66 %) of the captured CO2 is never stored. Can you see that anywhere in the UI? Do the sink capacities in the table (Boksić 13.7 Mt) match what is actually filled (3.6 Mt)?" | record (K05) | answer |
| 5 | Upload `valid_small_two_emitters.json` without changing the source | the new name appears; tables follow after Učitaj scenarij | snapshot |
| 6 | Switch the source to "Klaster" and back to "Učitaj JSON" | HUMAN CHECK: is the previously uploaded file still active, and is that clear? | answer |
