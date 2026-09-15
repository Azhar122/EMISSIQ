"""Tools available to the EMISSIQ Investigator.

SAFETY BOUNDARY. Every tool in this module is READ-ONLY except
`recommend_inspection`, which returns a recommendation and writes nothing.

There is deliberately no tool that can operate a valve, start or stop a
compressor, change a setpoint, write to a PLC, bypass an interlock or issue any
SCADA command. The agent cannot take a physical action because no such action
exists in its vocabulary — the restriction is structural, not a prompt
instruction that a model could talk its way around.

Creating a work order is likewise not a tool: it happens only when a human
presses the button in the UI.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import (
    Equipment,
    EventEvidence,
    EventSourceCandidate,
    MaintenanceRecord,
    MethaneEvent,
    Sensor,
)
from ..pipeline import load_readings, load_weather

# Recommended inspections by equipment type. Kept as a lookup rather than left
# to the model, so the agent cannot invent plant-specific advice.
INSPECTION_PLAYBOOK = {
    "compressor": (
        "Dry gas seal and seal-gas system inspection on the affected stage",
        "Mechanical / Rotating Equipment",
        [
            "Check seal gas differential pressure and vent flow at the primary seal",
            "Inspect the secondary seal vent for hydrocarbon carry-over",
            "Survey the discharge flange and seal housing with a portable CH4 detector",
            "Review the discharge pressure trend against the seal gas supply pressure",
        ],
    ),
    "control_valve": (
        "Valve stem packing and bonnet joint leak survey",
        "Instrumentation",
        ["Survey stem packing with a portable detector", "Check bonnet bolt torque"],
    ),
    "tank_vent": (
        "Tank vent and PRV seat inspection",
        "Mechanical",
        ["Verify PRV seat tightness", "Check vent line for blockage or backpressure"],
    ),
    "separator": (
        "Separator relief path and level control inspection",
        "Process",
        ["Check level control response", "Survey relief header connections"],
    ),
    "knockout_drum": (
        "Drain line and vent connection survey",
        "Mechanical",
        ["Survey drain valve and vent flange joints"],
    ),
    "pig_launcher": (
        "Launcher door seal and vent valve survey",
        "Mechanical",
        ["Inspect door seal", "Check vent valve seat"],
    ),
}


def _event(db: Session, event_id: str) -> MethaneEvent:
    ev = db.get(MethaneEvent, event_id)
    if ev is None:
        raise ValueError(f"unknown event {event_id}")
    return ev


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def get_event(db: Session, event_id: str) -> dict:
    ev = _event(db, event_id)
    eq = db.get(Equipment, ev.attributed_equipment_id) if ev.attributed_equipment_id else None
    sensor = db.get(Sensor, ev.detected_by_sensor_id) if ev.detected_by_sensor_id else None
    return {
        "event_id": ev.id,
        "facility_id": ev.facility_id,
        "started_at": ev.started_at.isoformat(),
        "peak_at": ev.peak_at.isoformat() if ev.peak_at else None,
        "ended_at": ev.ended_at.isoformat() if ev.ended_at else None,
        "duration_s": ev.duration_s,
        "first_detecting_sensor": sensor.tag if sensor else None,
        "peak_ch4_ppm": ev.peak_ch4_ppm,
        "baseline_ch4_ppm": ev.baseline_ch4_ppm,
        "peak_emission_rate_kg_h": ev.peak_emission_rate_kg_h,
        "total_mass_kg": ev.total_mass_kg,
        "uncertainty_pct": ev.uncertainty_pct,
        "severity": ev.severity,
        "status": ev.status,
        "detection_confidence": ev.detection_confidence,
        "attribution_confidence": ev.attribution_confidence,
        "currently_attributed_to": eq.tag if eq else None,
        "quantification_assumptions": ev.quantification_assumptions,
        "data_note": "Simulated demonstration data",
    }


def get_sensor_window(db: Session, event_id: str, pad_s: int = 120) -> dict:
    ev = _event(db, event_id)
    start = ev.started_at - dt.timedelta(seconds=pad_s)
    end = (ev.ended_at or ev.peak_at or ev.started_at) + dt.timedelta(seconds=pad_s)
    df = load_readings(db, ev.facility_id, start, end)
    if df.empty:
        return {"sensors": []}

    sensors = {s.id: s.tag for s in db.scalars(select(Sensor).where(Sensor.facility_id == ev.facility_id))}
    out = []
    for sid, group in df.groupby("sensor_id"):
        during = group[(group["ts"] >= ev.started_at) & (group["ts"] <= (ev.ended_at or ev.peak_at))]
        before = group[group["ts"] < ev.started_at]
        peak_row = group.loc[group["ch4_ppm"].idxmax()]
        out.append(
            {
                "sensor": sensors.get(sid, sid),
                "baseline_ppm": round(float(before["ch4_ppm"].median()), 3) if len(before) else None,
                "peak_ppm": round(float(peak_row["ch4_ppm"]), 3),
                "peak_at": peak_row["ts"].isoformat(),
                "mean_during_event_ppm": round(float(during["ch4_ppm"].mean()), 3) if len(during) else None,
                "detected": bool(sid == ev.detected_by_sensor_id or (len(during) and during["ch4_ppm"].max() > (before["ch4_ppm"].median() + 1.0 if len(before) else 3.0))),
            }
        )
    out.sort(key=lambda s: s["peak_ppm"], reverse=True)
    return {"window": [start.isoformat(), end.isoformat()], "sensors": out}


def get_weather_window(db: Session, event_id: str, pad_s: int = 120) -> dict:
    ev = _event(db, event_id)
    start = ev.started_at - dt.timedelta(seconds=pad_s)
    end = (ev.ended_at or ev.peak_at or ev.started_at) + dt.timedelta(seconds=pad_s)
    df = load_weather(db, ev.facility_id, start, end)
    if df.empty:
        return {"available": False}
    return {
        "available": True,
        "mean_wind_speed_ms": round(float(df["wind_speed_ms"].mean()), 2),
        "mean_wind_dir_from_deg": round(float(df["wind_dir_deg"].mean()), 1),
        "wind_dir_range_deg": [round(float(df["wind_dir_deg"].min()), 1), round(float(df["wind_dir_deg"].max()), 1)],
        "stability_class": str(df["stability_class"].mode().iloc[0]),
        "convention": "Wind direction is the direction the wind blows FROM, degrees true",
    }


def get_equipment_state(db: Session, event_id: str) -> dict:
    ev = _event(db, event_id)
    rows = db.scalars(select(Equipment).where(Equipment.facility_id == ev.facility_id)).all()
    return {
        "equipment": [
            {
                "tag": e.tag,
                "name": e.name,
                "type": e.equipment_type,
                "operating_state": e.operating_state,
                "criticality": e.criticality,
                "position_m": {"x": e.x_m, "y": e.y_m},
            }
            for e in rows
        ]
    }


def get_candidate_sources(db: Session, event_id: str) -> dict:
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
                "tag": eq.tag if eq else c.equipment_id,
                "name": eq.name if eq else "",
                "rank": c.rank,
                "score_pct": round(c.score * 100, 1),
                "distance_m": c.distance_m,
                "factors": c.factors,
            }
        )
    return {
        "candidates": out,
        "method": "Transparent weighted scoring over wind geometry, detection sequence, "
                  "operating state, maintenance status and event history",
        "caveat": "Estimated attribution. Not a validated source-attribution measurement.",
    }


def get_maintenance_history(db: Session, event_id: str, equipment_tag: str | None = None) -> dict:
    ev = _event(db, event_id)
    target = equipment_tag
    if not target and ev.attributed_equipment_id:
        eq = db.get(Equipment, ev.attributed_equipment_id)
        target = eq.tag if eq else None

    stmt = select(MaintenanceRecord)
    if target:
        eq = db.scalars(
            select(Equipment).where(
                Equipment.facility_id == ev.facility_id, Equipment.tag == target
            )
        ).first()
        if eq:
            stmt = stmt.where(MaintenanceRecord.equipment_id == eq.id)

    rows = db.scalars(stmt).all()
    return {
        "equipment_tag": target,
        "records": [
            {
                "task": r.task,
                "discipline": r.discipline,
                "performed_at": r.performed_at.isoformat() if r.performed_at else None,
                "due_at": r.due_at.isoformat() if r.due_at else None,
                "overdue": r.overdue,
                "notes": r.notes,
            }
            for r in rows
        ],
    }


def get_previous_events(db: Session, event_id: str, equipment_tag: str | None = None) -> dict:
    ev = _event(db, event_id)
    stmt = select(MethaneEvent).where(MethaneEvent.started_at < ev.started_at)
    target = equipment_tag
    if not target and ev.attributed_equipment_id:
        eq = db.get(Equipment, ev.attributed_equipment_id)
        target = eq.tag if eq else None
    if target:
        eq = db.scalars(
            select(Equipment).where(
                Equipment.facility_id == ev.facility_id, Equipment.tag == target
            )
        ).first()
        if eq:
            stmt = stmt.where(MethaneEvent.attributed_equipment_id == eq.id)

    rows = db.scalars(stmt.order_by(MethaneEvent.started_at.desc()).limit(10)).all()
    return {
        "equipment_tag": target,
        "count": len(rows),
        "events": [
            {
                "event_id": e.id,
                "started_at": e.started_at.isoformat(),
                "peak_emission_rate_kg_h": e.peak_emission_rate_kg_h,
                "duration_s": e.duration_s,
                "severity": e.severity,
                "status": e.status,
            }
            for e in rows
        ],
    }


def get_financial_impact(db: Session, event_id: str) -> dict:
    ev = _event(db, event_id)
    return {
        "financial": ev.financial,
        "environmental": ev.environmental,
        "note": "Daily and annual values are projections assuming recurrence, not measured losses.",
    }


def get_priority_breakdown(db: Session, event_id: str) -> dict:
    ev = _event(db, event_id)
    return {
        "priority": ev.priority,
        "score": ev.priority_score,
        "factors": ev.priority_factors,
        "note": "Priority is computed deterministically. It is not assigned by the model.",
    }


def recommend_inspection(db: Session, event_id: str, equipment_tag: str | None = None) -> dict:
    """Returns a recommendation only. It creates nothing and commands nothing."""
    ev = _event(db, event_id)
    eq = None
    if equipment_tag:
        eq = db.scalars(
            select(Equipment).where(
                Equipment.facility_id == ev.facility_id, Equipment.tag == equipment_tag
            )
        ).first()
    if eq is None and ev.attributed_equipment_id:
        eq = db.get(Equipment, ev.attributed_equipment_id)
    if eq is None:
        return {"available": False, "reason": "No attributed equipment"}

    title, discipline, steps = INSPECTION_PLAYBOOK.get(
        eq.equipment_type,
        ("General leak survey of the affected asset", "Mechanical", ["Portable CH4 survey of all joints"]),
    )
    overdue = db.scalars(
        select(MaintenanceRecord).where(
            MaintenanceRecord.equipment_id == eq.id, MaintenanceRecord.overdue.is_(True)
        )
    ).first()

    return {
        "equipment_tag": eq.tag,
        "inspection": title,
        "discipline": discipline,
        "steps": steps,
        "linked_overdue_task": overdue.task if overdue else None,
        "authority": "Recommendation only. EMISSIQ cannot operate plant equipment.",
    }


# ---------------------------------------------------------------------------
# Registry and schemas
# ---------------------------------------------------------------------------

REGISTRY = {
    "get_event": get_event,
    "get_sensor_window": get_sensor_window,
    "get_weather_window": get_weather_window,
    "get_equipment_state": get_equipment_state,
    "get_candidate_sources": get_candidate_sources,
    "get_maintenance_history": get_maintenance_history,
    "get_previous_events": get_previous_events,
    "get_financial_impact": get_financial_impact,
    "get_priority_breakdown": get_priority_breakdown,
    "recommend_inspection": recommend_inspection,
}

_NO_ARGS = {"type": "object", "properties": {}, "required": []}
_EQUIPMENT_ARG = {
    "type": "object",
    "properties": {
        "equipment_tag": {
            "type": "string",
            "description": "Equipment tag such as C-03. Omit to use the currently attributed asset.",
        }
    },
    "required": [],
}

_DESCRIPTIONS = {
    "get_event": ("Event header: timings, peak concentration, estimated emission rate and mass, confidences.", _NO_ARGS),
    "get_sensor_window": ("Per-sensor CH4 summary around the event, including which sensors stayed silent.", _NO_ARGS),
    "get_weather_window": ("Wind speed, direction and stability class during the event.", _NO_ARGS),
    "get_equipment_state": ("All assets at the facility with type, position and operating state.", _NO_ARGS),
    "get_candidate_sources": ("Ranked source candidates with the per-factor scoring breakdown.", _NO_ARGS),
    "get_maintenance_history": ("Maintenance records for an asset, including overdue tasks.", _EQUIPMENT_ARG),
    "get_previous_events": ("Previous methane events attributed to an asset.", _EQUIPMENT_ARG),
    "get_financial_impact": ("Gas value lost and environmental impact for this event.", _NO_ARGS),
    "get_priority_breakdown": ("Deterministic priority band, score and contributing factors.", _NO_ARGS),
    "recommend_inspection": ("Inspection playbook and discipline for an asset. Recommendation only.", _EQUIPMENT_ARG),
}


def tool_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": params},
        }
        for name, (desc, params) in _DESCRIPTIONS.items()
    ]


def call_tool(db: Session, name: str, event_id: str, arguments: dict) -> dict:
    fn = REGISTRY.get(name)
    if fn is None:
        # Anything not in the registry — including any control action — is
        # refused here rather than handled.
        return {"error": f"tool '{name}' is not available to this agent"}
    kwargs = {k: v for k, v in (arguments or {}).items() if k in ("equipment_tag", "pad_s")}
    try:
        return fn(db, event_id, **kwargs)
    except TypeError:
        return fn(db, event_id)
    except ValueError as exc:
        return {"error": str(exc)}
