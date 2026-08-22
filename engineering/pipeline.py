"""Coupled one-dimensional thermo-hydraulic horizontal-pipeline model."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from .fluid_properties import FluidProperties
from .transport import Transport


class Pipeline(Transport):
    """Calculate outlet pressure and temperature for CO2 or water.

    The pipe is horizontal. Every finite-volume step evaluates density,
    viscosity and isobaric heat capacity at its local pressure and
    temperature. Distributed Darcy-Weisbach friction and elbow losses lower
    pressure, while radial wall, insulation and environment resistances govern
    heat exchange with the specified ambient medium.
    """

    ELBOW_LOSS_COEFFICIENTS = {90: 0.9, 45: 0.4, 30: 0.2}
    _FLUID_ALIASES = {
        "co2": "CO2",
        "carbondioxide": "CO2",
        "carbon dioxide": "CO2",
        "h2o": "H2O",
        "water": "H2O",
        "voda": "H2O",
    }

    def __init__(self, inputs, fluid_props=None):
        super().__init__(inputs)
        self.fluid_props = fluid_props or FluidProperties()

    @staticmethod
    def _require_finite(name, value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"{name} mora biti konačan broj.")
        return value

    @classmethod
    def _normalise_fluid(cls, fluid):
        key = str(fluid).strip().lower()
        try:
            return cls._FLUID_ALIASES[key]
        except KeyError as exc:
            raise ValueError(
                "Pipeline podržava fluid 'CO2' ili 'Water'/'H2O'."
            ) from exc

    @staticmethod
    def _friction_factor(reynolds_number, relative_roughness):
        """Return Darcy friction factor with a smooth transition regime."""
        if reynolds_number <= 0.0:
            return 0.0
        if reynolds_number <= 2300.0:
            return 64.0 / reynolds_number

        turbulent = (
            -1.8
            * math.log10(
                (relative_roughness / 3.7) ** 1.11
                + 6.9 / reynolds_number
            )
        ) ** -2
        if reynolds_number >= 4000.0:
            return turbulent

        laminar = 64.0 / reynolds_number
        transition_fraction = (reynolds_number - 2300.0) / 1700.0
        return laminar + transition_fraction * (turbulent - laminar)

    def _input_float(self, name, default=None):
        value = getattr(self.inputs, name, default)
        if value is None:
            raise ValueError(f"Nedostaje obavezni ulazni parametar '{name}'.")
        return self._require_finite(name, value)

    def _elbow_counts(self, elbow_counts):
        if elbow_counts is None:
            values = {
                angle: getattr(
                    self.inputs,
                    f"pipeline_elbows_{angle}_count",
                    0,
                )
                for angle in self.ELBOW_LOSS_COEFFICIENTS
            }
        elif isinstance(elbow_counts, Mapping):
            supported_keys = {
                key
                for angle in self.ELBOW_LOSS_COEFFICIENTS
                for key in (
                    angle,
                    str(angle),
                    f"pipeline_elbows_{angle}_count",
                )
            }
            unknown_keys = set(elbow_counts) - supported_keys
            if unknown_keys:
                raise ValueError(
                    "Nepoznati ključevi u elbow_counts: "
                    + ", ".join(sorted(map(str, unknown_keys)))
                )
            values = {}
            for angle in self.ELBOW_LOSS_COEFFICIENTS:
                values[angle] = elbow_counts.get(
                    angle,
                    elbow_counts.get(
                        str(angle),
                        elbow_counts.get(f"pipeline_elbows_{angle}_count", 0),
                    ),
                )
        elif (
            isinstance(elbow_counts, Sequence)
            and not isinstance(elbow_counts, (str, bytes))
            and len(elbow_counts) == 3
        ):
            values = dict(zip((90, 45, 30), elbow_counts))
        else:
            raise ValueError(
                "elbow_counts mora biti mapa za 90/45/30° ili niz od tri broja."
            )

        parsed = {}
        for angle, value in values.items():
            if isinstance(value, bool):
                raise ValueError(
                    f"Broj koljena {angle}° mora biti nenegativan cijeli broj."
                )
            numeric = self._require_finite(f"Broj koljena {angle}°", value)
            if numeric < 0.0 or not numeric.is_integer():
                raise ValueError(
                    f"Broj koljena {angle}° mora biti nenegativan cijeli broj."
                )
            parsed[angle] = int(numeric)
        return parsed

    def _thermal_model(self, inner_diameter_m, environment_type=None):
        environment = str(
            environment_type
            if environment_type is not None
            else getattr(self.inputs, "pipeline_environment_type", "soil")
        ).strip().lower()
        if environment not in ("air", "soil"):
            raise ValueError("pipeline_environment_type mora biti 'air' ili 'soil'.")

        ambient_temperature_c = self._input_float(
            "pipeline_ambient_temperature_c",
            10.0,
        )
        if ambient_temperature_c <= -273.15:
            raise ValueError(
                "pipeline_ambient_temperature_c mora biti viša od apsolutne nule."
            )

        environment_conductivity = self._input_float(
            "pipeline_environment_thermal_conductivity_w_m_k",
            1.5,
        )
        environment_capacity = self._input_float(
            "pipeline_environment_volumetric_heat_capacity_j_m3_k",
            2.0e6,
        )
        wall_thickness = self._input_float("pipeline_wall_thickness_m", 0.01)
        wall_conductivity = self._input_float(
            "pipeline_wall_thermal_conductivity_w_m_k",
            45.0,
        )
        insulation_thickness = self._input_float(
            "pipeline_insulation_thickness_m",
            0.0,
        )
        insulation_conductivity = self._input_float(
            "pipeline_insulation_thermal_conductivity_w_m_k",
            0.04,
        )

        if environment_conductivity <= 0.0:
            raise ValueError(
                "Toplinska vodljivost okoliša mora biti veća od nule."
            )
        if environment_capacity <= 0.0:
            raise ValueError(
                "Volumetrijski toplinski kapacitet okoliša mora biti veći od nule."
            )
        if wall_thickness < 0.0 or insulation_thickness < 0.0:
            raise ValueError("Debljine stijenke i izolacije ne smiju biti negativne.")
        if wall_conductivity <= 0.0 or insulation_conductivity <= 0.0:
            raise ValueError(
                "Toplinske vodljivosti stijenke i izolacije moraju biti veće od nule."
            )

        inner_radius = inner_diameter_m / 2.0
        wall_outer_radius = inner_radius + wall_thickness
        outer_radius = wall_outer_radius + insulation_thickness
        wall_resistance = (
            math.log(wall_outer_radius / inner_radius)
            / (2.0 * math.pi * wall_conductivity)
            if wall_thickness > 0.0
            else 0.0
        )
        insulation_resistance = (
            math.log(outer_radius / wall_outer_radius)
            / (2.0 * math.pi * insulation_conductivity)
            if insulation_thickness > 0.0
            else 0.0
        )

        if environment == "air":
            external_coefficient = self._input_float(
                "pipeline_external_heat_transfer_coefficient_w_m2_k",
                10.0,
            )
            if external_coefficient <= 0.0:
                raise ValueError(
                    "Vanjski koeficijent prijelaza topline mora biti veći od nule."
                )
            external_resistance = 1.0 / (
                external_coefficient * 2.0 * math.pi * outer_radius
            )
        else:
            burial_depth = self._input_float("pipeline_burial_depth_m", 1.5)
            if burial_depth <= outer_radius:
                raise ValueError(
                    "Dubina osi ukopane cijevi mora biti veća od vanjskog polumjera."
                )
            # Steady radial resistance from an isothermal ground surface to a
            # buried cylinder. Heat capacity is reported via diffusivity below;
            # without an operating time it must not alter the steady solution.
            external_resistance = math.acosh(burial_depth / outer_radius) / (
                2.0 * math.pi * environment_conductivity
            )

        total_resistance = (
            wall_resistance + insulation_resistance + external_resistance
        )
        if total_resistance <= 0.0 or not math.isfinite(total_resistance):
            raise ValueError("Ukupni toplinski otpor pipelinea mora biti pozitivan.")

        return {
            "environment_type": environment,
            "ambient_temperature_c": ambient_temperature_c,
            "wall_thermal_resistance_k_m_w": wall_resistance,
            "insulation_thermal_resistance_k_m_w": insulation_resistance,
            "external_thermal_resistance_k_m_w": external_resistance,
            "total_thermal_resistance_k_m_w": total_resistance,
            "linear_heat_transfer_coefficient_w_m_k": 1.0 / total_resistance,
            "environment_thermal_diffusivity_m2_s": (
                environment_conductivity / environment_capacity
            ),
        }

    def _local_properties(self, fluid, pressure_pa, temperature_k, segment):
        try:
            density = float(
                self.fluid_props.get_density(fluid, pressure_pa, temperature_k)
            )
            viscosity = float(
                self.fluid_props.get_viscosity(fluid, pressure_pa, temperature_k)
            )
            specific_heat = float(
                self.fluid_props.get_specific_heat(
                    fluid,
                    pressure_pa,
                    temperature_k,
                    param="CPMASS",
                )
            )
        except Exception as exc:
            raise ValueError(
                "Nije moguće izračunati lokalna svojstva fluida u "
                f"segmentu {segment} pri p={pressure_pa / 1.0e5:.6g} bar i "
                f"T={temperature_k - 273.15:.6g} °C."
            ) from exc

        properties = {
            "gustoća": density,
            "viskoznost": viscosity,
            "specifični toplinski kapacitet": specific_heat,
        }
        for label, value in properties.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(
                    f"Lokalna {label} u segmentu {segment} mora biti pozitivna."
                )
        return density, viscosity, specific_heat

    def _local_phase(self, fluid, pressure_pa, temperature_k, segment):
        """Return a coarse phase family and reject explicit two-phase states."""
        phase_getter = getattr(self.fluid_props, "get_phase", None)
        if phase_getter is None:
            return None
        try:
            phase = str(
                phase_getter(fluid, pressure_pa, temperature_k)
            ).strip().lower()
        except Exception as exc:
            raise ValueError(
                "Nije moguće odrediti lokalnu fazu fluida u "
                f"segmentu {segment} pri p={pressure_pa / 1.0e5:.6g} bar i "
                f"T={temperature_k - 273.15:.6g} °C."
            ) from exc
        if "twophase" in phase or "two_phase" in phase:
            raise ValueError(
                "Jednofazni pipeline model ne podržava dvofazno stanje u "
                f"segmentu {segment} pri p={pressure_pa / 1.0e5:.6g} bar i "
                f"T={temperature_k - 273.15:.6g} °C."
            )
        if phase == "liquid":
            return "liquid"
        if phase == "gas":
            return "gas"
        # Supercritical labels can change continuously without a phase
        # boundary, so they are retained only as an informational family.
        if phase.startswith("supercritical"):
            return "supercritical"
        return phase or None

    def calculate_outlet_conditions(
        self,
        fluid,
        inlet_pressure_bar,
        inlet_temperature_c,
        mass_flow_kg_s,
        length_m=None,
        inner_diameter_m=None,
        roughness_m=None,
        elbow_counts=None,
        nsteps=50,
        return_diagnostics=False,
        ensure_convergence=True,
        maximum_nsteps=3200,
        pressure_tolerance_bar=0.01,
        temperature_tolerance_c=0.01,
    ):
        """Return outlet pressure and temperature for a horizontal pipeline.

        Pressure is supplied and returned in bar, temperature in degrees
        Celsius, mass flow in kg/s and geometry in metres. ``elbow_counts`` may
        be a mapping keyed by 90, 45 and 30 (degrees), or a three-item sequence
        in that order.

        ``nsteps`` is the initial grid. With ``ensure_convergence=True`` the
        grid is doubled until successive outlet pressure and temperature
        estimates agree within the requested tolerances; the finer converged
        result is returned and both grid sizes are recorded in diagnostics.
        """
        coolprop_fluid = self._normalise_fluid(fluid)
        inlet_pressure_bar = self._require_finite(
            "Ulazni tlak pipelinea",
            inlet_pressure_bar,
        )
        inlet_temperature_c = self._require_finite(
            "Ulazna temperatura pipelinea",
            inlet_temperature_c,
        )
        mass_flow_kg_s = self._require_finite(
            "Maseni protok pipelinea",
            mass_flow_kg_s,
        )
        length_m = self._require_finite(
            "Duljina pipelinea",
            self.distance_km * 1000.0 if length_m is None else length_m,
        )
        inner_diameter_m = self._require_finite(
            "Unutarnji promjer pipelinea",
            self._input_float("pipeline_inner_diameter_m")
            if inner_diameter_m is None
            else inner_diameter_m,
        )
        roughness_m = self._require_finite(
            "Hrapavost pipelinea",
            self._input_float("pipeline_roughness_m", 0.0)
            if roughness_m is None
            else roughness_m,
        )
        counts = self._elbow_counts(elbow_counts)

        if inlet_pressure_bar <= 0.0:
            raise ValueError("Ulazni tlak pipelinea mora biti veći od nule.")
        if inlet_temperature_c <= -273.15:
            raise ValueError("Ulazna temperatura mora biti viša od apsolutne nule.")
        if mass_flow_kg_s < 0.0:
            raise ValueError("Maseni protok pipelinea ne smije biti negativan.")
        if length_m < 0.0:
            raise ValueError("Duljina pipelinea ne smije biti negativna.")
        if inner_diameter_m <= 0.0:
            raise ValueError("Unutarnji promjer pipelinea mora biti veći od nule.")
        if roughness_m < 0.0 or roughness_m >= inner_diameter_m:
            raise ValueError(
                "Hrapavost pipelinea mora biti nenegativna i manja od promjera."
            )
        if isinstance(nsteps, bool) or not isinstance(nsteps, int) or nsteps < 1:
            raise ValueError("nsteps mora biti cijeli broj veći ili jednak 1.")
        if not isinstance(ensure_convergence, bool):
            raise ValueError("ensure_convergence mora biti bool vrijednost.")
        if ensure_convergence:
            if (
                isinstance(maximum_nsteps, bool)
                or not isinstance(maximum_nsteps, int)
                or maximum_nsteps < 2 * nsteps
            ):
                raise ValueError(
                    "Za provjeru konvergencije maximum_nsteps mora biti "
                    "cijeli broj najmanje 2 * nsteps."
                )
            pressure_tolerance_bar = self._require_finite(
                "Tolerancija konvergencije tlaka",
                pressure_tolerance_bar,
            )
            temperature_tolerance_c = self._require_finite(
                "Tolerancija konvergencije temperature",
                temperature_tolerance_c,
            )
            if pressure_tolerance_bar <= 0.0 or temperature_tolerance_c <= 0.0:
                raise ValueError(
                    "Tolerancije konvergencije moraju biti veće od nule."
                )

        thermal = self._thermal_model(inner_diameter_m)
        total_elbow_loss_coefficient = sum(
            counts[angle] * coefficient
            for angle, coefficient in self.ELBOW_LOSS_COEFFICIENTS.items()
        )

        basic_result = {
            "outlet_pressure_bar": inlet_pressure_bar,
            "outlet_temperature_c": inlet_temperature_c,
            "pressure_drop_bar": 0.0,
        }
        if mass_flow_kg_s == 0.0 or (
            length_m == 0.0 and total_elbow_loss_coefficient == 0.0
        ):
            if not return_diagnostics:
                return basic_result
            end_distance = length_m if length_m > 0.0 else 0.0
            basic_result.update(
                {
                    "friction_pressure_drop_bar": 0.0,
                    "minor_pressure_drop_bar": 0.0,
                    "temperature_change_c": 0.0,
                    "diagnostics": {
                        "distance_profile_m": [0.0, end_distance]
                        if end_distance > 0.0
                        else [0.0],
                        "pressure_profile_bar": [inlet_pressure_bar] * 2
                        if end_distance > 0.0
                        else [inlet_pressure_bar],
                        "temperature_profile_c": [inlet_temperature_c] * 2
                        if end_distance > 0.0
                        else [inlet_temperature_c],
                        "segment_density_kg_m3": [],
                        "segment_viscosity_pa_s": [],
                        "segment_specific_heat_j_kg_k": [],
                        "segment_velocity_m_s": [],
                        "segment_reynolds_number": [],
                        "segment_friction_factor": [],
                        "average_velocity_m_s": 0.0,
                        "total_elbow_loss_coefficient": (
                            total_elbow_loss_coefficient
                        ),
                        **thermal,
                    },
                }
            )
            return basic_result

        if ensure_convergence:
            common_arguments = {
                "fluid": coolprop_fluid,
                "inlet_pressure_bar": inlet_pressure_bar,
                "inlet_temperature_c": inlet_temperature_c,
                "mass_flow_kg_s": mass_flow_kg_s,
                "length_m": length_m,
                "inner_diameter_m": inner_diameter_m,
                "roughness_m": roughness_m,
                "elbow_counts": counts,
                "return_diagnostics": True,
                "ensure_convergence": False,
                "maximum_nsteps": maximum_nsteps,
                "pressure_tolerance_bar": pressure_tolerance_bar,
                "temperature_tolerance_c": temperature_tolerance_c,
            }
            accepted_nsteps = nsteps
            accepted = self.calculate_outlet_conditions(
                nsteps=accepted_nsteps,
                **common_arguments,
            )
            last_pressure_error = math.inf
            last_temperature_error = math.inf
            while accepted_nsteps * 2 <= maximum_nsteps:
                check_nsteps = accepted_nsteps * 2
                refined = self.calculate_outlet_conditions(
                    nsteps=check_nsteps,
                    **common_arguments,
                )
                last_pressure_error = abs(
                    accepted["outlet_pressure_bar"]
                    - refined["outlet_pressure_bar"]
                )
                last_temperature_error = abs(
                    accepted["outlet_temperature_c"]
                    - refined["outlet_temperature_c"]
                )
                if (
                    last_pressure_error <= pressure_tolerance_bar
                    and last_temperature_error <= temperature_tolerance_c
                ):
                    refined["diagnostics"].update(
                        {
                            "nsteps_used": check_nsteps,
                            "convergence_check_nsteps": check_nsteps,
                            "estimated_pressure_discretization_error_bar": (
                                last_pressure_error
                            ),
                            "estimated_temperature_discretization_error_c": (
                                last_temperature_error
                            ),
                        }
                    )
                    if return_diagnostics:
                        return refined
                    return {
                        "outlet_pressure_bar": refined[
                            "outlet_pressure_bar"
                        ],
                        "outlet_temperature_c": refined[
                            "outlet_temperature_c"
                        ],
                        "pressure_drop_bar": refined["pressure_drop_bar"],
                    }
                accepted = refined
                accepted_nsteps = check_nsteps

            raise ValueError(
                "Pipeline proračun nije konvergirao do maximum_nsteps="
                f"{maximum_nsteps}; zadnje razlike su "
                f"dP={last_pressure_error:.6g} bar i "
                f"dT={last_temperature_error:.6g} °C."
            )

        area_m2 = math.pi * inner_diameter_m**2 / 4.0
        segment_length_m = length_m / nsteps
        segment_elbow_coefficient = total_elbow_loss_coefficient / nsteps
        pressure_pa = inlet_pressure_bar * 1.0e5
        temperature_k = inlet_temperature_c + 273.15
        ambient_temperature_k = thermal["ambient_temperature_c"] + 273.15
        linear_heat_transfer = thermal[
            "linear_heat_transfer_coefficient_w_m_k"
        ]

        distance_profile = [0.0]
        pressure_profile = [inlet_pressure_bar]
        temperature_profile = [inlet_temperature_c]
        densities = []
        viscosities = []
        heat_capacities = []
        velocities = []
        reynolds_numbers = []
        friction_factors = []
        friction_drop_pa = 0.0
        minor_drop_pa = 0.0
        previous_phase_family = self._local_phase(
            coolprop_fluid,
            pressure_pa,
            temperature_k,
            0,
        )

        for segment in range(1, nsteps + 1):
            density, viscosity, specific_heat = self._local_properties(
                coolprop_fluid,
                pressure_pa,
                temperature_k,
                segment,
            )
            velocity = mass_flow_kg_s / (density * area_m2)
            reynolds_number = (
                density * velocity * inner_diameter_m / viscosity
            )
            friction_factor = self._friction_factor(
                reynolds_number,
                roughness_m / inner_diameter_m,
            )
            dynamic_pressure_pa = 0.5 * density * velocity**2
            segment_friction_drop_pa = (
                friction_factor
                * segment_length_m
                / inner_diameter_m
                * dynamic_pressure_pa
            )
            segment_minor_drop_pa = (
                segment_elbow_coefficient * dynamic_pressure_pa
            )
            next_pressure_pa = (
                pressure_pa
                - segment_friction_drop_pa
                - segment_minor_drop_pa
            )
            if next_pressure_pa <= 0.0 or not math.isfinite(next_pressure_pa):
                raise ValueError(
                    "Izračunati tlak pipelinea postaje nepozitivan u "
                    f"segmentu {segment}; povećajte ulazni tlak ili promjer."
                )

            temperature_exponent = (
                linear_heat_transfer
                * segment_length_m
                / (mass_flow_kg_s * specific_heat)
            )
            next_temperature_k = ambient_temperature_k + (
                temperature_k - ambient_temperature_k
            ) * math.exp(-temperature_exponent)
            next_phase_family = self._local_phase(
                coolprop_fluid,
                next_pressure_pa,
                next_temperature_k,
                segment,
            )
            if {
                previous_phase_family,
                next_phase_family,
            } == {"liquid", "gas"}:
                raise ValueError(
                    "Jednofazni pipeline model ne podržava fazni prijelaz "
                    f"liquid-gas u segmentu {segment} pri približno "
                    f"p={next_pressure_pa / 1.0e5:.6g} bar i "
                    f"T={next_temperature_k - 273.15:.6g} °C."
                )

            friction_drop_pa += segment_friction_drop_pa
            minor_drop_pa += segment_minor_drop_pa
            pressure_pa = next_pressure_pa
            temperature_k = next_temperature_k
            previous_phase_family = next_phase_family

            densities.append(density)
            viscosities.append(viscosity)
            heat_capacities.append(specific_heat)
            velocities.append(velocity)
            reynolds_numbers.append(reynolds_number)
            friction_factors.append(friction_factor)
            distance_profile.append(segment * segment_length_m)
            pressure_profile.append(pressure_pa / 1.0e5)
            temperature_profile.append(temperature_k - 273.15)

        result = {
            "outlet_pressure_bar": pressure_pa / 1.0e5,
            "outlet_temperature_c": temperature_k - 273.15,
            "pressure_drop_bar": inlet_pressure_bar - pressure_pa / 1.0e5,
        }
        if not return_diagnostics:
            return result

        result.update(
            {
                "friction_pressure_drop_bar": friction_drop_pa / 1.0e5,
                "minor_pressure_drop_bar": minor_drop_pa / 1.0e5,
                "temperature_change_c": (
                    temperature_k - 273.15 - inlet_temperature_c
                ),
                "diagnostics": {
                    "distance_profile_m": distance_profile,
                    "pressure_profile_bar": pressure_profile,
                    "temperature_profile_c": temperature_profile,
                    "segment_density_kg_m3": densities,
                    "segment_viscosity_pa_s": viscosities,
                    "segment_specific_heat_j_kg_k": heat_capacities,
                    "segment_velocity_m_s": velocities,
                    "segment_reynolds_number": reynolds_numbers,
                    "segment_friction_factor": friction_factors,
                    "average_velocity_m_s": sum(velocities) / len(velocities),
                    "total_elbow_loss_coefficient": (
                        total_elbow_loss_coefficient
                    ),
                    **thermal,
                },
            }
        )
        return result

    def calculate_pressure_drop(
        self,
        m_dot=None,
        length=None,
        diameter=None,
        **kwargs,
    ):
        """Backward-compatible scalar pressure-drop result in bar.

        ``m_dot`` is kg/s, ``length`` and ``diameter`` are metres. Additional
        keyword arguments are forwarded to :meth:`calculate_outlet_conditions`.
        """
        mass_flow_kg_s = (
            self.annual_co2_t * 1000.0 / (365.25 * 24.0 * 3600.0)
            if m_dot is None
            else m_dot
        )
        inlet_pressure_bar = kwargs.pop(
            "inlet_pressure_bar",
            getattr(self.inputs, "co2_pipeline_inlet_pressure_bar", None),
        )
        if inlet_pressure_bar is None:
            inlet_pressure_bar = getattr(self.inputs, "p_comp_in", None)
        inlet_temperature_c = kwargs.pop(
            "inlet_temperature_c",
            getattr(self.inputs, "co2_pipeline_inlet_temperature_c", None),
        )
        if inlet_temperature_c is None:
            inlet_temperature_c = getattr(self.inputs, "t_comp_in", None)
        fluid = kwargs.pop("fluid", "CO2")
        result = self.calculate_outlet_conditions(
            fluid=fluid,
            inlet_pressure_bar=inlet_pressure_bar,
            inlet_temperature_c=inlet_temperature_c,
            mass_flow_kg_s=mass_flow_kg_s,
            length_m=length,
            inner_diameter_m=diameter,
            **kwargs,
        )
        return result["pressure_drop_bar"]
