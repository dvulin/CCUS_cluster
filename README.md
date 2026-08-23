# GT-CCS – proračun geotermalno potpomognutog hvatanja i skladištenja CO2

**GT-CCS** je modularna Python i Streamlit aplikacija za integrirani tehnički i
ekonomski proračun lanca emiter → hvatanje → transport → utiskivanje →
skladištenje, uz geotermalni dublet. `services/ScenarioRunner` povezuje
inženjerske vremenske nizove s godišnjom energetskom bilancom i komponentnim
novčanim tokom.

---

## Repository structure

```
CCUS_cluster/
├── ccs_utilities/              # Retained empty legacy directory
│   └── .gitkeep
├── domain/                     # Domain entities
│   ├── __init__.py
│   ├── ccs_chain.py            # Naslijeđeni jednolančani objekti
│   └── ccs_network/            # Izolirani višeemiterski mrežni model
│       ├── models.py
│       ├── flow.py
│       └── costs.py
├── inputs/                     # Input loading and parameter metadata
│   ├── __init__.py
│   ├── metadata.py
│   ├── io_endpoints.py
│   └── examples/
│       └── main_inputs.json
├── engineering/                # Engineering calculations package
│   ├── __init__.py
│   ├── fluid_properties.py
│   ├── power.py
│   ├── wellbore.py
│   ├── mbalance.py
│   ├── geothermal.py
│   ├── transport.py
│   └── pipeline.py             # Horizontalni termo-hidraulički proračun
├── outputs/                    # Prikaz i izvoz rezultata
│   ├── __init__.py
│   ├── result_export.py
│   ├── visualization.py
│   └── legacy/                 # Historical generated results
│       ├── bhp.json
│       ├── GT_CCS_yearly_df.xlsx
│       ├── results_preview.html
│       ├── results_preview.xlsx
│       └── s_eff_vs_co2_stored_kr_co2.png
├── economics/                  # Economic calculations package
│   ├── __init__.py
│   ├── economics.py            # Naslijeđeni ekonomski model
│   ├── cost_models.py
│   ├── cash_flow_runner.py
│   └── price_scenarios.py
├── examples/                   # Runnable and legacy examples
│   ├── __init__.py
│   ├── engineering_demo.py
│   ├── economics_demo.py
│   └── legacy/
│       ├── __init__.py
│       ├── thermal_testing.py
│       ├── water_well_pressure.py
│       └── co2_well_pressure.py
├── docs/                       # Reserved documentation package
├── services/                   # Povezivanje tehničkog i ekonomskog modela
│   ├── scenario_runner.py
│   └── engineering_economics_adapter.py
├── pages/                      # Reserved Streamlit pages
├── tests/                      # Automatizirani testovi
│   └── network/                # Izolirani testovi višeemiterskog modela
├── app.py                      # Streamlit sučelje
├── README.md
├── requirements.txt
├── changelog.txt
├── LICENSE
└── .gitignore
```

---

## File descriptions

### `ccs_utilities/.gitkeep`

The former package directory is intentionally retained as an empty legacy directory. Active input, engineering and output classes are exported from their corresponding packages.

---

### `inputs/metadata.py` – class `ParamMetadata`

Base class that provides a uniform parameter dictionary with metadata (unit, description) to all engineering classes. Inheriting classes declare a `PARAM_METADATA` class variable — a dict of `{param_name: (unit_string, description_string)}`.

| Method / property | Description |
|---|---|
| `__init__(**kwargs)` | Initialises `self.params` dict; accepts only keys declared in `PARAM_METADATA`. |
| `get_param(param)` | Returns `{value, unit, description}` dict for a single parameter. |
| `__getattr__(name)` | Transparent access: `obj.rw` → `obj.params['rw']`. |
| `__setattr__(name, value)` | Routes writes to `params` dict if the name is a declared parameter; falls through to normal attribute otherwise. |
| `__str__()` | Pretty-prints all parameters with values and units. |

---

### `engineering/fluid_properties.py` – class `FluidProperties`

Thin wrapper around **CoolProp**'s `PropsSI` function. All methods accept SI units (Pa, K) and return SI results.

| Method | Returns |
|---|---|
| `get_density(fluid, p, T)` | Density, kg/m³ |
| `get_viscosity(fluid, p, T)` | Dynamic viscosity, Pa·s |
| `get_enthalpy(fluid, T, p)` | Specific enthalpy, J/kg |
| `get_molar_mass(fluid)` | Molar mass, kg/mol |
| `get_saturation_pressure(fluid, T)` | Saturation pressure, Pa |
| `get_compressibility_factor(fluid, p, T)` | Compressibility factor Z, – |
| `get_specific_heat(fluid, p, T, param)` | Cp or Cv, J/kg/K (param: `'CP0MASS'` or `'CVMASS'`) |
| `get_Tc(fluid)` | Critical temperature, K |
| `get_pc(fluid)` | Critical pressure, Pa |

