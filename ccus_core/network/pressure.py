"""Pressure cascade along a chain of hubs, and the compression duty per emitter.

The storage side defines the target: the CO2 must arrive at the injection hub with
``p_precompression`` (default 10 bar).  Walking backwards, every leg adds its
friction loss::

    p[i] = p[i + 1] + dp_i(flow_i)

so ``p[i]`` is the pressure that must exist at the *upstream* end of leg ``i``.

Compression duty follows the cluster convention: the emitter that joined the chain
last carries the compression of the shared trunk (from its entry hub to the
storage), while the emitters that joined earlier only compress their own first
leg.  The friction model mirrors ``engineering.Pipeline`` (Darcy–Weisbach with the
Haaland turbulent factor and the laminar 64/Re branch).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import BaseModel, Field

DEFAULT_PRECOMPRESSION_BAR = 10.0
DEFAULT_ROUGHNESS_M = 4.5e-5
DEFAULT_DIAMETER_M = 0.30


@dataclass
class LegSpec:
    """One transport leg between two hubs (or emitter and hub)."""

    edge_id: str
    from_node: str
    to_node: str
    length_m: float
    diameter_m: float = DEFAULT_DIAMETER_M
    flow_kg_s: float = 0.0
    roughness_m: float = DEFAULT_ROUGHNESS_M

    @property
    def length_km(self) -> float:
        return float(self.length_m) / 1000.0


class LegState(BaseModel):
    """Solved pressure state of one leg."""

    edge_id: str
    from_node: str
    to_node: str
    length_km: float
    flow_kg_s: float
    inlet_pressure_bar: float
    outlet_pressure_bar: float
    dp_bar: float


class CompressionDuty(BaseModel):
    """Who compresses which part of the chain, and at what power."""

    emitter_id: str
    from_node: str
    to_node: str
    inlet_pressure_bar: float
    outlet_pressure_bar: float
    flow_kg_s: float
    power_kw: float = 0.0
    energy_mwh: float = 0.0


def friction_factor(reynolds: float, relative_roughness: float) -> float:
    """Haaland turbulent factor with the laminar 64/Re branch."""

    if reynolds <= 0.0:
        return 0.0
    if reynolds < 2300.0:
        return 64.0 / reynolds
    term = relative_roughness / 3.7 + (5.74 / max(reynolds, 1e-9) ** 0.9)
    return float(1.0 / (1.82 * math.log10(term)) ** 2) if term > 0.0 else 0.02


def pressure_drop_bar(
    leg: LegSpec,
    *,
    inlet_pressure_bar: float,
    temperature_c: float,
    fluid_props,
) -> float:
    """Friction pressure drop of one leg (bar), evaluated at local conditions."""

    if leg.flow_kg_s <= 0.0 or leg.length_m <= 0.0:
        return 0.0
    pressure_pa = float(inlet_pressure_bar) * 1e5
    temperature_k = float(temperature_c) + 273.15
    rho = float(fluid_props.get_density("CO2", pressure_pa, temperature_k))
    mu = float(fluid_props.get_viscosity("CO2", pressure_pa, temperature_k))
    area = math.pi * (float(leg.diameter_m) ** 2) / 4.0
    velocity = float(leg.flow_kg_s) / (rho * area)
    reynolds = rho * velocity * float(leg.diameter_m) / mu
    factor = friction_factor(reynolds, float(leg.roughness_m) / float(leg.diameter_m))
    dp_pa = factor * (float(leg.length_m) / float(leg.diameter_m)) * (rho * velocity**2 / 2.0)
    return float(dp_pa / 1e5)


def solve_chain(
    legs: list[LegSpec],
    *,
    target_outlet_bar: float = DEFAULT_PRECOMPRESSION_BAR,
    temperature_c: float = 20.0,
    fluid_props=None,
) -> list[LegState]:
    """Return the pressure state of every leg, walking backwards from the sink."""

    states: list[LegState] = []
    downstream = float(target_outlet_bar)
    for leg in reversed(legs):
        dp = pressure_drop_bar(
            leg,
            inlet_pressure_bar=downstream,
            temperature_c=temperature_c,
            fluid_props=fluid_props,
        )
        upstream = downstream + dp
        states.append(
            LegState(
                edge_id=leg.edge_id,
                from_node=leg.from_node,
                to_node=leg.to_node,
                length_km=leg.length_km,
                flow_kg_s=float(leg.flow_kg_s),
                inlet_pressure_bar=float(upstream),
                outlet_pressure_bar=float(downstream),
                dp_bar=float(dp),
            )
        )
        downstream = upstream
    return list(reversed(states))


def compression_duties(
    states: list[LegState],
    *,
    emitter_ids_by_node: dict[str, list[str]],
    activation_year: dict[str, int],
    year: int,
    p_comp_in_bar: float,
    eta_isentropic: float = 0.75,
    eta_dense_phase: float = 0.90,
    h_per_year: float = 8766.0,
    fluid_props=None,
) -> list[CompressionDuty]:
    """Assign compression duty per emitter (last joined emitter takes the trunk).

    For each emitter the first leg of the chain starting at its node is its own
    leg; the emitter with the highest activation year among those present in the
    year also carries every downstream leg.
    """

    if not states:
        return []

    duties: dict[str, CompressionDuty] = {}

    def add(emitter_id: str, leg: LegState) -> None:
        power_kw = _compression_power_kw(
            leg.flow_kg_s, p_comp_in_bar, leg.inlet_pressure_bar, eta_isentropic, eta_dense_phase, fluid_props
        )
        existing = duties.get(emitter_id)
        if existing is None:
            duties[emitter_id] = CompressionDuty(
                emitter_id=emitter_id,
                from_node=leg.from_node,
                to_node=leg.to_node,
                inlet_pressure_bar=p_comp_in_bar,
                outlet_pressure_bar=leg.inlet_pressure_bar,
                flow_kg_s=leg.flow_kg_s,
                power_kw=power_kw,
                energy_mwh=power_kw * h_per_year / 1000.0,
            )
        else:
            existing.power_kw += power_kw
            existing.energy_mwh += power_kw * h_per_year / 1000.0

    active = [emitter for emitter, year_on in activation_year.items() if year_on <= year]
    if not active:
        return []
    last_joined = max(active, key=lambda emitter: activation_year[emitter])

    for index, leg in enumerate(states):
        candidates = [
            emitter
            for node in (leg.from_node,)
            for emitter in emitter_ids_by_node.get(node, [])
            if emitter in active
        ]
        if not candidates:
            continue
        owner = max(candidates, key=lambda emitter: activation_year[emitter])
        if owner == last_joined:
            # the last emitter to join carries the whole remaining chain
            for downstream in states[index:]:
                add(owner, downstream)
        else:
            add(owner, leg)

    return sorted(duties.values(), key=lambda item: item.emitter_id)


def _compression_power_kw(
    m_dot: float,
    p_in_bar: float,
    p_out_bar: float,
    eta_is: float,
    eta_p: float,
    fluid_props,
) -> float:
    if m_dot <= 0.0 or p_out_bar <= p_in_bar or fluid_props is None:
        return 0.0
    try:
        from engineering import Power
        from types import SimpleNamespace

        power = Power(
            SimpleNamespace(
                m_dot=m_dot,
                t_comp_in=20.0,
                p_comp_in=p_in_bar,
                eta_orc=0.2,
                eta_gt_injection_pump=0.9,
                eta_co2_compressor_isentropic=eta_is,
                eta_co2_dense_phase_pump=eta_p,
            ),
            fluid_props,
        )
        return float(
            power.calculate_compression_power(
                fluid="CO2",
                p_in_bar=float(p_in_bar),
                p_out_bar=float(p_out_bar),
                t_in_C=20.0,
                m_dot=float(m_dot),
            )
        )
    except Exception:  # pragma: no cover - never break a scenario run
        return 0.0


__all__ = [
    "DEFAULT_PRECOMPRESSION_BAR",
    "DEFAULT_ROUGHNESS_M",
    "DEFAULT_DIAMETER_M",
    "LegSpec",
    "LegState",
    "CompressionDuty",
    "friction_factor",
    "pressure_drop_bar",
    "solve_chain",
    "compression_duties",
]