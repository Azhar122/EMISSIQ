"""Event Investigation Report generation.

The report is an immutable JSON snapshot taken at generation time, assembled
purely from stored rows — nothing here calls the AI or recomputes an engine.
The frontend renders the snapshot as a printable industrial report.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import (
    AIInvestigation,
    Equipment,
    EventEvidence,
    EventSourceCandidate,
    Facility,
    MethaneEvent,
    RepairVerification,
    Report,
    Sensor,
    WorkOrder,
)
from .deps import get_db, iso, not_found

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _next_report_id(db: Session, event_id: str) -> str:
    count = db.scalar(
        select(func.count(Report.id)).where(Report.event_id == event_id)
    ) or 0
    return f"RPT-{event_id}-{count + 1}"


def _build_snapshot(db: Session, event: MethaneEvent) -> dict:
    facility = db.get(Facility, event.facility_id)
    eq = db.get(Equipment, event.attributed_equipment_id) if event.attributed_equipment_id else None
    sensor = db.get(Sensor, event.detected_by_sensor_id) if event.detected_by_sensor_id else None

    candidates = db.scalars(
        select(EventSourceCandidate)
        .where(EventSourceCandidate.event_id == event.id)
        .order_by(EventSourceCandidate.rank)
    ).all()
    evidence = db.scalars(select(EventEvidence).where(EventEvidence.event_id == event.id)).all()
    investigation = db.scalars(
        select(AIInvestigation)
        .where(AIInvestigation.event_id == event.id)
        .order_by(AIInvestigation.created_at.desc())
    ).first()
    work_order = db.scalars(select(WorkOrder).where(WorkOrder.event_id == event.id)).first()
    verification = db.scalars(
        select(RepairVerification)
        .where(RepairVerification.event_id == event.id)
        .order_by(RepairVerification.verified_at.desc())
    ).first()

    return {
        "generated_at": iso(dt.datetime.now(dt.timezone.utc)),
        "data_note": "SIMULATED DEMONSTRATION DATA — not measured operator data",
        "identification": {
            "event_id": event.id,
            "facility": facility.name if facility else event.facility_id,
            "region": facility.region if facility else "",
            "block": facility.block if facility else "",
        },
        "timestamps": {
            "detected_at": iso(event.started_at),
            "peak_at": iso(event.peak_at),
            "ended_at": iso(event.ended_at),
            "duration_s": event.duration_s,
        },
        "detection": {
            "sensor": sensor.tag if sensor else None,
            "baseline_ch4_ppm": event.baseline_ch4_ppm,
            "peak_ch4_ppm": event.peak_ch4_ppm,
            "peak_zscore": event.peak_zscore,
            "confidence": event.detection_confidence,
        },
        "probable_source": {
            "equipment_tag": eq.tag if eq else None,
            "equipment_name": eq.name if eq else None,
            "attribution_confidence": event.attribution_confidence,
            "caveat": "Estimated attribution from a transparent weighted-scoring model, "
                      "not a scientifically validated measurement.",
        },
        "candidate_sources": [
            {
                "tag": (db.get(Equipment, c.equipment_id).tag if db.get(Equipment, c.equipment_id) else c.equipment_id),
                "score_pct": round(c.score * 100, 1),
                "rank": c.rank,
                "factors": c.factors,
            }
            for c in candidates
        ],
        "sensor_evidence": [
            {"kind": e.kind, "summary": e.summary, "detail": e.detail} for e in evidence
        ],
        "emission_estimate": {
            "peak_rate_kg_ch4_h": event.peak_emission_rate_kg_h,
            "total_mass_kg_ch4": event.total_mass_kg,
            "uncertainty_pct": event.uncertainty_pct,
            "assumptions": event.quantification_assumptions,
        },
        "financial_impact": event.financial,
        "environmental_impact": event.environmental,
        "priority": {
            "level": event.priority,
            "score": event.priority_score,
            "factors": event.priority_factors,
        },
        "ai_investigation": investigation.report if investigation else None,
        "ai_investigation_meta": {
            "provider": investigation.provider,
            "tool_calls": investigation.tool_calls,
        } if investigation else None,
        "work_order": {
            "id": work_order.id,
            "status": work_order.status,
            "assignee": work_order.assignee,
            "discipline": work_order.discipline,
            "audit_trail": work_order.audit_trail,
        } if work_order else None,
        "repair_and_verification": {
            "outcome": verification.outcome,
            "reduction_pct": verification.reduction_pct,
            "ch4_avoided_kg_year": verification.ch4_avoided_kg_year,
            "gas_value_retained_omr_year": verification.gas_value_retained_omr_year,
            "co2e_avoided_t_year": verification.co2e_avoided_t_year,
            "resolution_time_s": verification.resolution_time_s,
        } if verification else None,
        "audit_trail": (work_order.audit_trail if work_order else []),
    }


@router.post("/{event_id}")
def generate_report(event_id: str, db: Session = Depends(get_db)):
    event = db.get(MethaneEvent, event_id)
    if event is None:
        raise not_found("event", event_id)

    snapshot = _build_snapshot(db, event)
    report = Report(id=_next_report_id(db, event_id), event_id=event_id, snapshot=snapshot)
    db.add(report)
    db.commit()
    db.refresh(report)
    return {"id": report.id, "event_id": report.event_id, "generated_at": iso(report.generated_at), "snapshot": report.snapshot}


@router.get("/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None:
        raise not_found("report", report_id)
    return {"id": r.id, "event_id": r.event_id, "generated_at": iso(r.generated_at), "snapshot": r.snapshot}


@router.get("")
def list_reports(event_id: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Report).order_by(Report.generated_at.desc())
    if event_id:
        stmt = stmt.where(Report.event_id == event_id)
    rows = db.scalars(stmt).all()
    return [{"id": r.id, "event_id": r.event_id, "generated_at": iso(r.generated_at)} for r in rows]
