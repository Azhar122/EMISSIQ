from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.copilot import SUGGESTED_QUESTIONS, ask
from ..ai.investigator import investigate
from ..db.models import (
    AIInvestigation,
    Equipment,
    EventEvidence,
    EventSourceCandidate,
    Facility,
    MethaneEvent,
    RepairVerification,
    Sensor,
    WorkOrder,
)
from ..demo import run_post_repair
from ..pipeline import load_readings, load_weather
from ..schemas import CopilotQuestion
from .deps import get_db, iso, not_found

router = APIRouter(prefix="/api/events", tags=["events"])


def _summary(db: Session, e: MethaneEvent) -> dict:
    facility = db.get(Facility, e.facility_id)
    eq = db.get(Equipment, e.attributed_equipment_id) if e.attributed_equipment_id else None
    sensor = db.get(Sensor, e.detected_by_sensor_id) if e.detected_by_sensor_id else None
    return {
        "id": e.id,
        "facility_id": e.facility_id,
        "facility_name": facility.name if facility else e.facility_id,
        "equipment_tag": eq.tag if eq else None,
        "equipment_name": eq.name if eq else None,
        "detected_by_sensor": sensor.tag if sensor else None,
        "started_at": iso(e.started_at),
        "peak_at": iso(e.peak_at),
        "ended_at": iso(e.ended_at),
        "duration_s": e.duration_s,
        "peak_emission_rate_kg_h": e.peak_emission_rate_kg_h,
        "total_mass_kg": e.total_mass_kg,
        "uncertainty_pct": e.uncertainty_pct,
        "severity": e.severity,
        "status": e.status,
        "priority": e.priority,
        "detection_confidence": e.detection_confidence,
        "attribution_confidence": e.attribution_confidence,
        "gas_value_lost_omr": (e.financial or {}).get("gas_value_lost_omr"),
        "run_phase": e.run_phase,
        "is_simulated": e.is_simulated,
    }