---

### `inputs/io_endpoints.py` – class `IOEndpoints(ParamMetadata)`

Reads `inputs/examples/main_inputs.json`, validates every parameter (type, unit, presence), and exposes them as attributes. Also computes several derived quantities on load.

**Parameters loaded from JSON** (partial list):

| Key | Unit | Description |
|---|---|---|
| `m_dot_annual` | ktpa | Annual CO2 injection mass flow |
| `rw` | m | Well radius |
| `A` | m² | Aquifer area |
| `h_ef` | m | Effective aquifer thickness |
| `poro` | – | Porosity |
| `h_ref_co2` | m | CO2 injection-well VFP reference depth |
| `h_ref_geothermal_production` | m | Geothermal production-well VFP reference depth |
| `h_ref_geothermal_injection` | m | Geothermal injection-well VFP reference depth |
| `p_ref` | bar | Initial reservoir pressure |
| `k` | m² | Average permeability |
| `eta` | – | ORC efficiency |
| `E_eff` | – | CO2 storage efficiency |
| `Sw_i` | – | Irreducible water saturation |
| `krg_max` | – | Maximum CO2 relative permeability |
| `nw`, `ng` | – | Corey exponents for water and gas |

**Derived attributes computed on init:**

| Attribute | Formula | Description |
|---|---|---|
| `m_dot` | `m_dot_annual × 1e6 / (365.25 × 24 × 3600)` | Instantaneous mass flow, kg/s |
| `re` | `sqrt(A / π)` | Effective drainage radius, m |
| `V_p_ref` | `A × h_ef × poro` | Reference pore volume, m³ |
| `p_max` | `0.18 × h_top` | Maximum allowed injection pressure, bar |

**Key method:**

| Method | Description |
|---|---|
| `_validate(data, key, type_, unit)` | Raises `ValueError` on missing key, wrong type, or unit mismatch. |

Legacy scenarios that contain only `h_ref` remain supported: that shared value is
copied to all three role-specific depths. `IOEndpoints.h_ref` remains an internal
alias of `h_ref_co2` for the generic VFP constructor, while `ScenarioRunner`
assigns the matching role-specific depth to every well instance.

---

### `engineering/transport.py` – class `Transport`

Konfiguracija zasebne transportne dionice: način transporta, godišnja količina
CO2, udaljenost, CAPEX/OPEX te geometrija i koljena cjevovoda. Modul
`engineering/pipeline.py` sadrži generički stacionarni 1D proračun za CO₂ i
vodu. Metoda `Pipeline.calculate_outlet_conditions` prima vrstu fluida, ulazni
tlak i temperaturu, maseni protok i geometriju te vraća izlazni tlak i
temperaturu.

Po segmentu se lokalno računaju gustoća, viskoznost i specifični toplinski
kapacitet iz trenutačnog tlaka i temperature. Pad tlaka koristi Darcy–Weisbach,
Haalandov turbulentni faktor trenja (`64/Re` za laminarni tok) i lokalne
koeficijente koljena `K90=0,9`, `K45=0,4`, `K30=0,2`. Cjevovod je horizontalan,
pa nema gravitacijskog člana. Budući da položaji koljena nisu ulaz, njihov se
ukupni `K` ravnomjerno raspodjeljuje po numeričkim segmentima. Temperatura se
približava zadanoj temperaturi
okoliša stabilnim eksponencijalnim korakom kroz serijski toplinski otpor
stijenke, izolacije i vanjskog okoliša. Za zrak se zadaje vanjski koeficijent
prijelaza topline, a za ukopani vod vodljivost tla i dubina osi cijevi.
Otpor unutarnjeg graničnog sloja fluida trenutačno se zanemaruje, pa modelirani
serijski otpor počinje na unutarnjoj stijenci cijevi.

CO₂ dionica koristi `transport_distance_km` i postojeću CO₂ geometriju. Vod za
geotermalnu vodu koristi `d_doublet` kao razmak geotermalnog para i duljinu
površinskog transporta vode te zasebne
`geothermal_pipeline_*` parametre promjera, hrapavosti i koljena. Integrirani
scenarij za CO₂ koristi eksplicitne `co2_pipeline_inlet_pressure_bar` i
`co2_pipeline_inlet_temperature_c`; za vodu su ulazni uvjeti postojeći ORC
izlazi `p_out` i `t_out`. Ako prvi `p_gt_transport_out` padne ispod
`1,01325 bar`, efektivni ORC izlazni tlak računa se potvrđenim pravilom
`p_gt_transport_in = p_gt_transport_in - (p_gt_transport_out - 1,01325 - 1)`
i pipeline se ponovno računa. Time se dobiva približno jedan bar rezerve iznad
atmosferskog tlaka.

