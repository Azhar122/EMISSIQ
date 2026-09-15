"""Analytics — every figure is aggregated from stored rows, nothing here is a
hardcoded demo number."""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Equipment, Facility, MethaneEvent, RepairVerification, WorkOrder
from .deps import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
def summary(days: int = 90, db: Session = Depends(get_db)):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    events = db.scalars(select(MethaneEvent).where(MethaneEvent.started_at >= since)).all()
    verifications = db.scalars(select(RepairVerification)).all()
    work_orders = db.scalars(select(WorkOrder)).all()

    methane_detected_kg = sum(e.total_mass_kg or 0 for e in events)
    financial_loss_omr = sum((e.financial or {}).get("gas_value_lost_omr", 0) for e in events)

    verified = [v for v in verifications if v.outcome == "REPAIR VERIFIED"]
    methane_avoided_kg_year = sum(v.ch4_avoided_kg_year for v in verified)
    value_recovered_omr_year = sum(v.gas_value_retained_omr_year for v in verified)

    closed = [w for w in work_orders if w.closed_at and w.created_at]
    avg_resolution_h = (
        sum((w.closed_at - w.created_at).total_seconds() for w in closed) / len(closed) / 3600.0
        if closed
        else 0.0
    )

    severity_counts = Counter(e.severity for e in events)

    equip_counts: dict[str, int] = defaultdict(int)
    for e in events:
        if e.attributed_equipment_id:
            equip_counts[e.attributed_equipment_id] += 1
    recurring = sorted(equip_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
    equipment_lookup = {eq.id: eq for eq in db.scalars(select(Equipment)).all()}
    recurring_equipment = [
        {"tag": equipment_lookup[eid].tag, "name": equipment_lookup[eid].name, "event_count": n}
        for eid, n in recurring
        if eid in equipment_lookup
    ]

    facility_lookup = {f.id: f for f in db.scalars(select(Facility)).all()}
    facility_totals: dict[str, dict] = defaultdict(lambda: {"methane_kg": 0.0, "events": 0, "financial_omr": 0.0})
    for e in events:
        row = facility_totals[e.facility_id]
        row["methane_kg"] += e.total_mass_kg or 0
        row["events"] += 1
        row["financial_omr"] += (e.financial or {}).get("gas_value_lost_omr", 0)
    facility_comparison = [
        {
            "facility_id": fid,
            "facility_name": facility_lookup[fid].name if fid in facility_lookup else fid,
            "methane_kg": round(v["methane_kg"], 2),
            "events": v["events"],
            "financial_omr": round(v["financial_omr"], 2),
        }
        for fid, v in facility_totals.items()
    ]

    daily: dict[str, float] = defaultdict(float)
    for e in events:
        day = e.started_at.date().isoformat()
        daily[day] += e.total_mass_kg or 0
    daily_series = [
        {"date": d, "methane_kg": round(v, 3)} for d, v in sorted(daily.items())
    ]

    return {
        "window_days": days,
        "methane_detected_kg": round(methane_detected_kg, 2),
        "methane_avoided_kg_year_projection": round(methane_avoided_kg_year, 1),
        "financial_loss_detected_omr": round(financial_loss_omr, 2),
        "gas_value_recovered_omr_year_projection": round(value_recovered_omr_year, 2),
        "event_count": len(events),
        "average_resolution_time_hours": round(avg_resolution_h, 1),
        "recurring_equipment": recurring_equipment,
        "events_by_severity": dict(severity_counts),
        "facility_comparison": facility_comparison,
        "daily_methane_detected_kg": daily_series,
        "verified_repair_count": len(verified),
        "note": "Annual/projection figures assume observed release duty cycles recur; "
                "they are projections, not measurements.",
    }
