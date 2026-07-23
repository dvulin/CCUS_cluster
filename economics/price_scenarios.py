"""CO2 price-path preparation for UI previews and future economics runs."""

from collections.abc import Mapping

import numpy as np
import pandas as pd


PRESET_MODE_TO_KEY = {
    "pessimistic": "co2_price_pessimistic",
    "conservative": "co2_price_conservative",
    "optimistic": "co2_price_optimistic",
}


def _input_value(inputs, key):
    """Return a scalar/list value from raw JSON data or an input object."""
    if isinstance(inputs, Mapping):
        raw_value = inputs[key]
        if isinstance(raw_value, list) and len(raw_value) >= 2:
            return raw_value[0]
        return raw_value
    return getattr(inputs, key)


def generate_co2_price_path(inputs):
    """Build the selected annual CO2 price path.

    Preset paths are aligned by calendar year. Outside their published input
    interval, the nearest available endpoint is held constant. This is an
    explicit demo extrapolation assumption; TODO: reference required.

    Custom paths use ``tau = year - economics_start_year``:

    - linear: ``P0 + a * tau``
    - logarithmic: ``P0 + a * ln(1 + b * tau)``
    - power law: ``P0 + a * tau**c``
    """
    start_year = int(_input_value(inputs, "economics_start_year"))
    end_year = int(_input_value(inputs, "economics_end_year"))
    if end_year < start_year:
        raise ValueError("Završna godina ekonomike mora biti nakon početne godine.")

    years = np.arange(start_year, end_year + 1, dtype=int)
    mode = str(_input_value(inputs, "economics_co2_price_mode")).lower()

    if mode in PRESET_MODE_TO_KEY:
        source_start_year = int(_input_value(inputs, "co2_price_start_year"))
        source_prices = np.asarray(
            _input_value(inputs, PRESET_MODE_TO_KEY[mode]),
            dtype=float,
        )
        if source_prices.size == 0:
            raise ValueError("Odabrana zadana CO2 cjenovna putanja je prazna.")
        source_indices = np.clip(
            years - source_start_year,
            0,
            source_prices.size - 1,
        )
        prices = source_prices[source_indices]
    elif mode == "custom":
        tau = years - start_year
        p0 = float(_input_value(inputs, "economics_custom_price_p0"))
        function_name = str(
            _input_value(inputs, "economics_custom_price_function")
        ).lower()

        if function_name == "linear":
            growth = float(
                _input_value(inputs, "economics_custom_linear_growth")
            )
            prices = p0 + growth * tau
        elif function_name == "logarithmic":
            amplitude = float(
                _input_value(inputs, "economics_custom_log_amplitude")
            )
            rate = float(_input_value(inputs, "economics_custom_log_rate"))
            if rate <= 0:
                raise ValueError("Logaritamska stopa mora biti veća od nule.")
            prices = p0 + amplitude * np.log1p(rate * tau)
        elif function_name == "power_law":
            coefficient = float(
                _input_value(inputs, "economics_custom_power_coefficient")
            )
            exponent = float(
                _input_value(inputs, "economics_custom_power_exponent")
            )
            if exponent <= 0:
                raise ValueError("Power-law eksponent mora biti veći od nule.")
            prices = p0 + coefficient * np.power(tau, exponent)
        else:
            raise ValueError(
                f"Nepodržana prilagođena CO2 cjenovna funkcija: {function_name}"
            )
    else:
        raise ValueError(f"Nepodržan CO2 cjenovni scenarij: {mode}")

    if not np.all(np.isfinite(prices)) or np.any(prices < 0):
        raise ValueError("CO2 cjenovna putanja mora imati konačne nenegativne vrijednosti.")

    return pd.DataFrame(
        {
            "Godina": years,
            "Cijena CO2 (EUR/tCO2)": prices,
        }
    )
