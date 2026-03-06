import json
import numpy as np
from .metadata import ParamMetadata

class IOEndpoints(ParamMetadata):
    PARAM_METADATA = {
        'm_dot_annual': ('ktpa', 'Godišnji maseni protok utiskivanja CO2'),
        'rw': ('m', 'Radijus bušotine'),
        'A': ('m^2', 'Površina akvifera'),
        'h_ef': ('m', 'Efektivna debljina akvifera'),
        'poro': ('-', 'Poroznost akvifera (bezdimenzionalna)'),
        'h_ref': ('m', 'Referentna dubina sloja'),
        'h_top': ('m', 'Minimalna dubina sloja (vrh akvifera)'),
        't': ('°C', 'Temperatura sloja'),
        'p_ref': ('bar', 'Referentni početni tlak DSA'),
        'dp': ('bar', 'Korak tlaka za niz tlakova'),
        'c_p': ('1/bar', 'Stlačivost pora'),
        'sal': ('gNaCl/L', 'Salinitet'),
        'k': ('m^2', 'Prosječna propusnost'),
        't_out': ('°C', 'ORC izlazna temperatura'),
        'p_out': ('bar', 'ORC izlazni tlak'),
        'eta': ('-', 'ORC učinkovitost (bezdimenzionalna)'),
        'd_doublet': ('m', 'udaljenost proizvodne i utisne geotermalne bušotine'),
        'bhp_dp': ('bar', 'Pad tlaka na dnu geotermalne proizvodne bušotine'),
        'p_comp_in': ('bar', 'Ulazni tlak u kompresiju CO2'),
        't_comp_in': ('°C', 'Ulazna temperatura u kompresiju CO2'),
        'E_eff' : ('-', 'Efikasnost skladištenja CO2 u akviferu'),
        'S_plume_core' : ('-','Osnovno zasićenje s CO2 u zoni bušotine'),
        'Sw_i': ('-', 'Minimalno zasićenje vodom'),
        'krw_max': ('-', 'Maksimalna relativna propusnost za vodu'),
        'krg_max': ('-', 'Maksimalno zasićenje za plin (CO2, zakrivljenost kr_CO2 krivulje)'),
        'nw': ('-', 'Corey-ev koeficijent za vodu (zakrivljenost krw krivulje)'),
        'ng': ('-', 'Corey-ev koeficijent za plin (CO2, zakrivljenost kr_CO2 krivulje)'),
        'krw_min': ('-', 'Minimalna relativna propusnost za vodu (da se izbjegne problem kr = 0)'),
        'krg_min': ('-', 'Minimalna relativna propusnost za plin (da se izbjegne problem kr = 0)')
    }

    def __init__(self, file_path):
        super().__init__()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                try:
                    data = json.loads(content)
                except json.JSONDecodeError as e:
                    print(f"JSON parsing error: {e}")
                    print(f"Error at line {e.lineno}, column {e.colno}: {e.msg}")
                    print(f"Content near error: {content[max(0, e.pos-20):e.pos+20]}")
                    raise
        except UnicodeDecodeError:
            print(f"UTF-8 decoding failed for {file_path}.")
            raise
        except FileNotFoundError:
            print(f"Error: File not found at {file_path}")
            raise
        
        # Load parameters
        for param in self.PARAM_METADATA:
            self.params[param] = self._validate(data, param, float, self.PARAM_METADATA[param][0])
        
        # Derived attributes
        self.m_dot = self.m_dot_annual * 1e6 / (365.25 * 24 * 3600)  # kg/s
        self.re = (self.A / np.pi) ** 0.5  # m
        self.V_p_ref = self.A * self.h_ef * self.poro  # m^3
        self.V_w_ref = self.V_p_ref  # m^3
        self.p_max = 0.18 * self.h_top  # bar
        self.g = 9.80665  # m/s^2
    
    def _validate(self, data, key, type_, unit):
        """Validate input parameter."""
        if key not in data:
            raise ValueError(f"Missing {key} in input data")
        if not isinstance(data[key], list) or len(data[key]) < 2:
            raise ValueError(f"Invalid format for {key}: expected [value, unit, description]")
        if not isinstance(data[key][0], (int, float)):
            raise ValueError(f"Invalid type for {key}: expected number (int or float)")
        if data[key][1] != unit:
            raise ValueError(f"Invalid unit for {key}: expected {unit}, got {data[key][1]}")
        # Convert to float if int
        return float(data[key][0])