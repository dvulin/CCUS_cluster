"""Streamlit UI for the current GT-CCS engineering demonstration."""

from copy import deepcopy
import json
import math

import numpy as np
import pandas as pd
import streamlit as st

from economics import generate_co2_price_path
from inputs.scenario_sync import (
    expand_storage_capacity_for_plan,
    required_storage_capacity_t,
)
from inputs.scenario_store import (
    LAST_INPUTS_FILENAME,
    delete_scenario,
    list_saved_scenarios,
    load_scenario,
    save_scenario,
    scenario_directory,
)
from outputs import build_results_excel, build_results_json
from services.scenario_runner import DEFAULT_INPUT_PATH, ScenarioRunner


RESULTS_KEY = "engineering_demo_results"
ERROR_KEY = "engineering_demo_error"
ACTIVE_INPUTS_KEY = "active_scenario_inputs"
CONTROL_PREFIX = "input__"
SCENARIO_NOTICE_KEY = "scenario_store_notice"
SCENARIO_STORE_ERROR_KEY = "scenario_store_error"
SCENARIO_SEARCH_KEY = "scenario_store_search"
SCENARIO_LOAD_SELECT_KEY = "scenario_store_load_selection"
SCENARIO_DELETE_SELECT_KEY = "scenario_store_delete_selection"
SCENARIO_DELETE_CONFIRM_KEY = "scenario_store_delete_confirm"
COLLAPSE_INPUTS_ON_RUN_KEY = "collapse_inputs_on_run_once"
CHART_FONT_SIZE_ADJUSTMENT_KEY = "chart_font_size_adjustment"
CALENDAR_HOURS_PER_YEAR = 365.25 * 24.0
WELL_DEPTH_DEFAULTS = {
    "h_ref_co2": "Referentna dubina utisne CO₂ bušotine za VFP proračun",
    "h_ref_geothermal_production": (
        "Referentna dubina proizvodne geotermalne bušotine za VFP proračun"
    ),
    "h_ref_geothermal_injection": (
        "Referentna dubina utisne geotermalne bušotine za VFP proračun"
    ),
}


def _chart_style_config(font_size_adjustment=0):
    """Return the shared chart style with a runtime-compatible font offset."""
    from chart_styles import vega_lite_chart_config

    # Always call the no-argument API so a Streamlit process that still has the
    # preceding chart_styles module cached can complete its current rerun.  The
    # runtime offset is deliberately applied here to the fresh configuration.
    config = vega_lite_chart_config()
    adjustment = int(font_size_adjustment)
    for section, font_size_keys in {
        "axis": ("labelFontSize", "titleFontSize"),
        "legend": ("labelFontSize", "titleFontSize"),
        "title": ("fontSize",),
    }.items():
        for font_size_key in font_size_keys:
            if font_size_key in config.get(section, {}):
                config[section][font_size_key] += adjustment
    return config


def _legend_visibility_parameter(series_field):
    """Return a legend-bound selection containing visible chart series."""
    return {
        "name": "legend_visible_series",
        "select": {
            "type": "point",
            "fields": [series_field],
            # Vega expression string forces ordinary clicks to toggle each
            # series independently; boolean True toggles only with Shift.
            "toggle": "true",
        },
        "bind": "legend",
    }


def _legend_opacity_encoding():
    """Show selected series and fully hide each deselected series."""
    return {
        "condition": {
            "param": "legend_visible_series",
            "empty": False,
            "value": 1.0,
        },
        "value": 0.0,
    }


def _initialize_legend_selection(spec, series_field, series_names):
    """Initialize a chart legend with every available series selected."""
    initial_value = [
        {series_field: series_name}
        for series_name in dict.fromkeys(str(name) for name in series_names)
    ]
    for container in [spec, *spec.get("layer", [])]:
        for parameter in container.get("params", []):
            if parameter.get("name") == "legend_visible_series":
                parameter["value"] = initial_value
                return spec
    raise ValueError("Vega-Lite specifikacija nema interaktivnu legendu.")


def _wide_chart_spec(
    *,
    x_title,
    y_title,
    x_field,
    x_type,
    chart_type="line",
    height=320,
    y_domain=None,
    font_size_adjustment=0,
):
    """Return a styled Vega-Lite spec for a long-form wide-data chart."""
    if chart_type not in {"line", "bar"}:
        raise ValueError("chart_type mora biti 'line' ili 'bar'.")
    mark = {"type": chart_type, "clip": True}
    if chart_type == "line":
        mark.update({"strokeWidth": 2.2, "point": {"filled": True, "size": 24}})
    x_axis = {"title": x_title}
    if x_type == "quantitative":
        x_axis["format"] = ".6~g"
    y_scale = {"zero": chart_type == "bar"}
    if y_domain is not None and chart_type == "line":
        y_scale["domain"] = list(y_domain)
    return {
        "mark": mark,
        "encoding": {
            "x": {
                "field": x_field,
                "type": x_type,
                "axis": x_axis,
            },
            "y": {
                "field": "Value",
                "type": "quantitative",
                "axis": {"title": y_title, "format": ".6~g"},
                "scale": y_scale,
            },
            "color": {
                "field": "Series",
                "type": "nominal",
                "legend": {"title": None},
            },
            "opacity": _legend_opacity_encoding(),
            "tooltip": [
                {"field": x_field, "type": x_type, "title": x_title},
                {"field": "Series", "type": "nominal", "title": "Serija"},
                {
                    "field": "Value",
                    "type": "quantitative",
                    "title": y_title,
                    "format": ",.4f",
                },
            ],
        },
        "params": [_legend_visibility_parameter("Series")],
        "height": height,
        "config": _chart_style_config(font_size_adjustment),
    }


def _current_chart_font_size_adjustment():
    return int(st.session_state.get(CHART_FONT_SIZE_ADJUSTMENT_KEY, 0))


def _render_wide_chart(
    frame,
    *,
    x_title,
    y_title,
    chart_type="line",
    height=320,
):
    """Render numeric wide data after removing non-finite chart points."""
    if isinstance(frame, pd.Series):
        frame = frame.to_frame()
    chart_frame = frame.reset_index()
    source_x_field = chart_frame.columns[0]
    value_columns = list(chart_frame.columns[1:])
    x_field = "X"
    chart_frame = chart_frame.rename(columns={source_x_field: x_field})
    long_frame = chart_frame.melt(
        id_vars=[x_field],
        value_vars=value_columns,
        var_name="Series",
        value_name="Value",
    )
    long_frame["Series"] = long_frame["Series"].astype(str)
    long_frame["Value"] = pd.to_numeric(
        long_frame["Value"], errors="coerce"
    )
    long_frame = long_frame.replace([np.inf, -np.inf], np.nan).dropna(
        subset=[x_field, "Value"]
    )
    if long_frame.empty:
        st.warning("Nema konačnih podataka za iscrtavanje ovog dijagrama.")
        return
    y_domain = None
    if chart_type == "line":
        y_min = float(long_frame["Value"].min())
        y_max = float(long_frame["Value"].max())
        y_span = y_max - y_min
        y_padding = (
            0.05 * y_span
            if y_span > 0.0
            else max(0.05 * abs(y_min), 1.0e-9)
        )
        y_domain = [y_min - y_padding, y_max + y_padding]
    x_type = (
        "quantitative"
        if pd.api.types.is_numeric_dtype(long_frame[x_field])
        else "ordinal"
    )
    spec = _initialize_legend_selection(
        _wide_chart_spec(
            x_title=x_title,
            y_title=y_title,
            x_field=x_field,
            x_type=x_type,
            chart_type=chart_type,
            height=height,
            y_domain=y_domain,
            font_size_adjustment=_current_chart_font_size_adjustment(),
        ),
        "Series",
        value_columns,
    )
    st.vega_lite_chart(
        long_frame,
        spec,
        width="stretch",
        theme=None,
    )


def _zoomable_line_chart_spec(
    *,
    x_title,
    y_title,
    zoom_name,
    y_zoom_name=None,
    x_field="Godina",
    series_field="Serija",
    value_field="Vrijednost",
    value_format=",.2f",
    integer_x=False,
    interpolate="linear",
    height=360,
    font_size_adjustment=0,
):
    """Return a multi-series Vega-Lite line spec with optional separate y zoom."""
    x_axis = {"title": x_title}
    x_tooltip = {
        "field": x_field,
        "type": "quantitative",
        "title": x_title,
    }
    if integer_x:
        x_axis.update({"format": "d", "tickMinStep": 1})
        x_tooltip["format"] = "d"

    spec = {
        "mark": {
            "type": "line",
            "interpolate": interpolate,
            "clip": True,
            "point": {"filled": True, "size": 32},
        },
        "encoding": {
            "x": {
                "field": x_field,
                "type": "quantitative",
                "axis": x_axis,
            },
            "y": {
                "field": value_field,
                "type": "quantitative",
                "axis": {"title": y_title},
                "scale": {"zero": True},
            },
            "color": {
                "field": series_field,
                "type": "nominal",
                "legend": {"title": None},
            },
            "opacity": _legend_opacity_encoding(),
            "tooltip": [
                x_tooltip,
                {
                    "field": series_field,
                    "type": "nominal",
                    "title": "Serija",
                },
                {
                    "field": value_field,
                    "type": "quantitative",
                    "title": y_title,
                    "format": value_format,
                },
            ],
        },
        "params": [],
        "height": height,
        "config": _chart_style_config(font_size_adjustment),
    }

    x_selection = {"type": "interval", "encodings": ["x"]}
    if y_zoom_name is not None:
        x_selection.update(
            {
                "translate": (
                    "[mousedown[!event.shiftKey], window:mouseup] "
                    "> window:mousemove!"
                ),
                "zoom": "wheel![!event.shiftKey]",
            }
        )
    spec["params"].append(
        {
            "name": zoom_name,
            "select": x_selection,
            "bind": "scales",
        }
    )
    if y_zoom_name is not None:
        spec["params"].append(
            {
                "name": y_zoom_name,
                "select": {
                    "type": "interval",
                    "encodings": ["y"],
                    "translate": (
                        "[mousedown[event.shiftKey], window:mouseup] "
                        "> window:mousemove!"
                    ),
                    "zoom": "wheel![event.shiftKey]",
                },
                "bind": "scales",
            }
        )
    spec["params"].append(_legend_visibility_parameter(series_field))
    return spec


def _compressor_density_chart_spec(font_size_adjustment=0):
    """Return an interactive dual-axis compressor-power/density chart spec."""
    common_x = {
        "field": "Vrijeme (god)",
        "type": "quantitative",
        "axis": {"title": "Vrijeme (god)"},
    }
    common_color = {
        "field": "Serija",
        "type": "nominal",
        "legend": {"title": None},
        "scale": {
            "domain": [
                "P komp.",
                "ρ BHP",
                "ρ WHP",
            ],
            "range": ["#C43C39", "#2F6B9A", "#2A9D68"],
        },
    }
    common_tooltip = [
        {
            "field": "Vrijeme (god)",
            "type": "quantitative",
            "title": "Vrijeme (god)",
            "format": ".2f",
        },
        {"field": "Serija", "type": "nominal", "title": "Serija"},
        {
            "field": "Vrijednost",
            "type": "quantitative",
            "title": "Vrijednost",
            "format": ",.2f",
        },
        {"field": "Jedinica", "type": "nominal", "title": "Jedinica"},
    ]
    return {
        "layer": [
            {
                "transform": [{"filter": "datum.Skupina === 'Snaga'"}],
                "mark": {"type": "line", "clip": True, "strokeWidth": 2.4},
                "params": [
                    {
                        "name": "compressor_density_x_zoom",
                        "select": {"type": "interval", "encodings": ["x"]},
                        "bind": "scales",
                    },
                    _legend_visibility_parameter("Serija"),
                ],
                "encoding": {
                    "x": common_x,
                    "y": {
                        "field": "Vrijednost",
                        "type": "quantitative",
                        "axis": {
                            "title": "Snaga kompresora za CO₂ (kW)",
                            "orient": "left",
                        },
                        "scale": {"zero": True},
                    },
                    "color": common_color,
                    "opacity": _legend_opacity_encoding(),
                    "tooltip": common_tooltip,
                },
            },
            {
                "transform": [{"filter": "datum.Skupina === 'Gustoća'"}],
                "mark": {"type": "line", "clip": True, "strokeWidth": 1.9},
                "encoding": {
                    "x": common_x,
                    "y": {
                        "field": "Vrijednost",
                        "type": "quantitative",
                        "axis": {
                            "title": "Gustoća CO₂ (kg/m³)",
                            "orient": "right",
                        },
                        "scale": {"zero": False},
                    },
                    "color": common_color,
                    "opacity": _legend_opacity_encoding(),
                    "strokeDash": {
                        "field": "Serija",
                        "type": "nominal",
                        "legend": None,
                    },
                    "tooltip": common_tooltip,
                },
            },
        ],
        "resolve": {"scale": {"x": "shared", "y": "independent"}},
        "height": 360,
        "config": _chart_style_config(font_size_adjustment),
    }


