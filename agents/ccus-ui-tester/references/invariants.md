# Invariants and oracle checks

`scripts/oracle.py` runs the engine directly and evaluates these rules. They do not need
a "correct answer" for the scenario: every valid result must obey them. Tolerances are in
`scripts/tester_config.json` → `tolerances`.

| ID | Rule | Tolerance | A failure means | Known issue |
|---|---|---|---|---|
| I01 | Every year: captured CO2 = routed + unallocated | 1 t or 0.1 % | CO2 is created or lost in routing | – |
| I02 | Every year: routed CO2 = CO2 injected into all sinks | 1 t | routing and reservoir disagree | – |
| I03 | Cumulative injection per sink ≤ nominal capacity | 1 t | a sink is over-filled | – |
| I04 | Injection BHP ≤ fracture pressure in every active year | 0.01 bar | unsafe injection is not flagged | K06 |
| I05 | Reservoir pressure ≤ fracture pressure | 0.01 bar | material balance beyond its limit | – |
| I06 | Σ stakeholder statements = consolidated cash flow (undiscounted, before inflation) | 1 % | per-party economics do not reconcile | K02 |
| I07 | Monitoring cost booked ≤ annual monitoring rate × number of years | 0.1 % | monitoring is multiplied | K01 |
| I08 | Save → load (canonical compact JSON) returns the same scenario | exact | saved files lose data or cannot be read | K09, K10 |
| I09 | UI tables round trip ("Apply" without edits) keeps stored CO2 and the edge count | 0.1 % | the UI silently changes the scenario | K08 |
| I10 | No CAPEX booked twice for the same infrastructure (planned state + upgrade) | exact | CAPEX double counted | K03 |
| W01 | Unallocated CO2 ≤ 5 % of captured CO2 | – | most CO2 has nowhere to go; the UI does not show it | K05 |
| W02 | Effective sink capacity = nominal capacity | 1 % | the default reservoir model silently caps a sink | K05 |
| W03 | Every sink flagged `geothermal_coupled` has a doublet in the engine | – | UI and engine give different results for the same JSON | K15 |

`W..` are warnings: they describe results a reviewer must see, not necessarily bugs.

## Headless UI checks (`scripts/apptest_runner.py`)

| ID | Story | Check | Known issue when failing |
|---|---|---|---|
| A01 | S01 | App renders without errors; the source label matches the loaded scenario | K16 |
| A02 | S01 | After "Pokreni", the 8 metrics equal the oracle strings (last year) | – |
| A03 | S02 | "Primijeni i pokreni" without edits keeps stored CO2 and NPV; status becomes "aktualan" | K08, K14 |
| A04 | S06 | Language switch keeps results and changes labels | K19 |
| A05 | S05 | Uploading a JSON refreshes the input tables | K21 |
| A06 | S03 | Lowering every sink capacity in the table lowers stored CO2 after Apply | – |
| A07 | S04 | Save → Load in the isolated folder works and shows success messages | K09, K20 |
| A08 | S07 | Broken JSON, duplicate ids and unknown references give a readable error, no traceback | – |

## Comparing UI text with the oracle

`oracle_<scenario>.json` → `ui_expected`:

* `overview_by_year["<year>"]` – the four Sažetak/Summary metrics for that slider year;
* `economics` – the four Ekonomika/Economics metrics;
* the strings are formatted exactly like the UI (`f"{value:,.0f}"`, IRR `"{x:.2f} %"`).

A difference in the last digit only is still a finding (rounding or a different code path).
Run `oracle.py --scenario <alias> --year <year>` for any extra slider year you inspect.