`pipeline_environment_volumetric_heat_capacity_j_m3_k` validira se i zajedno s
vodljivošću daje dijagnostičku toplinsku difuzivnost okoliša. Ne ulazi u
stacionarnu izlaznu temperaturu: za tranzijentni utjecaj toplinskog kapaciteta
trebali bi još vrijeme od pokretanja i početni temperaturni profil okoliša.
Model također ne uključuje promjenu nadmorske visine, dvofazni tok ni
Joule–Thomsonov član. CO₂ proračun zato prati CoolProp fazu i prekida se prije
prijelaza liquid↔gas ili eksplicitnog dvofaznog stanja. Početna segmentacija
automatski se udvostručuje dok izlazni tlak i temperatura ne zadovolje zadane
tolerancije ili dok se ne dosegne `maximum_nsteps`.

CO₂ tablica ostaje forward dijagnostika nominalnog projektnog protoka.
Geotermalni pipeline spojen je s energetskim i bušotinskim proračunom:
efektivni `p_gt_transport_in` koristi ORC, `p_gt_transport_out` je ulazni tlak
GT pumpe, a `t_gt_transport_out` ulazna temperatura utisnog VFP-a. Svaka
korekcija preniskog prvog izlaznog tlaka ispisuje se, sprema u
`calculation.log` i izlaže kroz `scenario_notes`.

---

### `engineering/wellbore.py` – class `VFP(ParamMetadata)`

Vertical Flow Performance class. Calculates the pressure profile along a CO2 injection or geothermal production/injection well using a step-wise integration of gravitational and frictional pressure gradients.

The fluid temperature is integrated in the physical flow direction while the
pressure can be integrated from either known endpoint. A linear formation
temperature profile and an effective heat-transfer coefficient are used in a
stable exponential heat-transfer step; every pressure segment evaluates local
density and viscosity at its local pressure and temperature. `T_C` is the
fluid inlet temperature (wellhead for injection, bottomhole for production).
The active scenario currently uses 20 °C as an explicit surface-formation
temperature proxy and the scenario reservoir/production temperature at the
bottom; this proxy is intentionally independent of ORC `t_out`. Fluid heat
capacity is evaluated once at scenario reference pressure `p_ref` and inlet
temperature so the thermal profile does not depend on whether BHP or WHP is
the known pressure boundary.
The model represents steady 1D heat exchange with the formation; it does not
include Joule–Thomson, adiabatic or transient cement/rock effects.

**Parameters:** `rw`, `re`, `h_ef`, `h_ref`, `k`, `m_dot`. The generic
`h_ref` attribute is set per instance from the corresponding role-specific
scenario input before the pressure profile is calculated.

| Method | Description |
|---|---|
| `colebrook(D, Re, e)` | Solves the Colebrook-White implicit equation via `scipy.optimize.fsolve`; returns the Darcy-Weisbach friction factor. |
| `calculate_dp(fluid, m_dot, bhp, whp, T_C, depth_total, nsteps, pipe_diameter, epsilon, flow_direction, formation_surface_temperature_C, formation_bottomhole_temperature_C, heat_transfer_coefficient_W_m2_K, specific_heat_capacity_J_kg_K)` | Integrates temperature in the physical flow direction and pressure from the known BHP or WHP. Local `ρ(p,T)` and `μ(p,T)` affect gravity, friction and the resulting endpoint pressure. The optional diagnostics include the complete temperature profile and endpoint properties. |

---

### `engineering/mbalance.py` – class `MaterialBalance(ParamMetadata)`

Aquifer material balance engine for CO2 storage in a deep saline aquifer (DSA). Tracks pore volume, water volume, free pore volume, and CO2 mass over time as reservoir pressure evolves.

**Parameters:** aquifer geometry (`A`, `h_ef`, `poro`), pressure (`p_ref`, `dp`, `p_max`), rock and fluid properties (`k`, `c_p`, `sal`), relative permeability parameters (Corey model).

| Method | Description |
|---|---|
| `c_w(p, T, S)` | Calculates water compressibility (Craft-Hawkins correlation, converted to 1/Pa). |
| `calculate_total_compressibility(p, T)` | Returns total compressibility `c_p + c_f` in 1/Pa; `c_f` is estimated numerically from CO2 density derivative. |
| `calculate_drainage_radius(k, t, phi, mu, ct)` | Returns the transient drainage radius from hydraulic diffusivity formula: `r = sqrt(k·t / (φ·μ·ct))`. |
| `kr_Corey(s_co2, s_wi, s_gr, process)` | Calculates water and CO2 relative permeabilities using Corey-type power law. Handles drainage and imbibition processes; enforces min/max bounds to prevent division-by-zero. Returns `(krw, krg)`. |
| `solve_BHP_from_CO2_mass_flow(pr, m_dot, t, k_ef)` | Newton-Raphson iteration to find BHP for a given CO2 injection rate, accounting for time-evolving drainage radius and fluid properties at reservoir conditions. Returns `(p_wf_bar, rho, mu, re)`. |
| `calculate_material_balance()` | Main loop: marches from `p_ref` to `p_max` in `dp` steps, computing for each pressure step the injected CO2 mass, pore/water volumes, time elapsed, and CO2 density. Returns a dict of time-series arrays. |
| `calculate_effective_saturation(m_co2)` | Estimates effective CO2 saturation for kr calculation as `m_co2 / storage_capacity + S_plume_core`. |
| `calculate_bhp_properties(S_co2_effective)` | For each time step uses `solve_BHP_from_CO2_mass_flow` with the effective CO2 relative permeability; returns a dict with `BHP`, `dp`, `density_BHP`, `viscosity_BHP`, `re`, `s_co2_eff`, `kr_co2`. |
| `calculate_co2_plume_radius(m_co2, t)` | Estimates CO2 plume radius from stored mass assuming cylindrical geometry. |

