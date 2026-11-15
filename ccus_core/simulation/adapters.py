"""Duck-typed adapters from core models to the existing engineering classes.

The engineering package expects a flat ``inputs`` object (historically
``IOEndpoints``).  Instead of forcing every caller to build a full flat scenario,
these helpers assemble exactly the attributes each legacy class reads.  This keeps
the physics code untouched while letting ``ccus_core`` drive it from typed models.
"""

from __future__ import annotations

from types import SimpleNamespace

from ccus_core.models import (
    GeothermalSystem,
    InjectionWellProperties,
    ReservoirProperties,
    StorageSink,
)

SECONDS_PER_YEAR = 365.25 * 24.0 * 3600.0
DEFAULT_WELL_RADIUS_M = 0.15


def reservoir_inputs(
    reservoir: ReservoirProperties,
    *,
    m_dot_kg_s: float,
    well: InjectionWellProperties | None = None,
) -> SimpleNamespace:
    """Attribute set required by :class:`engineering.MaterialBalance`."""

    radius = DEFAULT_WELL_RADIUS_M if well is None else float(well.radius_m)
    pore_volume = float(reservoir.area_m2) * float(reservoir.effective_thickness_m) * float(reservoir.porosity)
    return SimpleNamespace(
        A=float(reservoir.area_m2),
        h_ef=float(reservoir.effective_thickness_m),
        poro=float(reservoir.porosity),
        p_ref=float(reservoir.reference_pressure_bar),
        dp=float(reservoir.pressure_step_bar),
        c_p=float(reservoir.pore_compressibility_per_bar),
        sal=float(reservoir.salinity_g_per_l),
        k=float(reservoir.permeability_m2),
        rw=radius,
        t=float(reservoir.temperature_c),
        m_dot=float(m_dot_kg_s),
        re=(float(reservoir.area_m2) / 3.141592653589793) ** 0.5,
        V_p_ref=pore_volume,
        V_w_ref=pore_volume,
        p_max=float(reservoir.maximum_pressure_bar),
        E_eff=float(reservoir.storage_efficiency),
        S_plume_core=float(reservoir.plume_core_saturation),
        Sw_i=float(reservoir.irreducible_water_saturation),
        krw_max=float(reservoir.krw_max),
        krg_max=float(reservoir.krg_max),
        nw=float(reservoir.nw),
        ng=float(reservoir.ng),
        krw_min=float(reservoir.krw_min),
        krg_min=float(reservoir.krg_min),
    )


def well_inputs(
    reservoir: ReservoirProperties,
    *,
    radius_m: float,
    depth_m: float,
    m_dot_kg_s: float,
) -> SimpleNamespace:
    """Attribute set required by :class:`engineering.VFP`."""

    return SimpleNamespace(
        rw=float(radius_m),
        re=(float(reservoir.area_m2) / 3.141592653589793) ** 0.5,
        h_ef=float(reservoir.effective_thickness_m),
        h_ref=float(depth_m),
        k=float(reservoir.permeability_m2),
        m_dot=float(m_dot_kg_s),
        t=float(reservoir.temperature_c),
        p_ref=float(reservoir.reference_pressure_bar),
    )


def geothermal_inputs(
    reservoir: ReservoirProperties,
    system: GeothermalSystem,
    *,
    m_dot_kg_s: float = 1.0,
) -> SimpleNamespace:
    """Attribute set required by :class:`engineering.Geothermal`."""

    return SimpleNamespace(
        d_doublet=float(system.d_doublet_m),
        t=float(reservoir.temperature_c),
        h_ef=float(reservoir.effective_thickness_m),
        k=float(reservoir.permeability_m2),
        bhp_dp=float(system.bhp_dp_bar),
        eta=float(system.eta_orc),
        t_out=float(system.t_out_c),
        p_out=float(system.p_out_bar),
        rw=float(system.rw_production_m),
        poro=float(reservoir.porosity),
        m_dot=float(m_dot_kg_s),
        re=(float(reservoir.area_m2) / 3.141592653589793) ** 0.5,
    )


def power_inputs(
    *,
    m_dot_kg_s: float,
    p_comp_in_bar: float,
    t_comp_in_c: float,
    eta_orc: float,
    eta_gt_injection_pump: float,
    eta_co2_compressor_isentropic: float,
    eta_co2_dense_phase_pump: float,
) -> SimpleNamespace:
    """Attribute set required by :class:`engineering.Power`."""

    return SimpleNamespace(
        m_dot=float(m_dot_kg_s),
        t_comp_in=float(t_comp_in_c),
        p_comp_in=float(p_comp_in_bar),
        eta_orc=float(eta_orc),
        eta_gt_injection_pump=float(eta_gt_injection_pump),
        eta_co2_compressor_isentropic=float(eta_co2_compressor_isentropic),
        eta_co2_dense_phase_pump=float(eta_co2_dense_phase_pump),
    )


def sink_defaults(sink: StorageSink) -> dict[str, float]:
    """Compressor and efficiency inputs attached to a storage sink."""

    return {
        "compressor_inlet_pressure_bar": float(sink.compressor_inlet_pressure_bar),
        "compressor_inlet_temperature_c": float(sink.compressor_inlet_temperature_c),
        "eta_orc": float(sink.eta_orc),
        "eta_gt_injection_pump": float(sink.eta_gt_injection_pump),
        "eta_co2_compressor_isentropic": float(sink.eta_co2_compressor_isentropic),
        "eta_co2_dense_phase_pump": float(sink.eta_co2_dense_phase_pump),
    }


def power_inputs_for_sink(sink: StorageSink, m_dot_kg_s: float) -> SimpleNamespace:
    """Power inputs for the CO2 compressor serving one storage sink."""

    defaults = sink_defaults(sink)
    return power_inputs(
        m_dot_kg_s=m_dot_kg_s,
        p_comp_in_bar=defaults["compressor_inlet_pressure_bar"],
        t_comp_in_c=defaults["compressor_inlet_temperature_c"],
        eta_orc=defaults["eta_orc"],
        eta_gt_injection_pump=defaults["eta_gt_injection_pump"],
        eta_co2_compressor_isentropic=defaults["eta_co2_compressor_isentropic"],
        eta_co2_dense_phase_pump=defaults["eta_co2_dense_phase_pump"],
    )