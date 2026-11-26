# Known issues (baseline from the 2026-11-16 code review and headless run)

Tag every failure with one of these IDs, or `NEW` when none fits. A known issue that no
longer reproduces is also a finding ("fixed?") – report it.

Severity: **S1** wrong numbers or data loss, **S2** crash / blocked workflow, **S3** wrong
or confusing display, **S4** cosmetic.

| ID | Sev | Issue | Where it shows in the UI | Detected by |
|---|---|---|---|---|
| K01 | S1 | Monitoring cost is summed over all years and then charged every year (×N) | Ekonomika: PV troškovi too high; cash-flow column `monitoring` (single chain: 4.5 M EUR/yr instead of 0.25) | I07, S08 |
| K02 | S1 | Stakeholder transport CAPEX is charged in every year the edge is active | Ekonomika → "Ekonomika po sudionicima": transport operator hugely negative; does not add up to consolidated | I06, S08 |
| K03 | S1 | Upgrade CAPEX booked even if the trigger never fires; duplicated when the upgrade repeats a planned state | Ekonomika: transport CAPEX (single chain: +25 M EUR) | I10 |
| K04 | S1 | Cumulative-mass upgrade triggers never fire in the solver | Mreža: mode never switches for mass-triggered upgrades (JSON upload only) | code review |
| K05 | S1 | Default reservoir model silently caps nominal sink capacity; unallocated CO2 is not shown | Sažetak: Rutirano < Uhvaćeno with no explanation (Croatia: 66 % unallocated) | W01, W02, S01, S05 |
| K06 | S1 | BHP above fracture pressure is not flagged | Skladište: BHP line above limit, no warning (Croatia, Boksić 2033–34) | I04, S08 |
| K07 | S1 | Compressor energy takes the max over sinks, not the sum | Sažetak ledger column `co2_compressor_mwh` | code review |
| K08 | S1 | "Primijeni i pokreni" rebuilds the scenario from the tables only: hub edges, upgrades, designs are dropped | after Apply on the default sources: stored = 0, NPV changes | I09, A03, S02 |
| K09 | S2 | Saving writes invalid JSON when a piecewise emission curve exists; reload fails | Load of a "Jedan lanac" save shows "Scenarij nije spremljen: Expecting property name…" | I08, A07, S04 |
| K10 | S1 | Compact save drops manually defined edges when connections exist | after save/load of such a JSON upload | I08 |
| K11 | S1 | Editing an existing connection does not update its derived edge (engine level) | only via JSON round trips; UI rebuild avoids it | code review |
| K12 | S1 | Delete/Load use a file in the working directory when the name matches one | Obriši on a scenario named like a project file deletes that file – **do not test destructively** | code review |
| K13 | S2 | Inputs that validate but crash later: pipeline connection without capacity; geothermal water pipeline; polynomial curve before reference year | red error after Run/Apply with `edge_pipeline_without_capacity.json` | S07 |
| K14 | S3 | After a successful "Primijeni i pokreni" the banner still says "Scenarij je izmijenjen – pokreni ponovno"; "Pokreni" discards table edits; Save silently falls back to the file scenario when tables are mid-edit | status banner, tables | A03, S02, S03 |
| K15 | S3 | `geothermal_coupled` creates a doublet only in the UI, not in the engine | same JSON gives different results in UI and engine | W03 |
| K16 | S3 | Source "Klaster (14 emitera)" loads a 3-emitter scenario | sidebar success message names "Tri emitera…" | A01, S01 |
| K17 | S4 | Map legend label "Ĺ˝eljeznica" (mojibake, should be "Željeznica") | Mreža map legend for rail edges | S08 |
| K18 | S3 | Overview metrics show the first year of the slider by default (mostly 0) | Sažetak right after Run | S01, S08 |
| K19 | S2 | Switching language resets the source and discards results and edits | after Jezik → English the metrics disappear | A04, S06 |
| K20 | S3 | Save writes the file but shows "Scenarij nije spremljen: st.session_state['scenario_name'] cannot be modified…"; load errors reuse the "not saved" text | sidebar after Spremi / Učitaj | A07, S04 |
| K21 | S3 | After uploading a JSON the tables keep the previous scenario until "Učitaj scenarij" is clicked; Apply then runs the old tables | Ulazi tab after upload | A05, S05 |