---

### `engineering/geothermal.py` – class `Geothermal(ParamMetadata)`

Models the geothermal doublet system: production IPR (Inflow Performance Relationship), injection BHP, and thermal breakthrough.

**Parameters:** `d_doublet`, `t` (reservoir temperature), `h_ef`, `k`, `bhp_dp`, `eta`, `t_out`, `p_out`, `rw`, `poro`

**Fixed attributes set in `__init__`:** `Ea = 0.85` (areal sweep efficiency), `c_r = 950` J/kg·K, `rho_r = 2700` kg/m³, `lambda_r = 3.5` W/m·K

| Method | Description |
|---|---|
| `calculate_m_dot_prod(p_ref, bhp_dp, ...)` | Computes production mass flow rate and reservoir volumetric rate from Darcy radial flow equation: `q = 2π·k·h·ΔP / (μ·ln(re/rw))`. Returns `(m_dot [kg/s], q [rm³/day], bhp [bar])`. |
| `calculate_bhp_inj(p_ref, m_dot_h2o, ...)` | Newton-Raphson iteration for injection BHP at the given water injection rate. Returns `(bhp [bar], rho [kg/m³])`. |
| `calculate_production_temperature(m_dot_h2o, p_bar, t_C, t_inj_C, ...)` | Lauwerier/Gringarten-Sauty analytical solution for temperature at the production well over time. Calculates breakthrough time and post-breakthrough temperature decline using the error function. Returns dict with `time_years`, `temperature`, `t_bt`, `properties`. |
| `calculate_unsteady_production(mbal_df, ...)` | Variable-rate thermal front tracking: integrates front radius step-by-step from a `mbal_df` DataFrame (with time-varying flow rates from DSA pressure coupling). Applies superposition to calculate production temperature evolution after breakthrough. Returns `time_years`, `temperature`, `t_bt`, `cumulative_radius`, `front_velocities`. |
| `calculate_front_radius(...)` | Helper: calculates the thermal front radius for one time step (used internally by `calculate_unsteady_production`). |

---

### `engineering/power.py` – class `Power(ParamMetadata)`

Calculates mechanical power demand for ORC turbine output, pump, and multi-stage CO2 compressor.

**Parameters:** `m_dot`, `t_comp_in`, `p_comp_in`, `eta`

| Method | Description |
|---|---|
| `calculate_ORC_power(m_dot, p_in, p_out, t_in, t_out, fluid, eta)` | Simple enthalpy-drop ORC model: `P = (h_in − h_out) × m_dot × η`. Returns power in kW; clipped to 0 if negative. |
| `calculate_pump_power(fluid, m_dot, p_in_bar, p_out_bar, t_C, eta)` | Pump power from `P = Q·ΔP / η`. Returns kW; returns 0 if inlet pressure already exceeds outlet. |
| `calculate_compression_power(fluid, p_in_bar, p_out_bar, t_in_C, m_dot, N_stages, eta_is, eta_p)` | Multi-stage intercooled compression using real-gas isentropic work (`Z`, `cp/cv` from CoolProp). Automatically switches to liquid pumping if the critical temperature is exceeded during compression (CO2 dense phase injection). Returns total power in kW. |

---

### `outputs/result_export.py`

Pretvara mapiranje koje vraća `ScenarioRunner.run()` u strogi JSON ili Excel
radnu knjigu. Oba formata sadrže aktivne ulaze, tehničke i ekonomske tablice,
KPI-je, napomene scenarija i konfiguraciju transporta. Izvoz ne pokreće niti
mijenja proračunske jednadžbe.

| Funkcija | Rezultat |
|---|---|
| `build_results_json(results, active_inputs)` | UTF-8 JSON sa shemom `1.0`; `NaN` i beskonačne vrijednosti zapisuju se kao `null`. |
| `build_results_excel(results, active_inputs)` | XLSX u memoriji s listovima `inputs`, `summary` i svim DataFrame rezultatima. |

---

