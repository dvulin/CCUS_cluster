# GT-CCS – Geothermal-assisted Carbon Capture and Storage Calculator

**GT-CCS** is a modular Python toolkit for engineering and economic analysis of a complete CCS chain (emitter → transport → storage) with optional integration of a geothermal doublet system. The codebase is split into two loosely coupled wings:

- **Engineering wing** – `engineering/` package + `examples/engineering_demo.py`: reservoir material balance, wellbore hydraulics, geothermal IPR, fluid thermodynamics and power calculations; `inputs/` contains loading and metadata, while `outputs/` contains visualization.
- **Economics wing** – `economics/economics.py` + `domain/ccs_chain.py` + `examples/economics_demo.py`: time-series CAPEX/OPEX cash flows, CO2 tax, CCS savings, NPV.

---

## Repository structure

```
CCUS_cluster/
├── ccs_utilities/              # Retained empty legacy directory
│   └── .gitkeep
├── domain/                     # Domain entities
│   ├── __init__.py
│   └── ccs_chain.py
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
│   └── pipeline.py
├── outputs/                    # Result visualization helpers
│   ├── __init__.py
│   ├── visualization.py
│   └── legacy/                 # Historical generated results
│       ├── bhp.json
│       ├── GT_CCS_yearly_df.xlsx
│       ├── results_preview.html
│       ├── results_preview.xlsx
│       └── s_eff_vs_co2_stored_kr_co2.png
├── economics/                  # Economic calculations package
│   ├── __init__.py
│   └── economics.py            # Economic base class
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
├── services/                   # Reserved orchestration package
├── pages/                      # Reserved Streamlit pages
├── tests/                      # Reserved automated tests
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
| `h_ref` | m | Reference depth |
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

---

### `engineering/pipeline.py` – class `Pipeline(ParamMetadata)`

Stub for surface pipeline pressure drop calculation. Currently holds the `m_dot` parameter and a `calculate_pressure_drop` placeholder (not yet implemented).

---

### `engineering/wellbore.py` – class `VFP(ParamMetadata)`

Vertical Flow Performance class. Calculates the pressure profile along a CO2 injection or geothermal production/injection well using a step-wise integration of gravitational and frictional pressure gradients.

**Parameters:** `rw`, `re`, `h_ef`, `h_ref`, `k`, `m_dot`

| Method | Description |
|---|---|
| `colebrook(D, Re, e)` | Solves the Colebrook-White implicit equation via `scipy.optimize.fsolve`; returns the Darcy-Weisbach friction factor. |
| `calculate_dp(fluid, m_dot, bhp, whp, T_C, depth_total, nsteps, pipe_diameter, epsilon)` | Integrates from BHP→WHP (or WHP→BHP depending on which pressure is given). Returns the unknown end-point pressure in bar. Handles both production and injection directions. |

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

### `examples/economics_demo.py`

Runnable economic example. Instantiates three objects — `Emitter` (NEXE, 716 kt CO2/yr), `Transport` (NEXE → Poljana), and `Storage` (Poljana DSA) — sets their CAPEX/OPEX, calls `set_cash_flow()` on each, then exports a results DataFrame to `outputs/legacy/results_preview.html` and `outputs/legacy/results_preview.xlsx`.

---

### `inputs/examples/main_inputs.json`

Central input file for all engineering calculations. Each parameter is stored as `[value, unit, description]` and validated against `IOEndpoints.PARAM_METADATA` on load.

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

```bash
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # Linux/macOS

# Install dependencies
pip install numpy pandas coolprop scipy matplotlib openpyxl

# Run engineering simulation
python -m examples.engineering_demo

# Run economic example
python -m examples.economics_demo
```

---

## TODO – Connecting Economics with Engineering Calculations

The two wings currently run independently: the engineering wing produces physical outputs (BHP, power, flow rates, temperatures), while the economics wing consumes user-supplied CAPEX/OPEX scalars. The steps below propose a concrete integration path.

### Step 1 – Derive OPEX from engineering outputs

The most direct connection. `Power.calculate_compression_power` and `Power.calculate_ORC_power` already return annual energy demand in kW. Convert to yearly EUR costs using electricity prices:

```python
# In examples/engineering_demo.py (or a new integration service)
energy_price_eur_per_kWh = 0.08
annual_compression_cost = vfp_CO2_df['CO2 comp. P [kW]'] * 8760 * energy_price_eur_per_kWh
annual_gt_revenue = vfp_gt_df['net power GT, kW'] * 8760 * energy_price_eur_per_kWh
```

Pass these arrays directly into `Economics.set_OPEX()` instead of a flat `OPEX_per_ton` scalar.

### Step 2 – Time-align engineering and economic arrays

Engineering outputs are indexed in fractional years (from material balance time steps); economic arrays are indexed in integer calendar years. Write a helper that resamples or interpolates engineering DataFrames to annual resolution before passing them to `domain.ccs_chain` objects.

### Step 3 – Make `Storage` aware of injection rate from material balance

`Storage.injection_rate` currently accepts a constant or a manually supplied list. Feed it directly from `mbal_df['m_CO2, Mt']` differentiated to annual increments, so economic calculations reflect actual injection ramp-up.

### Step 4 – Introduce a `ScenarioRunner` orchestrator class

Create `services/ScenarioRunner`, which owns both an `IOEndpoints` instance and the three `domain.ccs_chain` objects, and exposes a single `run()` method:

```python
class ScenarioRunner:
    def __init__(self, json_path, economic_params):
        self.inputs = IOEndpoints(json_path)
        self.emitter = Emitter(...)
        self.transport = Transport(...)
        self.storage = Storage(...)

    def run(self):
        # 1. Engineering simulation
        # 2. Resample to annual
        # 3. Inject costs and revenues into economics objects
        # 4. Compute NPV
        # 5. Return combined results DataFrame
```

This makes `examples/economics_demo.py` a single call and enables parameter sweeps.

### Step 5 – Add geothermal revenue to the NPV calculation

Net geothermal power (`vfp_gt_df['net power GT, kW']`) represents a revenue stream that currently does not appear in the economic model. Introduce a `GTRevenue` subclass (or extend `Emitter`) that adds `annual_gt_revenue` as a negative OPEX (i.e. cost offset) in `_calc_CCS_savings`.

### Step 6 – Sensitivity / scenario analysis

Once steps 1–5 are in place, it becomes straightforward to run Monte Carlo or parameter sweeps over:
- CO2 price scenarios (already supported: pessimistic / conservative / optimistic)
- Electricity price
- ORC efficiency `eta`
- Reservoir permeability `k` and storage efficiency `E_eff`
- CAPEX uncertainty (±20 %)

Collect NPV distributions across scenarios and plot them using the existing `Visualization` class or a new dedicated method.

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
