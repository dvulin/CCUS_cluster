# S07 – Invalid inputs and error messages

**Goal:** wrong input never produces a Python traceback; the message tells a user what to fix.
**Covers:** A08 · known issue K13
**Inputs:** run `make_inputs.py` first; files in `test-reports\ui\inputs\`.

| # | Action | Expected | Evidence |
|---|---|---|---|
| 1 | Upload `invalid_syntax.json` | red "Neispravan scenarij: Expecting ',' delimiter…"; no traceback | snapshot |
| 2 | Upload `invalid_duplicate_emitter.json` | red message containing "duplicate emitter id(s)" | snapshot |
| 3 | Upload `invalid_unknown_sink.json` | red message naming the connection and "unknown storage sink" | snapshot |
| 4 | HUMAN CHECK for 1–3: "Would a non-programmer know what to fix from this message?" (rate 1–5) | answers | answer |
| 5 | Upload `edge_pipeline_without_capacity.json`, Učitaj scenarij, Pokreni | expected: validation message at load; known: loads, then red "a pipeline state must declare capacity_t_per_year explicitly" on Run (K13) | snapshot |
| 6 | Ulazi → Ekonomika: Završna godina smaller than Početna godina; Apply | readable error, previous results not destroyed silently | snapshot |
| 7 | Ulazi → Diskontna stopa `0.5` (max) and Inflacija `0`; Apply | runs; NPV changes; no error | snapshot |
| 8 | Emiteri: type text `abc` into a numeric column | the grid refuses or the message is readable | snapshot |