### `outputs/visualization.py` – class `Visualization`

All matplotlib-based plotting methods. Each saves a high-resolution PNG (600 dpi) and calls `plt.show()`.

| Method | Plot description |
|---|---|
| `s_eff_vs_co2_stored_kr_co2` | CO2 effective saturation and `kr_CO2` vs. time |
| `bhp_vs_density_viscosity` | BHP vs. CO2 density and viscosity |
| `time_vs_CO2_stored_vs_bhp_vs_whp` | Time series: CO2 stored, DSA pressure, BHP, WHP |
| `time_vs_power_vs_bhp_vs_pDSA` | Time series: compression power, BHP, DSA pressure |
| `time_vs_geothermal_flow_temperature` | Geothermal flow rate and production temperature over time |
| `time_vs_geothermal_co2_bhp_whp_comparison` | Comparison of geothermal vs. CO2 BHP/WHP |
| `time_vs_power` | Net geothermal power vs. CO2 compression power |
| `volumetric_flow_comparison` | Volumetric flow rate vs. stored CO2 mass |
| `pressure_efficiency_correlation` | CO2 BHP vs. compression power and net GT power (scatter) |
| `comprehensive_system_overview` | 4-subplot overview: CO2 storage, GT production, energy balance, system efficiency |

---

### `examples/engineering_demo.py`

Main engineering run script. Executes the full simulation chain:

1. Load parameters from `inputs/examples/main_inputs.json` via `IOEndpoints`.
2. Run material balance (`MaterialBalance.calculate_material_balance`) to get DSA pressure and CO2 mass time series.
3. Calculate effective CO2 saturation and BHP (`calculate_effective_saturation`, `calculate_bhp_properties`).
4. For each BHP step, compute CO2 wellhead pressure (`VFP.calculate_dp`) and compression power (`Power.calculate_compression_power`).
5. For each DSA pressure step, compute geothermal production flow (`Geothermal.calculate_m_dot_prod`) and injection BHP.
6. Compute ORC and pump power along the geothermal doublet lifetime.
7. Generate all visualisation plots via `Visualization`.

---

### `economics/economics.py` – class `Economics`

Base class for all CCS chain economic entities. All time-series arrays span `start_year … end_year` (inclusive, `nsteps` years total).

**Constructor parameters:** `start_year`, `end_year`, `OPEX_per_ton`, `interest_rate` (default 5 %), `inflation_rate` (default 5 %), `price_scenario` (−1 pessimistic / 0 conservative / +1 optimistic).

**Key properties (read-only after `set_cash_flow()`):**

| Property | Description |
|---|---|
| `payments` | `CAPEX + OPEX` per year (NumPy array) |
| `payments_future_values` | `payments` adjusted for inflation from `CCS_start_year` |
| `CO2_tax` | `CO2_price × emissions` per year (emitter-only) |
| `CCS_savings` | `CO2_tax − payments_future_values` (emitter-only) |
| `NPV` | Cumulative discounted NPV array, using `interest_rate` |
| `CAPEX` | Time-series array; scalar setter places CAPEX as lump sum in `CCS_start_year` |
| `OPEX` | Time-series array |
| `CO2_price` | Array of CO2 prices (EUR/t) for selected scenario, 2025–2050 |

**Key methods:**

| Method | Description |
|---|---|
| `set_cash_flow()` | Public trigger to compute all derived cash-flow properties. |
| `set_OPEX(CO2_flow)` | Builds OPEX array as `OPEX_per_ton × CO2_flow`; zeroed before `CCS_start_year`. |
| `_generate_CO2_price()` | Returns CO2 price trajectory array from three built-in scenarios (pessimistic, conservative, optimistic). |
| `_calc_payments()` | `CAPEX + OPEX` |
| `_calc_payments_future_values()` | Inflation-corrected payments. |
| `_calc_CO2_tax()` | `CO2_price × emissions`. |
| `_calc_CCS_savings()` | Year-by-year savings vs. paying the carbon tax. |
| `_calc_CCS_NPV()` | Cumulative discounted NPV with compound interest. |

---

### `domain/ccs_chain.py` – classes `Storage`, `Transport`, `Emitter`

Domain objects that currently inherit from `Economics` and add physical attributes. This inheritance is retained unchanged during the organizational move; replacing it with composition is a separate architectural step.

#### `Storage(Economics)`

Represents a geological storage site (type: `"DSA"` deep saline aquifer or `"DHF"` depleted hydrocarbon field).

| Property | Description |
|---|---|
| `name` | Site name |
| `storage_type` | `"DSA"` or `"DHF"` (validated by setter) |
| `capacity` | Total storage capacity, t |
| `injection_rate` | Time-series injection rate; scalar is broadcast to full nsteps array |
| `depth` | Storage depth, m |

#### `Transport(Economics)`

Represents one pipeline/transport leg.

