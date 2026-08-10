"""Annual engineering-to-economics ledger preparation.

The adapter converts the existing elapsed-time engineering results into a
calendar-year technical ledger.  It does not introduce physical equations:
stored mass is differentiated at annual boundaries and the existing power
series are integrated with the trapezoidal rule.
"""

from __future__ import annotations

from math import ceil
from typing import Any

import numpy as np
import pandas as pd


HOURS_PER_YEAR = 365.25 * 24.0
KWH_PER_MWH = 1000.0
MWH_PER_KW_YEAR = HOURS_PER_YEAR / KWH_PER_MWH
_INITIAL_TIME_TOLERANCE_YEARS = 1.0 / HOURS_PER_YEAR

LEDGER_COLUMNS = [
    "year",
    "co2_chain_t",
    "co2_stored_cumulative_t",
    "orc_gross_mwh",
    "gt_pump_mwh",
    "co2_compressor_mwh",
    "electricity_export_mwh",
    "electricity_import_mwh",
    "compressor_peak_kw",
    "injection_active",
    "geothermal_active",
    "monitoring_active",
    "injection_stop_note",
]


class _Series:
    def __init__(self, time_years: np.ndarray, values: np.ndarray):
        self.time_years = time_years
        self.values = values

    @property
    def coverage_end(self) -> float:
        return float(self.time_years[-1])


def _validate_year(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} mora biti cijela kalendarska godina.")
    return int(value)


def _read_series(
    dataframe: pd.DataFrame,
    *,
    dataframe_name: str,
    time_column: str,
    value_column: str,
) -> _Series:
    missing = [
        column
        for column in (time_column, value_column)
        if column not in dataframe.columns
    ]
    if missing:
        raise ValueError(
            f"{dataframe_name} nema obavezne stupce: {', '.join(missing)}."
        )

    time_years = pd.to_numeric(dataframe[time_column], errors="coerce").to_numpy(
        dtype=float
    )
    values = pd.to_numeric(dataframe[value_column], errors="coerce").to_numpy(
        dtype=float
    )
    if len(time_years) == 0:
        raise ValueError(f"{dataframe_name} ne smije biti prazan.")
    if not np.all(np.isfinite(time_years)) or not np.all(np.isfinite(values)):
        raise ValueError(f"{dataframe_name} sadrži nevaljane numeričke vrijednosti.")
    if np.any(time_years < 0.0) or np.any(np.diff(time_years) <= 0.0):
        raise ValueError(
            f"Vrijeme u {dataframe_name} mora biti strogo rastuće i nenegativno."
        )

    # The current material-balance result starts at one second with zero stored
    # mass.  Anchor that numerical start to elapsed time zero without extending
    # a materially incomplete engineering series.
    if time_years[0] > 0.0:
        if time_years[0] > _INITIAL_TIME_TOLERANCE_YEARS:
            raise ValueError(
                f"{dataframe_name} nema početnu vrijednost pri elapsed time 0."
            )
        time_years = np.insert(time_years, 0, 0.0)
        values = np.insert(values, 0, values[0])

    return _Series(time_years=time_years, values=values)


def _value_at(series: _Series, elapsed_year: float) -> float:
    if elapsed_year < 0.0 or elapsed_year > series.coverage_end:
        raise ValueError("Traženo vrijeme nije pokriveno inženjerskim vremenskim nizom.")
    return float(np.interp(elapsed_year, series.time_years, series.values))


def _integration_nodes(series: _Series, start: float, end: float) -> np.ndarray:
    internal = series.time_years[
        (series.time_years > start) & (series.time_years < end)
    ]
    return np.concatenate(([start], internal, [end]))


def _integrate_power(series: _Series, start: float, end: float) -> float:
    """Integrate kW over elapsed years and return MWh."""
    effective_start = max(0.0, start)
    effective_end = min(end, series.coverage_end)
    if effective_end <= effective_start:
        return 0.0
    nodes = _integration_nodes(series, effective_start, effective_end)
    values = np.interp(nodes, series.time_years, series.values)
    trapezoids = 0.5 * (values[:-1] + values[1:]) * np.diff(nodes)
    return float(np.sum(trapezoids) * MWH_PER_KW_YEAR)


