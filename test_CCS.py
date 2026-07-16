import numpy as np
import pandas as pd
import CCS_chain as CCS
from economics import Economics

start_year = 2025           # globalno pocetak razmatranog perioda
end_year = 2040             # globalno kraj razmatranog perioda
nexe_CCS_start = 2028       # specifican start pojedinog emitera
nexe_emissions = 716*1000   # t
nexe_CAPEX = 447245393.63   # eur
nexe_capture_OPEX = 25      # eur/t


# 1) kreiraj objekt emitera
nexe = CCS.Emitter(
    name="NEXE",
    emissions = nexe_emissions,         # single-value, or expand to match (end_year - start_year + 1)
    start_year=start_year,
    end_year=end_year,
)
nexe.CCS_start_year = nexe_CCS_start
nexe.capture_technology = "OXY"         # "PI", "NI", or "OXY"
nexe.CAPEX = nexe_CAPEX
nexe.OPEX_per_ton = nexe_capture_OPEX
nexe.set_OPEX()
nexe.set_cash_flow()

# 2) kreiraj objekt transporta
nexe_to_poljana = CCS.Transport(
    start_year=start_year,
    end_year = end_year
    )

nexe_to_poljana.section_name = "NEXE to Poljana"
nexe_to_poljana.flow_rate = nexe_emissions
nexe_to_poljana.CCS_start_year = nexe_CCS_start
nexe_to_poljana.CAPEX = 25e6
nexe_to_poljana.OPEX_per_ton = 15
nexe_to_poljana.set_OPEX(CO2_flow=nexe.emissions)
nexe_to_poljana.set_cash_flow()

# 3) kreiraj objekt skladista
poljana = CCS.Storage(
    name="Poljana",
    storage_type="DSA",  # or "DHF"
    capacity=1e6,
    start_year=start_year,
    end_year=end_year,
    CCS_start_year=nexe_CCS_start
)


poljana.CCS_start_year = nexe_CCS_start
poljana.CAPEX = 150e6
poljana.OPEX_per_ton = 10
poljana.set_OPEX(CO2_flow=nexe.emissions)
poljana.set_cash_flow()


print (nexe.emissions)
print (nexe.CAPEX)
print (nexe.OPEX)
print (nexe.NPV)

print (nexe_to_poljana.CAPEX)
print (nexe_to_poljana.OPEX)
print (nexe_to_poljana.NPV)

print (poljana.CAPEX)
print (poljana.OPEX)
print (poljana.NPV)


npv = nexe.NPV - nexe_to_poljana.NPV - poljana.NPV

years = list(range(start_year, end_year + 1))
objects = [nexe, nexe_to_poljana, poljana]
properties = ["payments", "emissions", "CAPEX", "OPEX", "NPV"]

# Create a DataFrame
data = []

for obj in objects:
    for prop in properties:
        value = getattr(obj, prop, None)  # Dynamically get the property
        if value is not None:  # Only include properties that exist
            row = [f"{type(obj).__name__}.{prop}", type(obj).__name__] + list(value)
            data.append(row)

# Define column names
columns = ["object.property", "object"] + years

payments_fv = nexe.payments_future_values + nexe_to_poljana.payments_future_values + poljana.payments_future_values

# Create the DataFrame
df = pd.DataFrame(data, columns=columns)
df.to_html('results_preview.html', index=False)
df.to_excel('results_preview.xlsx', index=False)