| Property | Description |
|---|---|
| `section_name` | Descriptive label |
| `flow_rate` | CO2 throughput, t/year |
| `transport_type` | Pipeline, ship, etc. (free-form) |
| `distance` | Length, m |

#### `Emitter(Economics)`

Represents an industrial CO2 emitter.

| Property | Description |
|---|---|
| `name` | Emitter name |
| `emissions` | NumPy array of annual CO2 emissions, t/year |
| `capture_technology` | `"PI"`, `"NI"`, or `"OXY"` (validated by setter) |

| Method | Description |
|---|---|
| `emissions_change(a, c)` | Applies a polynomial growth curve to baseline emissions: `E(t) = E₀ + a·E₀·t^c`. With default `a=0`, emissions stay flat. |

---

### `domain/ccs_network` – izolirani višeemiterski mrežni model

Ovaj paket je nova, UI-neovisna domenska osnova i nije povezan s trenutačnim
`IOEndpoints`, `ScenarioRunner` ni Streamlit aplikacijom. Klase primaju obične
tipizirane Python vrijednosti i ne poznaju JSON, web ili Streamlit. Budući
ulazni adapter može zato prevesti isti verzionirani mrežni dokument u domenske
objekte neovisno o tome dolazi li s web API-ja, iz datoteke ili iz Streamlita.

- `models.py` definira godišnje rasporede, emitere i njihova postrojenja za
  hvatanje, čvorove, dionice, zasebne pipeline/truck/rail specifikacije,
  komercijalno sudjelovanje emitera, utisne bušotine i skladišta.
- `flow.py` sprema eksplicitne godišnje tokove s obveznim `emitter_id`, provjerava
  bilancu mase za svaki `emitter × čvor × godina` te zajedničke kapacitete
  dionica i bušotina.
- `costs.py` vraća detaljan `emitter × dionica × godina` troškovni ledger.
  Stvarni udio protoka, rezervirani kapacitet, vlasništvo i ugovoreni udio
  fiksnog troška ostaju zasebni podaci. Interna tarifa ostaje vidljiva za
  obračun između sudionika, ali se ne dodaje ponovno konsolidiranom fizičkom
  trošku sustava.

`TransportLeg.owner_id` bilježi vlasnika svake dionice, dok
`LegParticipation` bilježi odnos konkretnog emitera prema toj dionici. Stvarna
količina nikada se ne sprema na dionicu kao jedan agregirani ulaz, nego u
emiterom označenom vremenskom ledgeru.

Kamionska specifikacija iz nosivosti, vožnji po kamionu dnevno i radnih dana
računa potreban broj punih vožnji dnevno i veličinu flote. Pipeline specifikacija
zasad sprema duljinu, kapacitet i projektne podatke; ne uvodi novu jednadžbu
horizontalnog pada tlaka.

Novi `StorageSite.nominal_capacity_t` trenutačno je opisni nameplate podatak i
sam ne prekida utiskivanje. Tlačni kriterij skladišta ostaje odgovornost budućeg
fizikalnog adaptera/injekcijskog modela.

Izolirani mrežni testovi pokreću se bez sadašnjeg scenarija i Streamlit testa:

```powershell
python -m unittest discover -s tests/network -p "test_*.py" -v
```

Referentni test ima emiter A od 400.000 t/god i emiter B od 300.000 t/god.
B svojih 300.000 t/god najprije prevozi privatnom kamionskom dionicom od 25 km,
a zatim istu masu zajedno s A kroz zajednički cjevovod od 40 km. Na cjevovodu
su stvarni udjeli A = 4/7 i B = 3/7, a na kamionskoj dionici B = 100 %. Zbroj
svih dioničkih protoka je 1.000.000 t/god, dok je jedinstvena masa utisnuta na
granici skladišta 700.000 t/god; zato se protoci uzastopnih dionica ne smiju
zbrajati i uspoređivati s utiskivanjem.

---

### `examples/economics_demo.py`

Runnable economic example. Instantiates three objects — `Emitter` (NEXE, 716 kt CO2/yr), `Transport` (NEXE → Poljana), and `Storage` (Poljana DSA) — sets their CAPEX/OPEX, calls `set_cash_flow()` on each, then exports a results DataFrame to `outputs/legacy/results_preview.html` and `outputs/legacy/results_preview.xlsx`.

---

### `inputs/examples/main_inputs.json`

Central input file for all engineering calculations. Each parameter is stored as `[value, unit, description]` and validated against `IOEndpoints.PARAM_METADATA` on load.

### Spremljeni Streamlit scenariji

Polje `scenario_name` nalazi se na početku Streamlit unosa i u glavnoj te
uncertainty JSON datoteci; zadana vrijednost je `GT-CCUS`. Svaki klik na
`Pokreni proračun` automatski sprema trenutačne ulaze u
`inputs/scenarios/last_inputs.json` te u novu arhivu oblika
`YYMMDD_HHmm_inputs.json`. Ako se više proračuna pokrene unutar iste minute,
arhive dobivaju nastavke `_2`, `_3`, ... i nijedna se postojeća arhiva ne
prepisuje.

