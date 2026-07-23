"""Streamlit UI for the current GT-CCS engineering demonstration."""

from copy import deepcopy
import json
import math

import pandas as pd
import streamlit as st

from economics import generate_co2_price_path
from services.scenario_runner import DEFAULT_INPUT_PATH, ScenarioRunner


RESULTS_KEY = "engineering_demo_results"
ERROR_KEY = "engineering_demo_error"
ACTIVE_INPUTS_KEY = "active_scenario_inputs"
CONTROL_PREFIX = "input__"


def _entry_value(inputs, key):
    return inputs[key][0]


def _set_entry_value(key, value):
    st.session_state[ACTIVE_INPUTS_KEY][key][0] = value


def _clear_stale_results():
    st.session_state[RESULTS_KEY] = None
    st.session_state[ERROR_KEY] = None


def _slider_key(parameter):
    return f"{CONTROL_PREFIX}{parameter}__slider"


def _number_key(parameter):
    return f"{CONTROL_PREFIX}{parameter}__number"


def _direct_key(parameter):
    return f"{CONTROL_PREFIX}{parameter}__direct"


def _format_numeric_value(value, number_format):
    try:
        return number_format % float(value)
    except (TypeError, ValueError):
        return str(value)


def _slider_changed(parameter, slider_widget_key, number_widget_key, integer):
    value = st.session_state[slider_widget_key]
    if integer:
        value = int(round(value))
    else:
        value = float(value)
    st.session_state[number_widget_key] = value
    _set_entry_value(parameter, value)
    _clear_stale_results()


def _number_changed(
    parameter,
    slider_widget_key,
    number_widget_key,
    logarithmic,
    integer,
    logarithmic_options,
):
    value = st.session_state[number_widget_key]
    if integer:
        value = int(value)
    else:
        value = float(value)
    if logarithmic:
        slider_value = min(
            logarithmic_options,
            key=lambda option: abs(math.log10(option) - math.log10(value)),
        )
    else:
        slider_value = value
    st.session_state[slider_widget_key] = slider_value
    _set_entry_value(parameter, value)
    _clear_stale_results()


def _direct_value_changed(parameter, widget_key):
    _set_entry_value(parameter, st.session_state[widget_key])
    _clear_stale_results()


def _price_mode_changed(widget_key):
    mode = st.session_state[widget_key]
    _set_entry_value("economics_co2_price_mode", mode)
    legacy_scenario = {
        "pessimistic": -1,
        "conservative": 0,
        "optimistic": 1,
        "custom": 0,
    }[mode]
    _set_entry_value("economics_co2_price_scenario", legacy_scenario)
    _clear_stale_results()


def _reset_scenario():
    st.session_state[ACTIVE_INPUTS_KEY] = deepcopy(DEFAULT_INPUTS)
    for key in list(st.session_state):
        if key.startswith(CONTROL_PREFIX):
            del st.session_state[key]
    _clear_stale_results()


def paired_numeric_control(
    parameter,
    label,
    minimum,
    maximum,
    *,
    slider_step,
    number_step,
    number_format,
    unit,
    help_text=None,
    integer=False,
    logarithmic=False,
):
    """Render a synchronized slider and precise number input."""
    inputs = st.session_state[ACTIVE_INPUTS_KEY]
    raw_value = _entry_value(inputs, parameter)
    value = int(raw_value) if integer else float(raw_value)
    bounded_value = min(max(value, minimum), maximum)
    if bounded_value != value:
        value = int(bounded_value) if integer else float(bounded_value)
        _set_entry_value(parameter, value)
        _clear_stale_results()

    slider_widget_key = _slider_key(parameter)
    number_widget_key = _number_key(parameter)
    logarithmic_options = ()
    if logarithmic:
        minimum_exponent = math.log10(minimum)
        maximum_exponent = math.log10(maximum)
        option_count = max(
            1,
            int(math.ceil((maximum_exponent - minimum_exponent) / slider_step)),
        )
        logarithmic_options = tuple(
            sorted(
                {
                    minimum,
                    maximum,
                    value,
                    *(
                        10.0
                        ** (
                            minimum_exponent
                            + (maximum_exponent - minimum_exponent)
                            * index
                            / option_count
                        )
                        for index in range(option_count + 1)
                    ),
                }
            )
        )
        slider_value = value
    else:
        slider_value = value

    st.session_state[slider_widget_key] = slider_value
    st.session_state[number_widget_key] = value

    slider_column, number_column = st.columns([1.7, 1.0])
    with slider_column:
        slider_label = label if unit == "-" else f"{label} ({unit})"
        if logarithmic:
            st.select_slider(
                slider_label,
                options=logarithmic_options,
                key=slider_widget_key,
                on_change=_slider_changed,
                args=(
                    parameter,
                    slider_widget_key,
                    number_widget_key,
                    integer,
                ),
                help=help_text,
                format_func=lambda selected_value: _format_numeric_value(
                    selected_value,
                    number_format,
                ),
            )
        else:
            st.slider(
                slider_label,
                min_value=minimum,
                max_value=maximum,
                step=slider_step,
                key=slider_widget_key,
                on_change=_slider_changed,
                args=(
                    parameter,
                    slider_widget_key,
                    number_widget_key,
                    integer,
                ),
                help=help_text,
            )
    with number_column:
        number_label = label if unit == "-" else f"{label} ({unit})"
        st.number_input(
            number_label,
            min_value=minimum,
            max_value=maximum,
            step=number_step,
            format=number_format,
            key=number_widget_key,
            on_change=_number_changed,
            args=(
                parameter,
                slider_widget_key,
                number_widget_key,
                logarithmic,
                integer,
                logarithmic_options,
            ),
            help=help_text,
        )


