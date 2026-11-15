"""Staggered onboarding and dynamic emission-curve behaviour."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ccus_core.models import CaptureTechnology, CaptureUnit, EmissionCurve, Emitter


def test_constant_curve_is_flat():
    curve = EmissionCurve.constant(700_000.0)
    assert [curve.value_at(year) for year in (2027, 2035, 2050)] == [700_000.0] * 3


def test_piecewise_ramp_steady_decline():
    curve = EmissionCurve.ramp(
        start_year=2030,
        start_t_per_year=0.0,
        plateau_year=2032,
        plateau_t_per_year=400_000.0,
        decline_year=2040,
        decline_t_per_year=0.0,
    )
    assert curve.value_at(2030) == 0.0
    assert curve.value_at(2031) == pytest.approx(200_000.0)
    assert curve.value_at(2032) == pytest.approx(400_000.0)
    assert curve.value_at(2036) == pytest.approx(200_000.0)
    assert curve.value_at(2038) == pytest.approx(100_000.0)
    assert curve.value_at(2040) == 0.0
    # outside the control-point range the curve is zero, not extrapolated
    assert curve.value_at(2029) == 0.0
    assert curve.value_at(2041) == 0.0


def test_legacy_polynomial_curve_matches_documented_shape():
    curve = EmissionCurve.polynomial(base_t_per_year=100_000.0, reference_year=2030, a=0.02, c=1.0)
    assert curve.value_at(2030) == pytest.approx(100_000.0)
    assert curve.value_at(2035) == pytest.approx(110_000.0)


def test_emitter_onboarding_is_staggered(staggered_emitters):
    nexe, plomin = staggered_emitters
    years = list(range(2027, 2041))
    nexe_series = nexe.captured_series(years)
    plomin_series = plomin.captured_series(years)

    assert nexe_series[0] == 0.0  # 2027 – not yet on line
    assert nexe_series[1] == 400_000.0  # 2028 – first full year
    assert plomin_series[:4] == [0.0, 0.0, 0.0, 0.0]  # 2027-2030 offline
    assert plomin_series[4] == pytest.approx(100_000.0)  # 2031 ramp start
    assert plomin_series[6] == pytest.approx(300_000.0)  # 2033 plateau


def test_capture_capacity_limits_the_offered_mass():
    emitter = Emitter(
        id="capped",
        name="Capped emitter",
        node_id="plant_nexe",
        activation_year=2028,
        gross_emissions=EmissionCurve.constant(500_000.0),
        capture=CaptureUnit(
            name="Capture train 1",
            technology=CaptureTechnology.OXY_FUEL,
            capacity_t_per_year=300_000.0,
            capex_eur=400_000_000.0,
            opex_eur_per_t=25.0,
            commissioning_year=2028,
        ),
    )
    assert emitter.captured_emissions(2028) == pytest.approx(300_000.0)
    assert emitter.captured_emissions(2029) == pytest.approx(300_000.0)
    # without a capture unit every tonne is offered to the network
    emitter.capture = None
    assert emitter.captured_emissions(2028) == pytest.approx(500_000.0)


def test_decommissioning_stops_the_emitter(staggered_emitters):
    nexe, _ = staggered_emitters
    nexe.decommission_year = 2035
    assert nexe.active_in(2035) is True
    assert nexe.active_in(2036) is False
    assert nexe.captured_emissions(2036) == 0.0


def test_capture_cannot_commission_before_the_emitter():
    with pytest.raises(ValidationError):
        Emitter(
            id="bad",
            name="Bad",
            node_id="plant_nexe",
            activation_year=2032,
            gross_emissions=EmissionCurve.constant(1_000.0),
            capture=CaptureUnit(name="Early", commissioning_year=2028),
        )


def test_negative_emissions_are_rejected():
    with pytest.raises(ValidationError):
        EmissionCurve.piecewise({2030: 100.0, 2031: -1.0})