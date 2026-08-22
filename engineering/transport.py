"""Transport configuration and pipeline-calculation delegation.

``Transport`` remains the lightweight configuration object used by the
integrated scenario. The approved thermo-hydraulic calculation lives in
``engineering.pipeline.Pipeline``; local imports in the delegate methods avoid
an import cycle because ``Pipeline`` subclasses this class for compatibility.
"""


class Transport:
    """Validated transport configuration derived from the scenario inputs."""

    SUPPORTED_MODES = ("pipeline", "truck", "rail")
    PIPELINE_HYDRAULIC_PARAMETER_NAMES = (
        "pipeline_inner_diameter_m",
        "pipeline_roughness_m",
        "pipeline_elbows_90_count",
        "pipeline_elbows_45_count",
        "pipeline_elbows_30_count",
    )
    PIPELINE_THERMAL_PARAMETER_NAMES = (
        "pipeline_environment_type",
        "pipeline_ambient_temperature_c",
        "pipeline_environment_thermal_conductivity_w_m_k",
        "pipeline_environment_volumetric_heat_capacity_j_m3_k",
        "pipeline_burial_depth_m",
        "pipeline_external_heat_transfer_coefficient_w_m2_k",
        "pipeline_wall_thickness_m",
        "pipeline_wall_thermal_conductivity_w_m_k",
        "pipeline_insulation_thickness_m",
        "pipeline_insulation_thermal_conductivity_w_m_k",
    )
    PIPELINE_INLET_PARAMETER_NAMES = (
        "co2_pipeline_inlet_pressure_bar",
        "co2_pipeline_inlet_temperature_c",
    )
    PIPELINE_PARAMETER_NAMES = (
        PIPELINE_HYDRAULIC_PARAMETER_NAMES
        + PIPELINE_THERMAL_PARAMETER_NAMES
        + PIPELINE_INLET_PARAMETER_NAMES
    )
    GEOTHERMAL_PIPELINE_PARAMETER_NAMES = (
        "d_doublet",
        "geothermal_pipeline_inner_diameter_m",
        "geothermal_pipeline_roughness_m",
        "geothermal_pipeline_elbows_90_count",
        "geothermal_pipeline_elbows_45_count",
        "geothermal_pipeline_elbows_30_count",
    )

    def __init__(self, inputs):
        self.inputs = inputs
        self.mode = inputs.transport_mode
        self.section_name = inputs.transport_section_name
        self.annual_co2_t = float(inputs.transport_flow_rate)
        self.distance_km = float(inputs.transport_distance_km)
        self.capex_eur = float(inputs.transport_capex)
        self.opex_eur_per_t = (
            float(inputs.transport_opex_per_ton)
            if inputs.transport_opex_per_ton is not None
            else 0.0
        )
        self.opex_eur_per_tkm = (
            float(inputs.transport_opex_eur_per_tkm)
            if inputs.transport_opex_eur_per_tkm is not None
            else 0.0
        )

        if self.mode not in self.SUPPORTED_MODES:
            raise ValueError("Način transporta mora biti pipeline, truck ili rail.")

        # Road and rail scenarios may intentionally omit pipeline-only inputs.
        self.pipeline_parameters = {
            name: getattr(inputs, name, None)
            for name in self.PIPELINE_PARAMETER_NAMES
        }
        self.geothermal_pipeline_parameters = {
            name: getattr(inputs, name)
            for name in self.GEOTHERMAL_PIPELINE_PARAMETER_NAMES
        }

    def as_dict(self):
        """Return the auditable transport configuration."""
        configuration = {
            "mode": self.mode,
            "section_name": self.section_name,
            "annual_co2_t": self.annual_co2_t,
            "distance_km": self.distance_km,
            "capex_eur": self.capex_eur,
            "opex_eur_per_t": self.opex_eur_per_t,
            "opex_eur_per_tkm": self.opex_eur_per_tkm,
        }
        if self.mode == "pipeline":
            configuration.update(self.pipeline_parameters)
        else:
            configuration.update(
                {
                    name: self.pipeline_parameters[name]
                    for name in self.PIPELINE_THERMAL_PARAMETER_NAMES
                }
            )
        configuration.update(self.geothermal_pipeline_parameters)
        return configuration

    def calculate_outlet_conditions(self, *args, **kwargs):
        """Delegate the coupled horizontal-pipeline calculation."""
        from .pipeline import Pipeline

        calculator = Pipeline(
            self.inputs,
            fluid_props=getattr(self, "fluid_props", None),
        )
        return calculator.calculate_outlet_conditions(*args, **kwargs)

    def calculate_pipeline_pressure_drop(
        self,
        m_dot=None,
        length=None,
        diameter=None,
        **kwargs,
    ):
        """Return pipeline pressure drop in bar through the approved model."""
        from .pipeline import Pipeline

        calculator = Pipeline(
            self.inputs,
            fluid_props=getattr(self, "fluid_props", None),
        )
        return calculator.calculate_pressure_drop(
            m_dot=m_dot,
            length=length,
            diameter=diameter,
            **kwargs,
        )