Lijevi izbornik omogućuje pretraživanje prema nazivu scenarija, učitavanje te
brisanje točno odabrane arhive prikazane kao `ime scenarija, ime datoteke`.
Brisanje zahtijeva zasebnu potvrdu i ne dopušta brisanje `last_inputs.json`.
Na Streamlit Cloud instalaciji datoteke na lokalnom filesystemu instance mogu
nestati pri ponovnom pokretanju ili novom deploymentu; za trajnu višekorisničku
pohranu potrebno je naknadno povezati vanjsko spremište.

---

### `outputs/legacy/bhp.json`

Historical intermediate output: time series of `Time [yr]`, `BHP [bar]`, `dp [bar]`, CO2 density and viscosity at BHP, drainage radius `re`, `S_eff`, and `kr_co2`. The current engineering demo does not generate this file.

---

### `outputs/legacy/GT_CCS_yearly_df.xlsx`

Historical annual aggregated results spreadsheet (pressures, flow rates, power, temperatures). The current engineering demo does not generate this file.

---

### `examples/legacy/co2_well_pressure.py` and `examples/legacy/water_well_pressure.py`

Standalone exploratory scripts that implement the Colebrook-White pressure-drop integration directly (without the `VFP` class). Useful for quick manual validation of wellbore hydraulics. Note: these duplicate logic now refactored into `VFP.calculate_dp`.

---

### `examples/legacy/thermal_testing.py`

Standalone proof-of-concept for the Lauwerier thermal breakthrough model, later integrated into `Geothermal.calculate_production_temperature`. Includes an explicit loop and `scipy.special.erf` call.

---

## Quick start

```powershell
# Lokalno razvojno okruženje projekta
& "C:/webdev/CCUS_cluster/CCUS_cluster/.gt_ccs_venv/Scripts/Activate.ps1"

# Pokretanje integrirane aplikacije
python -m streamlit run app.py

# Provjera testova
python -m unittest discover -s tests -p "test_*.py" -v
```

---

## Sigurnosne kopije prije izmjene

Prije prve izmjene datoteka napravi se lokalni snapshot eksplicitno navedenih
datoteka. Skripta odbija direktorije, wildcard izraze i putanje izvan projekta,
ne prepisuje postojeći snapshot te nakon kopiranja provjerava SHA-256 hash.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command `
  "& '.\scripts\new_backup.ps1' -Source @('app.py','README.md','changelog.txt') -Reason 'Prije izmjene geotermalnog modela'"
```

Snapshot se sprema u `backups/YYYYMMDD-HHMMSSfff/`, uz `manifest.json` s
razlogom, vremenom, veličinom i hashom svake datoteke. Nakon izmjene njezin se
sažetak upisuje u `changelog.txt`, po mogućnosti uz identifikator snapshot
direktorija. Povrat se radi samo za izričito odabranu datoteku nakon provjere
hasha iz manifesta; nema automatskog skupnog povrata ni brisanja starih kopija.

Direktorij je lokalni rollback snapshot i zato je pravilom `/backups/` isključen
iz Gita. Ne štiti od gubitka cijelog diska ili workspacea; za to je potrebna i
vanjska sigurnosna kopija.

---

## Integracija tehničkog i ekonomskog modela

`services/ScenarioRunner` sada vodi jedan integrirani izračun. Fizikalni izlazi
pretvaraju se u godišnju tehničku tablicu, a zatim u odvojene i provjerljive
stavke novčanog toka.

- `emitter_emissions_annual` je autoritativna godišnja količina CO2; izvedene
  količine hvatanja, transporta, utiskivanja i skladištenja moraju joj biti
  jednake u aktivnoj godini.
- Kalendar razlikuje početak ulaganja, početak i kraj utiskivanja, kraj rada
  geotermalnog sustava te kraj monitoringa.
- Snage ORC-a, geotermalne pumpe i kompresora integriraju se trapeznim pravilom
  u MWh uz 8.766 sati po godini.
- Električna bilanca je `ORC − geotermalna pumpa − kompresor CO2`; višak se
  prodaje, a manjak kupuje.
- Ako potencijalni proizvodni GT WHP nije viši od izlaznog ORC tlaka `p_out`,
  cijeli geotermalni krug je isključen: proizvodni i reinjekcijski protok,
  pumpna snaga, ORC snaga i neto GT snaga jednaki su nuli.
- `p_out` je obvezan JSON parametar i uređiv je na vrhu Streamlit kartice
  `Bušotine i geotermija`, zajedno s ostalim ORC izlaznim uvjetima.
