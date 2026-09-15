from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import MethaneEvent, RepairVerification, WorkOrder
from ..demo import run_post_repair
from ..schemas import WorkOrderCreate, WorkOrderStatusUpdate
from .deps import get_db, iso, not_found

router = APIRouter(prefix="/api/workorders", tags=["work-orders"])

# The only forward path. A work order cannot skip a stage or move backward
# through the API — that discipline is what makes the audit trail meaningful.
STATUS_ORDER = ["Open", "Assigned", "In Progress", "Repair Completed", "Verification", "Closed"]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _wo_dict(w: WorkOrder) -> dict:
    return {
        "id": w.id,
        "event_id": w.event_id,
        "facility_id": w.facility_id,
        "equipment_id": w.equipment_id,
        "title": w.title,
        "description": w.description,
        "discipline": w.discipline,
        "priority": w.priority,
        "status": w.status,
        "assignee": w.assignee,
        "created_by": w.created_by,
        "ai_drafted": w.ai_drafted,
        "created_at": iso(w.created_at),
        "updated_at": iso(w.updated_at),
        "repair_completed_at": iso(w.repair_completed_at),
        "closed_at": iso(w.closed_at),
        "audit_trail": w.audit_trail or [],
    }


def _next_wo_id(db: Session, year: int) -> str:
    prefix = f"WO-{year}-"
    count = db.scalar(select(func.count(WorkOrder.id)).where(WorkOrder.id.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


@router.get("")
def list_work_orders(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(WorkOrder).order_by(WorkOrder.created_at.desc())
    if status:
        stmt = stmt.where(WorkOrder.status == status)
    return [_wo_dict(w) for w in db.scalars(stmt).all()]


@router.get("/{work_order_id}")
def get_work_order(work_order_id: str, db: Session = Depends(get_db)):
    w = db.get(WorkOrder, work_order_id)
    if w is None:
        raise not_found("work order", work_order_id)
    return _wo_dict(w)


@router.post("")
def create_work_order(body: WorkOrderCreate, db: Session = Depends(get_db)):
    now = _now()
    wo = WorkOrder(
        id=_next_wo_id(db, now.year),
        event_id=body.event_id,
        facility_id=body.facility_id,
        equipment_id=body.equipment_id,
        title=body.title,
        description=body.description,
        discipline=body.discipline,
        priority=body.priority,
        status="Open",
        assignee=body.assignee,
        created_by="EMISSIQ (drafted)" if body.ai_drafted else "Operator",
        ai_drafted=body.ai_drafted,
        created_at=now,
        updated_at=now,
        audit_trail=[
            {
                "at": now.isoformat(),
                "actor": "EMISSIQ" if body.ai_drafted else "Operator",
                "action": "Work order created" + (" from AI recommendation" if body.ai_drafted else ""),
            }
        ],
    )
    db.add(wo)
    if body.event_id:
        event = db.get(MethaneEvent, body.event_id)
        if event:
            event.status = "Action Taken"
    db.commit()
    db.refresh(wo)
    return _wo_dict(wo)


@router.patch("/{work_order_id}")
async def update_status(work_order_id: str, body: WorkOrderStatusUpdate, db: Session = Depends(get_db)):
    wo = db.get(WorkOrder, work_order_id)
    if wo is None:
        raise not_found("work order", work_order_id)

    if body.status not in STATUS_ORDER:
        return {"error": f"unknown status '{body.status}'"}

    current_idx = STATUS_ORDER.index(wo.status) if wo.status in STATUS_ORDER else 0
    target_idx = STATUS_ORDER.index(body.status)
    if target_idx < current_idx:
        return {"error": f"cannot move status backward from '{wo.status}' to '{body.status}'"}

    now = _now()
    wo.status = body.status
    wo.updated_at = now
    if body.assignee:
        wo.assignee = body.assignee
    if body.status == "Repair Completed":
        wo.repair_completed_at = now
    if body.status == "Closed":
        wo.closed_at = now

    trail = list(wo.audit_trail or [])
    trail.append(
        {
            "at": now.isoformat(),
            "actor": body.assignee or wo.assignee or "Operator",
            "action": f"Status -> {body.status}" + (f": {body.note}" if body.note else ""),
        }
    )
    wo.audit_trail = trail
    db.commit()
    db.refresh(wo)

    # Entering "Verification" kicks off the post-repair sensor replay so the
    # comparison the workspace shows is generated, not asserted.
    if body.status == "Verification" and wo.event_id:
        await run_post_repair(wo.event_id)

    return _wo_dict(wo)


@router.post("/{work_order_id}/complete-repair")
async def complete_repair(work_order_id: str, db: Session = Depends(get_db)):
    wo = db.get(WorkOrder, work_order_id)
    if wo is None:
        raise not_found("work order", work_order_id)

    now = _now()
    wo.status = "Repair Completed"
    wo.repair_completed_at = now
    wo.updated_at = now
    trail = list(wo.audit_trail or [])
    trail.append({"at": now.isoformat(), "actor": wo.assignee or "Technician", "action": "Repair reported complete"})
    wo.audit_trail = trail
    db.commit()

    result = None
    if wo.event_id:
        wo.status = "Verification"
        trail.append({"at": now.isoformat(), "actor": "EMISSIQ", "action": "Verification started"})
        wo.audit_trail = trail
        db.commit()
        result = await run_post_repair(wo.event_id)

        verification = db.scalars(
            select(RepairVerification)
            .where(RepairVerification.event_id == wo.event_id)
            .order_by(RepairVerification.verified_at.desc())
        ).first()
        if verification and verification.outcome == "REPAIR VERIFIED":
            wo.status = "Closed"
            wo.closed_at = _now()
            trail.append({"at": wo.closed_at.isoformat(), "actor": "EMISSIQ", "action": "Repair verified, work order closed"})
            wo.audit_trail = trail
            db.commit()

    db.refresh(wo)
    return {"work_order": _wo_dict(wo), "verification_result": result}
