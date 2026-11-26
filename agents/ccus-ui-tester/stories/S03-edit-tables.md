# S03 – Edit the input tables and see the effect

**Goal:** a person can change emitters, connections and sinks in the grid, and the result
reacts as an engineer expects.
**Covers:** A06 · known issues K13, K14
**Input:** upload `test-reports\ui\inputs\valid_small_two_emitters.json`, click
"Učitaj scenarij", then **Primijeni i pokreni** once to get a baseline (write down stored at
the last year and NPV; or run `oracle.py --scenario test-reports\ui\inputs\valid_small_two_emitters.json`).

| # | Action | Expected | Evidence |
|---|---|---|---|
| 1 | Skladišta: set **kapacitet (t)** of every sink to `100000`; Apply | stored at the last year ≤ 300,000 t; NPV changes | snapshot |
| 2 | HUMAN CHECK: "Is the table easy to edit (click, type, Enter)? Did anything surprise you?" | answer | answer |
| 3 | Restore capacities (re-upload or undo), Emiteri: change **početak** of the first emitter to a year 5 years later; Apply | captured in the earlier years drops; stored drops | snapshot |
| 4 | Pristupi: change **L (km)** of one row to 3× its value; Apply | for `pipeline` rows the NPV does **not** change (tariff is per t, not per t·km); for `truck` rows it does. HUMAN CHECK: "Is this what you expect?" | answer |
| 5 | Pristupi: add a new row (emitter id that exists, sink id that exists, start year, mode pipeline, L, **capacity empty**); Apply | expected: clear validation message; known: red error "a pipeline state must declare capacity…" after Apply (K13) | snapshot |
| 6 | Add an emitter row with id `Bad Id` (space); Apply | readable validation error naming the field | snapshot |
| 7 | Edit any cell, then click **Pokreni** (sidebar) instead of Apply | HUMAN CHECK: "Your edit is gone – did you expect that?" (K14) | answer |

**Pass:** 1 and 3 change the results in the expected direction; 5 and 6 show readable
errors without a Python traceback.