def selection_control(parameter, label, options, labels, help_text=None):
    widget_key = _direct_key(parameter)
    current_value = _entry_value(st.session_state[ACTIVE_INPUTS_KEY], parameter)
    if current_value not in options:
        current_value = options[0]
        _set_entry_value(parameter, current_value)
    if widget_key not in st.session_state:
        st.session_state[widget_key] = current_value
    st.selectbox(
        label,
        options=options,
        format_func=lambda option: labels.get(option, option),
        key=widget_key,
        on_change=_direct_value_changed,
        args=(parameter, widget_key),
        help=help_text,
    )


def price_mode_control():
    parameter = "economics_co2_price_mode"
    widget_key = _direct_key(parameter)
    options = ["pessimistic", "conservative", "optimistic", "custom"]
    labels = {
        "pessimistic": "Pesimistični — visoka cijena CO₂",
        "conservative": "Konzervativni — srednja cijena CO₂",
        "optimistic": "Optimistični — niža cijena CO₂",
        "custom": "Novi prilagođeni scenarij",
    }
    current_value = _entry_value(st.session_state[ACTIVE_INPUTS_KEY], parameter)
    if current_value not in options:
        current_value = "conservative"
        _set_entry_value(parameter, current_value)
    if widget_key not in st.session_state:
        st.session_state[widget_key] = current_value
    st.selectbox(
        "Cjenovni scenarij CO₂",
        options=options,
        format_func=lambda option: labels[option],
        key=widget_key,
        on_change=_price_mode_changed,
        args=(widget_key,),
    )


def text_control(parameter, label):
    widget_key = _direct_key(parameter)
    current_value = str(_entry_value(st.session_state[ACTIVE_INPUTS_KEY], parameter))
    if widget_key not in st.session_state:
        st.session_state[widget_key] = current_value
    st.text_input(
        label,
        key=widget_key,
        on_change=_direct_value_changed,
        args=(parameter, widget_key),
    )


def validate_active_inputs(inputs):
    """Validate only constraints required by the existing equations."""
    errors = []
    warnings = []
    value = lambda key: _entry_value(inputs, key)

    if value("m_dot_annual") <= 0:
        errors.append(
            "Zatečeni model ne podržava 0 ktpa jer vrijeme računa dijeljenjem "
            "uskladištene mase s protokom. Unos 0 je dopušten, ali proračun nije."
        )
    if value("poro") <= 0:
        errors.append(
            "Zatečeni proračun drenažnog radijusa zahtijeva poroznost veću od nule."
        )

    p_max = 0.18 * value("h_top")
    if value("p_ref") + value("dp") > p_max:
        errors.append(
            f"p_ref + dp mora biti najviše p_max = 0,18 × h_top = {p_max:.1f} bar. "
            "Raspon widgeta ide do 450 bar, ali postojeća p_max jednadžba ostaje nepromijenjena."
        )
    if value("bhp_dp") >= value("p_ref"):
        errors.append("bhp_dp mora biti manji od početnog ležišnog tlaka p_ref.")

    aquifer_radius = math.sqrt(value("A") / math.pi)
    if value("rw_co2") >= aquifer_radius:
        errors.append("Radijus CO₂ bušotine mora biti manji od radijusa akvifera.")
    for key, label in (
        ("rw_geothermal_production", "proizvodne geotermalne bušotine"),
        ("rw_geothermal_injection", "utisne geotermalne bušotine"),
    ):
        if value(key) >= value("d_doublet"):
            errors.append(
                f"Radijus {label} mora biti manji od udaljenosti geotermalnog dubleta."
            )

    if value("krg_max") <= 0:
        errors.append(
            "krg_max = 0 daje nultu efektivnu propusnost CO₂ i postojeći BHP solver ne može raditi."
        )
    if value("krg_min") > value("krg_max"):
        errors.append("krg_min mora biti manji ili jednak krg_max.")
    if value("krw_min") > value("krw_max"):
        errors.append("krw_min mora biti manji ili jednak krw_max.")

    if value("S_plume_core") > 1.0 - value("Sw_i"):
        warnings.append(
            "S_plume_core je veći od raspoloživog raspona zasićenja 1 − Sw_i; "
            "postojeći Corey model tada reže CO₂ zasićenje na granicu."
        )

    if value("economics_end_year") < value("economics_start_year"):
        errors.append("Završna godina ekonomike mora biti nakon početne godine.")
    if not (
        value("economics_start_year")
        <= value("economics_ccs_start_year")
        <= value("economics_end_year")
    ):
        errors.append(
            "Godina početka CCS rada mora biti unutar odabranog ekonomskog razdoblja."
        )

    return errors, warnings


