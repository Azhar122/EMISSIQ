"""Deterministic priority scoring.

The LLM never assigns priority. It is a weighted sum of seven measurable
factors, and the per-factor contributions are returned so an operator can argue
with the ranking instead of trusting it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

PRIORITY_WEIGHTS = {
    "emission_magnitude": 0.26,
    "financial_loss": 0.18,
    "recurrence": 0.15,
    "equipment_criticality": 0.13,
    "regulatory_relevance": 0.12,
    "duration": 0.08,
    "confidence": 0.08,
}

# Score thresholds. Deliberately conservative: Critical should be rare.
BANDS = [(0.72, "Critical"), (0.52, "High"), (0.32, "Medium"), (0.0, "Low")]

# OGMP 2.0 / national reporting interest starts around this rate.
REGULATORY_REPORTABLE_KG_H = 10.0


def _saturate(value: float, scale: float) -> float:
    """Diminishing-returns curve: doubling a big number should not double priority."""
    return 1.0 - math.exp(-max(value, 0.0) / scale)


def _factor(name: str, value: float, weight: float, detail: str) -> dict:
    return {
        "name": name,
        "value": round(value, 3),
        "weight": weight,
        "contribution": round(value * weight, 4),
        "detail": detail,
    }


@dataclass
class PriorityResult:
    priority: str
    score: float
    factors: list[dict]

    def as_dict(self) -> dict:
        return asdict(self)


def score_priority(
    peak_rate_kg_h: float,
    total_mass_kg: float,
    duration_s: float,
    annual_loss_omr: float,
    prior_event_count: int,
    equipment_criticality: float,
    detection_confidence: float,
    attribution_confidence: float,
) -> PriorityResult:
    factors = [
        _factor(
            "Emission magnitude",
            _saturate(peak_rate_kg_h, 12.0),
            PRIORITY_WEIGHTS["emission_magnitude"],
            f"Peak {peak_rate_kg_h:.1f} kg CH4/h, {total_mass_kg:.2f} kg released",
        ),
        _factor(
            "Financial loss",
            _saturate(annual_loss_omr, 4000.0),
            PRIORITY_WEIGHTS["financial_loss"],
            f"{annual_loss_omr:,.0f} OMR/year projected if recurring",
        ),
        _factor(
            "Recurrence",
            min(1.0, prior_event_count / 3.0),
            PRIORITY_WEIGHTS["recurrence"],
            f"{prior_event_count} prior event(s) on the same asset",
        ),
        _factor(
            "Equipment criticality",
            equipment_criticality,
            PRIORITY_WEIGHTS["equipment_criticality"],
            "Asset criticality from the equipment register",
        ),
        _factor(
            "Regulatory relevance",
            min(1.0, peak_rate_kg_h / REGULATORY_REPORTABLE_KG_H),
            PRIORITY_WEIGHTS["regulatory_relevance"],
            f"Reportable-scale threshold {REGULATORY_REPORTABLE_KG_H:.0f} kg CH4/h",
        ),
        _factor(
            "Duration",
            _saturate(duration_s, 300.0),
            PRIORITY_WEIGHTS["duration"],
            f"{duration_s:.0f} s above detection threshold",
        ),
        _factor(
            "Confidence",
            0.5 * detection_confidence + 0.5 * attribution_confidence,
            PRIORITY_WEIGHTS["confidence"],
            f"Detection {detection_confidence:.0%}, attribution {attribution_confidence:.0%}",
        ),
    ]

    score = sum(f["contribution"] for f in factors)
    priority = next(label for threshold, label in BANDS if score >= threshold)
    return PriorityResult(priority=priority, score=round(score, 4), factors=factors)


def severity_from_rate(peak_rate_kg_h: float) -> str:
    """Severity describes the release itself; priority describes what to do about
    it. They are deliberately different axes."""
    if peak_rate_kg_h >= 20:
        return "Critical"
    if peak_rate_kg_h >= 8:
        return "High"
    if peak_rate_kg_h >= 3:
        return "Medium"
    return "Normal"