def _render_long_series_chart(
    frame,
    spec,
    *,
    series_field="Serija",
):
    """Render a long-form Vega chart with all legend series selected."""
    chart_frame = frame.copy()
    chart_frame[series_field] = chart_frame[series_field].astype(str)
    series_names = chart_frame[series_field].dropna().unique().tolist()
    spec = _initialize_legend_selection(spec, series_field, series_names)
    st.vega_lite_chart(
        chart_frame,
        spec,
        width="stretch",
        theme=None,
    )


def _entry_value(inputs, key):
    return inputs[key][0]


def _set_entry_value(key, value):
    inputs = st.session_state[ACTIVE_INPUTS_KEY]
    inputs[key][0] = value

    # Jedna godišnja količina CO₂ vrijedi za hvatanje, transport, utiskivanje
    # i verificirano skladištenje. Ovi ključevi ostaju sinkronizirani zbog
    # kompatibilnosti postojećih engineering klasa i JSON scenarija.
    if key == "m_dot_annual":
        annual_tonnes = float(value) * 1000.0
    elif key in {"emitter_emissions_annual", "transport_flow_rate"}:
        annual_tonnes = float(value)
    else:
        annual_tonnes = None
    if annual_tonnes is not None:
        inputs["emitter_emissions_annual"][0] = annual_tonnes
        inputs["transport_flow_rate"][0] = annual_tonnes
        inputs["m_dot_annual"][0] = annual_tonnes / 1000.0

    # The planning period and annual quantity define the mass that must fit in
    # storage.  When one of those inputs is edited, keep the selected end year
    # achievable by expanding the JSON-backed capacity if needed.  A later
    # direct edit of storage_capacity still creates an intentional capacity
    # limit and is therefore not overridden here.
    if key in {
        "ccs_injection_start_year",
        "ccs_injection_end_year",
        "m_dot_annual",
        "emitter_emissions_annual",
        "transport_flow_rate",
    }:
        expand_storage_capacity_for_plan(inputs)

    if key in {"eta", "eta_orc"}:
        inputs["eta"][0] = float(value)
        inputs["eta_orc"][0] = float(value)


def _clear_stale_results():
    st.session_state[RESULTS_KEY] = None
    st.session_state[ERROR_KEY] = None
    st.session_state[COLLAPSE_INPUTS_ON_RUN_KEY] = False


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


def _stored_numeric_value(value, integer, stored_units_per_display_unit):
    stored_value = value * stored_units_per_display_unit
    if integer:
        return int(round(stored_value))
    return float(stored_value)


def _slider_changed(
    parameter,
    slider_widget_key,
    number_widget_key,
    integer,
    stored_units_per_display_unit,
):
    value = st.session_state[slider_widget_key]
    if integer:
        value = int(round(value))
    else:
        value = float(value)
    st.session_state[number_widget_key] = value
    _set_entry_value(
        parameter,
        _stored_numeric_value(
            value,
            integer,
            stored_units_per_display_unit,
        ),
    )
    _clear_stale_results()


def _number_changed(
    parameter,
    slider_widget_key,
    number_widget_key,
    logarithmic,
    integer,
    logarithmic_options,
    stored_units_per_display_unit,
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
    _set_entry_value(
        parameter,
        _stored_numeric_value(
            value,
            integer,
            stored_units_per_display_unit,
        ),
    )
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


def _activate_scenario(inputs):
    st.session_state[ACTIVE_INPUTS_KEY] = deepcopy(inputs)
    for key in list(st.session_state):
        if key.startswith(CONTROL_PREFIX):
            del st.session_state[key]
    _clear_stale_results()


def _reset_scenario():
    _activate_scenario(DEFAULT_INPUTS)


def _collapse_inputs_on_run():
    st.session_state[COLLAPSE_INPUTS_ON_RUN_KEY] = True


def _load_selected_scenario():
    filename = st.session_state.get(SCENARIO_LOAD_SELECT_KEY)
    if not filename:
        return
    try:
        loaded_inputs = load_scenario(filename)
    except (OSError, ValueError) as exc:
        st.session_state[SCENARIO_STORE_ERROR_KEY] = str(exc)
        return
    _activate_scenario(loaded_inputs)
    st.session_state[SCENARIO_STORE_ERROR_KEY] = None
    st.session_state[SCENARIO_NOTICE_KEY] = (
        f"Učitan je scenarij iz datoteke {filename}."
    )


def _delete_selected_scenario():
    filename = st.session_state.get(SCENARIO_DELETE_SELECT_KEY)
    confirmed = st.session_state.get(SCENARIO_DELETE_CONFIRM_KEY, False)
    if not filename or not confirmed:
        return
    try:
        delete_scenario(filename)
    except (OSError, ValueError) as exc:
        st.session_state[SCENARIO_STORE_ERROR_KEY] = str(exc)
        return
    st.session_state.pop(SCENARIO_DELETE_SELECT_KEY, None)
    st.session_state.pop(SCENARIO_DELETE_CONFIRM_KEY, None)
    st.session_state[SCENARIO_STORE_ERROR_KEY] = None
    st.session_state[SCENARIO_NOTICE_KEY] = (
        f"Obrisana je arhiva scenarija {filename}."
    )


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
    stored_units_per_display_unit=1.0,
):
    """Render a synchronized slider and precise number input.

    ``stored_units_per_display_unit`` keeps the JSON value in its canonical
    unit while allowing a more readable UI unit, for example tonnes stored as
    Mt in the capacity control.
    """
    if maximum < minimum:
        raise ValueError(
            f"Neispravan raspon za {parameter}: {minimum} > {maximum}."
        )
    inputs = st.session_state[ACTIVE_INPUTS_KEY]
    raw_value = _entry_value(inputs, parameter)
    display_value = float(raw_value) / float(stored_units_per_display_unit)
    value = int(display_value) if integer else display_value
    bounded_value = min(max(value, minimum), maximum)
    if bounded_value != value:
        value = int(bounded_value) if integer else float(bounded_value)
        _set_entry_value(
            parameter,
            _stored_numeric_value(
                value,
                integer,
                stored_units_per_display_unit,
            ),
        )
        _clear_stale_results()

    slider_widget_key = _slider_key(parameter)
    number_widget_key = _number_key(parameter)
    number_label = label if unit == "-" else f"{label} ({unit})"
    if maximum == minimum:
        st.session_state.pop(slider_widget_key, None)
        st.session_state[number_widget_key] = value
        st.number_input(
            number_label,
            step=number_step,
            format=number_format,
            key=number_widget_key,
            disabled=True,
            help=help_text,
        )
        st.caption(
            "Kontrola je fiksirana jer su trenutačna donja i gornja "
            f"granica jednake ({_format_numeric_value(value, number_format)})."
        )
        return

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
                    stored_units_per_display_unit,
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
                format=number_format,
                key=slider_widget_key,
                on_change=_slider_changed,
                args=(
                    parameter,
                    slider_widget_key,
                    number_widget_key,
                    integer,
                    stored_units_per_display_unit,
                ),
                help=help_text,
            )
    with number_column:
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
                stored_units_per_display_unit,
            ),
            help=help_text,
        )


