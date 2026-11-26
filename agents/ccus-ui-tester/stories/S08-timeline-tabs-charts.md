# S08 – Timeline, tabs, charts and download

**Goal:** every tab is readable, consistent with the others and with the oracle, for a
scientific/engineering audience.
**Covers:** visual checks AppTest cannot do · known issues K01, K02, K06, K17, K18
**Input:** source "Jedan lanac (legacy)" (has a geothermal doublet and monitoring costs),
then repeat the economics part with the Croatia upload.

| # | Action | Expected | Evidence |
|---|---|---|---|
| 1 | Pokreni; move the slider through 3 years (first, peak, last) | Sažetak, Mreža and Skladište change consistently with the slider; Ekonomika does not depend on it | snapshots |
| 2 | Tab **Mreža**: map, edges table, hub pressures, flows | HUMAN CHECK: "Do line widths/arrows match the flows table? Are units shown?" | screenshot + answer |
| 3 | Tab **Skladište**: pressure and BHP per site | HUMAN CHECK: "Is the fracture limit visible? Croatia/Boksić 2033–34: BHP above 270 bar – is that flagged?" (K06) | screenshot + answer |
| 4 | Tab **Ekonomika**: cash-flow table column `monitoring` | single chain: oracle I07 says booked 81.00 M EUR vs bound 4.75 M EUR; UI shows −4,500,000 per year (K01) | snapshot |
| 5 | Ekonomika → "Ekonomika po sudionicima" | stakeholder totals should add up to the consolidated cash flow; known: transport operator ≈ −2.9 bn EUR (K02) | screenshot |
| 6 | Cost pie: change "Godina prikaza" | pie updates; labels readable; percentages sum to 100 % | screenshot |
| 7 | Per-entity economics: pick an emitter, then the transport operator | metrics and charts update; HUMAN CHECK on plausibility | screenshot + answer |
| 8 | Tab **Tablice**: "Preuzmi tehnički sažetak (CSV)" | file `ccus_ledger.csv` downloads; opens in Excel with correct columns and Croatian characters | human confirms |
| 9 | Browser console (`browser_console_messages`, level error) | no front-end errors | console log |
