"""The INGEST -> DETECT -> ATTRIBUTE -> QUANTIFY -> PRIORITIZE chain.

This is the only module that both touches the database and calls the engines.
The engines themselves stay pure: they take dataframes and dicts and return
dataclasses, which is what makes them testable and keeps the maths out of the
request handlers.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db.models import (
    Equipment,
    EventEvidence,
    EventSourceCandidate,
    Facility,
    MaintenanceRecord,
    MethaneEvent,
    Sensor,
    SensorReading,
    WeatherReading,
)
from .engines.attribution import attribution_confidence, score_candidates
from .engines.detection import DetectedEvent, detect_across_sensors
from .engines.financial import environmental_impact, financial_impact
from .engines.priority import score_priority, severity_from_rate
from .engines.quantification import quantify_event
from .sim import layout

# An intermittent seal release does not run continuously. Projections assume the
# observed release repeats on this duty cycle, and every projection says so.
DEFAULT_RECURRENCE_FACTOR = 0.35


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_readings(
    db: Session,
    facility_id: str,
    start: dt.datetime,
    end: dt.datetime,
    run_phases: list[str] | None = None,
) -> pd.DataFrame:
    stmt = select(SensorReading).where(
        SensorReading.facility_id == facility_id,
        SensorReading.ts >= start,
        SensorReading.ts <= end,
    )
    if run_phases:
        stmt = stmt.where(SensorReading.run_phase.in_(run_phases))
    rows = db.scalars(stmt.order_by(SensorReading.ts)).all()
    return pd.DataFrame(
        [
            {
                "ts": pd.Timestamp(r.ts),
                "sensor_id": r.sensor_id,
                "ch4_ppm": r.ch4_ppm,
                "pressure_barg": r.pressure_barg,
                "flow_kg_h": r.flow_kg_h,
                "equipment_state": r.equipment_state,
                "quality": r.quality,
            }
            for r in rows
        ]
    )


def load_weather(
    db: Session, facility_id: str, start: dt.datetime, end: dt.datetime
) -> pd.DataFrame:
    rows = db.scalars(
        select(WeatherReading)
        .where(
            WeatherReading.facility_id == facility_id,
            WeatherReading.ts >= start,
            WeatherReading.ts <= end,
        )
        .order_by(WeatherReading.ts)
    ).all()
    return pd.DataFrame(
        [
            {
                "ts": pd.Timestamp(r.ts),
                "wind_speed_ms": r.wind_speed_ms,
                "wind_dir_deg": r.wind_dir_deg,
                "stability_class": r.stability_class,
                "temperature_c": r.temperature_c,
            }
            for r in rows
        ]
    )


def _prior_event_count(db: Session, equipment_id: str, before: dt.datetime) -> int:
    return int(
        db.scalar(
            select(func.count(MethaneEvent.id)).where(
                MethaneEvent.attributed_equipment_id == equipment_id,
                MethaneEvent.started_at < before,
            )
        )
        or 0
    )


def _overdue_maintenance(db: Session, equipment_id: str) -> MaintenanceRecord | None:
    return db.scalars(
        select(MaintenanceRecord).where(
            MaintenanceRecord.equipment_id == equipment_id,
            MaintenanceRecord.overdue.is_(True),
        )
    ).first()


def next_event_id(db: Session, when: dt.datetime) -> str:
    year = when.year
    prefix = f"EVT-{year}-"
    count = int(
        db.scalar(
            select(func.count(MethaneEvent.id)).where(MethaneEvent.id.like(f"{prefix}%"))
        )
        or 0
    )
    return f"{prefix}{count + 1:05d}"


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


def process_window(
    db: Session,
    facility_id: str,
    start: dt.datetime,
    end: dt.datetime,
    run_phase: str = "demo-event",
    event_id: str | None = None,
) -> MethaneEvent | None:
    """Run the full deterministic chain over one window and persist the result.

    Returns the created event, or None when nothing crossed the threshold.
    """
    readings = load_readings(db, facility_id, start, end, run_phases=["baseline", run_phase])
    if readings.empty:
        return None

    weather = load_weather(db, facility_id, start, end)
    detections_by_sensor = detect_across_sensors(readings[["ts", "sensor_id", "ch4_ppm"]])
    if not detections_by_sensor:
        return None

    sensors = {s.id: s for s in db.scalars(select(Sensor).where(Sensor.facility_id == facility_id))}
    equipment = list(db.scalars(select(Equipment).where(Equipment.facility_id == facility_id)))

    # Order sensors by when they first alarmed — the detection sequence is
    # itself evidence, so it is preserved rather than collapsed into a set.
    ordered = [(sid, evs[0]) for sid, evs in detections_by_sensor.items()]
    ordered.sort(key=lambda pair: pair[1].started_at)
    lead_sensor_id, lead = ordered[0]

    wind_speed, wind_dir = _wind_at(weather, lead.peak_at)

    detections = [
        {
            "tag": sensors[sid].tag,
            "sensor_id": sid,
            "x_m": sensors[sid].x_m,
            "y_m": sensors[sid].y_m,
            "lag_s": (ev.started_at - lead.started_at).total_seconds(),
            "wind_dir_from_deg": wind_dir,
            "started_at": ev.started_at,
            "peak_ppm": ev.peak_ppm,
        }
        for sid, ev in ordered
    ]
    silent = [
        {"tag": s.tag, "sensor_id": s.id, "x_m": s.x_m, "y_m": s.y_m}
        for s in sensors.values()
        if s.id not in detections_by_sensor
    ]

    # --- attribute ------------------------------------------------------
    eq_payload = []
    for eq in equipment:
        overdue = _overdue_maintenance(db, eq.id)
        eq_payload.append(
            {
                "id": eq.id,
                "tag": eq.tag,
                "name": eq.name,
                "equipment_type": eq.equipment_type,
                "x_m": eq.x_m,
                "y_m": eq.y_m,
                "operating_state": eq.operating_state,
                "leak_propensity": eq.leak_propensity,
                "overdue_maintenance": overdue is not None,
                "overdue_task": overdue.task if overdue else "",
                "prior_event_count": _prior_event_count(db, eq.id, lead.started_at),
            }
        )

    ranked = score_candidates(eq_payload, detections, wind_speed, wind_dir, silent)
    attr_conf = attribution_confidence(ranked)
    leader = ranked[0] if ranked else None
    leader_eq = next((e for e in equipment if leader and e.id == leader.equipment_id), None)

    # --- quantify -------------------------------------------------------
    lead_sensor = sensors[lead_sensor_id]
    profile = readings[
        (readings["sensor_id"] == lead_sensor_id)
        & (readings["ts"] >= lead.started_at)
        & (readings["ts"] <= (lead.ended_at or lead.peak_at))
    ][["ts", "ch4_ppm"]]

    source_xy = (leader_eq.x_m, leader_eq.y_m) if leader_eq else (0.0, 0.0)
    quant = quantify_event(
        profile,
        lead.baseline_ppm,
        source_xy,
        (lead_sensor.x_m, lead_sensor.y_m),
        wind_speed,
        wind_dir,
    )

    # --- value and priority --------------------------------------------
    fin = financial_impact(
        quant.total_mass_kg,
        quant.duration_s,
        quant.peak_emission_rate_kg_h,
        DEFAULT_RECURRENCE_FACTOR,
    )
    env = environmental_impact(
        quant.total_mass_kg, quant.duration_s, DEFAULT_RECURRENCE_FACTOR
    )
    prior_events = _prior_event_count(db, leader_eq.id, lead.started_at) if leader_eq else 0
    prio = score_priority(
        quant.peak_emission_rate_kg_h,
        quant.total_mass_kg,
        quant.duration_s,
        fin.annual_loss_omr,
        prior_events,
        leader_eq.criticality if leader_eq else 0.5,
        lead.confidence,
        attr_conf,
    )

    # --- persist --------------------------------------------------------
    event = MethaneEvent(
        id=event_id or next_event_id(db, lead.started_at),
        facility_id=facility_id,
        detected_by_sensor_id=lead_sensor_id,
        attributed_equipment_id=leader_eq.id if leader_eq else None,
        started_at=lead.started_at.to_pydatetime(),
        peak_at=lead.peak_at.to_pydatetime(),
        ended_at=lead.ended_at.to_pydatetime() if lead.ended_at is not None else None,
        duration_s=quant.duration_s,
        peak_ch4_ppm=lead.peak_ppm,
        baseline_ch4_ppm=lead.baseline_ppm,
        peak_zscore=lead.peak_zscore,
        peak_emission_rate_kg_h=quant.peak_emission_rate_kg_h,
        total_mass_kg=quant.total_mass_kg,
        uncertainty_pct=quant.uncertainty_pct,
        quantification_assumptions={
            **quant.assumptions,
            "rate_range_kg_h": [quant.rate_low_kg_h, quant.rate_high_kg_h],
            "mass_range_kg": [quant.mass_low_kg, quant.mass_high_kg],
            "detection_config": lead.config,
            "wind_used": {"speed_ms": wind_speed, "direction_from_deg": wind_dir},
        },
        detection_confidence=lead.confidence,
        attribution_confidence=attr_conf,
        data_quality=round(float(readings["quality"].mean()), 3),
        priority=prio.priority,
        priority_score=prio.score,
        priority_factors=prio.factors,
        financial=fin.as_dict(),
        environmental=env.as_dict(),
        severity=severity_from_rate(quant.peak_emission_rate_kg_h),
        status="Investigating",
        run_phase=run_phase,
    )
    db.add(event)
    db.flush()

    for c in ranked:
        db.add(
            EventSourceCandidate(
                event_id=event.id,
                equipment_id=c.equipment_id,
                rank=c.rank,
                score=c.score,
                factors=c.factors
                + [
                    {
                        "name": "Silent sensor consistency",
                        "value": c.silent_sensor_multiplier,
                        "weight": "multiplier",
                        "contribution": None,
                        "detail": c.silent_sensor_note,
                    }
                ],
                distance_m=c.distance_m,
                bearing_alignment_deg=c.bearing_alignment_deg,
            )
        )

    for ev in build_evidence(db, event, detections, ranked, readings, wind_speed, wind_dir):
        db.add(ev)

    db.commit()
    db.refresh(event)
    return event


def _wind_at(weather: pd.DataFrame, when) -> tuple[float, float]:
    if weather.empty:
        return layout.DEMO_WIND_SPEED_MS, layout.DEMO_WIND_DIR_FROM_DEG
    idx = (weather["ts"] - pd.Timestamp(when)).abs().idxmin()
    row = weather.loc[idx]
    return float(row["wind_speed_ms"]), float(row["wind_dir_deg"])


def build_evidence(
    db: Session,
    event: MethaneEvent,
    detections: list[dict],
    ranked,
    readings: pd.DataFrame,
    wind_speed: float,
    wind_dir: float,
) -> list[EventEvidence]:
    """Turn the chain's intermediate findings into human-readable evidence rows.

    These are statements about the data, not the model's reasoning. The AI
    investigator reads them; it does not write them.
    """
    items: list[EventEvidence] = []
    leader = ranked[0] if ranked else None
    leader_tag = leader.tag if leader else "unknown"

    if len(detections) >= 2:
        a, b = detections[0], detections[1]
        items.append(
            EventEvidence(
                event_id=event.id,
                kind="wind",
                summary=(
                    f"Wind vector consistent with {leader_tag} -> {a['tag']} -> {b['tag']}: "
                    f"{wind_speed:.1f} m/s from {wind_dir:.0f} deg"
                ),
                detail={"wind_speed_ms": wind_speed, "wind_dir_from_deg": wind_dir},
                supports_equipment_id=event.attributed_equipment_id,
                weight=1.0,
            )
        )
        items.append(
            EventEvidence(
                event_id=event.id,
                kind="sequence",
                summary=(
                    f"{a['tag']} detected methane {b['lag_s']:.0f} s before {b['tag']}, "
                    "matching downwind travel time"
                ),
                detail={"lead_sensor": a["tag"], "second_sensor": b["tag"], "lag_s": b["lag_s"]},
                supports_equipment_id=event.attributed_equipment_id,
                weight=0.9,
            )
        )

    eq = db.get(Equipment, event.attributed_equipment_id) if event.attributed_equipment_id else None
    if eq:
        items.append(
            EventEvidence(
                event_id=event.id,
                kind="process",
                summary=f"{eq.tag} was {eq.operating_state} throughout the event window",
                detail={"operating_state": eq.operating_state},
                supports_equipment_id=eq.id,
                weight=0.7,
            )
        )

        pressure = readings.dropna(subset=["pressure_barg"])
        if not pressure.empty:
            # Compare only a short window immediately around the event — the
            # long pre-roll baseline is there for the detector's statistics,
            # not for finding the pressure step, and searching all of it picks
            # up unrelated noise from minutes earlier.
            lookback = event.started_at - pd.Timedelta(seconds=90)
            recent_pre = pressure[
                (pressure["ts"] >= lookback) & (pressure["ts"] < event.started_at)
            ]["pressure_barg"]
            during = pressure[
                (pressure["ts"] >= event.started_at) & (pressure["ts"] <= (event.ended_at or event.peak_at))
            ]["pressure_barg"]
            if len(recent_pre) and len(during):
                delta = float(during.min() - recent_pre.median())
                if abs(delta) > 0.3:
                    window = pressure[(pressure["ts"] >= lookback) & (pressure["ts"] <= event.started_at)]
                    first_drop = window[window["pressure_barg"] < recent_pre.median() - 0.3]["ts"]
                    lead_s = (
                        (event.started_at - first_drop.iloc[0].to_pydatetime()).total_seconds()
                        if len(first_drop)
                        else None
                    )
                    items.append(
                        EventEvidence(
                            event_id=event.id,
                            kind="process",
                            summary=(
                                f"{eq.tag} discharge pressure changed {delta:+.1f} barg "
                                + (f"{lead_s:.0f} s before" if lead_s else "around")
                                + " the methane rise"
                            ),
                            detail={"delta_barg": round(delta, 2), "lead_seconds": lead_s},
                            supports_equipment_id=eq.id,
                            weight=1.0,
                        )
                    )

        prior = _prior_event_count(db, eq.id, event.started_at)
        if prior:
            items.append(
                EventEvidence(
                    event_id=event.id,
                    kind="history",
                    summary=f"{prior} previous methane event(s) attributed to {eq.tag}",
                    detail={"prior_event_count": prior},
                    supports_equipment_id=eq.id,
                    weight=0.8,
                )
            )

        overdue = _overdue_maintenance(db, eq.id)
        if overdue:
            items.append(
                EventEvidence(
                    event_id=event.id,
                    kind="maintenance",
                    summary=f"{overdue.task} on {eq.tag} is overdue",
                    detail={
                        "task": overdue.task,
                        "due_at": overdue.due_at.isoformat() if overdue.due_at else None,
                        "discipline": overdue.discipline,
                    },
                    supports_equipment_id=eq.id,
                    weight=0.9,
                )
            )

    for c in ranked[1:4]:
        items.append(
            EventEvidence(
                event_id=event.id,
                kind="alternative",
                summary=f"{c.tag} considered and scored {c.score:.0%}: {c.silent_sensor_note or c.factors[0]['detail']}",
                detail={"score": c.score, "rank": c.rank},
                supports_equipment_id=c.equipment_id,
                weight=0.4,
            )
        )

    return items