def minimum_numeric_control(
    parameter,
    label,
    minimum,
    *,
    number_step,
    number_format,
    unit,
    help_text=None,
):
    """Render a JSON-backed numeric input without an arbitrary upper bound."""
    inputs = st.session_state[ACTIVE_INPUTS_KEY]
    value = float(_entry_value(inputs, parameter))
    if value < minimum:
        value = float(minimum)
        _set_entry_value(parameter, value)
        _clear_stale_results()

    widget_key = _direct_key(parameter)
    st.session_state[widget_key] = value
    number_label = label if unit == "-" else f"{label} ({unit})"
    st.number_input(
        number_label,
        min_value=float(minimum),
        step=number_step,
        format=number_format,
        key=widget_key,
        on_change=_direct_value_changed,
        args=(parameter, widget_key),
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

    if not str(value("scenario_name")).strip():
        errors.append("Naziv scenarija ne smije biti prazan.")

    if value("m_dot_annual") <= 0:
        errors.append(
            "Zatečeni model ne podržava 0 ktpa jer vrijeme računa dijeljenjem "
            "uskladištene mase s protokom. Unos 0 je dopušten, ali proračun nije."
        )
    if value("poro") <= 0:
        errors.append(
            "Zatečeni proračun drenažnog radijusa zahtijeva poroznost veću od nule."
        )
    if value("dp") < 0.5:
        errors.append("Korak tlaka dp mora biti najmanje 0,5 bar.")

    p_max = value("fracture_pressure_gradient") * value("h_top")
    if value("p_ref") > p_max:
        errors.append(
            "Početni tlak ležišta p_ref mora biti najviše dopušteni tlak izveden "
            "iz gradijenta "
            f"tlaka frakturiranja i dubine vrha ležišta: {p_max:.1f} bar."
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
                f"Radijus {label} mora biti manji od razmaka geotermalnog para."
            )

    minimum_well_diameter = 2.0 * min(
        value("rw_co2"),
        value("rw_geothermal_production"),
        value("rw_geothermal_injection"),
    )
    if not 0.0 <= value("epsilon") < minimum_well_diameter:
        errors.append(
            "Hrapavost bušotinske cijevi epsilon mora biti nenegativna i "
            "manja od najmanjeg promjera bušotinske cijevi."
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
            "Minimalno zasićenje CO₂ veće je od raspoloživog "
            "raspona zasićenja 1 − Sw_i; "
            "postojeći Corey model tada reže CO₂ zasićenje na granicu."
        )

    expected_tonnes = float(value("emitter_emissions_annual"))
    if not math.isclose(
        float(value("m_dot_annual")) * 1000.0,
        expected_tonnes,
        rel_tol=1e-12,
        abs_tol=1e-6,
    ) or not math.isclose(
        float(value("transport_flow_rate")),
        expected_tonnes,
        rel_tol=1e-12,
        abs_tol=1e-6,
    ):
        errors.append(
            "Godišnje količine uhvaćenog, transportiranog, utisnutog i "
            "uskladištenog CO₂ moraju biti jednake."
        )

    planned_co2_tonnes = expected_tonnes * (
        int(value("ccs_injection_end_year"))
        - int(value("ccs_injection_start_year"))
        + 1
    )
    if float(value("storage_capacity")) < planned_co2_tonnes:
        capacity_limited_end_year = int(value("ccs_injection_start_year")) + (
            math.ceil(float(value("storage_capacity")) / expected_tonnes) - 1
        )
        warnings.append(
            "Nazivni kapacitet skladišta nije dovoljan za zadani kraj "
            f"utiskivanja: potrebno je {planned_co2_tonnes:,.0f} t, zadano "
            f"je {float(value('storage_capacity')):,.0f} t. Sam kapacitet "
            f"ograničava zadnju aktivnu godinu na {capacity_limited_end_year}."
        )

    timeline = (
        value("economics_start_year"),
        value("economics_ccs_start_year"),
        value("ccs_injection_start_year"),
        value("ccs_injection_end_year"),
        value("economics_end_year"),
    )
    if any(earlier > later for earlier, later in zip(timeline, timeline[1:])):
        errors.append(
            "Mora vrijediti: početak ekonomike ≤ početak ulaganja ≤ početak "
            "utiskivanja ≤ kraj utiskivanja ≤ kraj ekonomike."
        )
    for key, label in (
        ("geothermal_operation_end_year", "Kraj rada geotermalnog sustava"),
        ("ccs_monitoring_end_year", "Kraj monitoringa"),
    ):
        if not value("ccs_injection_end_year") <= value(key) <= value(
            "economics_end_year"
        ):
            errors.append(
                f"{label} mora biti između kraja utiskivanja i kraja ekonomike."
            )

    for key in (
        "eta_orc",
        "eta_gt_injection_pump",
        "eta_co2_compressor_isentropic",
        "eta_co2_dense_phase_pump",
    ):
        if not 0.0 < float(value(key)) <= 1.0:
            errors.append(f"{key} mora biti veći od 0 i manji ili jednak 1.")

    for key in ("economics_interest_rate", "economics_inflation_rate"):
        if float(value(key)) < 0.0:
            errors.append(f"{key} ne smije biti negativan.")

    if value("d_doublet") <= 0:
        errors.append("Razmak geotermalnog para mora biti veći od nule.")
    if value("geothermal_pipeline_inner_diameter_m") <= 0:
        errors.append(
            "Unutarnji promjer geotermalnog cjevovoda mora biti veći od nule."
        )
    if not 0 <= value("geothermal_pipeline_roughness_m") < value(
        "geothermal_pipeline_inner_diameter_m"
    ):
        errors.append(
            "Hrapavost geotermalnog cjevovoda mora biti manja od njegova promjera."
        )
    for key in (
        "geothermal_pipeline_elbows_90_count",
        "geothermal_pipeline_elbows_45_count",
        "geothermal_pipeline_elbows_30_count",
    ):
        if value(key) < 0:
            errors.append(f"{key} ne smije biti negativan.")

    if value("pipeline_ambient_temperature_c") <= -273.15:
        errors.append("Temperatura okoliša mora biti iznad apsolutne nule.")
    for key in (
        "pipeline_environment_thermal_conductivity_w_m_k",
        "pipeline_environment_volumetric_heat_capacity_j_m3_k",
        "pipeline_external_heat_transfer_coefficient_w_m2_k",
        "pipeline_wall_thickness_m",
        "pipeline_wall_thermal_conductivity_w_m_k",
        "pipeline_insulation_thermal_conductivity_w_m_k",
    ):
        if value(key) <= 0:
            errors.append(f"{key} mora biti veći od nule.")
    if value("pipeline_insulation_thickness_m") < 0:
        errors.append("Debljina izolacije ne smije biti negativna.")
    largest_pipeline_outer_radius = max(
        value("geothermal_pipeline_inner_diameter_m") / 2.0,
        (
            value("pipeline_inner_diameter_m") / 2.0
            if value("pipeline_inner_diameter_m") is not None
            else 0.0
        ),
    ) + value("pipeline_wall_thickness_m") + value(
        "pipeline_insulation_thickness_m"
    )
    if (
        value("pipeline_environment_type") == "soil"
        and value("pipeline_burial_depth_m") <= largest_pipeline_outer_radius
    ):
        errors.append(
            "Dubina osi ukopanog cjevovoda mora biti veća od vanjskog "
            "radijusa cijevi s izolacijom."
        )

    if value("transport_mode") == "pipeline":
        if value("co2_pipeline_inlet_pressure_bar") <= 0:
            errors.append("Ulazni tlak CO₂ cjevovoda mora biti veći od nule.")
        if value("co2_pipeline_inlet_temperature_c") <= -273.15:
            errors.append(
                "Ulazna temperatura CO₂ cjevovoda mora biti iznad apsolutne nule."
            )
        if value("pipeline_inner_diameter_m") <= 0:
            errors.append("Unutarnji promjer cjevovoda mora biti veći od nule.")
        if not 0 <= value("pipeline_roughness_m") < value(
            "pipeline_inner_diameter_m"
        ):
            errors.append("Hrapavost cjevovoda mora biti manja od njegova promjera.")

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

# Stariji JSON scenariji imali su jednu zajedničku dubinu ``h_ref``. Ako je
# takav scenarij učitan, pripremi tri role-specific vrijednosti prije nego što
# se napravi aktivna Streamlit kopija.
legacy_default_depth = float(
    _entry_value(DEFAULT_INPUTS, "h_ref")
    if "h_ref" in DEFAULT_INPUTS
    else 2075.0
)
for depth_parameter, depth_description in WELL_DEPTH_DEFAULTS.items():
    DEFAULT_INPUTS.setdefault(
        depth_parameter,
        [legacy_default_depth, "m", depth_description],
    )
DEFAULT_INPUTS.pop("h_ref", None)

if RESULTS_KEY not in st.session_state:
    st.session_state[RESULTS_KEY] = None
if ERROR_KEY not in st.session_state:
    st.session_state[ERROR_KEY] = None
if ACTIVE_INPUTS_KEY not in st.session_state:
    st.session_state[ACTIVE_INPUTS_KEY] = deepcopy(DEFAULT_INPUTS)
else:
    active_inputs = st.session_state[ACTIVE_INPUTS_KEY]
    if active_inputs.pop("geothermal_pipeline_distance_m", None) is not None:
        # Privremeni ključ više nije ulaz modela; d_doublet je jedina aktivna
        # duljina GT voda. Ukloni i rezultate stare sheme iz hot-reload sesije.
        _clear_stale_results()
    if "emitter_emissions_annual" in active_inputs:
        migrated_annual_tonnes = float(
            _entry_value(active_inputs, "emitter_emissions_annual")
        )
    elif "m_dot_annual" in active_inputs:
        migrated_annual_tonnes = float(
            _entry_value(active_inputs, "m_dot_annual")
        ) * 1000.0
    elif "transport_flow_rate" in active_inputs:
        migrated_annual_tonnes = float(
            _entry_value(active_inputs, "transport_flow_rate")
        )
    else:
        migrated_annual_tonnes = float(
            _entry_value(DEFAULT_INPUTS, "emitter_emissions_annual")
        )

    if "eta_orc" in active_inputs:
        migrated_eta_orc = float(_entry_value(active_inputs, "eta_orc"))
    elif "eta" in active_inputs:
        migrated_eta_orc = float(_entry_value(active_inputs, "eta"))
    else:
        migrated_eta_orc = float(_entry_value(DEFAULT_INPUTS, "eta_orc"))

    if "h_ref" in active_inputs:
        legacy_depth = float(_entry_value(active_inputs, "h_ref"))
        for depth_parameter in WELL_DEPTH_DEFAULTS:
            if depth_parameter not in active_inputs:
                depth_entry = deepcopy(DEFAULT_INPUTS[depth_parameter])
                depth_entry[0] = legacy_depth
                active_inputs[depth_parameter] = depth_entry
        del active_inputs["h_ref"]

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

    # Migracija aktivne Streamlit sesije na jedinstvenu godišnju količinu i
    # zasebno imenovanu ORC učinkovitost.
    active_inputs["emitter_emissions_annual"][0] = migrated_annual_tonnes
    active_inputs["m_dot_annual"][0] = migrated_annual_tonnes / 1000.0
    active_inputs["transport_flow_rate"][0] = migrated_annual_tonnes
    active_inputs["eta_orc"][0] = migrated_eta_orc
    active_inputs["eta"][0] = migrated_eta_orc

st.title("GT-CCS demonstracijski proračun")
st.caption(
    "Integrirani proračun skladištenja CO₂, bušotinskih tlakova, "
    "geotermalne proizvodnje, energije i godišnjeg novčanog toka."
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

collapse_inputs_now = bool(
    st.session_state.get(COLLAPSE_INPUTS_ON_RUN_KEY, False)
)
with st.expander(
    "Prilagodba ulaznog scenarija",
    expanded=not collapse_inputs_now,
):
    text_control("scenario_name", "Naziv scenarija")
    st.divider()
    st.caption(
        "Početne vrijednosti svih kontrola učitavaju se iz aktivnog JSON ulaza; "
        "brojčana polja prikazuju trenutačno aktivne vrijednosti."
    )
    (
        reservoir_controls_tab,
        wells_controls_tab,
        relperm_controls_tab,
        economics_controls_tab,
    ) = st.tabs(
        [
            "CCS i akvifer",
            "Bušotine i geotermija",
            "Petrofizikalni parametri",
            "Ekonomika i energija",
        ]
    )

    with reservoir_controls_tab:
        paired_numeric_control(
            "m_dot_annual",
            "Godišnja količina CO₂ kroz cijeli lanac",
            0.0,
            1000.0,
            slider_step=5.0,
            number_step=0.1,
            number_format="%.2f",
            unit="ktpa",
            help_text=(
                "Ovo je jedini uređivi izvor godišnje količine. Vrijednosti "
                "hvatanja, transporta, utiskivanja i verificiranog "
                "skladištenja automatski su jednake."
            ),
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
                "dopušteni tlak prema gradijentu tlaka frakturiranja."
            ),
        )
        minimum_numeric_control(
            "dp",
            "Korak tlaka dp",
            0.5,
            number_step=0.5,
            number_format="%.2f",
            unit="bar",
            help_text=(
                "Tlačni korak materijalne bilance; nije vremenski korak. "
                "Aktivna početna vrijednost učitava se iz JSON ulaza."
            ),
        )
        paired_numeric_control(
            "fracture_pressure_gradient",
            "Gradijent tlaka frakturiranja",
            0.01,
            0.50,
            slider_step=0.005,
            number_step=0.001,
            number_format="%.3f",
            unit="bar/m",
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
        st.markdown("#### ORC — izlazni uvjeti i učinkovitost")
        st.caption(
            "Sve tri vrijednosti ispod spremaju se u aktivni JSON scenarij. "
            "Izlazni tlak dostupan je pod ključem `p_out`."
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
            "ORC izlazni tlak vode p_out",
            1.0,
            100.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="bar",
            help_text=(
                "Tlak geotermalne vode na izlazu iz ORC-a. GT krug može raditi "
                "samo kada je izračunati tlak na ušću proizvodne bušotine "
                "(WHP) viši od p_out. Vrijednost se izvozi u aktivni JSON kao "
                "p_out."
            ),
        )
        paired_numeric_control(
            "eta_orc",
            "Učinkovitost ORC-a",
            0.01,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )

        st.markdown("#### Bušotine i pogonska učinkovitost")
        st.caption(
            "Dubine i radijusi zasebno ulaze u VFP i ležišni proračun "
            "odgovarajuće CO₂ ili geotermalne bušotine."
        )
        minimum_numeric_control(
            "h_ref_co2",
            "Dubina utisne CO₂ bušotine",
            1.0,
            number_step=1.0,
            number_format="%.2f",
            unit="m",
            help_text="Referentna vertikalna dubina CO₂ bušotine za VFP.",
        )
        st.markdown("##### Kompresor za utiskivanje CO₂")
        st.caption(
            "p_comp_in i t_comp_in su usisni uvjeti kompresora za "
            "utiskivanje. Nisu ulazni uvjeti neovisnog transportnog CO₂ "
            "cjevovoda prikazanog u ekonomskom dijelu forme."
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
        paired_numeric_control(
            "eta_co2_compressor_isentropic",
            "Izentropska učinkovitost kompresora CO₂",
            0.01,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "eta_co2_dense_phase_pump",
            "Učinkovitost pumpe CO₂ u gustoj fazi",
            0.01,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        st.markdown("##### Geotermalne bušotine")
        minimum_numeric_control(
            "h_ref_geothermal_production",
            "Dubina proizvodne geotermalne bušotine",
            1.0,
            number_step=1.0,
            number_format="%.2f",
            unit="m",
            help_text=(
                "Referentna vertikalna dubina proizvodne geotermalne "
                "bušotine za VFP."
            ),
        )
        minimum_numeric_control(
            "h_ref_geothermal_injection",
            "Dubina utisne geotermalne bušotine",
            1.0,
            number_step=1.0,
            number_format="%.2f",
            unit="m",
            help_text=(
                "Referentna vertikalna dubina utisne geotermalne "
                "bušotine za VFP."
            ),
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
            "epsilon",
            "Apsolutna hrapavost bušotinske cijevi ε",
            0.0,
            0.05,
            slider_step=0.00001,
            number_step=1e-7,
            number_format="%.7f",
            unit="m",
            help_text=(
                "Zajednička VFP hrapavost za CO₂ utisnu te proizvodnu i "
                "utisnu geotermalnu bušotinu. Vrijednost 0,05 m odgovara "
                "testu 100 × zadana hrapavost 0,0005 m."
            ),
        )
        paired_numeric_control(
            "eta_gt_injection_pump",
            "Učinkovitost geotermalne utisne pumpe",
            0.01,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "d_doublet",
            "Razmak geotermalnog para d_doublet",
            10.0,
            5000.0,
            slider_step=10.0,
            number_step=1.0,
            number_format="%.2f",
            unit="m",
        )
        st.markdown("#### Površinski cjevovod geotermalne vode")
        st.caption(
            "Ulazni tlak i temperatura ovog voda preuzimaju se s izlaza "
            "ORC-a (`p_out`, `t_out`). Razmak geotermalnog para `d_doublet` "
            "ujedno je duljina površinskog transporta, a ostala geometrija "
            "odvojena je od CO₂ voda. Ako prvi izlazni tlak padne ispod "
            "1,01325 bar, ORC izlazni tlak korigira se s rezervom od 1 bar "
            "i pipeline proračun se ponavlja."
        )
        paired_numeric_control(
            "geothermal_pipeline_inner_diameter_m",
            "Unutarnji promjer geotermalnog cjevovoda",
            0.01,
            2.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="m",
        )
        paired_numeric_control(
            "geothermal_pipeline_roughness_m",
            "Apsolutna hrapavost geotermalnog cjevovoda",
            0.0,
            0.01,
            slider_step=0.00001,
            number_step=1e-7,
            number_format="%.7f",
            unit="m",
        )
        for elbow_parameter, elbow_label in (
            ("geothermal_pipeline_elbows_90_count", "GT koljena od 90°"),
            ("geothermal_pipeline_elbows_45_count", "GT koljena od 45°"),
            ("geothermal_pipeline_elbows_30_count", "GT koljena od 30°"),
        ):
            paired_numeric_control(
                elbow_parameter,
                elbow_label,
                0,
                1000,
                slider_step=1,
                number_step=1,
                number_format="%d",
                unit="-",
                integer=True,
            )

        st.markdown("#### Toplinski parametri horizontalnih cjevovoda")
        selection_control(
            "pipeline_environment_type",
            "Vanjski okoliš cjevovoda",
            ["soil", "air"],
            {"soil": "Tlo", "air": "Zrak"},
        )
        paired_numeric_control(
            "pipeline_ambient_temperature_c",
            "Temperatura vanjskog okoliša",
            -50.0,
            100.0,
            slider_step=1.0,
            number_step=0.1,
            number_format="%.2f",
            unit="°C",
        )
        paired_numeric_control(
            "pipeline_environment_thermal_conductivity_w_m_k",
            "Toplinska vodljivost okoliša",
            0.01,
            10.0,
            slider_step=0.1,
            number_step=0.001,
            number_format="%.4f",
            unit="W/(m·K)",
            logarithmic=True,
        )
        paired_numeric_control(
            "pipeline_environment_volumetric_heat_capacity_j_m3_k",
            "Volumetrijski toplinski kapacitet okoliša",
            1_000.0,
            5_000_000.0,
            slider_step=0.1,
            number_step=1_000.0,
            number_format="%.0f",
            unit="J/(m³·K)",
            logarithmic=True,
            help_text=(
                "Služi za svojstvo toplinske difuzivnosti i budući tranzijentni "
                "model. U sadašnjem stacionarnom proračunu ne mijenja izlaznu "
                "temperaturu bez vremena rada i početnog profila okoliša."
            ),
        )
        st.caption(
            "Volumetrijski toplinski kapacitet određuje dijagnostičku "
            "toplinsku difuzivnost i priprema budući tranzijentni model; "
            "u sadašnjem stacionarnom modelu ne mijenja izlaznu temperaturu. "
            "Za okoliš `air` stacionarni vanjski otpor određuje zadani h; "
            "vodljivost zraka također ostaje samo dio dijagnostičke "
            "difuzivnosti."
        )
        paired_numeric_control(
            "pipeline_wall_thickness_m",
            "Debljina stijenke cijevi",
            0.001,
            0.10,
            slider_step=0.001,
            number_step=0.0001,
            number_format="%.4f",
            unit="m",
        )
        paired_numeric_control(
            "pipeline_wall_thermal_conductivity_w_m_k",
            "Toplinska vodljivost stijenke",
            0.1,
            500.0,
            slider_step=0.1,
            number_step=0.1,
            number_format="%.3f",
            unit="W/(m·K)",
            logarithmic=True,
        )
        paired_numeric_control(
            "pipeline_insulation_thickness_m",
            "Debljina izolacije",
            0.0,
            0.50,
            slider_step=0.005,
            number_step=0.001,
            number_format="%.3f",
            unit="m",
        )
        paired_numeric_control(
            "pipeline_insulation_thermal_conductivity_w_m_k",
            "Toplinska vodljivost izolacije",
            0.005,
            1.0,
            slider_step=0.1,
            number_step=0.001,
            number_format="%.4f",
            unit="W/(m·K)",
            logarithmic=True,
        )
        if _entry_value(
            st.session_state[ACTIVE_INPUTS_KEY],
            "pipeline_environment_type",
        ) == "soil":
            paired_numeric_control(
                "pipeline_burial_depth_m",
                "Dubina osi ukopanog cjevovoda",
                0.1,
                10.0,
                slider_step=0.1,
                number_step=0.01,
                number_format="%.2f",
                unit="m",
            )
        else:
            paired_numeric_control(
                "pipeline_external_heat_transfer_coefficient_w_m2_k",
                "Vanjski koeficijent prijelaza topline prema zraku",
                0.1,
                200.0,
                slider_step=0.1,
                number_step=0.1,
                number_format="%.2f",
                unit="W/(m²·K)",
                logarithmic=True,
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
    with relperm_controls_tab:
        paired_numeric_control(
            "E_eff",
            "Učinkovitost skladištenja E_eff",
            0.005,
            0.3,
            slider_step=0.005,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
        )
        paired_numeric_control(
            "S_plume_core",
            "Minimalno zasićenje CO₂",
            0.0,
            1.0,
            slider_step=0.01,
            number_step=0.001,
            number_format="%.3f",
            unit="-",
            help_text=(
                "Bazna vrijednost zasićenja CO₂ u zoni blizu bušotine. "
                "Tijekom utiskivanja model je dodaje članu "
                "m_CO₂ / storage_capacity; nije rezidualno zasićenje "
                "nakon utiskivanja."
            ),
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
        paired_numeric_control(
            "economics_ccs_start_year",
            "Početna godina ulaganja u CCS",
            economics_start_year,
            economics_end_year,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )
        ccs_investment_start_year = int(
            _entry_value(
                st.session_state[ACTIVE_INPUTS_KEY],
                "economics_ccs_start_year",
            )
        )
        paired_numeric_control(
            "ccs_injection_start_year",
            "Početna godina utiskivanja i geotermalne proizvodnje",
            ccs_investment_start_year,
            economics_end_year,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )
        ccs_injection_start_year = int(
            _entry_value(
                st.session_state[ACTIVE_INPUTS_KEY],
                "ccs_injection_start_year",
            )
        )
        paired_numeric_control(
            "ccs_injection_end_year",
            "Posljednja planirana godina utiskivanja",
            ccs_injection_start_year,
            economics_end_year,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )
        ccs_injection_end_year = int(
            _entry_value(
                st.session_state[ACTIVE_INPUTS_KEY],
                "ccs_injection_end_year",
            )
        )
        required_capacity_t = required_storage_capacity_t(
            _entry_value(
                st.session_state[ACTIVE_INPUTS_KEY],
                "emitter_emissions_annual",
            ),
            ccs_injection_start_year,
            ccs_injection_end_year,
        )
        st.caption(
            "Planirano razdoblje zahtijeva najmanje "
            f"{required_capacity_t:,.0f} t CO₂ kapaciteta. Promjena razdoblja "
            "ili godišnje količine po potrebi automatski povećava nazivni "
            "kapacitet u aktivnom JSON-u; naknadno ručno smanjenje kapaciteta "
            "namjerno ograničava stvarni kraj utiskivanja."
        )
        paired_numeric_control(
            "geothermal_operation_end_year",
            "Posljednja godina rada geotermalnog sustava",
            ccs_injection_end_year,
            economics_end_year,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )
        paired_numeric_control(
            "ccs_monitoring_end_year",
            "Posljednja godina monitoringa skladišta CO₂",
            ccs_injection_end_year,
            economics_end_year,
            slider_step=1,
            number_step=1,
            number_format="%d",
            unit="godina",
            integer=True,
        )

        with st.expander("PV, NPV, IRR i inflacija", expanded=True):
            paired_numeric_control(
                "economics_interest_rate",
                "Nominalna godišnja diskontna stopa",
                0.0,
                1.0,
                slider_step=0.005,
                number_step=0.001,
                number_format="%.3f",
                unit="decimalno",
            )
            paired_numeric_control(
                "economics_inflation_rate",
                "Godišnja inflacija troškova",
                0.0,
                1.0,
                slider_step=0.005,
                number_step=0.001,
                number_format="%.3f",
                unit="decimalno",
            )
            st.caption(
                "PV i NPV koriste početnu godinu ekonomike kao baznu godinu. "
                "IRR se izvodi iz godišnjih novčanih tokova i zato nema zaseban "
                "ulaz stope. Svi troškovi prvo rastu sa zadanom inflacijom, a "
                "zatim se nominalni tok diskontira. Cijena CO₂ ostaje zadana "
                "odabranom godišnjom putanjom."
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
            )
            co2_price_chart["Godina"] = (
                co2_price_chart["Godina"].astype(int).astype(str)
            )
            co2_price_chart = co2_price_chart.set_index("Godina")
            _render_wide_chart(
                co2_price_chart,
                x_title="Godina",
                y_title="Cijena CO₂ (EUR/tCO₂)",
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

        with st.expander("Cijene električne energije"):
            paired_numeric_control(
                "electricity_buy_price",
                "Cijena kupnje električne energije",
                0.0,
                1000.0,
                slider_step=5.0,
                number_step=0.1,
                number_format="%.2f",
                unit="EUR/MWh",
            )
            paired_numeric_control(
                "electricity_sell_price",
                "Cijena prodaje električne energije",
                0.0,
                1000.0,
                slider_step=5.0,
                number_step=0.1,
                number_format="%.2f",
                unit="EUR/MWh",
            )

        with st.expander("Kompresor, geotermalni sustav i monitoring"):
            paired_numeric_control(
                "compressor_capex",
                "CAPEX kompresora CO₂",
                0.0,
                100.0,
                slider_step=1.0,
                number_step=0.01,
                number_format="%.2f",
                unit="mil. EUR",
                stored_units_per_display_unit=1_000_000.0,
            )
            paired_numeric_control(
                "compressor_annual_opex",
                "Godišnji OPEX kompresora CO₂",
                0.0,
                10_000_000.0,
                slider_step=100_000.0,
                number_step=1000.0,
                number_format="%.2f",
                unit="EUR/god",
            )
            paired_numeric_control(
                "geothermal_capex",
                "CAPEX geotermalnog sustava",
                0.0,
                1_000.0,
                slider_step=1.0,
                number_step=0.01,
                number_format="%.2f",
                unit="mil. EUR",
                stored_units_per_display_unit=1_000_000.0,
            )
            paired_numeric_control(
                "geothermal_annual_opex",
                "Godišnji OPEX geotermalnog sustava",
                0.0,
                100_000_000.0,
                slider_step=100_000.0,
                number_step=1000.0,
                number_format="%.2f",
                unit="EUR/god",
            )
            paired_numeric_control(
                "monitoring_annual_cost_during_injection",
                "Godišnji monitoring tijekom utiskivanja",
                0.0,
                10_000_000.0,
                slider_step=100_000.0,
                number_step=1000.0,
                number_format="%.2f",
                unit="EUR/god",
            )
            paired_numeric_control(
                "monitoring_annual_cost_after_injection",
                "Godišnji monitoring nakon utiskivanja",
                0.0,
                10_000_000.0,
                slider_step=100_000.0,
                number_step=1000.0,
                number_format="%.2f",
                unit="EUR/god",
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
            st.caption(
                "Godišnja količina uhvaćenog CO₂: "
                f"{_entry_value(st.session_state[ACTIVE_INPUTS_KEY], 'emitter_emissions_annual'):,.2f} "
                "tCO₂/god (izvedeno iz jedinstvene godišnje količine)."
            )
            paired_numeric_control(
                "emitter_capex",
                "CAPEX hvatanja",
                0.0,
                10_000.0,
                slider_step=10.0,
                number_step=0.01,
                number_format="%.2f",
                unit="mil. EUR",
                stored_units_per_display_unit=1_000_000.0,
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
        with st.expander("Transport CO₂"):
            text_control("transport_section_name", "Naziv transportne dionice")
            selection_control(
                "transport_mode",
                "Način transporta",
                ["pipeline", "truck", "rail"],
                {
                    "pipeline": "Cjevovod",
                    "truck": "Cestovni transport",
                    "rail": "Željeznički transport",
                },
            )
            transport_mode = _entry_value(
                st.session_state[ACTIVE_INPUTS_KEY],
                "transport_mode",
            )
            paired_numeric_control(
                "transport_distance_km",
                "Duljina transportne dionice",
                0.0,
                5000.0,
                slider_step=10.0,
                number_step=0.1,
                number_format="%.2f",
                unit="km",
            )
            st.caption(
                "Godišnja količina CO₂ u transportu: "
                f"{_entry_value(st.session_state[ACTIVE_INPUTS_KEY], 'transport_flow_rate'):,.2f} "
                "tCO₂/god (izvedeno iz jedinstvene godišnje količine)."
            )
            paired_numeric_control(
                "transport_capex",
                "CAPEX transporta",
                0.0,
                1_000.0,
                slider_step=1.0,
                number_step=0.01,
                number_format="%.2f",
                unit="mil. EUR",
                stored_units_per_display_unit=1_000_000.0,
            )
            if transport_mode == "pipeline":
                st.info(
                    "Sljedeći tlak i temperatura zadaju početak zasebnog "
                    "forward proračuna transportnog CO₂ cjevovoda. Ulazni "
                    "tlak nije p_comp_in niti se automatski računa kao izlaz "
                    "kompresora; rezultat zasad ne mijenja kompresor ni CO₂ "
                    "utisnu bušotinu."
                )
                paired_numeric_control(
                    "co2_pipeline_inlet_pressure_bar",
                    "Zadani tlak na početku CO₂ transportnog cjevovoda",
                    1.0,
                    500.0,
                    slider_step=5.0,
                    number_step=0.1,
                    number_format="%.2f",
                    unit="bar",
                    help_text=(
                        "Neovisni projektni ulaz transportnog voda. Zadana "
                        "vrijednost 150 bar nije tlak iza kompresora iz "
                        "energetskog proračuna."
                    ),
                )
                paired_numeric_control(
                    "co2_pipeline_inlet_temperature_c",
                    "Zadana temperatura na početku CO₂ transportnog cjevovoda",
                    -50.0,
                    100.0,
                    slider_step=1.0,
                    number_step=0.1,
                    number_format="%.2f",
                    unit="°C",
                )
                paired_numeric_control(
                    "pipeline_inner_diameter_m",
                    "Unutarnji promjer cjevovoda",
                    0.01,
                    2.0,
                    slider_step=0.01,
                    number_step=0.001,
                    number_format="%.3f",
                    unit="m",
                )
                paired_numeric_control(
                    "pipeline_roughness_m",
                    "Apsolutna hrapavost cjevovoda",
                    0.0,
                    0.01,
                    slider_step=0.00001,
                    number_step=1e-7,
                    number_format="%.7f",
                    unit="m",
                )
                for elbow_parameter, elbow_label in (
                    ("pipeline_elbows_90_count", "Broj koljena od 90°"),
                    ("pipeline_elbows_45_count", "Broj koljena od 45°"),
                    ("pipeline_elbows_30_count", "Broj koljena od 30°"),
                ):
                    paired_numeric_control(
                        elbow_parameter,
                        elbow_label,
                        0,
                        1000,
                        slider_step=1,
                        number_step=1,
                        number_format="%d",
                        unit="-",
                        integer=True,
                    )
                paired_numeric_control(
                    "transport_opex_per_ton",
                    "OPEX transporta cjevovodom",
                    0.0,
                    500.0,
                    slider_step=1.0,
                    number_step=0.1,
                    number_format="%.2f",
                    unit="EUR/tCO₂",
                )
            else:
                paired_numeric_control(
                    "transport_opex_eur_per_tkm",
                    "OPEX transporta po toni i kilometru",
                    0.0,
                    10.0,
                    slider_step=0.05,
                    number_step=0.001,
                    number_format="%.3f",
                    unit="EUR/tCO₂/km",
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
                10_000.0,
                slider_step=10.0,
                number_step=0.01,
                number_format="%.2f",
                unit="MtCO₂",
                help_text=(
                    "Prikaz je u milijunima tona (MtCO₂), dok se vrijednost "
                    "u aktivnom JSON-u i dalje sprema u tCO₂. Fizička granica "
                    "ukupno utisnute mase: ako je ručno "
                    "postavite ispod planirane mase, utiskivanje završava prije "
                    "odabrane posljednje godine."
                ),
                stored_units_per_display_unit=1_000_000.0,
            )
            paired_numeric_control(
                "storage_capex",
                "CAPEX skladišta",
                0.0,
                2_000.0,
                slider_step=1.0,
                number_step=0.01,
                number_format="%.2f",
                unit="mil. EUR",
                stored_units_per_display_unit=1_000_000.0,
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
    scenario_notice = st.session_state.pop(SCENARIO_NOTICE_KEY, None)
    scenario_store_error = st.session_state.pop(SCENARIO_STORE_ERROR_KEY, None)
    if scenario_notice:
        st.success(scenario_notice)
    if scenario_store_error:
        st.error(scenario_store_error)

    st.subheader("Učitavanje spremljenog scenarija")
    scenario_search = st.text_input(
        "Pretraži prema nazivu scenarija",
        key=SCENARIO_SEARCH_KEY,
        placeholder="Upišite dio naziva",
    )
    try:
        saved_scenarios = list_saved_scenarios()
    except OSError as exc:
        saved_scenarios = []
        st.error(f"Spremište scenarija nije dostupno: {exc}")
    normalized_search = scenario_search.strip().casefold()
    matching_scenarios = [
        scenario
        for scenario in saved_scenarios
        if not normalized_search
        or normalized_search in scenario.scenario_name.casefold()
    ]
    scenario_by_filename = {
        scenario.filename: scenario for scenario in matching_scenarios
    }
    if scenario_by_filename:
        st.selectbox(
            "Scenarij za učitavanje (ime scenarija, ime datoteke)",
            options=list(scenario_by_filename),
            format_func=lambda filename: scenario_by_filename[filename].label,
            key=SCENARIO_LOAD_SELECT_KEY,
        )
        st.button(
            "Učitaj odabrani scenarij",
            width="stretch",
            on_click=_load_selected_scenario,
        )
    else:
        st.caption("Nema spremljenih scenarija koji odgovaraju pretraživanju.")

    archive_by_filename = {
        scenario.filename: scenario
        for scenario in matching_scenarios
        if scenario.filename != LAST_INPUTS_FILENAME
    }
    with st.expander("Brisanje spremljenog scenarija"):
        if archive_by_filename:
            st.selectbox(
                "Scenarij za brisanje (ime scenarija, ime datoteke)",
                options=list(archive_by_filename),
                format_func=lambda filename: archive_by_filename[filename].label,
                key=SCENARIO_DELETE_SELECT_KEY,
            )
            delete_confirmed = st.checkbox(
                "Potvrđujem brisanje odabrane arhive",
                key=SCENARIO_DELETE_CONFIRM_KEY,
            )
            st.button(
                "Obriši odabrani scenarij",
                width="stretch",
                disabled=not delete_confirmed,
                on_click=_delete_selected_scenario,
            )
            st.caption(
                "Briše se samo odabrana arhiva; last_inputs.json ostaje sačuvan."
            )
        else:
            st.caption("Nema arhivskih scenarija za brisanje.")

    st.caption(f"Direktorij scenarija: {scenario_directory()}")
    st.divider()
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
        on_click=_collapse_inputs_on_run,
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
    try:
        last_inputs_path, archived_inputs_path = save_scenario(
            st.session_state[ACTIVE_INPUTS_KEY]
        )
        st.success(
            "Ulazi su automatski spremljeni u "
            f"{last_inputs_path.name} i {archived_inputs_path.name}."
        )
    except (OSError, TypeError, ValueError) as exc:
        st.warning(
            "Proračun se nastavlja, ali automatsko spremanje ulaza nije uspjelo: "
            f"{exc}"
        )
    with st.spinner("Izvodim tehničko-ekonomski proračun aktivnog scenarija..."):
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
if results is not None and not {
    "co2_pipeline_df",
    "geothermal_pipeline_df",
}.issubset(results):
    st.session_state[RESULTS_KEY] = None
    results = None
    st.info(
        "Prethodni rezultati nastali su prije uvođenja pipeline tablica; "
        "pokrenite proračun ponovno."
    )

if results is None:
    st.info(
        "Za prikaz rezultata odaberite **Pokreni proračun** u bočnom izborniku."
    )
else:
    st.session_state.setdefault(CHART_FONT_SIZE_ADJUSTMENT_KEY, 0)
    with st.expander("Aa  Veličina fonta dijagrama", expanded=False):
        st.slider(
            "Dodatna promjena veličine fonta",
            min_value=-6,
            max_value=12,
            step=1,
            key=CHART_FONT_SIZE_ADJUSTMENT_KEY,
            help=(
                "Vrijednost se dodaje svim fontovima Streamlit dijagrama. "
                "Nula koristi zajednički projektni stil iz chart_styles.py."
            ),
        )
        st.caption(
            "Promjena se odmah primjenjuje na naslove i oznake osi, "
            "brojčane vrijednosti i legende svih prikazanih dijagrama."
        )

    mbal_df = results["mbal_df"]
    vfp_co2_df = results["vfp_co2_df"]
    co2_pipeline_df = results["co2_pipeline_df"]
    doublet_df = results["doublet_df"]
    vfp_gt_df = results["vfp_gt_df"]
    geothermal_pipeline_df = results["geothermal_pipeline_df"]
    well_pressure_df = results["well_pressure_df"]
    gt_info = results["gt_info"]
    relative_permeability_df = results["relative_permeability_df"]
    annual_relative_permeability_df = results[
        "annual_relative_permeability_df"
    ]
    annual_injection_diagnostics_df = results[
        "annual_injection_diagnostics_df"
    ]
    annual_technical_ledger = results["annual_technical_ledger"]
    annual_cash_flow_df = results["annual_cash_flow_df"]
    economic_kpis = results["economic_kpis"]
    operational_kpis = results["operational_kpis"]
    scenario_notes = results["scenario_notes"]

    final_stored_co2 = float(operational_kpis["stored_co2_mt"])
    final_dsa_pressure = float(operational_kpis["final_storage_pressure_bar"])
    max_co2_bhp = float(operational_kpis["max_co2_bhp_bar"])
    max_co2_power = float(
        operational_kpis["compressor_nameplate_power_kw"]
    )
    final_gt_temperature = float(
        operational_kpis["final_geothermal_temperature_c"]
    )
    max_net_gt_power = float(
        operational_kpis["max_net_geothermal_power_kw"]
    )

    if gt_info["breakthrough_reached"]:
        breakthrough_value = f"{float(gt_info['t_bt']):.2f} god."
    else:
        breakthrough_value = "Nije dosegnut"

    if scenario_notes["injection_stop_note"]:
        st.warning(
            f"Planirani kraj utiskivanja: "
            f"{scenario_notes['planned_injection_end_year']}; stvarni kraj: "
            f"{scenario_notes['actual_injection_end_year']}. "
            f"{scenario_notes['injection_stop_note']}"
        )
    for transport_note in scenario_notes.get(
        "geothermal_transport_pressure_corrections",
        [],
    ):
        st.warning(f"Korekcija tlaka GT površinskog transporta: {transport_note}")
    for coverage_note in scenario_notes["annualization"].get(
        "coverage_notes",
        [],
    ):
        st.warning(coverage_note)

    st.subheader("Ključni pokazatelji")
    first_metric_row = st.columns(4)
    first_metric_row[0].metric("Uskladišteni CO₂", f"{final_stored_co2:.2f} Mt")
    first_metric_row[1].metric("Konačni DSA tlak", f"{final_dsa_pressure:.2f} bar")
    first_metric_row[2].metric("Maksimalni CO₂ BHP", f"{max_co2_bhp:.2f} bar")
    first_metric_row[3].metric("Toplinski prodor", breakthrough_value)

    second_metric_row = st.columns(3)
    second_metric_row[0].metric(
        "Nazivna snaga kompresora za CO₂", f"{max_co2_power:.2f} kW"
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
    pressure_chart = well_pressure_df[
        [
            "Time [yr]",
            "DSA pressure [bar]",
            "CO2 injection BHP [bar]",
            "CO2 injection WHP [bar]",
            "GT production BHP [bar]",
            "GT production WHP [bar]",
            "GT injection BHP [bar]",
            "GT injection WHP [bar]",
        ]
    ].rename(
        columns={
            "Time [yr]": "Vrijeme (god)",
            "DSA pressure [bar]": "DSA",
            "CO2 injection BHP [bar]": "CO₂ BHP",
            "CO2 injection WHP [bar]": "CO₂ WHP",
            "GT production BHP [bar]": "GT-P BHP",
            "GT production WHP [bar]": "GT-P WHP",
            "GT injection BHP [bar]": "GT-I BHP",
            "GT injection WHP [bar]": "GT-I WHP",
        }
    ).set_index("Vrijeme (god)")
    well_pressure_caption = (
        "BHP = tlak na dnu bušotine; WHP = tlak na ušću bušotine; "
        "GT-P = proizvodna geotermalna bušotina; "
        "GT-I = utisna geotermalna bušotina."
    )
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
    geothermal_velocity_chart = vfp_gt_df[
        [
            "Time [yr]",
            "avg prod velocity [m/s]",
            "avg inj velocity [m/s]",
        ]
    ].rename(
        columns={
            "Time [yr]": "Vrijeme (god)",
            "avg prod velocity [m/s]": "Proizvodna bušotina (m/s)",
            "avg inj velocity [m/s]": "Utisna bušotina (m/s)",
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
    annual_relative_permeability_chart = annual_relative_permeability_df[
        ["year", "krw (-)", "krg (-)"]
    ].rename(
        columns={
            "year": "Godina",
            "krw (-)": "Relativna propusnost vode krw (-)",
            "krg (-)": "Relativna propusnost CO₂ krg (-)",
        }
    )
    annual_relative_permeability_chart["Godina"] = (
        annual_relative_permeability_chart["Godina"].astype(str)
    )
    annual_relative_permeability_chart = (
        annual_relative_permeability_chart.set_index("Godina")
    )

    annual_co2_chart = annual_technical_ledger[
        ["year", "co2_chain_t"]
    ].rename(
        columns={
            "year": "Godina",
            "co2_chain_t": "Godišnja količina CO₂ (t)",
        }
    )
    annual_co2_chart["Godina"] = annual_co2_chart["Godina"].astype(str)
    annual_co2_chart = annual_co2_chart.set_index("Godina")
    annual_energy_chart = annual_technical_ledger[
        [
            "year",
            "orc_gross_mwh",
            "gt_pump_mwh",
            "co2_compressor_mwh",
            "electricity_export_mwh",
            "electricity_import_mwh",
        ]
    ].rename(
        columns={
            "year": "Godina",
            "orc_gross_mwh": "ORC",
            "gt_pump_mwh": "GT pumpa",
            "co2_compressor_mwh": "CO₂ kompresor",
            "electricity_export_mwh": "Prodaja el.",
            "electricity_import_mwh": "Kupnja el.",
        }
    )
    annual_energy_chart["Godina"] = annual_energy_chart["Godina"].astype(int)
    for consumption_column in (
        "GT pumpa",
        "CO₂ kompresor",
        "Kupnja el.",
    ):
        annual_energy_chart[consumption_column] *= -1.0
    annual_energy_chart_long = annual_energy_chart.melt(
        id_vars="Godina",
        var_name="Serija",
        value_name="Vrijednost",
    )

    annualization_metadata = annual_technical_ledger.attrs.get(
        "adapter_metadata",
        {},
    )
    calendar_hours_per_year = float(
        annualization_metadata.get(
            "hours_per_year",
            CALENDAR_HOURS_PER_YEAR,
        )
    )
    if not math.isfinite(calendar_hours_per_year) or calendar_hours_per_year <= 0:
        calendar_hours_per_year = CALENDAR_HOURS_PER_YEAR
    annual_average_power_chart = annual_technical_ledger[
        ["year", "orc_gross_mwh", "gt_pump_mwh", "co2_compressor_mwh"]
    ].rename(
        columns={
            "year": "Godina",
            "orc_gross_mwh": "ORC",
            "gt_pump_mwh": "GT pumpa",
            "co2_compressor_mwh": "CO₂ kompresor",
        }
    )
    annual_average_power_chart["Godina"] = annual_average_power_chart[
        "Godina"
    ].astype(int)
    for power_column in ("ORC", "GT pumpa", "CO₂ kompresor"):
        # MWh / h = MW. Sve tri serije ostaju pozitivne veličine komponenti.
        annual_average_power_chart[power_column] /= calendar_hours_per_year
    annual_average_power_chart_long = annual_average_power_chart.melt(
        id_vars="Godina",
        var_name="Serija",
        value_name="Vrijednost",
    )

    # Svaka troškovna komponenta prikazuje se u nominalnim eurima godine u
    # kojoj nastaje. Isti faktor inflacije koji cash-flow runner primjenjuje na
    # ukupne troškove ovdje se raspodjeljuje po komponentama radi preglednog
    # i potpuno uskladivog prikaza, uključujući monitoring.
    annual_base_cost = annual_cash_flow_df[
        [
            "capture_capex",
            "capture_opex",
            "transport_capex",
            "transport_opex",
            "compressor_capex",
            "compressor_opex",
            "storage_capex",
            "storage_opex",
            "geothermal_capex",
            "geothermal_opex",
            "monitoring",
            "electricity_purchase",
        ]
    ].sum(axis=1)
    annual_cost_inflation_factor = np.ones(len(annual_cash_flow_df), dtype=float)
    nonzero_annual_cost = ~np.isclose(annual_base_cost.to_numpy(dtype=float), 0.0)
    annual_cost_inflation_factor[nonzero_annual_cost] += (
        annual_cash_flow_df.loc[
            nonzero_annual_cost, "cost_inflation_adjustment"
        ].to_numpy(dtype=float)
        / annual_base_cost.loc[nonzero_annual_cost].to_numpy(dtype=float)
    )
    annual_cost_component_chart = pd.DataFrame(
        {
            "Godina": annual_cash_flow_df["year"].astype(int),
            "Hvatanje": (
                annual_cash_flow_df["capture_capex"]
                + annual_cash_flow_df["capture_opex"]
            )
            * annual_cost_inflation_factor,
            "Transport": (
                annual_cash_flow_df["transport_capex"]
                + annual_cash_flow_df["transport_opex"]
            )
            * annual_cost_inflation_factor,
            "Kompresor": (
                annual_cash_flow_df["compressor_capex"]
                + annual_cash_flow_df["compressor_opex"]
            )
            * annual_cost_inflation_factor,
            "Skladište": (
                annual_cash_flow_df["storage_capex"]
                + annual_cash_flow_df["storage_opex"]
            )
            * annual_cost_inflation_factor,
            "GT": (
                annual_cash_flow_df["geothermal_capex"]
                + annual_cash_flow_df["geothermal_opex"]
            )
            * annual_cost_inflation_factor,
            "Monitoring": annual_cash_flow_df["monitoring"]
            * annual_cost_inflation_factor,
            "Kupnja el.": annual_cash_flow_df["electricity_purchase"]
            * annual_cost_inflation_factor,
            "Prihod el.": annual_cash_flow_df["electricity_revenue"],
        }
    )
    annual_cost_component_chart_long = annual_cost_component_chart.melt(
        id_vars="Godina",
        var_name="Serija",
        value_name="Vrijednost",
    )
    annual_cost_component_chart_long["Vrijednost"] /= 1_000_000.0
    annual_cash_flow_chart = annual_cash_flow_df[
        [
            "year",
            "net_cash_flow",
            "discounted_cash_flow",
            "without_ccs_cash_flow",
            "discounted_without_ccs_cash_flow",
        ]
    ].rename(
        columns={
            "year": "Godina",
            "net_cash_flow": "CCS godišnji",
            "discounted_cash_flow": "CCS PV",
            "without_ccs_cash_flow": "Bez CCS-a",
            "discounted_without_ccs_cash_flow": "Bez CCS-a PV",
        }
    )
    annual_cash_flow_chart["Godina"] = annual_cash_flow_chart["Godina"].astype(
        int
    )
    annual_cash_flow_chart_long = annual_cash_flow_chart.melt(
        id_vars="Godina",
        var_name="Serija",
        value_name="Vrijednost",
    )
    cumulative_cash_flow_chart = annual_cash_flow_df[
        [
            "year",
            "cumulative_net_cash_flow",
            "cumulative_npv",
            "cumulative_without_ccs_cash_flow",
            "cumulative_discounted_without_ccs_cash_flow",
        ]
    ].rename(
        columns={
            "year": "Godina",
            "cumulative_net_cash_flow": "CCS kum.",
            "cumulative_npv": "CCS NPV",
            "cumulative_without_ccs_cash_flow": "Bez CCS-a kum.",
            "cumulative_discounted_without_ccs_cash_flow": "Bez CCS-a NPV",
        }
    )
    cumulative_cash_flow_chart["Godina"] = cumulative_cash_flow_chart[
        "Godina"
    ].astype(str)
    cumulative_cash_flow_chart = cumulative_cash_flow_chart.set_index("Godina")
    electricity_cash_flow_chart_long = annual_cash_flow_df[
        ["year", "net_electricity_cash_flow"]
    ].rename(
        columns={
            "year": "Godina",
            "net_electricity_cash_flow": "Vrijednost",
        }
    )
    electricity_cash_flow_chart_long["Vrijednost"] /= 1_000_000.0
    electricity_cash_flow_chart_long["Serija"] = (
        "Trošak/prihod od el. energije"
    )

    (
        overview_tab,
        storage_tab,
        geothermal_tab,
        economics_tab,
        tables_tab,
        assumptions_tab,
    ) = st.tabs(
        [
            "Sažetak",
            "CCS",
            "Geotermalni sustav",
            "Ekonomika i energija",
            "Tablice",
            "Pretpostavke",
        ]
    )

    with overview_tab:
        st.markdown("#### Vremenski niz uskladištenog CO₂")
        _render_wide_chart(
            storage_mass_chart,
            x_title="Vrijeme (god)",
            y_title="Uskladišteni CO₂ (Mt)",
            height=320,
        )

        st.markdown("#### Tlakovi na ušću i dnu bušotina")
        _render_wide_chart(
            pressure_chart,
            x_title="Vrijeme (god)",
            y_title="Tlak (bar)",
            height=320,
        )
        st.caption(well_pressure_caption)

        st.markdown("#### Izlazna snaga sustava")
        gt_power_time = vfp_gt_df["Time [yr]"].to_numpy(dtype=float)
        co2_power_time = vfp_co2_df["Time [yr]"].to_numpy(dtype=float)
        co2_power_on_gt_time = np.interp(
            gt_power_time,
            co2_power_time,
            vfp_co2_df["CO2 comp. P [kW]"].to_numpy(dtype=float),
            left=float(vfp_co2_df["CO2 comp. P [kW]"].iloc[0]),
            right=0.0,
        )
        combined_power_chart = pd.DataFrame(
            {
                "Vrijeme (god)": gt_power_time,
                "ORC snaga (kW)": vfp_gt_df["ORC power, kW"].to_numpy(),
                "Snaga pumpe (kW)": vfp_gt_df["pump power, kW"].to_numpy(),
                "Neto GT snaga (kW)": vfp_gt_df["net power GT, kW"].to_numpy(),
                "Snaga kompresora za CO₂ (kW)": co2_power_on_gt_time,
                "Izlazna snaga sustava (kW)": (
                    vfp_gt_df["ORC power, kW"].to_numpy()
                    - vfp_gt_df["pump power, kW"].to_numpy()
                    - co2_power_on_gt_time
                ),
            }
        ).set_index("Vrijeme (god)")
        _render_wide_chart(
            combined_power_chart,
            x_title="Vrijeme (god)",
            y_title="Snaga (kW)",
            height=360,
        )
        st.caption(
            "ORC i neto snaga geotermalnog sustava prikazuju proizvodnju, "
            "a snaga pumpe i snaga kompresora za CO₂ zasebne su komponente "
            "potrošnje."
        )

    with storage_tab:
        st.markdown("#### Masa skladištenja")
        _render_wide_chart(
            storage_mass_chart,
            x_title="Vrijeme (god)",
            y_title="Uskladišteni CO₂ (Mt)",
        )
        st.markdown("#### Tlakovi na ušću i dnu bušotina")
        _render_wide_chart(
            pressure_chart,
            x_title="Vrijeme (god)",
            y_title="Tlak (bar)",
        )
        st.caption(well_pressure_caption)
        st.markdown("#### Godišnja količina utisnutog CO₂")
        _render_wide_chart(
            annual_co2_chart,
            x_title="Godina",
            y_title="Utisnuti CO₂ (t/god)",
            chart_type="bar",
        )
        st.markdown("#### Snaga kompresora za CO₂")
        co2_time = vfp_co2_df["Time [yr]"].to_numpy(dtype=float)
        compressor_density_chart = pd.concat(
            [
                pd.DataFrame(
                    {
                        "Vrijeme (god)": co2_time,
                        "Serija": "P komp.",
                        "Skupina": "Snaga",
                        "Vrijednost": vfp_co2_df[
                            "CO2 comp. P [kW]"
                        ].to_numpy(dtype=float),
                        "Jedinica": "kW",
                    }
                ),
                pd.DataFrame(
                    {
                        "Vrijeme (god)": co2_time,
                        "Serija": "ρ BHP",
                        "Skupina": "Gustoća",
                        "Vrijednost": vfp_co2_df[
                            "CO2 VFP density at BHP [kg/m3]"
                        ].to_numpy(dtype=float),
                        "Jedinica": "kg/m³",
                    }
                ),
                pd.DataFrame(
                    {
                        "Vrijeme (god)": co2_time,
                        "Serija": "ρ WHP",
                        "Skupina": "Gustoća",
                        "Vrijednost": vfp_co2_df[
                            "CO2 VFP density at WHP [kg/m3]"
                        ].to_numpy(dtype=float),
                        "Jedinica": "kg/m³",
                    }
                ),
            ],
            ignore_index=True,
        )
        _render_long_series_chart(
            compressor_density_chart,
            _compressor_density_chart_spec(
                _current_chart_font_size_adjustment()
            ),
        )
        st.caption(
            "Graf podržava pomicanje i uvećavanje po x-osi. Lijeva os "
            "prikazuje snagu kompresora, a desna gustoću "
            "CO₂ na BHP-u i WHP-u; gustoće koriste lokalni tlak i temperaturu "
            "iz spregnutog VFP profila."
        )
        st.markdown("#### Relativne propusnosti vode i CO₂")
        _render_wide_chart(
            relative_permeability_chart,
            x_title="Zasićenje vodom Sw (-)",
            y_title="Relativna propusnost (-)",
        )
        st.markdown("#### Godišnje relativne propusnosti vode i CO₂")
        _render_wide_chart(
            annual_relative_permeability_chart,
            x_title="Godina",
            y_title="Relativna propusnost (-)",
        )
        st.caption(
            "Prije početka utiskivanja koristi se zasićenje CO₂ jednako nuli. "
            "Nakon prestanka utiskivanja zadržava se završno drenažno stanje; "
            "imbibicija i histereza relativnih propusnosti nisu modelirane."
        )
        if not co2_pipeline_df.empty:
            st.markdown(
                "#### Neovisni forward proračun CO₂ transportnog cjevovoda"
            )
            pipeline_row = co2_pipeline_df.iloc[0]
            pipeline_metrics = st.columns(4)
            pipeline_metrics[0].metric(
                "Zadani tlak na početku voda",
                f"{pipeline_row['Inlet pressure [bar]']:.2f} bar",
            )
            pipeline_metrics[1].metric(
                "Izlazni tlak CO₂ voda",
                f"{pipeline_row['Outlet pressure [bar]']:.2f} bar",
            )
            pipeline_metrics[2].metric(
                "Pad tlaka CO₂ voda",
                f"{pipeline_row['Pressure drop [bar]']:.2f} bar",
            )
            pipeline_metrics[3].metric(
                "Izlazna temperatura CO₂ voda",
                f"{pipeline_row['Outlet temperature [°C]']:.2f} °C",
            )
            st.info(
                "Ovaj rezultat polazi od zasebno zadanog projektnog ulaza, "
                "koji je u defaultnom scenariju 150 bar. Zato približno "
                "148,7 bar na kraju znači pad od približno 1,3 bar duž "
                "transportne dionice; to nije izračunati izlaz kompresora. "
                "Transportni endpoint zasad nije spojen sa snagom kompresora "
                "ni WHP-om CO₂ utisne bušotine."
            )

    with geothermal_tab:
        temperature_column, flow_column = st.columns(2)
        with temperature_column:
            st.markdown("#### Proizvodna temperatura")
            _render_wide_chart(
                geothermal_temperature_chart,
                x_title="Vrijeme (god)",
                y_title="Temperatura (°C)",
            )
        with flow_column:
            st.markdown("#### Maseni protok geotermalne vode")
            _render_wide_chart(
                geothermal_flow_chart,
                x_title="Vrijeme (god)",
                y_title="Maseni protok geotermalne vode (kg/s)",
            )

        st.markdown("#### Prosječna brzina geotermalne vode u bušotinama")
        _render_wide_chart(
            geothermal_velocity_chart,
            x_title="Vrijeme (god)",
            y_title="Prosječna aksijalna brzina (m/s)",
        )
        st.caption(
            "Prikazan je duljinski prosjek apsolutne lokalne brzine kroz "
            "jednake segmente VFP modela za svaki raspoloživi vremenski "
            "moment. Kada geotermalni krug ne radi, obje su brzine 0 m/s."
        )

        st.markdown("#### Neto snaga geotermalnog sustava")
        _render_wide_chart(
            geothermal_power_chart,
            x_title="Vrijeme (god)",
            y_title="Snaga (kW)",
        )
        st.markdown("#### Napredovanje toplinske fronte")
        _render_wide_chart(
            thermal_front_chart,
            x_title="Vrijeme (god)",
            y_title="Radijus toplinske fronte (m)",
        )
        st.markdown("#### Izlazni uvjeti cjevovoda geotermalne vode")
        st.caption(
            "Proračun polazi od ORC izlaza p_out/t_out. Efektivni "
            "p_gt_transport_in ulazi u ORC proračun, p_gt_transport_out je "
            "ulazni tlak GT pumpe, a izlazna temperatura voda ulazi u utisni "
            "VFP. Crvena korekcijska note pojavljuje se kada je prvi izlaz "
            "ispod 1,01325 bar."
        )
        geothermal_pipeline_active = geothermal_pipeline_df.loc[
            geothermal_pipeline_df["geothermal active"].astype(bool)
        ].copy()
        pipeline_pressure_column, pipeline_temperature_column = st.columns(2)
        with pipeline_pressure_column:
            _render_wide_chart(
                geothermal_pipeline_active[
                    [
                        "Time [yr]",
                        "p_gt_transport_in [bar]",
                        "p_gt_transport_out [bar]",
                    ]
                ].set_index("Time [yr]"),
                x_title="Vrijeme (god)",
                y_title="Tlak (bar)",
            )
        with pipeline_temperature_column:
            _render_wide_chart(
                geothermal_pipeline_active[
                    ["Time [yr]", "Outlet temperature [°C]"]
                ].set_index("Time [yr]"),
                x_title="Vrijeme (god)",
                y_title="Izlazna temperatura (°C)",
            )

    with economics_tab:
        total_cash_flow = float(annual_cash_flow_df["net_cash_flow"].sum())
        total_co2_value = float(annual_cash_flow_df["co2_value"].sum())
        net_electricity_cash_flow = float(
            annual_cash_flow_df["net_electricity_cash_flow"].sum()
        )
        ccs_cost_columns = (
            "Hvatanje",
            "Transport",
            "Kompresor",
            "Skladište",
            "Monitoring",
        )
        total_ccs_cost = max(
            0.0,
            -float(
                annual_cost_component_chart.loc[:, ccs_cost_columns]
                .to_numpy(dtype=float)
                .sum()
            ),
        )
        total_geothermal_cost = max(
            0.0,
            -float(annual_cost_component_chart["GT"].sum()),
        )
        total_electricity_purchase = max(
            0.0,
            -float(annual_cost_component_chart["Kupnja el."].sum()),
        )
        total_all_costs = (
            total_ccs_cost
            + total_geothermal_cost
            + total_electricity_purchase
        )
        total_electricity_revenue = max(
            0.0,
            float(annual_cost_component_chart["Prihod el."].sum()),
        )
        irr = economic_kpis["irr"]
        irr_label = "Nije definiran" if irr is None else f"{irr * 100:.2f} %"
        economics_metric_row = st.columns(4)
        economics_metric_row[0].metric(
            "Ukupni nediskontirani novčani tok",
            f"{total_cash_flow / 1_000_000:.2f} mil. EUR",
        )
        economics_metric_row[1].metric(
            "NPV scenarija s CCS-om",
            f"{economic_kpis['npv_eur'] / 1_000_000:.2f} mil. EUR",
        )
        economics_metric_row[2].metric(
            "IRR scenarija s CCS-om",
            irr_label,
        )
        economics_metric_row[3].metric(
            "NPV scenarija bez CCS-a",
            f"{economic_kpis['without_ccs_npv_eur'] / 1_000_000:.2f} mil. EUR",
        )

        economics_pv_row = st.columns(4)
        economics_pv_row[0].metric(
            "PV koristi i prihoda s CCS-om",
            f"{economic_kpis['pv_revenues_eur'] / 1_000_000:.2f} mil. EUR",
        )
        economics_pv_row[1].metric(
            "PV troškova s CCS-om",
            f"{economic_kpis['pv_costs_eur'] / 1_000_000:.2f} mil. EUR",
        )
        economics_pv_row[2].metric(
            "Izbjegnuti CO₂ rashod",
            f"{total_co2_value / 1_000_000:.2f} mil. EUR",
        )
        economics_pv_row[3].metric(
            "Neto novčani tok električne energije",
            f"{net_electricity_cash_flow / 1_000_000:.2f} mil. EUR",
        )

        economics_component_cost_row = st.columns(3)
        economics_component_cost_row[0].metric(
            "Ukupni trošak CCS-a",
            f"{total_ccs_cost / 1_000_000:.2f} mil. EUR",
        )
        economics_component_cost_row[1].metric(
            "Ukupni trošak geotermalnog sustava",
            f"{total_geothermal_cost / 1_000_000:.2f} mil. EUR",
        )
        economics_component_cost_row[2].metric(
            "Ukupni trošak kupnje električne energije",
            f"{total_electricity_purchase / 1_000_000:.2f} mil. EUR",
        )
        economics_total_cost_row = st.columns(2)
        economics_total_cost_row[0].metric(
            "Sveukupni troškovi",
            f"{total_all_costs / 1_000_000:.2f} mil. EUR",
        )
        economics_total_cost_row[1].metric(
            "Prihod od električne energije",
            f"{total_electricity_revenue / 1_000_000:.2f} mil. EUR",
        )

        st.markdown("#### Godišnja količina utisnutog CO₂")
        _render_wide_chart(
            annual_co2_chart,
            x_title="Godina",
            y_title="Utisnuti CO₂ (t/god)",
            chart_type="bar",
        )
        st.markdown("#### Godišnja energetska bilanca")
        _render_long_series_chart(
            annual_energy_chart_long,
            _zoomable_line_chart_spec(
                x_title="Godina",
                y_title="Energija (MWh)",
                zoom_name="annual_energy_x_zoom",
                integer_x=True,
                font_size_adjustment=_current_chart_font_size_adjustment(),
            ),
        )
        st.caption(
            "ORC i prodana energija prikazani su pozitivno; GT pumpa, CO₂ "
            "kompresor i kupljena energija prikazani su negativno. Graf se "
            "može pomicati i uvećavati po x-osi."
        )
        st.markdown("#### Prosječna godišnja snaga komponenti")
        _render_long_series_chart(
            annual_average_power_chart_long,
            _zoomable_line_chart_spec(
                x_title="Godina",
                y_title="Prosječna snaga (MW)",
                zoom_name="annual_average_power_x_zoom",
                integer_x=True,
                font_size_adjustment=_current_chart_font_size_adjustment(),
            ),
        )
        st.caption(
            "ORC, GT pumpa i CO₂ kompresor prikazani su kao pozitivne "
            "veličine. Kalendarski godišnji prosjek dobiven je dijeljenjem "
            f"godišnje energije s {calendar_hours_per_year:.0f} sati; MWh/h = MW."
        )
        st.markdown("#### Godišnji troškovi po komponentama")
        _render_long_series_chart(
            annual_cost_component_chart_long,
            _zoomable_line_chart_spec(
                x_title="Godina",
                y_title="Nominalni novčani tok (mil. EUR)",
                zoom_name="annual_cost_revenue_x_zoom",
                y_zoom_name="annual_cost_revenue_y_zoom",
                value_format=",.3f",
                integer_x=True,
                font_size_adjustment=_current_chart_font_size_adjustment(),
            ),
        )
        st.caption(
            "Troškovi su negativni i uključuju inflaciju do godine nastanka; "
            "prihod od prodaje električne energije pozitivan je i prikazan kroz "
            "cijeli horizont ekonomike. Kupnja električne energije ostaje "
            "zasebna stavka i nije proizvoljno raspodijeljena na CCS i GT. "
            "Vrijednost izbjegnutog CO₂ troška nije prihod u ovom grafikonu. "
            "Pomičite i zumirajte x-os uobičajenom interakcijom, a y-os uz "
            "pritisnutu tipku Shift."
        )
        st.markdown("#### Trošak/prihod od električne energije")
        _render_long_series_chart(
            electricity_cash_flow_chart_long,
            _zoomable_line_chart_spec(
                x_title="Godina",
                y_title="Trošak/prihod (mil. EUR)",
                zoom_name="electricity_cash_flow_x_zoom",
                y_zoom_name="electricity_cash_flow_y_zoom",
                value_format=",.3f",
                integer_x=True,
                interpolate="step-after",
                font_size_adjustment=_current_chart_font_size_adjustment(),
            ),
        )
        st.caption(
            "Pozitivna vrijednost je prihod neto izvoza električne energije, a "
            "negativna trošak neto uvoza. Energetska bilanca uključuje ORC, "
            "CO₂ kompresor i geotermalnu pumpu. Kotačić zumira x-os, a "
            "Shift + kotačić y-os."
        )
        st.markdown("#### Godišnji novčani tok: s CCS-om i bez CCS-a")
        _render_long_series_chart(
            annual_cash_flow_chart_long,
            _zoomable_line_chart_spec(
                x_title="Godina",
                y_title="Novčani tok (EUR)",
                zoom_name="annual_cash_flow_x_zoom",
                integer_x=True,
                font_size_adjustment=_current_chart_font_size_adjustment(),
            ),
        )
        st.caption(
            "Svaka linija predstavlja vrijednost samo te godine; PV je "
            "diskontirana vrijednost pojedine godine u baznoj godini ekonomike. "
            "Graf se može pomicati i uvećavati po x-osi."
        )
        st.markdown("#### Kumulativni novčani tok i NPV")
        _render_wide_chart(
            cumulative_cash_flow_chart,
            x_title="Godina",
            y_title="Kumulativna vrijednost (EUR)",
        )
        st.caption(
            "Troškovne stavke izražene su u baznim eurima te se prvo uvećavaju "
            "za inflaciju; cijeli nominalni tok potom se svodi na PV zadanom "
            "diskontnom stopom. Kumulativni diskontirani tok jest NPV do "
            "uključivo prikazane godine. Bez CCS-a prikazan je godišnji rashod "
            "−emisije × cijena CO₂. Pozitivna vrijednost CO₂ u scenariju "
            "s CCS-om predstavlja izbjegnuti rashod, a ne prodajni prihod. "
            "Pozitivni višak prodane električne energije "
            "ostaje prihod i nakon prestanka utiskivanja, dok god geotermalni "
            "sustav radi."
        )
        if economic_kpis["irr_status"] == "multiple_roots":
            st.warning(
                "Tok mijenja predznak više puta pa postoji više matematičkih "
                "IRR rješenja; prikazano je rješenje najbliže početnoj procjeni "
                "od 10 %."
            )

    with tables_tab:
        st.markdown("#### Preuzimanje rezultata")
        st.caption(
            "Oba formata sadrže aktivne ulaze, tehničke i ekonomske tablice, "
            "ključne pokazatelje, napomene scenarija i konfiguraciju transporta."
        )
        json_export = build_results_json(
            results,
            st.session_state[ACTIVE_INPUTS_KEY],
        )
        excel_export = build_results_excel(
            results,
            st.session_state[ACTIVE_INPUTS_KEY],
        )
        json_download_column, excel_download_column = st.columns(2)
        with json_download_column:
            st.download_button(
                "Preuzmi rezultate (JSON)",
                data=json_export,
                file_name="gt_ccs_results.json",
                mime="application/json",
                width="stretch",
            )
        with excel_download_column:
            st.download_button(
                "Preuzmi rezultate (Excel)",
                data=excel_export,
                file_name="gt_ccs_results.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                width="stretch",
            )

        with st.expander("Godišnja tehnička tablica", expanded=True):
            st.dataframe(annual_technical_ledger, width="stretch")
        with st.expander("Godišnji novčani tok", expanded=True):
            st.dataframe(annual_cash_flow_df, width="stretch")
        with st.expander("Godišnji CO₂ debug: količina, BHP i DSA tlak"):
            st.dataframe(annual_injection_diagnostics_df, width="stretch")
        with st.expander("Materijalna bilanca", expanded=True):
            st.dataframe(mbal_df, width="stretch")
        with st.expander("Tlakovi na ušću i dnu bušotina", expanded=True):
            st.dataframe(well_pressure_df, width="stretch")
        with st.expander("CO₂ bušotina i kompresija"):
            st.dataframe(vfp_co2_df, width="stretch")
        with st.expander("CO₂ cjevovod"):
            st.dataframe(co2_pipeline_df, width="stretch")
        with st.expander("Geotermalni dublet i snaga"):
            st.dataframe(vfp_gt_df, width="stretch")
        with st.expander("Cjevovod geotermalne vode"):
            st.dataframe(geothermal_pipeline_df, width="stretch")
        with st.expander("Toplinska fronta"):
            st.dataframe(doublet_df, width="stretch")
        with st.expander("Relativne propusnosti"):
            st.dataframe(relative_permeability_df, width="stretch")
        with st.expander("Godišnje relativne propusnosti"):
            st.dataframe(annual_relative_permeability_df, width="stretch")

    with assumptions_tab:
        st.markdown(
            """
            Ova verzija zadržava postojeće inženjerske jednadžbe, ali više ne
            zaobilazi odabrane ulaze u servisnom sloju:

            - `bhp_dp` je korisnički drawdown proizvodne geotermalne bušotine;
            - proizvodni GT WHP trenutačno nije ulaz, nego rezultat BHP-a,
              hidrostatskih i trenjskih gubitaka; ako potencijalni proizvodni
              WHP nije viši od efektivnog `p_gt_transport_in`, cijeli GT krug ima nulti protok,
              reinjekciju, pumpnu snagu, ORC snagu i neto snagu;
            - CO₂, proizvodna GT i utisna GT bušotina imaju zasebne radijuse;
            - `t_out` se koristi na ORC izlazu i ulazu površinskog GT voda, a
              izračunati `t_gt_transport_out` koristi utisni VFP;
            - `p_out` je početni ORC izlazni tlak; ako je prvi
              `p_gt_transport_out < 1,01325 bar`, efektivni
              `p_gt_transport_in` korigira se potvrđenom formulom;
            - `d_doublet` je razmak geotermalnog para i duljina površinskog
              transporta vode;
            - neto geotermalna snaga predstavlja ORC snagu umanjenu za snagu pumpe;
            - godišnja masa CO₂ jednaka je za hvatanje, transport, utiskivanje
              i verificirano skladištenje;
            - godišnja energija dobiva se integriranjem postojećih nizova snage
              uz 8766 sati po godini;
            - ORC najprije pokriva GT pumpu i kompresor CO₂, a razlika je prodana
              ili kupljena električna energija;
            - komponentni novčani tok spojen je na godišnje tehničke rezultate;
              troškovi se uvećavaju za inflaciju prije izračuna PV-a, NPV-a i
              IRR-a;
            - nakon prestanka utiskivanja tlak ležišta drži se konstantnim jer
              model pretpostavlja jednaku proizvodnju i ponovno utiskivanje
              geotermalne vode;
            - horizontalni CO₂ i geotermalni cjevovodi računaju lokalna
              svojstva, Darcyjeve i lokalne gubitke te stacionarnu izmjenu
              topline kroz stijenku, izolaciju i zrak ili tlo;
            - volumetrijski toplinski kapacitet okoliša služi za dijagnostičku
              toplinsku difuzivnost; tranzijentni utjecaj zahtijevao bi još
              vrijeme rada i početni temperaturni profil okoliša.
            """
        )
        st.info(
            "Streamlit sloj upravlja ulazima i prikazuje rezultate. "
            "Inženjerske jednadžbe ostaju u modulima direktorija engineering."
        )
