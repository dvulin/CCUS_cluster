import json
from collections.abc import Mapping
from copy import deepcopy

import numpy as np
from .metadata import ParamMetadata

class IOEndpoints(ParamMetadata):
    ENGINEERING_PARAM_METADATA = {
        'm_dot_annual': ('ktpa', 'Godišnji maseni protok utiskivanja CO2'),
        'rw_co2': ('m', 'Radijus utisne CO2 bušotine'),
        'rw_geothermal_production': ('m', 'Radijus proizvodne geotermalne bušotine'),
        'rw_geothermal_injection': ('m', 'Radijus utisne geotermalne bušotine'),
        'A': ('m^2', 'Površina akvifera'),
        'h_ef': ('m', 'Efektivna debljina akvifera'),
        'poro': ('-', 'Poroznost akvifera (bezdimenzionalna)'),
        'h_ref': ('m', 'Referentna dubina bušotine za VFP proračun'),
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

    ECONOMICS_PARAM_METADATA = {
        'economics_start_year': ('year', 'Početna godina ekonomskog razdoblja'),
        'economics_end_year': ('year', 'Završna godina ekonomskog razdoblja'),
        'economics_ccs_start_year': ('year', 'Početna godina rada CCS lanca'),
        'economics_interest_rate': ('-', 'Kamatna stopa kao decimalni broj'),
        'economics_inflation_rate': ('-', 'Stopa inflacije kao decimalni broj'),
        'economics_co2_price_scenario': ('-', 'CO2 cjenovni scenarij: -1, 0 ili 1'),
        'emitter_name': ('-', 'Naziv emitera'),
        'emitter_emissions_annual': ('tCO2/year', 'Godišnje emisije emitera'),
        'emitter_capture_technology': ('-', 'Tehnologija hvatanja: PI, NI ili OXY'),
        'emitter_capex': ('EUR', 'CAPEX sustava hvatanja CO2'),
        'emitter_opex_per_ton': ('EUR/tCO2', 'OPEX hvatanja po toni CO2'),
        'emitter_emissions_change_a': ('-', 'Faktor promjene emisija a'),
        'emitter_emissions_change_c': ('-', 'Eksponent promjene emisija c'),
        'transport_section_name': ('-', 'Naziv transportne dionice'),
        'transport_flow_rate': ('tCO2/year', 'Godišnji protok CO2 kroz transportnu dionicu'),
        'transport_capex': ('EUR', 'CAPEX transportne dionice'),
        'transport_opex_per_ton': ('EUR/tCO2', 'OPEX transporta po toni CO2'),
        'storage_name': ('-', 'Naziv skladišta'),
        'storage_type': ('-', 'Tip skladišta: DSA ili DHF'),
        'storage_capacity': ('tCO2', 'Nazivni kapacitet skladišta CO2'),
        'storage_capex': ('EUR', 'CAPEX skladišta'),
        'storage_opex_per_ton': ('EUR/tCO2', 'OPEX skladištenja po toni CO2'),
        'co2_price_start_year': ('year', 'Početna godina CO2 cjenovnih putanja'),
        'co2_price_pessimistic': ('EUR/tCO2', 'Pesimistična CO2 cjenovna putanja'),
        'co2_price_conservative': ('EUR/tCO2', 'Konzervativna CO2 cjenovna putanja'),
        'co2_price_optimistic': ('EUR/tCO2', 'Optimistična CO2 cjenovna putanja'),
        'economics_co2_price_mode': ('-', 'Odabrana CO2 cjenovna putanja ili prilagođeni scenarij'),
        'economics_custom_price_function': ('-', 'Funkcija prilagođene CO2 cjenovne putanje'),
        'economics_custom_price_p0': ('EUR/tCO2', 'Početna cijena prilagođene CO2 putanje'),
        'economics_custom_linear_growth': ('EUR/tCO2/year', 'Godišnji linearni porast cijene CO2'),
        'economics_custom_log_amplitude': ('EUR/tCO2', 'Amplituda logaritamskog porasta cijene CO2'),
        'economics_custom_log_rate': ('1/year', 'Stopa logaritamskog porasta cijene CO2'),
        'economics_custom_power_coefficient': ('EUR/tCO2', 'Koeficijent power-law porasta cijene CO2'),
        'economics_custom_power_exponent': ('-', 'Eksponent power-law porasta cijene CO2'),
    }

    PARAM_METADATA = {
        **ENGINEERING_PARAM_METADATA,
        **ECONOMICS_PARAM_METADATA,
    }
    REQUIRED_PARAMETERS = tuple(ENGINEERING_PARAM_METADATA)
    PARAM_TYPES = {
        'economics_start_year': int,
        'economics_end_year': int,
        'economics_ccs_start_year': int,
        'economics_co2_price_scenario': int,
        'emitter_name': str,
        'emitter_capture_technology': str,
        'transport_section_name': str,
        'storage_name': str,
        'storage_type': str,
        'co2_price_start_year': int,
        'co2_price_pessimistic': list,
        'co2_price_conservative': list,
        'co2_price_optimistic': list,
        'economics_co2_price_mode': str,
        'economics_custom_price_function': str,
    }
    PARAM_CHOICES = {
        'economics_co2_price_scenario': {-1, 0, 1},
        'economics_co2_price_mode': {
            'pessimistic',
            'conservative',
            'optimistic',
            'custom',
        },
        'economics_custom_price_function': {'linear', 'logarithmic', 'power_law'},
        'emitter_capture_technology': {'PI', 'NI', 'OXY'},
        'storage_type': {'DSA', 'DHF'},
    }

    def __init__(self, input_source):
        super().__init__()
        if isinstance(input_source, Mapping):
            data = deepcopy(dict(input_source))
        else:
            try:
                with open(input_source, 'r', encoding='utf-8') as f:
                    content = f.read()
                    try:
                        data = json.loads(content)
                    except json.JSONDecodeError as e:
                        print(f"JSON parsing error: {e}")
                        print(f"Error at line {e.lineno}, column {e.colno}: {e.msg}")
                        print(f"Content near error: {content[max(0, e.pos-20):e.pos+20]}")
                        raise
            except UnicodeDecodeError:
                print(f"UTF-8 decoding failed for {input_source}.")
                raise
            except FileNotFoundError:
                print(f"Error: File not found at {input_source}")
                raise

        # Backward compatibility for scenarios created before the three well
        # radii were separated. New scenarios should use the explicit keys.
        if 'rw' in data:
            legacy_radius = data['rw'][0]
            radius_descriptions = {
                'rw_co2': 'Radijus utisne CO2 bušotine',
                'rw_geothermal_production': 'Radijus proizvodne geotermalne bušotine',
                'rw_geothermal_injection': 'Radijus utisne geotermalne bušotine',
            }
            for key, description in radius_descriptions.items():
                data.setdefault(key, [legacy_radius, 'm', description])
        
        # Engineering parameters remain required for backward-compatible runs.
        for param in self.REQUIRED_PARAMETERS:
            self.params[param] = self._validate(
                data,
                param,
                self.PARAM_TYPES.get(param, float),
                self.PARAM_METADATA[param][0],
            )

        # Economics parameters are optional until the economics runner is connected.
        for param in self.ECONOMICS_PARAM_METADATA:
            if param in data:
                self.params[param] = self._validate(
                    data,
                    param,
                    self.PARAM_TYPES.get(param, float),
                    self.PARAM_METADATA[param][0],
                )
        
        # Derived attributes
        self.m_dot = self.m_dot_annual * 1e6 / (365.25 * 24 * 3600)  # kg/s
        # Existing engineering classes still expose ``rw`` internally. The
        # runner assigns the role-specific radius to each model instance.
        self.rw = self.rw_co2
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
        if data[key][1] != unit:
            raise ValueError(f"Invalid unit for {key}: expected {unit}, got {data[key][1]}")

        value = data[key][0]
        if type_ is float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Invalid type for {key}: expected number")
            validated_value = float(value)
        elif type_ is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Invalid type for {key}: expected integer")
            validated_value = value
        elif type_ is str:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Invalid type for {key}: expected non-empty string")
            validated_value = value
        elif type_ is list:
            if not isinstance(value, list) or not value:
                raise ValueError(f"Invalid type for {key}: expected numeric list")
            if any(
                isinstance(item, bool) or not isinstance(item, (int, float))
                for item in value
            ):
                raise ValueError(f"Invalid type for {key}: expected numeric list")
            validated_value = [float(item) for item in value]
        else:
            raise TypeError(f"Unsupported validation type for {key}: {type_}")

        if key in self.PARAM_CHOICES and validated_value not in self.PARAM_CHOICES[key]:
            choices = sorted(self.PARAM_CHOICES[key], key=str)
            raise ValueError(f"Invalid value for {key}: expected one of {choices}")

        return validated_value
