# GT-CCS – Geothermal-assisted Carbon-Capture-and-Storage Calculator

**GT-CCS** is a small, self-contained Python project that models the
cash-flow, savings and net-present-value (NPV) of a complete CCS chain
(emitter → transport → storage) while optionally offsetting energy needs
from geothermal resources.

The codebase is intentionally modular:

| Module | Responsibility |
| ------ | -------------- |
| **economics.py** | *Core time-series engine* – defines a light `Economics` base (stores CAPEX / OPEX arrays and `OPEX_per_ton`) **and** an optional `load_co2_price_scenario()` helper that supplies CO₂ price data for pessimistic (-1), conservative (0) and optimistic (+1) outlooks. |
| **CCS_chain.py** | Domain objects that **inherit** from `Economics`:<br>• `Emitter` (plant or industrial source)<br>• `Transport` (one or many legs)<br>• `Storage` (DSA / DHF). |
| **test.py** | A runnable example that instantiates:<br>• Emitter *NEXE* (716 kt CO₂ yr-¹)<br>• Storage *Poljana* (DSA)<br>• Links both to an `Economics` aggregator that computes payments, inflation-corrected payments, CO₂-tax, CCS savings and NPV from **2025 → 2040** with CCS coming online in **2028**. |
| **CO2_price_scenarios.csv** | Lookup table with annual CO₂ price trajectories (2025-2050) for all three scenarios. |

### Key project features

* **Time-series economics**  
  * Arrays span `start_year … end_year` (inclusive).  
  * **CAPEX** is placed as a lump sum in `CCS_start_year` by default.  
  * **OPEX** is auto-built from `OPEX_per_ton × emissions(t)` (zero before CCS starts).  

* **Scenario-based CO₂ prices**  
  Simple helper reads **CO2_price_scenarios.csv** and returns a NumPy
  array for the requested horizon and scenario flag.

* **Derived cash-flows** (all NumPy – vectorised, no slow loops)  
  * `payments` (CAPEX + OPEX)  
  * `payments_future_values` (inflation-corrected)  
  * `CO2_tax` (emissions × price)  
  * `CCS_savings` (tax − payments)  
  * `NPV` (cumulative, discounting with `interest_rate`)

* **Extensible**  
  Transport can hold multiple legs (`add_transport_section`).  
  Storage can store injection-rate time-series; emitters can apply custom
  `emissions_change()` growth curves.

### Quick start

```bash
# create & activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate        # Linux/Mac: source .venv/bin/activate

pip install numpy pandas        # minimal runtime deps

# run the example
python test.py
