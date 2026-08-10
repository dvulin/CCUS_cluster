"""Transport configuration for the integrated CCUS chain.

The class separates transport inputs from the CO2 injection-well model.  It
does not yet calculate horizontal pipeline pressure drop because that would
introduce a new physical equation that requires explicit approval.
"""


class Transport:
    """Validated transport configuration derived from the scenario inputs."""

    SUPPORTED_MODES = ("pipeline", "truck", "rail")
    PIPELINE_PARAMETER_NAMES = (
        "pipeline_inner_diameter_m",
        "pipeline_roughness_m",
        "pipeline_elbows_90_count",
        "pipeline_elbows_45_count",
        "pipeline_elbows_30_count",
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
            raise ValueError(
                "Način transporta mora biti pipeline, truck ili rail."
            )

        self.pipeline_parameters = {
            name: getattr(inputs, name)
            for name in self.PIPELINE_PARAMETER_NAMES
        }

    def as_dict(self):
        """Return an auditable transport configuration without calculations."""
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
        return configuration

    def calculate_pipeline_pressure_drop(self):
        """Reserve the API for the separately approved hydraulic equation."""
        raise NotImplementedError(
            "Pad tlaka u horizontalnom cjevovodu još nije izračunat: "
            "potrebno je posebno potvrditi jednadžbu trenja i koeficijente "
            "lokalnih gubitaka za koljena."
        )