def _peak_power(series: _Series, start: float, end: float) -> float:
    effective_start = max(0.0, start)
    effective_end = min(end, series.coverage_end)
    if effective_end <= effective_start:
        return 0.0
    nodes = _integration_nodes(series, effective_start, effective_end)
    return float(np.max(np.interp(nodes, series.time_years, series.values)))


def _component_value(
    series: _Series,
    elapsed_year: float,
    *,
    active_end: float,
) -> float:
    if elapsed_year < 0.0 or elapsed_year > active_end:
        return 0.0
    return _value_at(series, elapsed_year)


def _integrate_export_import(
    *,
    orc: _Series,
    pump: _Series,
    compressor: _Series,
    start: float,
    end: float,
    geothermal_active_end: float,
    injection_active_end: float,
) -> tuple[float, float]:
    """Integrate positive export and negative import from the power balance."""
    boundaries = {float(start), float(end)}
    for series, active_end in (
        (orc, geothermal_active_end),
        (pump, geothermal_active_end),
        (compressor, injection_active_end),
    ):
        clipped_end = min(end, series.coverage_end, active_end)
        if start < clipped_end < end:
            boundaries.add(float(clipped_end))
        boundaries.update(
            float(value)
            for value in series.time_years
            if start < value < clipped_end
        )

    export_kw_year = 0.0
    import_kw_year = 0.0
    nodes = sorted(boundaries)
    for left, right in zip(nodes[:-1], nodes[1:]):
        if right <= left:
            continue
        midpoint = 0.5 * (left + right)
        gt_active = 0.0 <= midpoint < geothermal_active_end
        injection_active = 0.0 <= midpoint < injection_active_end

        def balance_at(elapsed_year: float) -> float:
            orc_kw = (
                _component_value(orc, elapsed_year, active_end=geothermal_active_end)
                if gt_active
                else 0.0
            )
            pump_kw = (
                _component_value(pump, elapsed_year, active_end=geothermal_active_end)
                if gt_active
                else 0.0
            )
            compressor_kw = (
                _component_value(
                    compressor,
                    elapsed_year,
                    active_end=injection_active_end,
                )
                if injection_active
                else 0.0
            )
            return orc_kw - pump_kw - compressor_kw

        left_balance = balance_at(left)
        right_balance = balance_at(right)
        interval = right - left

        if left_balance * right_balance < 0.0:
            zero_fraction = abs(left_balance) / (
                abs(left_balance) + abs(right_balance)
            )
            zero_time = left + interval * zero_fraction
            pieces = (
                (left, zero_time, left_balance, 0.0),
                (zero_time, right, 0.0, right_balance),
            )
        else:
            pieces = ((left, right, left_balance, right_balance),)

        for piece_left, piece_right, value_left, value_right in pieces:
            area = 0.5 * (value_left + value_right) * (piece_right - piece_left)
            if area >= 0.0:
                export_kw_year += area
            else:
                import_kw_year += -area

    return (
        export_kw_year * MWH_PER_KW_YEAR,
        import_kw_year * MWH_PER_KW_YEAR,
    )


def _join_reason_note(reason: str | None, note: str | None) -> str | None:
    parts = [str(value).strip() for value in (reason, note) if value and str(value).strip()]
    return ": ".join(parts) if parts else None


def _last_active_calendar_year(start_year: int, active_end: float) -> int:
    return start_year + max(0, ceil(active_end) - 1)


