from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Equipment, Facility, MethaneEvent, Sensor
from .deps import get_db, iso, not_found

router = APIRouter(prefix="/api/facilities", tags=["facilities"])


def _facility_dict(db: Session, f: Facility) -> dict:
    open_events = db.scalars(
        select(MethaneEvent).where(
            MethaneEvent.facility_id == f.id, MethaneEvent.status != "Closed"
        )
    ).all()
    equipment_count = len(db.scalars(select(Equipment).where(Equipment.facility_id == f.id)).all())
    status = "Attention" if any(e.priority in ("Critical", "High") for e in open_events) else (
        "Monitoring" if open_events else "Normal"
    )
    return {
        "id": f.id,
        "name": f.name,
        "name_ar": f.name_ar,
        "region": f.region,
        "block": f.block,
        "lat": f.lat,
        "lon": f.lon,
        "extent_m": f.extent_m,
        "equipment_count": equipment_count,
        "open_events": len(open_events),
        "status": status,
        "is_simulated": f.is_simulated,
        "data_origin": f.data_origin,
    }


@router.get("")
def list_facilities(db: Session = Depends(get_db)):
    rows = db.scalars(select(Facility)).all()
    return [_facility_dict(db, f) for f in rows]


@router.get("/{facility_id}")
def get_facility(facility_id: str, db: Session = Depends(get_db)):
    f = db.get(Facility, facility_id)
    if f is None:
        raise not_found("facility", facility_id)
    equipment = db.scalars(select(Equipment).where(Equipment.facility_id == facility_id)).all()
    sensors = db.scalars(select(Sensor).where(Sensor.facility_id == facility_id)).all()
    out = _facility_dict(db, f)
    out["equipment"] = [
        {
            "id": e.id, "tag": e.tag, "name": e.name, "type": e.equipment_type,
            "x_m": e.x_m, "y_m": e.y_m, "criticality": e.criticality,
            "operating_state": e.operating_state,
        }
        for e in equipment
    ]
    out["sensors"] = [
        {
            "id": s.id, "tag": s.tag, "type": s.sensor_type, "x_m": s.x_m, "y_m": s.y_m,
            "status": s.status, "baseline_ppm": s.baseline_ppm,
        }
        for s in sensors
    ]
    return out