- Proizvodni geotermalni protok i dalje se računa uz korisnički zadani fiksni
  drawdown `bhp_dp`; ciljani proizvodni WHP nije uveden kao rubni uvjet.
- Za svaki raspoloživi vremenski moment rezultat prikazuje prosječnu aksijalnu
  brzinu geotermalne vode u proizvodnoj i utisnoj bušotini. Brzina je duljinski
  prosjek apsolutnih lokalnih brzina kroz jednake segmente VFP modela, a za
  isključeni geotermalni krug iznosi nula.
- Novčani tok zasebno prikazuje CAPEX i OPEX hvatanja, transporta, kompresora,
  skladištenja i geotermalnog sustava, monitoring, električnu energiju i
  vrijednost CO2.
- Troškovi se prvo uvećavaju zadanom inflacijom, a nominalni novčani tok zatim
  diskontira. Rezultati uključuju godišnji PV, kumulativni NPV, IRR te PV
  prihoda i troškova.
- U istom godišnjem prikazu uspoređuje se CCS scenarij s protuscenarijem bez
  CCS-a, čiji je rashod `−emisije × godišnja cijena CO2`.
- Godišnji novčani tok prikazuje se stupcima, kumulativni nediskontirani tok i
  NPV linijama, a prihod prodaje i inflacijski prilagođen rashod kupnje
  električne energije zasebnim provjerljivim komponentama.
- Višeserijski godišnji stupci prikazuju se grupirano, jedan uz drugi, bez
  zbrajanja. Legende koriste kratke oznake, a zaseban nominalni troškovni
  dijagram uključuje hvatanje, transport, kompresor, skladište, geotermiju,
  kupnju električne energije i monitoring nakon inflacijske prilagodbe.
- Svaki proračun ispisuje godišnju količinu utisnutog CO2, krajnji godišnji BHP
  CO2 utisne bušotine i vremenski ponderirani prosječni DSA tlak u konzolu i
  ASCII datoteku `calculation.log`. Količina se ispisuje kao cijeli broj, a oba
  tlaka na jednu decimalu. `result_active_year_CO2_quantity_constant` je
  provjera izračunatog godišnjeg niza, a ne ulaz modela.
- Zajednički rezultat tlakova prikazuje DSA tlak te BHP i WHP CO2 utisne,
  geotermalne proizvodne i geotermalne utisne bušotine na jednom vremenskom
  dijagramu i u tablici. Neaktivne bušotine nemaju prikazan tekući BHP/WHP.
- Godišnje relativne propusnosti vode i CO2 uzorkuju se na kraju kalendarske
  godine. Nakon utiskivanja drži se završno drenažno stanje jer imbibicija i
  histereza nisu uključene u postojeći model.
- Nazivna snaga kompresora jednaka je najvećoj izračunatoj potrebnoj snazi.
- Utiskivanje završava na najranijem od planiranog kraja, nazivnog kapaciteta
  skladišta i dopuštenog tlaka frakturiranja; rezultat sadrži razlog.
- U Streamlitu promjena razdoblja utiskivanja ili godišnje količine po potrebi
  automatski povećava `storage_capacity` u aktivnom JSON-u kako bi odabrana
  posljednja godina ostala ostvariva. Naknadno ručno smanjenje kapaciteta ili
  izravno učitan JSON s manjim kapacitetom i dalje namjerno skraćuje utiskivanje.
- Raspoloživosti kompresora, ORC-a i triju bušotina evidentirane su u ulazima;
  pripadni raspoloživi sati izvode se kao `8766 × raspoloživost`.
- Kartica `Tablice` omogućuje preuzimanje potpunog rezultata u JSON i Excel
  formatu, zajedno s aktivnim ulazima potrebnima za reprodukciju scenarija.

Bazna godina PV-a je početna godina ekonomike. IRR nema zaseban ulaz stope,
nego se izvodi iz nominalnog godišnjeg novčanog toka; pri više matematičkih
korijena rezultat tu dvosmislenost izričito označava. Horizontalni pipeline
model računa izlazni tlak i temperaturu za CO₂ i geotermalnu vodu. CO₂ endpoint
zasad je zasebna forward dijagnostika, dok GT endpoint mijenja pumpnu i ORC
snagu te ulaznu temperaturu utisnog VFP-a.

Raspoloživost još ne mijenja on-stream protok ni energiju. Za očuvanje jednake
godišnje mase CO2 pri raspoloživosti manjoj od jedan treba zasebno potvrditi
način povećanja protoka tijekom radnih sati i zajednički raspored opreme.

---

## Dependencies

| Package | Purpose |
|---|---|
| `numpy` | Array maths |
| `pandas` | DataFrames and Excel export |
| `scipy` | `fsolve`, `erf`, `cumtrapz` |
| `CoolProp` | Thermophysical fluid properties |
| `matplotlib` | Visualisation |
| `openpyxl` | Excel read/write |
| `streamlit` | Web korisničko sučelje |