@router.get("")
def list_events(
    status: str | None = None,
    severity: str | None = None,
    facility_id: str | None = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(MethaneEvent).order_by(MethaneEvent.started_at.desc())
    if status:
        stmt = stmt.where(MethaneEvent.status == status)
    if severity:
        stmt = stmt.where(MethaneEvent.severity == severity)
    if facility_id:
        stmt = stmt.where(MethaneEvent.facility_id == facility_id)
    rows = db.scalars(stmt.limit(limit)).all()
    return [_summary(db, e) for e in rows]


@router.get("/{event_id}")
def get_event_detail(event_id: str, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    out = _summary(db, e)
    out.update(
        {
            "baseline_ch4_ppm": e.baseline_ch4_ppm,
            "peak_ch4_ppm": e.peak_ch4_ppm,
            "peak_zscore": e.peak_zscore,
            "quantification_assumptions": e.quantification_assumptions,
            "financial": e.financial,
            "environmental": e.environmental,
            "priority_score": e.priority_score,
            "priority_factors": e.priority_factors,
            "data_quality": e.data_quality,
        }
    )
    return out


@router.get("/{event_id}/timeseries")
def get_timeseries(event_id: str, pad_s: int = 120, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    start = e.started_at - dt.timedelta(seconds=pad_s)
    end = (e.ended_at or e.peak_at or e.started_at) + dt.timedelta(seconds=pad_s)
    readings = load_readings(db, e.facility_id, start, end)
    weather = load_weather(db, e.facility_id, start, end)

    sensors = {s.id: s.tag for s in db.scalars(select(Sensor).where(Sensor.facility_id == e.facility_id))}
    series: dict[str, list] = {}
    for sid, group in readings.groupby("sensor_id"):
        tag = sensors.get(sid, sid)
        series[tag] = [
            {"t": r.ts.isoformat(), "ch4_ppm": r.ch4_ppm} for r in group.itertuples()
        ]

    process = []
    if not readings.empty:
        lead = readings[readings["sensor_id"] == e.detected_by_sensor_id]
        process = [
            {"t": r.ts.isoformat(), "pressure_barg": r.pressure_barg, "flow_kg_h": r.flow_kg_h}
            for r in lead.itertuples()
        ]

    wind = [
        {"t": r.ts.isoformat(), "wind_speed_ms": r.wind_speed_ms, "wind_dir_deg": r.wind_dir_deg}
        for r in weather.itertuples()
    ]

    markers = [
        {"t": iso(e.started_at), "label": "Detection start"},
        {"t": iso(e.peak_at), "label": "Peak"},
    ]
    if e.ended_at:
        markers.append({"t": iso(e.ended_at), "label": "Event end"})

    return {"ch4_by_sensor": series, "process": process, "wind": wind, "markers": markers}


@router.get("/{event_id}/candidates")
def get_candidates(event_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(EventSourceCandidate)
        .where(EventSourceCandidate.event_id == event_id)
        .order_by(EventSourceCandidate.rank)
    ).all()
    out = []
    for c in rows:
        eq = db.get(Equipment, c.equipment_id)
        out.append(
            {
                "equipment_id": c.equipment_id,
                "tag": eq.tag if eq else c.equipment_id,
                "name": eq.name if eq else "",
                "equipment_type": eq.equipment_type if eq else "",
                "rank": c.rank,
                "score_pct": round(c.score * 100, 1),
                "distance_m": c.distance_m,
                "bearing_alignment_deg": c.bearing_alignment_deg,
                "factors": c.factors,
            }
        )
    return {
        "candidates": out,
        "disclaimer": "Estimated source attribution from a transparent weighted-scoring model. "
                      "Not a scientifically validated measurement.",
    }


@router.get("/{event_id}/evidence")
def get_evidence(event_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(EventEvidence).where(EventEvidence.event_id == event_id).order_by(EventEvidence.weight.desc())
    ).all()
    return [
        {"kind": r.kind, "summary": r.summary, "detail": r.detail, "weight": r.weight}
        for r in rows
    ]


@router.get("/{event_id}/financial")
def get_financial(event_id: str, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    return {"financial": e.financial, "environmental": e.environmental}


@router.get("/{event_id}/priority")
def get_priority(event_id: str, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    return {"priority": e.priority, "score": e.priority_score, "factors": e.priority_factors}


@router.get("/{event_id}/similar")
def get_similar(event_id: str, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    if not e.attributed_equipment_id:
        return {"events": []}
    rows = db.scalars(
        select(MethaneEvent)
        .where(
            MethaneEvent.attributed_equipment_id == e.attributed_equipment_id,
            MethaneEvent.id != event_id,
        )
        .order_by(MethaneEvent.started_at.desc())
        .limit(5)
    ).all()
    return {"events": [_summary(db, r) for r in rows]}


@router.get("/{event_id}/investigations")
def get_investigations(event_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AIInvestigation)
        .where(AIInvestigation.event_id == event_id)
        .order_by(AIInvestigation.created_at.desc())
    ).all()
    return [
        {
            "id": r.id,
            "provider": r.provider,
            "model": r.model,
            "autonomy_level": r.autonomy_level,
            "tool_calls": r.tool_calls,
            "report": r.report,
            "duration_ms": r.duration_ms,
            "created_at": iso(r.created_at),
        }
        for r in rows
    ]


@router.post("/{event_id}/investigate")
def post_investigate(event_id: str, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    investigation = investigate(db, event_id)
    return {
        "id": investigation.id,
        "provider": investigation.provider,
        "tool_calls": investigation.tool_calls,
        "report": investigation.report,
        "duration_ms": investigation.duration_ms,
    }


@router.get("/{event_id}/copilot/suggestions")
def copilot_suggestions(event_id: str):
    return {"questions": SUGGESTED_QUESTIONS}


@router.post("/{event_id}/copilot")
def post_copilot(event_id: str, body: CopilotQuestion, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    return ask(db, event_id, body.question)


@router.get("/{event_id}/verification")
def get_verification(event_id: str, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(RepairVerification)
        .where(RepairVerification.event_id == event_id)
        .order_by(RepairVerification.verified_at.desc())
    ).all()
    return [
        {
            "outcome": r.outcome,
            "verified_at": iso(r.verified_at),
            "pre_mean_ppm": r.pre_mean_ppm,
            "post_mean_ppm": r.post_mean_ppm,
            "pre_peak_ppm": r.pre_peak_ppm,
            "post_peak_ppm": r.post_peak_ppm,
            "reduction_pct": r.reduction_pct,
            "ch4_avoided_kg_day": r.ch4_avoided_kg_day,
            "ch4_avoided_kg_year": r.ch4_avoided_kg_year,
            "gas_value_retained_omr_year": r.gas_value_retained_omr_year,
            "co2e_avoided_t_year": r.co2e_avoided_t_year,
            "resolution_time_s": r.resolution_time_s,
            "comparison_series": r.comparison_series,
        }
        for r in rows
    ]


@router.post("/{event_id}/verify")
async def post_verify(event_id: str, db: Session = Depends(get_db)):
    e = db.get(MethaneEvent, event_id)
    if e is None:
        raise not_found("event", event_id)
    result = await run_post_repair(event_id)
    return result
