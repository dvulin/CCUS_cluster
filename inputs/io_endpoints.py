import json
import math
from collections.abc import Mapping
from copy import deepcopy

from .metadata import ParamMetadata

class IOEndpoints(ParamMetadata):
    ENGINEERING_PARAM_METADATA = {
        'm_dot_annual': ('ktpa', 'Izvedena godišnja količina CO2 za utiskivanje'),
        'rw_co2': ('m', 'Radijus utisne CO2 bušotine'),
        'rw_geothermal_production': ('m', 'Radijus proizvodne geotermalne bušotine'),
        'rw_geothermal_injection': ('m', 'Radijus utisne geotermalne bušotine'),
        'epsilon': ('m', 'Apsolutna hrapavost bušotinske cijevi u VFP proračunu'),
        'A': ('m^2', 'Površina akvifera'),
        'h_ef': ('m', 'Efektivna debljina akvifera'),
        'poro': ('-', 'Poroznost akvifera (bezdimenzionalna)'),
        'h_ref': ('m', 'Kompatibilni naziv za dubinu CO2 bušotine'),
        'h_ref_co2': ('m', 'Referentna dubina utisne CO2 bušotine za VFP proračun'),
        'h_ref_geothermal_production': (
            'm',
            'Referentna dubina proizvodne geotermalne bušotine za VFP proračun',
        ),
        'h_ref_geothermal_injection': (
            'm',
            'Referentna dubina utisne geotermalne bušotine za VFP proračun',
        ),
        'h_top': ('m', 'Minimalna dubina sloja (vrh akvifera)'),
        't': ('°C', 'Temperatura sloja'),
        'p_ref': ('bar', 'Referentni početni tlak DSA'),
        'dp': ('bar', 'Korak tlaka za niz tlakova'),
        'c_p': ('1/bar', 'Stlačivost pora'),
        'sal': ('gNaCl/L', 'Salinitet'),
        'k': ('m^2', 'Prosječna propusnost'),
        't_out': ('°C', 'ORC izlazna temperatura'),
        'p_out': ('bar', 'ORC izlazni tlak'),
        'eta': ('-', 'ORC učinkovitost (kompatibilni naziv za eta_orc)'),
        'eta_orc': ('-', 'ORC učinkovitost (bezdimenzionalna)'),
        'eta_gt_injection_pump': ('-', 'Učinkovitost geotermalne utisne pumpe'),
        'eta_co2_compressor_isentropic': ('-', 'Izentropska učinkovitost kompresora CO2'),
        'eta_co2_dense_phase_pump': ('-', 'Učinkovitost pumpe CO2 u gustoj fazi'),
        'co2_compressor_availability': ('-', 'Raspoloživost kompresora CO2'),
        'co2_injection_well_availability': ('-', 'Raspoloživost utisne CO2 bušotine'),
        'orc_availability': ('-', 'Raspoloživost ORC postrojenja'),
        'geothermal_production_well_availability': (
            '-',
            'Raspoloživost proizvodne geotermalne bušotine',
        ),
        'geothermal_injection_well_availability': (
            '-',
            'Raspoloživost utisne geotermalne bušotine',
        ),
        'fracture_pressure_gradient': (
            'bar/m',
            'Gradijent tlaka frakturiranja pokrovnih naslaga',
        ),
        'd_doublet': (
            'm',
            'Razmak geotermalnog para i duljina površinskog transporta vode',
        ),
        'geothermal_pipeline_inner_diameter_m': (
            'm',
            'Unutarnji promjer geotermalnog cjevovoda',
        ),
        'geothermal_pipeline_roughness_m': (
            'm',
            'Apsolutna hrapavost geotermalnog cjevovoda',
        ),
        'geothermal_pipeline_elbows_90_count': (
            '-',
            'Broj koljena geotermalnog cjevovoda od 90 stupnjeva',
        ),
        'geothermal_pipeline_elbows_45_count': (
            '-',
            'Broj koljena geotermalnog cjevovoda od 45 stupnjeva',
        ),
        'geothermal_pipeline_elbows_30_count': (
            '-',
            'Broj koljena geotermalnog cjevovoda od 30 stupnjeva',
        ),
        'pipeline_environment_type': (
            '-',
            'Vanjski uvjeti cjevovoda: zrak ili tlo',
        ),
        'pipeline_ambient_temperature_c': (
            '°C',
            'Temperatura okoliša cjevovoda',
        ),
        'pipeline_environment_thermal_conductivity_w_m_k': (
            'W/(m K)',
            'Toplinska vodljivost okoliša cjevovoda',
        ),
        'pipeline_environment_volumetric_heat_capacity_j_m3_k': (
            'J/(m^3 K)',
            'Volumetrijski toplinski kapacitet okoliša cjevovoda',
        ),
        'pipeline_burial_depth_m': (
            'm',
            'Dubina osi ukopanog cjevovoda',
        ),
        'pipeline_external_heat_transfer_coefficient_w_m2_k': (
            'W/(m^2 K)',
            'Vanjski koeficijent prijelaza topline cjevovoda',
        ),
        'pipeline_wall_thickness_m': ('m', 'Debljina stijenke cjevovoda'),
        'pipeline_wall_thermal_conductivity_w_m_k': (
            'W/(m K)',
            'Toplinska vodljivost stijenke cjevovoda',
        ),
        'pipeline_insulation_thickness_m': ('m', 'Debljina izolacije cjevovoda'),
        'pipeline_insulation_thermal_conductivity_w_m_k': (
            'W/(m K)',
            'Toplinska vodljivost izolacije cjevovoda',
        ),
        'bhp_dp': ('bar', 'Pad tlaka na dnu geotermalne proizvodne bušotine'),
        'p_comp_in': ('bar', 'Ulazni tlak u kompresiju CO2'),
        't_comp_in': ('°C', 'Ulazna temperatura u kompresiju CO2'),
        'E_eff' : ('-', 'Učinkovitost skladištenja CO2 u akviferu'),
        'S_plume_core' : ('-','Osnovno zasićenje s CO2 u zoni bušotine'),
        'Sw_i': ('-', 'Minimalno zasićenje vodom'),
        'krw_max': ('-', 'Maksimalna relativna propusnost za vodu'),
        'krg_max': ('-', 'Maksimalna relativna propusnost za CO2'),
        'nw': ('-', 'Corey-ev koeficijent za vodu (zakrivljenost krw krivulje)'),
        'ng': ('-', 'Corey-ev koeficijent za plin (CO2, zakrivljenost kr_CO2 krivulje)'),
        'krw_min': ('-', 'Minimalna relativna propusnost za vodu (da se izbjegne problem kr = 0)'),
        'krg_min': ('-', 'Minimalna relativna propusnost za plin (da se izbjegne problem kr = 0)')
    }

    ECONOMICS_PARAM_METADATA = {
        'economics_start_year': ('year', 'Početna godina ekonomskog razdoblja'),
        'economics_end_year': ('year', 'Završna godina ekonomskog razdoblja'),
        'economics_ccs_start_year': ('year', 'Početna godina ulaganja u CCS lanac'),
        'ccs_injection_start_year': ('year', 'Godina početka utiskivanja CO2'),
        'ccs_injection_end_year': ('year', 'Planirana godina prestanka utiskivanja CO2'),
        'geothermal_operation_end_year': (
            'year',
            'Godina prestanka rada geotermalnog sustava',
        ),
        'ccs_monitoring_end_year': (
            'year',
            'Godina prestanka monitoringa skladišta CO2',
        ),
        'monitoring_annual_cost_during_injection': (
            'EUR/year',
            'Godišnji trošak monitoringa tijekom utiskivanja CO2',
        ),
        'monitoring_annual_cost_after_injection': (
            'EUR/year',
            'Godišnji trošak monitoringa nakon prestanka utiskivanja CO2',
        ),
        'compressor_capex': ('EUR', 'CAPEX kompresora CO2'),
        'compressor_annual_opex': ('EUR/year', 'Godišnji OPEX kompresora CO2'),
        'geothermal_capex': ('EUR', 'CAPEX geotermalnog sustava'),
        'geothermal_annual_opex': ('EUR/year', 'Godišnji OPEX geotermalnog sustava'),
        'electricity_buy_price': ('EUR/MWh', 'Cijena kupnje električne energije'),
        'electricity_sell_price': ('EUR/MWh', 'Cijena prodaje električne energije'),
        'economics_interest_rate': (
            '-',
            'Nominalna godišnja diskontna stopa kao decimalni broj',
        ),
        'economics_inflation_rate': (
            '-',
            'Godišnja stopa inflacije troškova kao decimalni broj',
        ),
        'economics_co2_price_scenario': ('-', 'CO2 cjenovni scenarij: -1, 0 ili 1'),
        'emitter_name': ('-', 'Naziv emitera'),
        'emitter_emissions_annual': (
            'tCO2/year',
            'Autoritativna godišnja količina uhvaćenog CO2',
        ),
        'emitter_capture_technology': ('-', 'Tehnologija hvatanja: PI, NI ili OXY'),
        'emitter_capex': ('EUR', 'CAPEX sustava hvatanja CO2'),
        'emitter_opex_per_ton': ('EUR/tCO2', 'OPEX hvatanja po toni CO2'),
        'emitter_emissions_change_a': ('-', 'Faktor promjene emisija a'),
        'emitter_emissions_change_c': ('-', 'Eksponent promjene emisija c'),
        'transport_section_name': ('-', 'Naziv transportne dionice'),
        'transport_flow_rate': (
            'tCO2/year',
            'Izvedena godišnja količina CO2 kroz transportnu dionicu',
        ),
        'transport_mode': (
            '-',
            'Način transporta: cjevovod, cestovni ili željeznički transport',
        ),
        'transport_distance_km': ('km', 'Duljina transportne dionice'),
        'pipeline_inner_diameter_m': ('m', 'Unutarnji promjer transportnog cjevovoda'),
        'pipeline_roughness_m': ('m', 'Apsolutna hrapavost transportnog cjevovoda'),
        'pipeline_elbows_90_count': ('-', 'Broj koljena transportnog cjevovoda od 90 stupnjeva'),
        'pipeline_elbows_45_count': ('-', 'Broj koljena transportnog cjevovoda od 45 stupnjeva'),
        'pipeline_elbows_30_count': ('-', 'Broj koljena transportnog cjevovoda od 30 stupnjeva'),
        'co2_pipeline_inlet_pressure_bar': (
            'bar',
            'Ulazni tlak CO2 u transportni cjevovod',
        ),
        'co2_pipeline_inlet_temperature_c': (
            '°C',
            'Ulazna temperatura CO2 u transportni cjevovod',
        ),
        'transport_capex': ('EUR', 'CAPEX transportne dionice'),
        'transport_opex_per_ton': ('EUR/tCO2', 'OPEX transporta po toni CO2'),
        'transport_opex_eur_per_tkm': (
            'EUR/tCO2/km',
            'OPEX transporta po toni CO2 i kilometru',
        ),
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
    REQUIRED_ECONOMICS_PARAMETERS = (
        'economics_start_year',
        'economics_end_year',
        'economics_ccs_start_year',
        'ccs_injection_start_year',
        'ccs_injection_end_year',
        'geothermal_operation_end_year',
        'ccs_monitoring_end_year',
        'monitoring_annual_cost_during_injection',
        'monitoring_annual_cost_after_injection',
        'compressor_capex',
        'compressor_annual_opex',
        'geothermal_capex',
        'geothermal_annual_opex',
        'electricity_buy_price',
        'electricity_sell_price',
        'economics_interest_rate',
        'economics_inflation_rate',
        'emitter_emissions_annual',
        'emitter_capex',
        'emitter_opex_per_ton',
        'transport_flow_rate',
        'transport_mode',
        'transport_distance_km',
        'transport_capex',
        'storage_capacity',
        'storage_capex',
        'storage_opex_per_ton',
    )
    PARAM_TYPES = {
        'economics_start_year': int,
        'economics_end_year': int,
        'economics_ccs_start_year': int,
        'ccs_injection_start_year': int,
        'ccs_injection_end_year': int,
        'geothermal_operation_end_year': int,
        'ccs_monitoring_end_year': int,
        'economics_co2_price_scenario': int,
        'emitter_name': str,
        'emitter_capture_technology': str,
        'transport_section_name': str,
        'transport_mode': str,
        'pipeline_elbows_90_count': int,
        'pipeline_elbows_45_count': int,
        'pipeline_elbows_30_count': int,
        'co2_pipeline_inlet_pressure_bar': float,
        'co2_pipeline_inlet_temperature_c': float,
        'geothermal_pipeline_elbows_90_count': int,
        'geothermal_pipeline_elbows_45_count': int,
        'geothermal_pipeline_elbows_30_count': int,
        'pipeline_environment_type': str,
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
        'transport_mode': {'pipeline', 'truck', 'rail'},
        'pipeline_environment_type': {'air', 'soil'},
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

        self._synchronize_co2_quantities(data)
        self._synchronize_orc_efficiency(data)
        self._synchronize_well_depths(data)

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

        self._populate_pipeline_defaults(data)
        
        # Engineering parameters remain required for backward-compatible runs.
        for param in self.REQUIRED_PARAMETERS:
            self.params[param] = self._validate(
                data,
                param,
                self.PARAM_TYPES.get(param, float),
                self.PARAM_METADATA[param][0],
            )

        # Parametri novog integriranog ugovora obvezni su, dok ostali postojeći
        # ekonomski parametri ostaju neobvezni radi kompatibilnosti scenarija.
        for param in self.ECONOMICS_PARAM_METADATA:
            if param in data or param in self.REQUIRED_ECONOMICS_PARAMETERS:
                self.params[param] = self._validate(
                    data,
                    param,
                    self.PARAM_TYPES.get(param, float),
                    self.PARAM_METADATA[param][0],
                )

        self._validate_contract()
        
        # Derived attributes
        # ``eta`` ostaje alias jer ga postojeće engineering klase još koriste.
        self.eta = self.eta_orc
        # ``h_ref`` ostaje interni alias jer ga generička VFP klasa očekuje.
        # Scenario runner svakoj VFP instanci zatim dodjeljuje dubinu njezine
        # konkretne bušotine.
        self.h_ref = self.h_ref_co2
        self.m_dot = self.m_dot_annual * 1e6 / (365.25 * 24 * 3600)  # kg/s
        # Existing engineering classes still expose ``rw`` internally. The
        # runner assigns the role-specific radius to each model instance.
        self.rw = self.rw_co2
        self.re = (self.A / math.pi) ** 0.5  # m
        self.V_p_ref = self.A * self.h_ef * self.poro  # m^3
        self.V_w_ref = self.V_p_ref  # m^3
        self.p_max = self.fracture_pressure_gradient * self.h_top  # bar
        self.g = 9.80665  # m/s^2
        self.component_available_hours_per_year = {
            'co2_compressor': 8766.0 * self.co2_compressor_availability,
            'co2_injection_well': 8766.0 * self.co2_injection_well_availability,
            'orc': 8766.0 * self.orc_availability,
            'geothermal_production_well': (
                8766.0 * self.geothermal_production_well_availability
            ),
            'geothermal_injection_well': (
                8766.0 * self.geothermal_injection_well_availability
            ),
        }

    def _populate_pipeline_defaults(self, data):
        """Migrate scenarios created before the thermo-hydraulic pipeline API."""

        # Privremena razvojna shema imala je zasebnu GT duljinu. Jedini
        # autoritativni razmak proizvodne i utisne bušotine sada je d_doublet.
        data.pop('geothermal_pipeline_distance_m', None)

        def existing_value(key, fallback):
            entry = data.get(key)
            if isinstance(entry, list) and entry:
                return entry[0]
            return fallback

        default_values = {
            'geothermal_pipeline_inner_diameter_m': existing_value(
                'pipeline_inner_diameter_m', 0.30
            ),
            'geothermal_pipeline_roughness_m': existing_value(
                'pipeline_roughness_m', 0.000045
            ),
            'geothermal_pipeline_elbows_90_count': existing_value(
                'pipeline_elbows_90_count', 0
            ),
            'geothermal_pipeline_elbows_45_count': existing_value(
                'pipeline_elbows_45_count', 0
            ),
            'geothermal_pipeline_elbows_30_count': existing_value(
                'pipeline_elbows_30_count', 0
            ),
            'pipeline_environment_type': 'soil',
            'pipeline_ambient_temperature_c': 12.0,
            'pipeline_environment_thermal_conductivity_w_m_k': 1.5,
            'pipeline_environment_volumetric_heat_capacity_j_m3_k': 2_000_000.0,
            'pipeline_burial_depth_m': 1.0,
            'pipeline_external_heat_transfer_coefficient_w_m2_k': 10.0,
            'pipeline_wall_thickness_m': 0.01,
            'pipeline_wall_thermal_conductivity_w_m_k': 45.0,
            'pipeline_insulation_thickness_m': 0.05,
            'pipeline_insulation_thermal_conductivity_w_m_k': 0.035,
        }
        for key, value in default_values.items():
            unit, description = self.PARAM_METADATA[key]
            data.setdefault(key, [value, unit, description])

        transport_mode = existing_value('transport_mode', None)
        if transport_mode == 'pipeline':
            for key, value in (
                ('co2_pipeline_inlet_pressure_bar', 150.0),
                (
                    'co2_pipeline_inlet_temperature_c',
                    existing_value('t_comp_in', 20.0),
                ),
            ):
                unit, description = self.PARAM_METADATA[key]
                data.setdefault(key, [value, unit, description])

    def _synchronize_co2_quantities(self, data):
        """Validate and normalize all aliases of the annual CO2 quantity."""
        emitter_t_per_year = self._validate(
            data,
            'emitter_emissions_annual',
            float,
            self.ECONOMICS_PARAM_METADATA['emitter_emissions_annual'][0],
        )
        if emitter_t_per_year <= 0:
            raise ValueError('emitter_emissions_annual mora biti veći od nule')

        aliases = {
            'm_dot_annual': (emitter_t_per_year / 1000.0, 'ktpa'),
            'transport_flow_rate': (emitter_t_per_year, 'tCO2/year'),
        }
        for key, (expected_value, unit) in aliases.items():
            if key in data:
                supplied_value = self._validate(data, key, float, unit)
                if not math.isclose(
                    supplied_value,
                    expected_value,
                    rel_tol=1e-12,
                    abs_tol=1e-9,
                ):
                    raise ValueError(
                        'Nekonzistentna godišnja količina CO2: '
                        f'{key}={supplied_value:g} {unit}, a '
                        f'emitter_emissions_annual={emitter_t_per_year:g} '
                        'tCO2/year'
                    )
                normalized_entry = list(data[key])
                normalized_entry[0] = expected_value
                data[key] = normalized_entry
            else:
                data[key] = [
                    expected_value,
                    unit,
                    self.PARAM_METADATA[key][1],
                ]

    def _synchronize_orc_efficiency(self, data):
        """Expose ``eta_orc`` while retaining the legacy ``eta`` alias."""
        if 'eta_orc' not in data and 'eta' not in data:
            raise ValueError('Nedostaje eta_orc u ulaznim podacima')

        if 'eta_orc' not in data:
            legacy_eta = self._validate(data, 'eta', float, '-')
            data['eta_orc'] = [legacy_eta, '-', self.PARAM_METADATA['eta_orc'][1]]
        elif 'eta' not in data:
            eta_orc = self._validate(data, 'eta_orc', float, '-')
            data['eta'] = [eta_orc, '-', self.PARAM_METADATA['eta'][1]]
        else:
            eta_orc = self._validate(data, 'eta_orc', float, '-')
            legacy_eta = self._validate(data, 'eta', float, '-')
            if not math.isclose(eta_orc, legacy_eta, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError(
                    'Nekonzistentna ORC učinkovitost: eta mora biti jednaka eta_orc'
                )
            normalized_entry = list(data['eta'])
            normalized_entry[0] = eta_orc
            data['eta'] = normalized_entry

    def _synchronize_well_depths(self, data):
        """Expose role-specific VFP depths with a legacy ``h_ref`` alias."""
        depth_descriptions = {
            'h_ref_co2': self.PARAM_METADATA['h_ref_co2'][1],
            'h_ref_geothermal_production': (
                self.PARAM_METADATA['h_ref_geothermal_production'][1]
            ),
            'h_ref_geothermal_injection': (
                self.PARAM_METADATA['h_ref_geothermal_injection'][1]
            ),
        }

        if 'h_ref' in data:
            legacy_depth = self._validate(data, 'h_ref', float, 'm')
            for key, description in depth_descriptions.items():
                data.setdefault(key, [legacy_depth, 'm', description])

        if 'h_ref_co2' in data:
            co2_depth = self._validate(data, 'h_ref_co2', float, 'm')
            data['h_ref'] = [
                co2_depth,
                'm',
                self.PARAM_METADATA['h_ref'][1],
            ]

    def _validate_contract(self):
        """Validate cross-parameter constraints of the integrated input contract."""
        timeline = (
            ('economics_start_year', self.economics_start_year),
            ('economics_ccs_start_year', self.economics_ccs_start_year),
            ('ccs_injection_start_year', self.ccs_injection_start_year),
            ('ccs_injection_end_year', self.ccs_injection_end_year),
            ('economics_end_year', self.economics_end_year),
        )
        for (earlier_name, earlier), (later_name, later) in zip(
            timeline,
            timeline[1:],
        ):
            if earlier > later:
                raise ValueError(
                    'Neispravna kronologija: '
                    f'{earlier_name} ({earlier}) mora biti manji ili jednak '
                    f'{later_name} ({later})'
                )

        for end_name in ('geothermal_operation_end_year', 'ccs_monitoring_end_year'):
            end_year = getattr(self, end_name)
            if end_year < self.ccs_injection_end_year:
                raise ValueError(
                    'Neispravna kronologija: '
                    f'{end_name} ({end_year}) ne smije biti prije '
                    f'ccs_injection_end_year ({self.ccs_injection_end_year})'
                )
            if end_year > self.economics_end_year:
                raise ValueError(
                    'Neispravna kronologija: '
                    f'{end_name} ({end_year}) ne smije biti nakon '
                    f'economics_end_year ({self.economics_end_year})'
                )

        efficiency_parameters = (
            'eta_orc',
            'eta_gt_injection_pump',
            'eta_co2_compressor_isentropic',
            'eta_co2_dense_phase_pump',
        )
        for key in efficiency_parameters:
            value = getattr(self, key)
            if not 0 < value <= 1:
                raise ValueError(f'{key} mora biti veći od 0 i manji ili jednak 1')

        availability_parameters = (
            'co2_compressor_availability',
            'co2_injection_well_availability',
            'orc_availability',
            'geothermal_production_well_availability',
            'geothermal_injection_well_availability',
        )
        for key in availability_parameters:
            value = getattr(self, key)
            if not 0 < value <= 1:
                raise ValueError(
                    f'{key} mora biti veći od 0 i manji ili jednak 1'
                )

        if self.fracture_pressure_gradient <= 0:
            raise ValueError('fracture_pressure_gradient mora biti veći od nule')
        if self.dp < 0.5:
            raise ValueError('Korak tlaka dp mora biti najmanje 0,5 bar')
        for key in (
            'h_ref_co2',
            'h_ref_geothermal_production',
            'h_ref_geothermal_injection',
        ):
            if getattr(self, key) <= 0:
                raise ValueError(f'{key} mora biti veći od nule')
        minimum_well_diameter = 2.0 * min(
            self.rw_co2,
            self.rw_geothermal_production,
            self.rw_geothermal_injection,
        )
        if not 0.0 <= self.epsilon < minimum_well_diameter:
            raise ValueError(
                'epsilon mora biti nenegativan i manji od najmanjeg promjera '
                'bušotinske cijevi'
            )
        geomechanical_pressure_limit = (
            self.fracture_pressure_gradient * self.h_top
        )
        if self.p_ref > geomechanical_pressure_limit:
            raise ValueError(
                'Početni tlak ležišta p_ref ne smije biti veći od dopuštenog '
                'tlaka izvedenog iz gradijenta tlaka frakturiranja i dubine '
                'vrha ležišta'
            )

        non_negative_parameters = (
            'monitoring_annual_cost_during_injection',
            'monitoring_annual_cost_after_injection',
            'compressor_capex',
            'compressor_annual_opex',
            'geothermal_capex',
            'geothermal_annual_opex',
            'electricity_buy_price',
            'electricity_sell_price',
            'economics_interest_rate',
            'economics_inflation_rate',
            'emitter_capex',
            'emitter_opex_per_ton',
            'transport_capex',
            'transport_opex_per_ton',
            'transport_opex_eur_per_tkm',
            'storage_capex',
            'storage_opex_per_ton',
            'storage_capacity',
            'transport_distance_km',
            'pipeline_roughness_m',
            'pipeline_elbows_90_count',
            'pipeline_elbows_45_count',
            'pipeline_elbows_30_count',
            'geothermal_pipeline_roughness_m',
            'geothermal_pipeline_elbows_90_count',
            'geothermal_pipeline_elbows_45_count',
            'geothermal_pipeline_elbows_30_count',
            'pipeline_burial_depth_m',
            'pipeline_insulation_thickness_m',
        )
        for key in non_negative_parameters:
            value = getattr(self, key)
            if value is not None and value < 0:
                raise ValueError(f'{key} ne smije biti negativan')

        pipeline_parameters = (
            'pipeline_inner_diameter_m',
            'pipeline_roughness_m',
            'pipeline_elbows_90_count',
            'pipeline_elbows_45_count',
            'pipeline_elbows_30_count',
            'co2_pipeline_inlet_pressure_bar',
            'co2_pipeline_inlet_temperature_c',
        )
        if self.transport_mode == 'pipeline':
            required_pipeline_parameters = (
                *pipeline_parameters,
                'transport_opex_per_ton',
            )
            missing = [
                key
                for key in required_pipeline_parameters
                if getattr(self, key) is None
            ]
            if missing:
                raise ValueError(
                    'Za transport cjevovodom nedostaju parametri: '
                    + ', '.join(missing)
                )
        elif self.transport_opex_eur_per_tkm is None:
            raise ValueError(
                'Za cestovni ili željeznički transport nedostaje '
                'transport_opex_eur_per_tkm'
            )

        if (
            self.pipeline_inner_diameter_m is not None
            and self.pipeline_inner_diameter_m <= 0
        ):
            raise ValueError('pipeline_inner_diameter_m mora biti veći od nule')
        if (
            self.pipeline_roughness_m is not None
            and self.pipeline_inner_diameter_m is not None
            and self.pipeline_roughness_m >= self.pipeline_inner_diameter_m
        ):
            raise ValueError(
                'pipeline_roughness_m mora biti manji od '
                'pipeline_inner_diameter_m'
            )

        if self.d_doublet <= 0:
            raise ValueError('Razmak geotermalnog para mora biti veći od nule')
        if self.geothermal_pipeline_inner_diameter_m <= 0:
            raise ValueError(
                'geothermal_pipeline_inner_diameter_m mora biti veći od nule'
            )
        if (
            self.geothermal_pipeline_roughness_m
            >= self.geothermal_pipeline_inner_diameter_m
        ):
            raise ValueError(
                'geothermal_pipeline_roughness_m mora biti manji od '
                'geothermal_pipeline_inner_diameter_m'
            )

        strictly_positive_thermal_parameters = (
            'pipeline_environment_thermal_conductivity_w_m_k',
            'pipeline_environment_volumetric_heat_capacity_j_m3_k',
            'pipeline_external_heat_transfer_coefficient_w_m2_k',
            'pipeline_wall_thickness_m',
            'pipeline_wall_thermal_conductivity_w_m_k',
            'pipeline_insulation_thermal_conductivity_w_m_k',
        )
        for key in strictly_positive_thermal_parameters:
            if getattr(self, key) <= 0:
                raise ValueError(f'{key} mora biti veći od nule')

        if self.pipeline_ambient_temperature_c <= -273.15:
            raise ValueError(
                'pipeline_ambient_temperature_c mora biti veća od -273,15 °C'
            )
        if (
            self.co2_pipeline_inlet_temperature_c is not None
            and self.co2_pipeline_inlet_temperature_c <= -273.15
        ):
            raise ValueError(
                'co2_pipeline_inlet_temperature_c mora biti veća od -273,15 °C'
            )
        if (
            self.co2_pipeline_inlet_pressure_bar is not None
            and self.co2_pipeline_inlet_pressure_bar <= 0
        ):
            raise ValueError(
                'co2_pipeline_inlet_pressure_bar mora biti veći od nule'
            )

        if self.pipeline_environment_type == 'soil':
            outside_radii = [
                self.geothermal_pipeline_inner_diameter_m / 2.0
                + self.pipeline_wall_thickness_m
                + self.pipeline_insulation_thickness_m
            ]
            if self.pipeline_inner_diameter_m is not None:
                outside_radii.append(
                    self.pipeline_inner_diameter_m / 2.0
                    + self.pipeline_wall_thickness_m
                    + self.pipeline_insulation_thickness_m
                )
            minimum_burial_depth = max(outside_radii)
            if self.pipeline_burial_depth_m <= minimum_burial_depth:
                raise ValueError(
                    'pipeline_burial_depth_m mora biti veći od vanjskog '
                    'radijusa cjevovoda za okoliš tipa soil'
                )
    
    def _validate(self, data, key, type_, unit):
        """Validate input parameter."""
        if key not in data:
            raise ValueError(f"Nedostaje {key} u ulaznim podacima")
        if not isinstance(data[key], list) or len(data[key]) < 2:
            raise ValueError(
                f"Neispravan format za {key}: očekuje se "
                "[vrijednost, jedinica, opis]"
            )
        if data[key][1] != unit:
            raise ValueError(
                f"Neispravna jedinica za {key}: očekuje se {unit}, "
                f"dobiveno je {data[key][1]}"
            )

        value = data[key][0]
        if type_ is float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Neispravan tip za {key}: očekuje se broj")
            validated_value = float(value)
            if not math.isfinite(validated_value):
                raise ValueError(
                    f"Neispravna vrijednost za {key}: očekuje se konačan broj"
                )
        elif type_ is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Neispravan tip za {key}: očekuje se cijeli broj")
            validated_value = value
        elif type_ is str:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Neispravan tip za {key}: očekuje se neprazan tekst"
                )
            validated_value = value
        elif type_ is list:
            if not isinstance(value, list) or not value:
                raise ValueError(
                    f"Neispravan tip za {key}: očekuje se numerički niz"
                )
            if any(
                isinstance(item, bool) or not isinstance(item, (int, float))
                for item in value
            ):
                raise ValueError(
                    f"Neispravan tip za {key}: očekuje se numerički niz"
                )
            validated_value = [float(item) for item in value]
            if any(not math.isfinite(item) for item in validated_value):
                raise ValueError(
                    f"Neispravna vrijednost za {key}: očekuju se konačni brojevi"
                )
        else:
            raise TypeError(f"Nepodržan tip validacije za {key}: {type_}")

        if key in self.PARAM_CHOICES and validated_value not in self.PARAM_CHOICES[key]:
            choices = sorted(self.PARAM_CHOICES[key], key=str)
            raise ValueError(
                f"Neispravna vrijednost za {key}: očekuje se jedna od {choices}"
            )

        return validated_value
