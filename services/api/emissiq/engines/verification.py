"""Post-repair verification.

Compares the sensor that detected the event before and after the repair. The
verdict is a statistical comparison, not an opinion: if methane is still there,
the work order does not close.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from ..config import get_settings
from .financial import gas_value_omr

VERIFIED = "REPAIR VERIFIED"
STILL_DETECTED = "EMISSION STILL DETECTED"

# Post-repair peak must fall back to within this many sigma of the pre-event
# baseline, and the mean must drop by at least this fraction.
MAX_POST_ZSCORE = 3.0
MIN_REDUCTION_PCT = 70.0


@dataclass
class VerificationResult:
    outcome: str
    pre_mean_ppm: float
    post_mean_ppm: float
    pre_peak_ppm: float
    post_peak_ppm: float
    baseline_ppm: float
    post_peak_zscore: float
    reduction_pct: float
    ch4_avoided_kg_day: float
    ch4_avoided_kg_year: float
    gas_value_retained_omr_year: float
    co2e_avoided_t_year: float
    resolution_time_s: float
    criteria: dict

    def as_dict(self) -> dict:
        return asdict(self)


def verify_repair(
    pre: pd.DataFrame,
    post: pd.DataFrame,
    baseline_ppm: float,
    baseline_sigma_ppm: float,
    event_mass_kg: float,
    event_duration_s: float,
    resolution_time_s: float,
    recurrence_factor: float = 1.0,
) -> VerificationResult:
    """`pre` and `post` are the same sensor's CH4 series over comparable windows."""
    s = get_settings()
    sigma = max(baseline_sigma_ppm, 0.05)

    pre_mean = float(pre["ch4_ppm"].mean())
    post_mean = float(post["ch4_ppm"].mean())
    pre_peak = float(pre["ch4_ppm"].max())
    post_peak = float(post["ch4_ppm"].max())

    pre_excess = max(pre_mean - baseline_ppm, 1e-9)
    post_excess = max(post_mean - baseline_ppm, 0.0)
    reduction = float(np.clip(100.0 * (1 - post_excess / pre_excess), 0.0, 100.0))
    post_z = (post_peak - baseline_ppm) / sigma

    verified = post_z <= MAX_POST_ZSCORE and reduction >= MIN_REDUCTION_PCT
    outcome = VERIFIED if verified else STILL_DETECTED

    # Avoided emissions are only claimed when the repair actually verified.
    if verified and event_duration_s > 0:
        hours = event_duration_s / 3600.0
        kg_day = (event_mass_kg / hours) * 24.0 * recurrence_factor
        kg_year = kg_day * 365.0
        value_year = gas_value_omr(kg_year)
        co2e_year = kg_year * s.gwp100_ch4 / 1000.0
    else:
        kg_day = kg_year = value_year = co2e_year = 0.0

    return VerificationResult(
        outcome=outcome,
        pre_mean_ppm=round(pre_mean, 3),
        post_mean_ppm=round(post_mean, 3),
        pre_peak_ppm=round(pre_peak, 3),
        post_peak_ppm=round(post_peak, 3),
        baseline_ppm=round(baseline_ppm, 3),
        post_peak_zscore=round(post_z, 2),
        reduction_pct=round(reduction, 1),
        ch4_avoided_kg_day=round(kg_day, 3),
        ch4_avoided_kg_year=round(kg_year, 1),
        gas_value_retained_omr_year=round(value_year, 2),
        co2e_avoided_t_year=round(co2e_year, 2),
        resolution_time_s=round(resolution_time_s, 0),
        criteria={
            "post_peak_within_sigma": f"<= {MAX_POST_ZSCORE} sigma of pre-event baseline",
            "minimum_mean_reduction": f">= {MIN_REDUCTION_PCT}%",
            "avoided_basis": "Observed event duty cycle projected forward; a PROJECTION, "
                             "not a measured annual saving",
            "recurrence_factor": recurrence_factor,
        },
    )
