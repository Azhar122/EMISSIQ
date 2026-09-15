"""Emission rate and released-mass estimation.

Method: inversion of a Gaussian plume with Briggs open-country dispersion
coefficients. This is a screening-level estimate, not a validated measurement.
Every assumption is returned alongside the number and rendered in the UI.

  C(x,y,z) = Q / (2*pi*u*sy*sz) * exp(-y^2 / 2sy^2)
             * [ exp(-(z-H)^2 / 2sz^2) + exp(-(z+H)^2 / 2sz^2) ]

solved for Q given the measured excess concentration at a known receptor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .geometry import crosswind_offset_m

CH4_MOLAR_MASS_G = 16.043
IDEAL_MOLAR_VOLUME_L = 24.45  # 25 degC, 1 atm

# Relative 1-sigma uncertainty of each input, combined in quadrature below.
UNCERTAINTY_TERMS = {
    "wind_speed": 0.25,  # single mast, 1 Hz, not at plume height
    "dispersion_coefficients": 0.40,  # Briggs curves applied to a plant site
    "concentration_and_baseline": 0.15,
    "source_geometry": 0.20,  # source location known to the equipment, not the leak point
}

# Briggs (1973) open-country sigma curves, sigma in metres for downwind x in metres.
_BRIGGS = {
    "A": (lambda x: 0.22 * x * (1 + 1e-4 * x) ** -0.5, lambda x: 0.20 * x),
    "B": (lambda x: 0.16 * x * (1 + 1e-4 * x) ** -0.5, lambda x: 0.12 * x),
    "C": (lambda x: 0.11 * x * (1 + 1e-4 * x) ** -0.5,
          lambda x: 0.08 * x * (1 + 2e-4 * x) ** -0.5),
    "D": (lambda x: 0.08 * x * (1 + 1e-4 * x) ** -0.5,
          lambda x: 0.06 * x * (1 + 1.5e-3 * x) ** -0.5),
    "E": (lambda x: 0.06 * x * (1 + 1e-4 * x) ** -0.5,
          lambda x: 0.03 * x * (1 + 3e-4 * x) ** -1),
    "F": (lambda x: 0.04 * x * (1 + 1e-4 * x) ** -0.5,
          lambda x: 0.016 * x * (1 + 3e-4 * x) ** -1),
}


@dataclass
class Quantification:
    peak_emission_rate_kg_h: float
    total_mass_kg: float
    duration_s: float
    uncertainty_pct: float
    rate_low_kg_h: float
    rate_high_kg_h: float
    mass_low_kg: float
    mass_high_kg: float
    assumptions: dict

    def as_dict(self) -> dict:
        return asdict(self)


def ppm_to_kg_m3(ppm: float) -> float:
    """Volumetric ppm of methane in air to mass concentration, kg/m^3."""
    mg_m3 = ppm * CH4_MOLAR_MASS_G / IDEAL_MOLAR_VOLUME_L
    return mg_m3 * 1e-6


def stability_class(wind_speed_ms: float, daytime: bool = True) -> str:
    """Pasquill class from wind speed alone — the site has no radiation sensor,
    so daytime insolation is assumed moderate. Stated in the assumptions."""
    if not daytime:
        return "E" if wind_speed_ms < 3 else "D"
    if wind_speed_ms < 2:
        return "A"
    if wind_speed_ms < 3:
        return "B"
    if wind_speed_ms < 5:
        return "C"
    return "D"


def sigmas(downwind_m: float, stab: str) -> tuple[float, float]:
    sy_fn, sz_fn = _BRIGGS.get(stab, _BRIGGS["D"])
    x = max(downwind_m, 1.0)
    return max(sy_fn(x), 0.5), max(sz_fn(x), 0.5)


def emission_rate_kg_h(
    excess_ppm: float,
    wind_speed_ms: float,
    source_xy: tuple[float, float],
    receptor_xy: tuple[float, float],
    wind_dir_from_deg: float,
    release_height_m: float = 2.5,
    receptor_height_m: float = 2.0,
    stab: str | None = None,
) -> tuple[float, dict]:
    """Invert the plume equation for Q. Returns (kg/h, working)."""
    u = max(wind_speed_ms, 0.5)  # the model is undefined at calm; floor it
    stab = stab or stability_class(u)

    downwind, crosswind = crosswind_offset_m(*source_xy, *receptor_xy, wind_dir_from_deg)
    if downwind <= 0:
        # Receptor is upwind: this source cannot explain the reading.
        return 0.0, {"reason": "receptor upwind of source", "downwind_m": round(downwind, 1)}

    sy, sz = sigmas(downwind, stab)
    h, z = release_height_m, receptor_height_m

    lateral = math.exp(-(crosswind**2) / (2 * sy**2))
    vertical = math.exp(-((z - h) ** 2) / (2 * sz**2)) + math.exp(
        -((z + h) ** 2) / (2 * sz**2)
    )
    shape = lateral * vertical
    if shape < 1e-6:
        return 0.0, {"reason": "receptor outside plume envelope"}

    c_kg_m3 = ppm_to_kg_m3(excess_ppm)
    q_kg_s = c_kg_m3 * 2 * math.pi * u * sy * sz / shape

    working = {
        "downwind_m": round(downwind, 1),
        "crosswind_m": round(crosswind, 1),
        "sigma_y_m": round(sy, 2),
        "sigma_z_m": round(sz, 2),
        "stability_class": stab,
        "wind_speed_ms": round(u, 2),
        "excess_ppm": round(excess_ppm, 3),
        "release_height_m": h,
        "receptor_height_m": z,
    }
    return q_kg_s * 3600.0, working


def combined_uncertainty_pct(terms: dict[str, float] | None = None) -> float:
    terms = terms or UNCERTAINTY_TERMS
    return round(100.0 * math.sqrt(sum(v**2 for v in terms.values())), 1)


def quantify_event(
    profile: pd.DataFrame,
    baseline_ppm: float,
    source_xy: tuple[float, float],
    receptor_xy: tuple[float, float],
    wind_speed_ms: float,
    wind_dir_from_deg: float,
    release_height_m: float = 2.5,
    receptor_height_m: float = 2.0,
) -> Quantification:
    """Peak rate from the peak sample; total mass by integrating the whole profile.

    `profile` covers the detected window with columns `ts` and `ch4_ppm`.
    """
    prof = profile.sort_values("ts").reset_index(drop=True)
    excess = (prof["ch4_ppm"] - baseline_ppm).clip(lower=0.0)
    duration_s = float((prof["ts"].iloc[-1] - prof["ts"].iloc[0]).total_seconds())

    peak_excess = float(excess.max())
    peak_rate, working = emission_rate_kg_h(
        peak_excess,
        wind_speed_ms,
        source_xy,
        receptor_xy,
        wind_dir_from_deg,
        release_height_m,
        receptor_height_m,
    )

    # The plume inversion is linear in concentration, so the rate at any sample
    # is the peak rate scaled by that sample's excess. Integrate with the
    # trapezoid rule to get released mass — this is a mass in kg, never an
    # hourly rate, and the two are reported separately everywhere.
    if peak_excess > 0 and len(prof) > 1:
        t_s = (prof["ts"] - prof["ts"].iloc[0]).dt.total_seconds().to_numpy()
        rate_kg_s = (excess.to_numpy() / peak_excess) * (peak_rate / 3600.0)
        total_mass = float(np.trapezoid(rate_kg_s, t_s))
    else:
        total_mass = 0.0

    unc = combined_uncertainty_pct()
    f = unc / 100.0

    assumptions = {
        "model": "Gaussian plume inversion (Briggs open-country sigma curves)",
        "validation_status": "Screening estimate — NOT a validated measurement",
        "terrain": "Flat, open, no building downwash correction applied",
        "release_type": "Continuous point source over the detected window",
        "release_height_assumed_m": release_height_m,
        "stability_derived_from": "Wind speed only; moderate daytime insolation assumed",
        "mass_integration": "Peak rate scaled by per-sample excess, trapezoid integration",
        "uncertainty_terms_1sigma": UNCERTAINTY_TERMS,
        "uncertainty_combination": "Root-sum-square of independent relative terms",
        "molar_basis": "16.043 g/mol at 25 degC, 1 atm (24.45 L/mol)",
        "plume_working": working,
    }

    return Quantification(
        peak_emission_rate_kg_h=round(peak_rate, 3),
        total_mass_kg=round(total_mass, 4),
        duration_s=round(duration_s, 1),
        uncertainty_pct=unc,
        rate_low_kg_h=round(peak_rate * (1 - f), 3),
        rate_high_kg_h=round(peak_rate * (1 + f), 3),
        mass_low_kg=round(total_mass * (1 - f), 4),
        mass_high_kg=round(total_mass * (1 + f), 4),
        assumptions=assumptions,
    )
