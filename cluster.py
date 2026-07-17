import numpy as np
import pandas as pd
import CCS_chain as CCS
from economics import Economics
import json
import os
from pathlib import Path
from datetime import datetime


start_year = 2025           # globalno pocetak razmatranog perioda
end_year = 2040             # globalno kraj razmatranog perioda


json_folder = Path("ccs_emitters")

results_folder = Path("CCS_cluster_results")
results_folder.mkdir(exist_ok=True)

summary = []

for json_file_path in json_folder.glob("*.json"):
    print(f"Processing file: {json_file_path}")
    
    with open(json_file_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    engineering = config["engineering"]
    emitter_data = config["emitters"][0]
    transport_data = config["transport"]
    storage_data = config["storage"]
    economics_data = config["economics"]

    
    # 1) kreiraj objekt emitera iz json konfiguracije
    emitter = CCS.Emitter(
        name=emitter_data["name"],
        emissions=emitter_data["emissions"],
        start_year=start_year,
        end_year=end_year,
    )
    emitter.CCS_start_year = emitter_data["CCS_start_year"]
    emitter.capture_technology = emitter_data["capture_technology"]
    emitter.CAPEX = emitter_data["CAPEX"]
    emitter.OPEX_per_ton = emitter_data["OPEX_per_ton"]

    emitter.set_OPEX()
    emitter.set_cash_flow()



    # 2) kreiraj objekt transporta
    transport = CCS.Transport(
        start_year=start_year,
        end_year = end_year
        )

    transport.section_name = f"{emitter.name} to {storage_data['name']}"
    transport.flow_rate = emitter.emissions
    transport.CCS_start_year = emitter.CCS_start_year
    transport.CAPEX = transport_data["CAPEX"]
    transport.OPEX_per_ton = transport_data["OPEX_per_ton"]
    transport.set_OPEX(CO2_flow=emitter.emissions)
    transport.set_cash_flow()

    

    # 3) kreiraj objekt skladista
    storage = CCS.Storage(
        name=storage_data["name"],
        storage_type=storage_data["storage_type"],
        capacity=storage_data["capacity"],
        start_year=start_year,
        end_year=end_year,
        CCS_start_year=emitter.CCS_start_year
    )


    storage.CCS_start_year = emitter.CCS_start_year
    storage.CAPEX = storage_data["CAPEX"]
    storage.OPEX_per_ton = storage_data["OPEX_per_ton"]
    storage.set_OPEX(CO2_flow=emitter.emissions)
    storage.set_cash_flow()


    


    npv = emitter.NPV - transport.NPV - storage.NPV
    print(f"Total NPV for {emitter.name} cluster: {npv}")
    
    years = list(range(start_year, end_year + 1))
    objects = [emitter, transport, storage]
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

    payments_fv = emitter.payments_future_values + transport.payments_future_values + storage.payments_future_values

    # Create the DataFrame
    df = pd.DataFrame(data, columns=columns)
    
    output_name = json_file_path.stem  # Get the base name without extension
    df.to_html(results_folder / f'results_preview_{output_name}.html', index=False)
    df.to_excel(results_folder / f'results_preview_{output_name}.xlsx', index=False)
    
    summary.append({
        "emitter": emitter.name,
        "transport": transport.section_name,
        "storage": storage.name,
        "total_NPV": npv
    })
    
summary_df = pd.DataFrame(summary)    
summary_df.to_excel(results_folder /'summary_results.xlsx', index=False)    
    
print("Processing completed. Results saved to HTML and Excel files.")