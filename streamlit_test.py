import streamlit as st
import json
import subprocess
import sys
import pandas as pd 
import os


st.set_page_config (page_title="GT CCS + CCS cluster economics", page_icon=":smile:", layout="wide")
st.title("GT CCS + CCS cluster economics")
st.write("GT CCS + CCS cluster economics")


st.sidebar.title("GT CCS + CCS cluster economics")  
page = st.sidebar.radio("Odabir modela", ["home","GT_CCS", "ekonomika CCS klastera",])
st.markdown("""
            Proračun integriranog GT + CCS sustava i CCS klastera.
            ### Proračun integriranog GT + CCS sustava
            - home
            - GT_CCS model
            - ekonomika CCS klastera
             odabrati model iz izbornika.""")

if page == "home":
    st.write("Dobrodošli u GT CCS + CCS cluster economics")
    st.write("Odaberite model iz izbornika.")   
    
elif page == "GT_CCS":
    st.title("GT_CCS model")
    with open("reservoir_inputs.json","r", encoding="utf-8") as f:
        reservoir_data = json.load(f)
    rows = []
    for key, value in reservoir_data.items():
        rows.append({"Parametar": key, "Vrijednost": value[0], "Mjerna jedinica": value[1],"opis": value[2]})
    df = pd.DataFrame(rows)
    st.dataframe(df)    
    
    if st.button("Run reservior model"):
        st.info("GT_CCS model je pokrenut. Rezultati su spremljeni u datoteku 'reservoir_results.json'.")
        result = subprocess.run([sys.executable, 'GT_CCS_engineering.py'], capture_output=True, text=True)
        st.write(result.stdout)
        st.write(result.stderr) 
    
        if result.returncode == 0:
           
            st.success("GT_CCS model je uspješno završen.")
           
            st.image("time_vs_co2_stored_bhp_whp_dsa.png", caption="Time vs CO2 stored, BHP, WHP, DSA")
            st.image("time_vs_geothermal_co2_bhp_whp_comparison.png", caption="Time vs Geothermal CO2, BHP, WHP comparison")
            st.image("time_vs_geothermal_flow_temperature.png", caption="Time vs Geothermal flow temperature")
            st.image("time_vs_power_bhp_pDSA.png", caption="Time vs Power, BHP, pDSA")
            st.image("time_vs_power.png", caption="Time vs Power")
            st.image("s_eff_vs_co2_stored_kr_co2.png", caption="s_eff vs CO2 stored, kr_CO2")
        
        else:     
           
            st.error("Došlo je do greške prilikom pokretanja modela ležišta.")  
            st.code(result.stderr)
            
elif page == "ekonomika CCS klastera":
    st.title("ekonomika CCS klastera")
    st.write("Proračun troškova CCS klastera")
    
    if st.button("Run CCS cluster economics model"):
        st.info("CCS cluster economics model is running.")
        result = subprocess.run([sys.executable, 'test.py'], capture_output=True, text=True)
        st.write(result.stdout)
        st.write(result.stderr) 
    
        if result.returncode == 0:
            st.success("CCS cluster economics model completed successfully.")
            result_df = pd.read_excel("results_preview.xlsx")
            st.dataframe(result_df, use_container_width=True)
        else:     
            st.error("An error occurred while running the CCS cluster economics model.")  
            st.code(result.stderr)
            
   
    
    