st.set_page_config(
    page_title="GT-CCS demonstracija",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """
    <style>
    [data-testid="stMetricValue"] {
        font-size: 1.125rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    DEFAULT_INPUTS = json.loads(DEFAULT_INPUT_PATH.read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    st.error(f"Zadana ulazna datoteka nije dostupna: {exc}")
    st.stop()

if RESULTS_KEY not in st.session_state:
    st.session_state[RESULTS_KEY] = None
if ERROR_KEY not in st.session_state:
    st.session_state[ERROR_KEY] = None
if ACTIVE_INPUTS_KEY not in st.session_state:
    st.session_state[ACTIVE_INPUTS_KEY] = deepcopy(DEFAULT_INPUTS)
else:
    active_inputs = st.session_state[ACTIVE_INPUTS_KEY]
    if "rw" in active_inputs:
        legacy_radius = active_inputs["rw"][0]
        for radius_key in (
            "rw_co2",
            "rw_geothermal_production",
            "rw_geothermal_injection",
        ):
            active_inputs.setdefault(
                radius_key,
                deepcopy(DEFAULT_INPUTS[radius_key]),
            )
            active_inputs[radius_key][0] = legacy_radius
        del active_inputs["rw"]
    for parameter, default_entry in DEFAULT_INPUTS.items():
        active_inputs.setdefault(parameter, deepcopy(default_entry))

st.title("GT-CCS demonstracijski proračun")
st.caption(
    "Postojeći proračun skladištenja CO₂, bušotinskih tlakova, "
    "geotermalne proizvodnje i snage u jednom prikazu."
)

if st.session_state[ACTIVE_INPUTS_KEY] == DEFAULT_INPUTS:
    st.warning(
        "Ovo je razvojni demonstracijski scenarij. Rezultati koriste zatečene "
        "pretpostavke i još se ne smiju smatrati kalibriranim projektnim proračunom."
    )
else:
    st.caption(
        "Aktivan je prilagođeni scenarij. Promjena bilo kojeg ulaza briše "
        "prethodne rezultate kako se ne bi prikazivali zastarjeli podaci."
    )

with st.expander("Prilagodba ulaznog scenarija", expanded=True):
    (
        reservoir_controls_tab,
        wells_controls_tab,
        relperm_controls_tab,
        economics_controls_tab,
    ) = st.tabs(
        [
            "CCS i akvifer",
            "Bušotine i geotermija",
            "Relativna propusnost",
            "Ekonomika",
        ]
    )

    with reservoir_controls_tab:
        paired_numeric_control(
            "m_dot_annual",
            "Godišnje utiskivanje CO₂",
            0.0,
            1000.0,
            slider_step=5.0,
            number_step=0.1,
            number_format="%.2f",
            unit="ktpa",
            help_text="Ispravan JSON ključ je m_dot_annual.",
        )
        paired_numeric_control(
            "A",
            "Površina akvifera A",
            1.0,
            1_000_000_000.0,
            slider_step=0.01,
            number_step=1.0,
            number_format="%.2f",
            unit="m²",
            logarithmic=True,
        )
        paired_numeric_control(
            "h_ef",
            "Efektivna debljina akvifera h_ef",
            1.0,
            1000.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="m",
        )
        paired_numeric_control(
            "poro",
            "Poroznost akvifera poro",
            0.0,
            0.4,
            slider_step=0.005,
            number_step=0.0001,
            number_format="%.4f",
            unit="-",
            help_text="Nula se može unijeti, ali postojeći proračun tada ne može raditi.",
        )
        paired_numeric_control(
            "t",
            "Temperatura sloja t",
            0.0,
            300.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="°C",
        )
        paired_numeric_control(
            "p_ref",
            "Referentni početni tlak p_ref",
            50.0,
            450.0,
            slider_step=5.0,
            number_step=0.1,
            number_format="%.2f",
            unit="bar",
            help_text=(
                "Widget dopušta traženi raspon. Proračun dodatno provjerava "
                "postojeći p_max = 0,18 × h_top."
            ),
        )
        paired_numeric_control(
            "c_p",
            "Stlačivost pora c_p",
            1e-7,
            5e-3,
            slider_step=0.05,
            number_step=1e-7,
            number_format="%.7f",
            unit="1/bar",
            logarithmic=True,
            help_text=(
                "Privremeni raspon 1e-7–5e-3 uključuje zatečenu vrijednost 5e-5. "
                "U zahtjevu gornja granica nije bila dovršena."
            ),
        )
        paired_numeric_control(
            "sal",
            "Salinitet sal",
            0.0,
            50.0,
            slider_step=0.5,
            number_step=0.001,
            number_format="%.3f",
            unit="gNaCl/L",
        )
        paired_numeric_control(
            "k",
            "Prosječna propusnost k",
            1e-15,
            1000e-15,
            slider_step=0.01,
            number_step=1e-15,
            number_format="%.3e",
            unit="m²",
            logarithmic=True,
        )
    with wells_controls_tab:
        st.caption(
            "Radijusi zasebno ulaze u ležišnu injektivnost/proizvodnost i "
            "u VFP promjer odgovarajuće bušotine."
        )
        paired_numeric_control(
            "rw_co2",
            "Radijus utisne CO₂ bušotine",
            0.05,
            0.50,
            slider_step=0.005,
            number_step=0.001,
            number_format="%.3f",
            unit="m",
        )
        paired_numeric_control(
            "rw_geothermal_production",
            "Radijus proizvodne geotermalne bušotine",
            0.05,
            0.50,
            slider_step=0.005,
            number_step=0.001,
            number_format="%.3f",
            unit="m",
        )
        paired_numeric_control(
            "rw_geothermal_injection",
            "Radijus utisne geotermalne bušotine",
            0.05,
            0.50,
            slider_step=0.005,
            number_step=0.001,
            number_format="%.3f",
            unit="m",
        )
        paired_numeric_control(
            "t_out",
            "ORC izlazna temperatura t_out",
            0.0,
            100.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="°C",
        )
        paired_numeric_control(
            "p_out",
            "ORC izlazni tlak p_out",
            1.0,
            100.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="bar",
        )
        paired_numeric_control(
            "eta",
            "ORC učinkovitost eta",
            0.0,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "d_doublet",
            "Udaljenost geotermalnog dubleta d_doublet",
            10.0,
            5000.0,
            slider_step=10.0,
            number_step=1.0,
            number_format="%.2f",
            unit="m",
        )
        paired_numeric_control(
            "bhp_dp",
            "Pad tlaka proizvodne geotermalne bušotine bhp_dp",
            1.0,
            100.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="bar",
            help_text=(
                "U postojećoj jednadžbi ovo je drawdown: "
                "BHP proizvodne bušotine = p_ref − bhp_dp."
            ),
        )
        paired_numeric_control(
            "p_comp_in",
            "Ulazni tlak kompresora p_comp_in",
            1.0,
            100.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="bar",
        )
        paired_numeric_control(
            "t_comp_in",
            "Ulazna temperatura kompresora t_comp_in",
            -30.0,
            100.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="°C",
        )

    with relperm_controls_tab:
        paired_numeric_control(
            "E_eff",
            "Efikasnost skladištenja E_eff",
            0.005,
            0.3,
            slider_step=0.005,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "S_plume_core",
            "Zasićenje jezgre plumea S_plume_core",
            0.0,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "Sw_i",
            "Minimalno zasićenje vodom Sw_i",
            0.0,
            0.5,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "krw_max",
            "Maksimalna relativna propusnost vode krw_max",
            0.0,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "krg_max",
            "Maksimalna relativna propusnost CO₂ krg_max",
            0.0,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "nw",
            "Coreyjev eksponent vode nw",
            1.0,
            10.0,
            slider_step=0.1,
            number_step=0.01,
            number_format="%.2f",
            unit="-",
        )
        paired_numeric_control(
            "ng",
            "Coreyjev eksponent CO₂ ng",
            1.0,
            10.0,
            slider_step=0.1,
            number_step=0.01,
            number_format="%.2f",
            unit="-",
        )
        paired_numeric_control(
            "krw_min",
            "Minimalna relativna propusnost vode krw_min",
            0.01,
            0.5,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "krg_min",
            "Minimalna relativna propusnost CO₂ krg_min",
            0.01,
            0.5,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
    with economics_controls_tab:
        st.markdown("#### Razdoblje i cijena CO₂")
        paired_numeric_control(
            "economics_start_year",
            "Početna godina ekonomike",
            2027,
            2040,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )
        economics_start_year = int(
            _entry_value(st.session_state[ACTIVE_INPUTS_KEY], "economics_start_year")
        )
        economics_end_year = int(
            _entry_value(st.session_state[ACTIVE_INPUTS_KEY], "economics_end_year")
        )
        if economics_end_year < economics_start_year:
            _set_entry_value("economics_end_year", economics_start_year)
            economics_end_year = economics_start_year
            st.session_state.pop(_slider_key("economics_end_year"), None)
            st.session_state.pop(_number_key("economics_end_year"), None)
            _clear_stale_results()
        paired_numeric_control(
            "economics_end_year",
            "Završna godina ekonomike",
            economics_start_year,
            2200,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )
        economics_end_year = int(
            _entry_value(st.session_state[ACTIVE_INPUTS_KEY], "economics_end_year")
        )
        ccs_start_year = int(
            _entry_value(
                st.session_state[ACTIVE_INPUTS_KEY],
                "economics_ccs_start_year",
            )
        )
        bounded_ccs_start = min(
            max(ccs_start_year, economics_start_year),
            economics_end_year,
        )
        if bounded_ccs_start != ccs_start_year:
            _set_entry_value("economics_ccs_start_year", bounded_ccs_start)
            st.session_state.pop(_slider_key("economics_ccs_start_year"), None)
            st.session_state.pop(_number_key("economics_ccs_start_year"), None)
            _clear_stale_results()
        paired_numeric_control(
            "economics_ccs_start_year",
            "Početna godina rada CCS lanca",
            economics_start_year,
            economics_end_year,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )

        price_mode_control()
        selected_price_mode = _entry_value(
            st.session_state[ACTIVE_INPUTS_KEY],
            "economics_co2_price_mode",
        )
        if selected_price_mode == "custom":
            selection_control(
                "economics_custom_price_function",
                "Funkcija prilagođene cijene",
                ["linear", "logarithmic", "power_law"],
                {
                    "linear": "Linearno",
                    "logarithmic": "Logaritamski",
                    "power_law": "Power law",
                },
            )
            paired_numeric_control(
                "economics_custom_price_p0",
                "Početna cijena P₀",
                0.0,
                1000.0,
                slider_step=5.0,
                number_step=0.1,
                number_format="%.2f",
                unit="EUR/tCO₂",
            )
            custom_function = _entry_value(
                st.session_state[ACTIVE_INPUTS_KEY],
                "economics_custom_price_function",
            )
            if custom_function == "linear":
                st.code("P(τ) = P₀ + a · τ", language=None)
                paired_numeric_control(
                    "economics_custom_linear_growth",
                    "Linearni godišnji porast a",
                    0.0,
                    100.0,
                    slider_step=1.0,
                    number_step=0.01,
                    number_format="%.3f",
                    unit="EUR/tCO₂/god",
                )
            elif custom_function == "logarithmic":
                st.code("P(τ) = P₀ + a · ln(1 + b · τ)", language=None)
                paired_numeric_control(
                    "economics_custom_log_amplitude",
                    "Logaritamska amplituda a",
                    0.0,
                    1000.0,
                    slider_step=5.0,
                    number_step=0.1,
                    number_format="%.2f",
                    unit="EUR/tCO₂",
                )
                paired_numeric_control(
                    "economics_custom_log_rate",
                    "Logaritamska stopa b",
                    0.001,
                    1.0,
                    slider_step=0.02,
                    number_step=0.001,
                    number_format="%.4f",
                    unit="1/god",
                    logarithmic=True,
                )
            else:
                st.code("P(τ) = P₀ + a · τᶜ", language=None)
                paired_numeric_control(
                    "economics_custom_power_coefficient",
                    "Power-law koeficijent a",
                    0.0,
                    100.0,
                    slider_step=1.0,
                    number_step=0.01,
                    number_format="%.3f",
                    unit="EUR/tCO₂",
                )
                paired_numeric_control(
                    "economics_custom_power_exponent",
                    "Power-law eksponent c",
                    0.01,
                    5.0,
                    slider_step=0.05,
                    number_step=0.01,
                    number_format="%.3f",
                    unit="-",
                )

        try:
            co2_price_chart = generate_co2_price_path(
                st.session_state[ACTIVE_INPUTS_KEY]
            ).rename(
                columns={"Cijena CO2 (EUR/tCO2)": "Cijena CO₂ (EUR/tCO₂)"}
            ).set_index("Godina")
            st.line_chart(
                co2_price_chart,
                x_label="Godina",
                y_label="Cijena CO₂ (EUR/tCO₂)",
                height=240,
            )
            if selected_price_mode != "custom":
                st.caption(
                    "Zadane putanje kalendarski su poravnate s izvornim nizom "
                    "2025.–2050.; nakon 2050. zadržava se posljednja dostupna cijena "
                    "(demonstracijska pretpostavka, TODO: potreban izvor)."
                )
        except ValueError as exc:
            st.error(f"Cjenovna putanja nije valjana: {exc}")

        with st.expander("Opći financijski parametri"):
            paired_numeric_control(
                "economics_interest_rate",
                "Kamatna stopa",
                0.0,
                0.30,
                slider_step=0.005,
                number_step=0.001,
                number_format="%.3f",
                unit="-",
            )
            paired_numeric_control(
                "economics_inflation_rate",
                "Stopa inflacije",
                0.0,
                0.30,
                slider_step=0.005,
                number_step=0.001,
                number_format="%.3f",
                unit="-",
            )

        with st.expander("Emiter i hvatanje CO₂"):
            text_control("emitter_name", "Naziv emitera")
            selection_control(
                "emitter_capture_technology",
                "Tehnologija hvatanja",
                ["PI", "NI", "OXY"],
                {
                    "PI": "Post-combustion (PI)",
                    "NI": "Pre-combustion (NI)",
                    "OXY": "Oxy-fuel (OXY)",
                },
            )
            paired_numeric_control(
                "emitter_emissions_annual",
                "Godišnje emisije emitera",
                0.0,
                10_000_000.0,
                slider_step=10_000.0,
                number_step=1.0,
                number_format="%.2f",
                unit="tCO₂/god",
            )
            paired_numeric_control(
                "emitter_capex",
                "CAPEX hvatanja",
                0.0,
                2_000_000_000.0,
                slider_step=1_000_000.0,
                number_step=1000.0,
                number_format="%.2f",
                unit="EUR",
            )
            paired_numeric_control(
                "emitter_opex_per_ton",
                "OPEX hvatanja",
                0.0,
                500.0,
                slider_step=1.0,
                number_step=0.1,
                number_format="%.2f",
                unit="EUR/tCO₂",
            )
            paired_numeric_control(
                "emitter_emissions_change_a",
                "Koeficijent promjene emisija a",
                -0.10,
                0.10,
                slider_step=0.005,
                number_step=0.0001,
                number_format="%.4f",
                unit="-",
            )
            paired_numeric_control(
                "emitter_emissions_change_c",
                "Eksponent promjene emisija c",
                0.1,
                5.0,
                slider_step=0.1,
                number_step=0.01,
                number_format="%.2f",
                unit="-",
            )

        with st.expander("Transport CO₂"):
            text_control("transport_section_name", "Naziv transportne dionice")
            paired_numeric_control(
                "transport_flow_rate",
                "Godišnji transportni protok",
                0.0,
                10_000_000.0,
                slider_step=10_000.0,
                number_step=1.0,
                number_format="%.2f",
                unit="tCO₂/god",
            )
            paired_numeric_control(
                "transport_capex",
                "CAPEX transporta",
                0.0,
                2_000_000_000.0,
                slider_step=1_000_000.0,
                number_step=1000.0,
                number_format="%.2f",
                unit="EUR",
            )
            paired_numeric_control(
                "transport_opex_per_ton",
                "OPEX transporta",
                0.0,
                500.0,
                slider_step=1.0,
                number_step=0.1,
                number_format="%.2f",
                unit="EUR/tCO₂",
            )

        with st.expander("Skladište CO₂"):
            text_control("storage_name", "Naziv skladišta")
            selection_control(
                "storage_type",
                "Tip skladišta",
                ["DSA", "DHF"],
                {
                    "DSA": "Duboki slani akvifer (DSA)",
                    "DHF": "Iscrpljeno ugljikovodično ležište (DHF)",
                },
            )
            paired_numeric_control(
                "storage_capacity",
                "Nazivni kapacitet skladišta",
                0.0,
                10_000_000_000.0,
                slider_step=10_000_000.0,
                number_step=1.0,
                number_format="%.2f",
                unit="tCO₂",
            )
            paired_numeric_control(
                "storage_capex",
                "CAPEX skladišta",
                0.0,
                2_000_000_000.0,
                slider_step=1_000_000.0,
                number_step=1000.0,
                number_format="%.2f",
                unit="EUR",
            )
            paired_numeric_control(
                "storage_opex_per_ton",
                "OPEX skladištenja",
                0.0,
                500.0,
                slider_step=1.0,
                number_step=0.1,
                number_format="%.2f",
                unit="EUR/tCO₂",
            )

validation_errors, validation_warnings = validate_active_inputs(
    st.session_state[ACTIVE_INPUTS_KEY]
)
if validation_errors:
    st.error(
        "Proračun je privremeno onemogućen zbog ulaza:\n\n- "
        + "\n- ".join(validation_errors)
    )
for validation_warning in validation_warnings:
    st.warning(validation_warning)

with st.sidebar:
    st.header("Aktivni scenarij")
    st.caption("Zadana ulazna datoteka")
    st.code(str(DEFAULT_INPUT_PATH), language=None)

    with st.expander("Prikaži aktivne ulazne parametre"):
        st.json(st.session_state[ACTIVE_INPUTS_KEY])

    st.download_button(
        "Preuzmi aktivni JSON",
        data=json.dumps(
            st.session_state[ACTIVE_INPUTS_KEY],
            ensure_ascii=False,
            indent=2,
        ),
        file_name="main_inputs_custom.json",
        mime="application/json",
        width="stretch",
    )
    run_requested = st.button(
        "Pokreni proračun",
        type="primary",
        width="stretch",
        disabled=bool(validation_errors),
    )
    clear_requested = st.button(
        "Očisti rezultate",
        width="stretch",
    )
    st.button(
        "Vrati zadane ulaze",
        width="stretch",
        on_click=_reset_scenario,
    )
    if validation_errors:
        st.caption("Ispravite označene ulaze prije pokretanja proračuna.")

if clear_requested:
    _clear_stale_results()

if run_requested:
    st.session_state[ERROR_KEY] = None
    with st.spinner("Izvodim inženjerski proračun aktivnog scenarija..."):
        try:
            st.session_state[RESULTS_KEY] = ScenarioRunner(
                st.session_state[ACTIVE_INPUTS_KEY]
            ).run()
        except Exception as exc:  # Streamlit mora prikazati grešku modela bez rušenja UI-ja.
            st.session_state[RESULTS_KEY] = None
            st.session_state[ERROR_KEY] = str(exc)

if st.session_state[ERROR_KEY] is not None:
    st.error(f"Proračun nije završen: {st.session_state[ERROR_KEY]}")

results = st.session_state[RESULTS_KEY]

if results is None:
    st.info(
        "Za prikaz rezultata odaberite **Pokreni proračun** u bočnom izborniku."
    )
else:
    mbal_df = results["mbal_df"]
    vfp_co2_df = results["vfp_co2_df"]
    doublet_df = results["doublet_df"]
    vfp_gt_df = results["vfp_gt_df"]
    gt_info = results["gt_info"]
    relative_permeability_df = results["relative_permeability_df"]

    final_stored_co2 = float(mbal_df["m_CO2, Mt"].iloc[-1])
    final_dsa_pressure = float(mbal_df["DSA pressure, bar"].iloc[-1])
    max_co2_bhp = float(vfp_co2_df["BHP [bar]"].max())
    max_co2_power = float(vfp_co2_df["CO2 comp. P [kW]"].max())
    final_gt_temperature = float(vfp_gt_df["prod t, °C"].iloc[-1])
    max_net_gt_power = float(vfp_gt_df["net power GT, kW"].max())

    if gt_info["breakthrough_reached"]:
        breakthrough_value = f"{float(gt_info['t_bt']):.2f} god."
    else:
        breakthrough_value = "Nije dosegnut"

    st.subheader("Ključni pokazatelji")
    first_metric_row = st.columns(4)
    first_metric_row[0].metric("Uskladišteni CO₂", f"{final_stored_co2:.2f} Mt")
    first_metric_row[1].metric("Konačni DSA tlak", f"{final_dsa_pressure:.2f} bar")
    first_metric_row[2].metric("Maksimalni CO₂ BHP", f"{max_co2_bhp:.2f} bar")
    first_metric_row[3].metric("Toplinski prodor", breakthrough_value)

    second_metric_row = st.columns(3)
    second_metric_row[0].metric(
        "Maksimalna snaga kompresora za CO₂", f"{max_co2_power:.2f} kW"
    )
    second_metric_row[1].metric(
        "Završna GT temperatura", f"{final_gt_temperature:.2f} °C"
    )
    second_metric_row[2].metric(
        "Maksimalna neto GT snaga", f"{max_net_gt_power:.2f} kW"
    )

    storage_mass_chart = mbal_df[["Time, yr", "m_CO2, Mt"]].rename(
        columns={
            "Time, yr": "Vrijeme (god)",
            "m_CO2, Mt": "Uskladišteni CO₂ (Mt)",
        }
    ).set_index("Vrijeme (god)")
    pressure_chart = pd.DataFrame(
        {
            "Vrijeme (god)": mbal_df["Time, yr"].to_numpy(),
            "DSA tlak (bar)": mbal_df["DSA pressure, bar"].to_numpy(),
            "CO₂ BHP (bar)": vfp_co2_df["BHP [bar]"].to_numpy(),
            "CO₂ WHP (bar)": vfp_co2_df["CO2 WHP [bar]"].to_numpy(),
        }
    ).set_index("Vrijeme (god)")
    co2_power_chart = vfp_co2_df[["Time [yr]", "CO2 comp. P [kW]"]].rename(
        columns={
            "Time [yr]": "Vrijeme (god)",
            "CO2 comp. P [kW]": "Snaga kompresora za CO₂ (kW)",
        }
    ).set_index("Vrijeme (god)")
    geothermal_temperature_chart = vfp_gt_df[["Time [yr]", "prod t, °C"]].rename(
        columns={
            "Time [yr]": "Vrijeme (god)",
            "prod t, °C": "Proizvodna temperatura (°C)",
        }
    ).set_index("Vrijeme (god)")
    geothermal_flow_chart = vfp_gt_df[["Time [yr]", "m_dot, kg/s"]].rename(
        columns={
            "Time [yr]": "Vrijeme (god)",
            "m_dot, kg/s": "Geotermalni maseni protok (kg/s)",
        }
    ).set_index("Vrijeme (god)")
    geothermal_power_chart = vfp_gt_df[
        ["Time [yr]", "ORC power, kW", "pump power, kW", "net power GT, kW"]
    ].rename(
        columns={
            "Time [yr]": "Vrijeme (god)",
            "ORC power, kW": "ORC snaga (kW)",
            "pump power, kW": "Snaga pumpe (kW)",
            "net power GT, kW": "Neto GT snaga (kW)",
        }
    ).set_index("Vrijeme (god)")
    thermal_front_chart = doublet_df[["time, years", "front radius, m"]].rename(
        columns={
            "time, years": "Vrijeme (god)",
            "front radius, m": "Radijus toplinske fronte (m)",
        }
    ).set_index("Vrijeme (god)")
    relative_permeability_chart = relative_permeability_df.rename(
        columns={
            "Sw (-)": "Zasićenje vodom Sw (-)",
            "krw (-)": "krw (-)",
            "krg (-)": "krg (-)",
        }
    ).set_index("Zasićenje vodom Sw (-)")

    overview_tab, storage_tab, geothermal_tab, tables_tab, assumptions_tab = st.tabs(
        [
            "Sažetak",
            "CCS",
            "Geotermalni sustav",
            "Tablice",
            "Pretpostavke",
        ]
    )

    with overview_tab:
        st.markdown("#### Vremenski niz uskladištenog CO₂")
        st.line_chart(
            storage_mass_chart,
            x_label="Vrijeme (god)",
            y_label="Uskladišteni CO₂ (Mt)",
            height=320,
        )

        st.markdown("#### Vremenski niz tlakova sustava")
        st.line_chart(
            pressure_chart,
            x_label="Vrijeme (god)",
            y_label="Tlak (bar)",
            height=320,
        )

        st.markdown("#### Izlazna snaga sustava")
        combined_power_chart = pd.DataFrame(
            {
                "Vrijeme (god)": vfp_gt_df["Time [yr]"].to_numpy(),
                "ORC snaga (kW)": vfp_gt_df["ORC power, kW"].to_numpy(),
                "Snaga pumpe (kW)": vfp_gt_df["pump power, kW"].to_numpy(),
                "Neto GT snaga (kW)": vfp_gt_df["net power GT, kW"].to_numpy(),
                "Snaga kompresora za CO₂ (kW)": vfp_co2_df[
                    "CO2 comp. P [kW]"
                ].to_numpy(),
            }
        ).set_index("Vrijeme (god)")
        st.line_chart(
            combined_power_chart,
            x_label="Vrijeme (god)",
            y_label="Snaga (kW)",
            height=360,
        )
        st.caption(
            "ORC i neto snaga geotermalnog sustava prikazuju proizvodnju, "
            "a snaga pumpe i snaga kompresora za CO₂ zasebne su komponente "
            "potrošnje."
        )

    with storage_tab:
        st.markdown("#### Masa i tlak skladištenja")
        st.line_chart(
            storage_mass_chart,
            x_label="Vrijeme (god)",
            y_label="Uskladišteni CO₂ (Mt)",
        )
        st.line_chart(
            pressure_chart,
            x_label="Vrijeme (god)",
            y_label="Tlak (bar)",
        )
        st.markdown("#### Snaga kompresora za CO₂")
        st.line_chart(
            co2_power_chart,
            x_label="Vrijeme (god)",
            y_label="Snaga kompresora za CO₂ (kW)",
        )
        st.markdown("#### Relativne propusnosti vode i CO₂")
        st.line_chart(
            relative_permeability_chart,
            x_label="Zasićenje vodom Sw (-)",
            y_label="Relativna propusnost (-)",
        )

    with geothermal_tab:
        temperature_column, flow_column = st.columns(2)
        with temperature_column:
            st.markdown("#### Proizvodna temperatura")
            st.line_chart(
                geothermal_temperature_chart,
                x_label="Vrijeme (god)",
                y_label="Temperatura (°C)",
            )
        with flow_column:
            st.markdown("#### Maseni protok geotermalne vode")
            st.line_chart(
                geothermal_flow_chart,
                x_label="Vrijeme (god)",
                y_label="Maseni protok geotermalne vode (kg/s)",
            )

        st.markdown("#### Neto snaga geotermalnog sustava")
        st.line_chart(
            geothermal_power_chart,
            x_label="Vrijeme (god)",
            y_label="Snaga (kW)",
        )
        st.markdown("#### Napredovanje toplinske fronte")
        st.line_chart(
            thermal_front_chart,
            x_label="Vrijeme (god)",
            y_label="Radijus toplinske fronte (m)",
        )

    with tables_tab:
        with st.expander("Materijalna bilanca", expanded=True):
            st.dataframe(mbal_df, width="stretch")
        with st.expander("CO₂ bušotina i kompresija"):
            st.dataframe(vfp_co2_df, width="stretch")
        with st.expander("Geotermalni dubl i snaga"):
            st.dataframe(vfp_gt_df, width="stretch")
        with st.expander("Toplinska fronta"):
            st.dataframe(doublet_df, width="stretch")
        with st.expander("Relativne propusnosti"):
            st.dataframe(relative_permeability_df, width="stretch")

    with assumptions_tab:
        st.markdown(
            """
            Ova verzija zadržava postojeće inženjerske jednadžbe, ali više ne
            zaobilazi odabrane ulaze u servisnom sloju:

            - `bhp_dp` je korisnički drawdown proizvodne geotermalne bušotine;
            - CO₂, proizvodna GT i utisna GT bušotina imaju zasebne radijuse;
            - `t_out` se koristi za ORC izlaz i ohlađenu utisnu vodu;
            - `p_out` se koristi kao ORC izlazni tlak;
            - neto geotermalna snaga predstavlja ORC snagu umanjenu za snagu pumpe;
            - cjenovna putanja i ekonomski ulazi mogu se uređivati, ali cash-flow
              ekonomika još nije spojena na inženjerske rezultate.
            """
        )
        st.info(
            "Streamlit sloj upravlja ulazima i prikazuje rezultate. "
            "Inženjerske jednadžbe ostaju u modulima direktorija engineering."
        )
