"""Equipment inspection panel data — what an operator sees when they click an
asset on the digital twin."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.tools import INSPECTION_PLAYBOOK
from ..db.models import Equipment, MaintenanceRecord, MethaneEvent
from .deps import get_db, iso, not_found

router = APIRouter(prefix="/api/equipment", tags=["equipment"])


@router.get("/{equipment_id}")
def get_equipment(equipment_id: str, db: Session = Depends(get_db)):
    eq = db.get(Equipment, equipment_id)
    if eq is None:
        # Allow lookup by tag too, which is what the twin has to hand.
        eq = db.scalars(select(Equipment).where(Equipment.tag == equipment_id)).first()
    if eq is None:
        raise not_found("equipment", equipment_id)

    maintenance = db.scalars(
        select(MaintenanceRecord)
        .where(MaintenanceRecord.equipment_id == eq.id)
        .order_by(MaintenanceRecord.due_at)
    ).all()
    events = db.scalars(
        select(MethaneEvent)
        .where(MethaneEvent.attributed_equipment_id == eq.id)
        .order_by(MethaneEvent.started_at.desc())
        .limit(6)
    ).all()
    open_event = next((e for e in events if e.status != "Closed"), None)

    title, discipline, steps = INSPECTION_PLAYBOOK.get(
        eq.equipment_type,
        ("General leak survey of the affected asset", "Mechanical", ["Portable CH4 survey of all joints"]),
    )
    overdue = [m for m in maintenance if m.overdue]

    return {
        "id": eq.id,
        "tag": eq.tag,
        "name": eq.name,
        "type": eq.equipment_type,
        "operating_state": eq.operating_state,
        "criticality": eq.criticality,
        "position_m": {"x": eq.x_m, "y": eq.y_m},
        "current_event": {
            "id": open_event.id,
            "status": open_event.status,
            "peak_emission_rate_kg_h": open_event.peak_emission_rate_kg_h,
            "total_mass_kg": open_event.total_mass_kg,
            "uncertainty_pct": open_event.uncertainty_pct,
            "attribution_confidence": open_event.attribution_confidence,
            "priority": open_event.priority,
        } if open_event else None,
        "maintenance": [
            {
                "task": m.task,
                "discipline": m.discipline,
                "performed_at": iso(m.performed_at),
                "due_at": iso(m.due_at),
                "overdue": m.overdue,
                "notes": m.notes,
            }
            for m in maintenance
        ],
        "overdue_count": len(overdue),
        "previous_events": [
            {
                "id": e.id,
                "started_at": iso(e.started_at),
                "peak_emission_rate_kg_h": e.peak_emission_rate_kg_h,
                "severity": e.severity,
                "status": e.status,
            }
            for e in events
        ],
        "recommended_inspection": {
            "title": title,
            "discipline": discipline,
            "steps": steps,
            "linked_overdue_task": overdue[0].task if overdue else None,
        },
        "is_simulated": eq.is_simulated,
    }
