"""Source attribution.

Scores every nearby asset against the observed plume as a transparent weighted
sum. Each candidate is scored independently on 0..1, so scores do not sum to
100% — they read as "how consistent is the evidence with this asset", which is
what an investigator actually wants.

This is an ESTIMATE. Nothing here is a validated source-attribution method and
every surface that renders these numbers says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict

from .geometry import (
    angle_difference_deg,
    bearing_deg,
    crosswind_offset_m,
    distance_m,
    downwind_bearing,
)

# Weights sum to 1.0. Kept in one dict so the scoring contract is auditable.
# Geometry dominates: where the wind was blowing is far stronger evidence than
# an asset's maintenance record.
ATTRIBUTION_WEIGHTS = {
    "wind_alignment": 0.34,
    "plume_fit": 0.18,
    "detection_sequence": 0.10,
    "operating_state": 0.09,
    "asset_prior": 0.09,
    "maintenance_status": 0.10,
    "event_history": 0.10,
}

SEQUENCE_TOLERANCE_S = 12.0
# Sensors that stayed silent are evidence too. A candidate whose plume would
# have swept a quiet sensor is penalised by up to this fraction.
SILENT_SENSOR_PENALTY = 0.6
SILENT_SENSOR_EXPECTATION_THRESHOLD = 0.25


@dataclass
class Candidate:
    equipment_id: str
    tag: str
    name: str
    equipment_type: str
    score: float
    rank: int
    distance_m: float
    bearing_alignment_deg: float
    factors: list[dict]
    silent_sensor_multiplier: float = 1.0
    silent_sensor_note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _factor(name: str, value: float, weight: float, detail: str) -> dict:
    return {
        "name": name,
        "value": round(value, 3),
        "weight": weight,
        "contribution": round(value * weight, 4),
        "detail": detail,
    }


def _wind_alignment(equip, first_sensor, wind_dir_from_deg) -> tuple[float, float, str]:
    """How well the wind places this asset upwind of the FIRST sensor to alarm.

    Scored as plume reach rather than raw bearing error, because a fixed angular
    tolerance is meaningless without distance: 20 degrees off-axis is a couple of
    metres at 10 m and forty metres at 100 m.
    """
    to_sensor = bearing_deg(equip["x_m"], equip["y_m"], first_sensor["x_m"], first_sensor["y_m"])
    plume = downwind_bearing(wind_dir_from_deg)
    dev = angle_difference_deg(to_sensor, plume)
    value = _plume_reach(equip, first_sensor, wind_dir_from_deg)
    detail = (
        f"Plume travels {plume:.0f}deg; {equip['tag']} -> {first_sensor['tag']} bears "
        f"{to_sensor:.0f}deg ({dev:.0f}deg off-axis, {value:.0%} plume coverage)"
    )
    return value, dev, detail


def _plume_reach(equip, sensor, wind_dir_from_deg) -> float:
    """Likelihood that a plume from this asset covers this sensor: how many
    lateral sigma off the centreline the sensor sits. Zero if it is upwind."""
    downwind, crosswind = crosswind_offset_m(
        equip["x_m"], equip["y_m"], sensor["x_m"], sensor["y_m"], wind_dir_from_deg
    )
    if downwind <= 1.0:
        return 0.0
    sigma_y = max(0.08 * downwind * (1 + 1e-4 * downwind) ** -0.5, 0.5)
    return math.exp(-(crosswind**2) / (2 * sigma_y**2))


def _plume_fit(equip, detections, wind_dir_from_deg) -> tuple[float, str]:
    """Do ALL the sensors that alarmed actually sit inside this asset's plume?
    The weakest link decides — one unexplained detection breaks the hypothesis."""
    reaches = [(d["tag"], _plume_reach(equip, d, wind_dir_from_deg)) for d in detections]
    worst_tag, worst = min(reaches, key=lambda r: r[1])
    described = ", ".join(f"{tag} {val:.0%}" for tag, val in reaches)
    if worst < 0.05:
        return worst, f"Plume from {equip['tag']} does not reach {worst_tag} ({described})"
    return worst, f"All alarming sensors lie within the plume envelope ({described})"


def _silent_sensor_consistency(
    equip, detections, silent_sensors, wind_dir_from_deg
) -> tuple[float, str]:
    """Penalise a candidate whose plume should have tripped a sensor that stayed
    quiet. Only ever a penalty — a candidate nobody could have detected does not
    get credit for being invisible."""
    detected_tags = {d["tag"] for d in detections}
    quiet = [s for s in silent_sensors if s["tag"] not in detected_tags]
    if not quiet:
        return 1.0, "No additional sensors available to corroborate"

    expectations = [(s["tag"], _plume_reach(equip, s, wind_dir_from_deg)) for s in quiet]
    tag, worst = max(expectations, key=lambda e: e[1])
    if worst < SILENT_SENSOR_EXPECTATION_THRESHOLD:
        return 1.0, "No silent sensor should have seen a plume from this asset"
    multiplier = 1.0 - SILENT_SENSOR_PENALTY * worst
    return multiplier, (
        f"{tag} sits {worst:.0%} inside this asset's plume but recorded nothing — "
        "inconsistent with a release here"
    )


def _detection_sequence(equip, detections, wind_speed_ms) -> tuple[float, str]:
    """Does the observed order and spacing of sensor alarms match travel time
    from this source at the measured wind speed?"""
    if len(detections) < 2:
        return 0.5, "Only one sensor detected — sequence uninformative"

    u = max(wind_speed_ms, 0.5)
    first, second = detections[0], detections[1]
    dw1, _ = crosswind_offset_m(
        equip["x_m"], equip["y_m"], first["x_m"], first["y_m"], first["wind_dir_from_deg"]
    )
    dw2, _ = crosswind_offset_m(
        equip["x_m"], equip["y_m"], second["x_m"], second["y_m"], second["wind_dir_from_deg"]
    )
    if dw1 <= 0 or dw2 <= 0:
        return 0.05, "One or both detecting sensors sit upwind of this asset"
    if dw2 < dw1:
        return 0.1, (
            f"{second['tag']} is closer downwind than {first['tag']}, but alarmed later — "
            "order is inconsistent with this source"
        )

    predicted = (dw2 - dw1) / u
    observed = float(second["lag_s"])
    err = abs(predicted - observed)
    value = math.exp(-((err / SEQUENCE_TOLERANCE_S) ** 2))
    detail = (
        f"{first['tag']} then {second['tag']}: travel time predicted {predicted:.0f}s, "
        f"observed {observed:.0f}s"
    )
    return value, detail


def score_candidates(
    equipment: list[dict],
    detections: list[dict],
    wind_speed_ms: float,
    wind_dir_from_deg: float,
    silent_sensors: list[dict] | None = None,
) -> list[Candidate]:
    """Rank assets against one event.

    `equipment` items need: id, tag, name, equipment_type, x_m, y_m,
    operating_state, leak_propensity, overdue_maintenance, prior_event_count.
    `detections` are sensor alarms in time order, each with tag, x_m, y_m,
    lag_s (seconds after the first alarm) and wind_dir_from_deg.
    """
    if not detections:
        return []

    first_sensor = detections[0]
    results: list[Candidate] = []

    for eq in equipment:
        factors: list[dict] = []

        align, dev, align_detail = _wind_alignment(eq, first_sensor, wind_dir_from_deg)
        factors.append(_factor("Wind alignment", align, ATTRIBUTION_WEIGHTS["wind_alignment"], align_detail))

        fit, fit_detail = _plume_fit(eq, detections, wind_dir_from_deg)
        factors.append(_factor("Plume fit", fit, ATTRIBUTION_WEIGHTS["plume_fit"], fit_detail))

        seq, seq_detail = _detection_sequence(eq, detections, wind_speed_ms)
        factors.append(_factor("Detection sequence", seq, ATTRIBUTION_WEIGHTS["detection_sequence"], seq_detail))

        dist = distance_m(eq["x_m"], eq["y_m"], first_sensor["x_m"], first_sensor["y_m"])

        state = str(eq.get("operating_state", "running")).lower()
        state_value = {"running": 1.0, "pressurised": 0.9, "standby": 0.45,
                       "idle": 0.3, "isolated": 0.05, "shutdown": 0.05}.get(state, 0.4)
        factors.append(
            _factor("Operating state", state_value, ATTRIBUTION_WEIGHTS["operating_state"],
                    f"{eq['tag']} was {state} during the event")
        )

        prior = float(eq.get("leak_propensity", 0.3))
        factors.append(
            _factor("Asset type prior", prior, ATTRIBUTION_WEIGHTS["asset_prior"],
                    f"{eq['equipment_type'].replace('_', ' ')} baseline leak propensity")
        )

        overdue = bool(eq.get("overdue_maintenance", False))
        maint_detail = (
            f"{eq.get('overdue_task', 'Inspection')} overdue"
            if overdue
            else "No overdue inspections"
        )
        factors.append(
            _factor("Maintenance status", 1.0 if overdue else 0.25,
                    ATTRIBUTION_WEIGHTS["maintenance_status"], maint_detail)
        )

        prior_events = int(eq.get("prior_event_count", 0))
        hist = min(1.0, prior_events / 3.0)
        factors.append(
            _factor("Event history", hist, ATTRIBUTION_WEIGHTS["event_history"],
                    f"{prior_events} prior methane event(s) attributed to {eq['tag']}")
        )

        multiplier, silent_note = _silent_sensor_consistency(
            eq, detections, silent_sensors or [], wind_dir_from_deg
        )
        score = sum(f["contribution"] for f in factors) * multiplier
        results.append(
            Candidate(
                equipment_id=eq["id"],
                tag=eq["tag"],
                name=eq["name"],
                equipment_type=eq["equipment_type"],
                score=round(score, 4),
                rank=0,
                distance_m=round(dist, 1),
                bearing_alignment_deg=round(dev, 1),
                factors=factors,
                silent_sensor_multiplier=round(multiplier, 3),
                silent_sensor_note=silent_note,
            )
        )

    results.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(results, start=1):
        c.rank = i
    return results


def attribution_confidence(ranked: list[Candidate]) -> float:
    """Confidence in the leading candidate: how well it scores, discounted by how
    close the runner-up is. A clear winner is worth more than a high score."""
    if not ranked:
        return 0.0
    top = ranked[0].score
    runner = ranked[1].score if len(ranked) > 1 else 0.0
    separation = min(1.0, (top - runner) / 0.35) if top > 0 else 0.0
    return round(min(0.99, 0.7 * top + 0.3 * separation), 3)