def build_annual_engineering_ledger(
    mbal_df: pd.DataFrame,
    vfp_co2_df: pd.DataFrame,
    vfp_gt_df: pd.DataFrame,
    *,
    economics_start_year: int,
    economics_end_year: int,
    ccs_injection_start_year: int,
    ccs_injection_end_year: int,
    geothermal_operation_end_year: int,
    ccs_monitoring_end_year: int,
    injection_stop_reason: str | None = None,
    injection_stop_note: str | None = None,
    geothermal_stop_reason: str | None = None,
    geothermal_stop_note: str | None = None,
) -> pd.DataFrame:
    """Build the annual technical ledger consumed by economics.

    Lifecycle end years are inclusive.  The returned ledger covers
    ``economics_start_year`` through ``economics_end_year``; elapsed time zero
    is mapped to ``ccs_injection_start_year`` and earlier technical rows are
    zero.  If engineering coverage ends before a planned lifecycle end, only
    the covered interval is integrated and the truncation is recorded in
    ``ledger.attrs['adapter_metadata']``.
    """
    economic_start_year = _validate_year(
        "economics_start_year", economics_start_year
    )
    economic_end_year = _validate_year(
        "economics_end_year", economics_end_year
    )
    injection_start_year = _validate_year(
        "ccs_injection_start_year", ccs_injection_start_year
    )
    injection_end_year = _validate_year(
        "ccs_injection_end_year", ccs_injection_end_year
    )
    geothermal_end_year = _validate_year(
        "geothermal_operation_end_year", geothermal_operation_end_year
    )
    monitoring_end_year = _validate_year(
        "ccs_monitoring_end_year", ccs_monitoring_end_year
    )
    if economic_end_year < economic_start_year:
        raise ValueError(
            "Kraj ekonomskog razdoblja ne smije biti prije njegova početka."
        )
    if injection_end_year < injection_start_year:
        raise ValueError("Kraj utiskivanja ne smije biti prije početka utiskivanja.")
    if economic_start_year > injection_start_year:
        raise ValueError(
            "Početak ekonomskog razdoblja ne smije biti nakon početka utiskivanja."
        )
    if injection_end_year > economic_end_year:
        raise ValueError(
            "Kraj utiskivanja ne smije biti nakon kraja ekonomskog razdoblja."
        )
    if geothermal_end_year < injection_end_year:
        raise ValueError(
            "Kraj rada geotermalnog sustava ne smije biti prije kraja "
            "utiskivanja."
        )
    if geothermal_end_year > economic_end_year:
        raise ValueError(
            "Kraj rada geotermalnog sustava ne smije biti nakon kraja "
            "ekonomskog razdoblja."
        )
    if monitoring_end_year < injection_end_year:
        raise ValueError(
            "Kraj CCS monitoringa ne smije biti prije kraja utiskivanja."
        )
    if monitoring_end_year > economic_end_year:
        raise ValueError(
            "Kraj CCS monitoringa ne smije biti nakon kraja ekonomskog razdoblja."
        )

    stored_mass_mt = _read_series(
        mbal_df,
        dataframe_name="mbal_df",
        time_column="Time, yr",
        value_column="m_CO2, Mt",
    )
    compressor = _read_series(
        vfp_co2_df,
        dataframe_name="vfp_co2_df",
        time_column="Time [yr]",
        value_column="CO2 comp. P [kW]",
    )
    orc = _read_series(
        vfp_gt_df,
        dataframe_name="vfp_gt_df",
        time_column="Time [yr]",
        value_column="ORC power, kW",
    )
    pump = _read_series(
        vfp_gt_df,
        dataframe_name="vfp_gt_df",
        time_column="Time [yr]",
        value_column="pump power, kW",
    )

    if np.any(np.diff(stored_mass_mt.values) < -1e-12):
        raise ValueError("Kumulativna masa CO₂ u ležištu mora biti neopadajuća.")
    for label, series in (
        ("ORC snaga", orc),
        ("snaga GT pumpe", pump),
        ("snaga kompresora", compressor),
    ):
        if np.any(series.values < 0.0):
            raise ValueError(f"{label} ne smije sadržavati negativne vrijednosti.")

    planned_injection_end = float(
        injection_end_year - injection_start_year + 1
    )
    planned_geothermal_end = float(
        geothermal_end_year - injection_start_year + 1
    )
    injection_coverage_end = min(
        stored_mass_mt.coverage_end,
        compressor.coverage_end,
    )
    geothermal_coverage_end = min(orc.coverage_end, pump.coverage_end)
    injection_active_end = min(planned_injection_end, injection_coverage_end)
    geothermal_active_end = min(planned_geothermal_end, geothermal_coverage_end)

    coverage_notes: list[str] = []
    injection_coverage_note = None
    if (
        injection_coverage_end < planned_injection_end
        and not injection_stop_reason
        and not injection_stop_note
    ):
        injection_coverage_note = (
            "Planirani kraj utiskivanja prelazi dostupni inženjerski vremenski niz; "
            "masa i snaga kompresora nisu ekstrapolirane."
        )
        coverage_notes.append(injection_coverage_note)
    if geothermal_coverage_end < planned_geothermal_end:
        coverage_notes.append(
            "Planirani kraj rada geotermalnog sustava prelazi dostupni "
            "inženjerski vremenski niz; GT snaga nije ekstrapolirana."
        )

    stop_text = _join_reason_note(injection_stop_reason, injection_stop_note)
    if injection_coverage_note:
        stop_text = _join_reason_note(stop_text, injection_coverage_note)
    actual_injection_stop_year = _last_active_calendar_year(
        injection_start_year, injection_active_end
    )

    stop_mass_mt = _value_at(stored_mass_mt, injection_active_end)
    rows: list[dict[str, Any]] = []
    for year in range(economic_start_year, economic_end_year + 1):
        elapsed_start = float(year - injection_start_year)
        elapsed_end = elapsed_start + 1.0
        injection_interval_start = max(0.0, elapsed_start)
        injection_interval_end = min(elapsed_end, injection_active_end)
        geothermal_interval_start = max(0.0, elapsed_start)
        geothermal_interval_end = min(elapsed_end, geothermal_active_end)

        injection_active = injection_interval_end > injection_interval_start
        geothermal_active = geothermal_interval_end > geothermal_interval_start

        if injection_active:
            mass_start_mt = _value_at(stored_mass_mt, injection_interval_start)
            mass_end_mt = _value_at(stored_mass_mt, injection_interval_end)
            annual_mass_t = max(0.0, mass_end_mt - mass_start_mt) * 1_000_000.0
            cumulative_mass_t = mass_end_mt * 1_000_000.0
            compressor_mwh = _integrate_power(
                compressor, injection_interval_start, injection_interval_end
            )
            compressor_peak_kw = _peak_power(
                compressor, injection_interval_start, injection_interval_end
            )
        else:
            annual_mass_t = 0.0
            cumulative_mass_t = (
                0.0
                if elapsed_end <= 0.0
                else stop_mass_mt * 1_000_000.0
            )
            compressor_mwh = 0.0
            compressor_peak_kw = 0.0

        if geothermal_active:
            orc_mwh = _integrate_power(
                orc, geothermal_interval_start, geothermal_interval_end
            )
            pump_mwh = _integrate_power(
                pump, geothermal_interval_start, geothermal_interval_end
            )
        else:
            orc_mwh = 0.0
            pump_mwh = 0.0

        export_mwh, import_mwh = _integrate_export_import(
            orc=orc,
            pump=pump,
            compressor=compressor,
            start=elapsed_start,
            end=elapsed_end,
            geothermal_active_end=geothermal_active_end,
            injection_active_end=injection_active_end,
        )

        rows.append(
            {
                "year": year,
                "co2_chain_t": annual_mass_t,
                "co2_stored_cumulative_t": cumulative_mass_t,
                "orc_gross_mwh": orc_mwh,
                "gt_pump_mwh": pump_mwh,
                "co2_compressor_mwh": compressor_mwh,
                "electricity_export_mwh": export_mwh,
                "electricity_import_mwh": import_mwh,
                "compressor_peak_kw": compressor_peak_kw,
                "injection_active": injection_active,
                "geothermal_active": geothermal_active,
                "monitoring_active": (
                    injection_start_year <= year <= monitoring_end_year
                ),
                "injection_stop_note": (
                    stop_text if year == actual_injection_stop_year else None
                ),
            }
        )

    ledger = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    ledger.attrs["adapter_metadata"] = {
        "economics_start_year": economic_start_year,
        "economics_end_year": economic_end_year,
        "ccs_injection_start_year": injection_start_year,
        "ccs_injection_end_year": injection_end_year,
        "geothermal_operation_end_year": geothermal_end_year,
        "ccs_monitoring_end_year": monitoring_end_year,
        "injection_stop_reason": injection_stop_reason,
        "injection_stop_note": injection_stop_note,
        "geothermal_stop_reason": geothermal_stop_reason,
        "geothermal_stop_note": geothermal_stop_note,
        "injection_engineering_coverage_elapsed_years": injection_coverage_end,
        "geothermal_engineering_coverage_elapsed_years": geothermal_coverage_end,
        "injection_coverage_complete": (
            injection_coverage_end >= planned_injection_end
        ),
        "geothermal_coverage_complete": (
            geothermal_coverage_end >= planned_geothermal_end
        ),
        "coverage_notes": coverage_notes,
        "annualization": "piecewise-linear trapezoidal integration",
        "hours_per_year": HOURS_PER_YEAR,
    }
    return ledger


__all__ = ["LEDGER_COLUMNS", "build_annual_engineering_ledger"]
