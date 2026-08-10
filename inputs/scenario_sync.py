"""Consistency helpers for JSON-backed Streamlit scenario inputs."""


def required_storage_capacity_t(
    annual_co2_t: float,
    injection_start_year: int,
    injection_end_year: int,
) -> float:
    """Return the CO2 mass required to inject through the inclusive end year."""
    active_years = int(injection_end_year) - int(injection_start_year) + 1
    if active_years <= 0:
        return 0.0
    return float(annual_co2_t) * active_years


def expand_storage_capacity_for_plan(inputs: dict) -> tuple[float, float] | None:
    """Raise JSON-backed storage capacity when an edited plan requires more.

    Capacity is only expanded, never reduced.  This lets the most recently
    edited planning input (period or annual CO2 quantity) remain authoritative,
    while a later manual reduction of ``storage_capacity`` can still represent
    an intentional capacity-limited scenario.

    Returns ``(old_capacity_t, new_capacity_t)`` when an update was made.
    """
    required_capacity_t = required_storage_capacity_t(
        inputs["emitter_emissions_annual"][0],
        inputs["ccs_injection_start_year"][0],
        inputs["ccs_injection_end_year"][0],
    )
    old_capacity_t = float(inputs["storage_capacity"][0])
    if required_capacity_t <= old_capacity_t:
        return None

    inputs["storage_capacity"][0] = required_capacity_t
    return old_capacity_t, required_capacity_t
