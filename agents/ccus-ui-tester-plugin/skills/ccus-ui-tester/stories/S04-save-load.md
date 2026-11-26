# S04 – Save, list and load scenarios (isolated folder)

**Goal:** a user can keep work and get it back unchanged.
**Covers:** A07, I08 · known issues K09, K12, K20
**Safety:** the app must have been started by `start_app.py` (saves go to
`test-reports\ui\scenarios`). **Do not click Obriši/Delete** in this story.

| # | Action | Expected | Evidence |
|---|---|---|---|
| 1 | Source "Klaster", Pokreni. Sidebar "Naziv scenarija": type `s04_cluster`; click **Spremi** | green "Scenarij spremljen: s04_cluster"; known: red "Scenarij nije spremljen: st.session_state…" although the file exists (K20) | snapshot + `dir test-reports\ui\scenarios` |
| 2 | "Snimljeni scenariji": choose `s04_cluster`; click **Učitaj** | green "Scenarij učitan: s04_cluster"; tables filled | snapshot |
| 3 | Pokreni; compare stored (last year) and NPV with S01 | equal? note: the saved file contains the **table** version of the scenario (K08) | snapshot |
| 4 | Source "Jedan lanac (legacy)"; save as `s04_single`; load it | expected success; known: "Scenarij nije spremljen: Expecting property name enclosed in double quotes…" (K09) | snapshot |
| 5 | Type the name `s04_cluster` again and click Spremi | expected: "already exists" message, file not overwritten | snapshot |
| 6 | Type an invalid name `../x` and click Spremi | readable validation message, nothing written outside the folder | snapshot + dir |
| 7 | HUMAN CHECK: "Is it clear where the scenario was saved and what 'Učitaj scenarij' vs 'Učitaj' do?" | answer | answer |
