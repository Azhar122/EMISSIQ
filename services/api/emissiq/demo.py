"""Demo orchestration.

Drives the full INGEST -> ... -> VERIFY chain for the Fahud / C-03 scenario as
one repeatable run, broadcasting WebSocket ticks and named stages as it goes.
Judges press one button; this module is what actually walks the workflow.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .ai.investigator import investigate
from .db.models import (
    AIInvestigation,
    EventEvidence,
    EventSourceCandidate,
    MethaneEvent,
    RepairVerification,
    SensorReading,
    WeatherReading,
    WorkOrder,
)
from .db.session import SessionLocal
from .engines.verification import verify_repair
from .pipeline import load_readings, process_window
from .sim import layout, scenario_fahud as sc
from .sim.simulator import SensorSimulator
from .ws import manager

log = logging.getLogger(__name__)

DEMO_EVENT_ID_PREFIX = "EVT"
_state = {"running": False, "stage": None, "event_id": None, "started_at": None}


def state() -> dict:
    return dict(_state)


async def _emit_stage(key: str, label: str, detail: str, extra: dict | None = None) -> None:
    _state["stage"] = key
    payload = {"type": "stage", "key": key, "label": label, "detail": detail, **(extra or {})}
    await manager.broadcast(payload)
    log.info("demo stage: %s", key)


def reset_demo_data(db: Session) -> None:
    """Remove any prior demo-run rows, leaving seeded history intact."""
    db.execute(delete(SensorReading).where(SensorReading.run_phase.in_(["baseline", "demo-event", "post-repair"])))
    db.execute(delete(WeatherReading).where(WeatherReading.run_phase.in_(["baseline", "demo-event", "post-repair"])))

    demo_event_ids = db.query(MethaneEvent.id).filter(
        MethaneEvent.run_phase.in_(["demo-event", "post-repair"])
    )
    db.execute(delete(EventEvidence).where(EventEvidence.event_id.in_(demo_event_ids)))
    db.execute(delete(EventSourceCandidate).where(EventSourceCandidate.event_id.in_(demo_event_ids)))
    db.execute(delete(AIInvestigation).where(AIInvestigation.event_id.in_(demo_event_ids)))
    db.execute(delete(RepairVerification).where(RepairVerification.event_id.in_(demo_event_ids)))
    db.execute(delete(WorkOrder).where(WorkOrder.event_id.in_(demo_event_ids)))
    db.execute(delete(MethaneEvent).where(MethaneEvent.run_phase.in_(["demo-event", "post-repair"])))
    db.commit()
    manager.reset()
    _state.update({"running": False, "stage": None, "event_id": None, "started_at": None})


def _write_baseline_history(db: Session, start: dt.datetime, duration_s: int) -> None:
    """Populate the pre-roll window the detector needs as a baseline, quietly,
    without going through the WebSocket (nothing here is newsworthy)."""
    sim = SensorSimulator()
    rows_sensor, rows_weather = [], []
    for tick in sim.generate(start, duration_s, release_profile=lambda t: 0.0, run_phase="baseline"):
        for r in tick.readings:
            rows_sensor.append(
                SensorReading(
                    ts=tick.ts,
                    sensor_id=r["sensor_id"],
                    facility_id=tick.facility_id,
                    ch4_ppm=r["ch4_ppm"],
                    pressure_barg=r["pressure_barg"],
                    flow_kg_h=r["flow_kg_h"],
                    equipment_state=r["equipment_state"],
                    run_phase="baseline",
                    quality=r["quality"],
                )
            )
        rows_weather.append(
            WeatherReading(
                ts=tick.ts,
                facility_id=tick.facility_id,
                wind_speed_ms=tick.weather["wind_speed_ms"],
                wind_dir_deg=tick.weather["wind_dir_deg"],
                temperature_c=tick.weather["temperature_c"],
                pressure_hpa=tick.weather["pressure_hpa"],
                stability_class=tick.weather["stability_class"],
                run_phase="baseline",
            )
        )
    db.bulk_save_objects(rows_sensor)
    db.bulk_save_objects(rows_weather)
    db.commit()


async def _replay_and_persist(
    db: Session,
    sim: SensorSimulator,
    start: dt.datetime,
    duration_s: int,
    run_phase: str,
    release_profile,
    pressure_profile,
    flow_profile,
    speed: float,
    live: bool,
) -> None:
    """Step through the simulator, persisting every tick and — when `live` —
    broadcasting it so the Live Monitoring canvas can animate in step."""
    step_s = 1
    for tick in sim.generate(
        start,
        duration_s,
        release_profile=release_profile,
        pressure_profile=pressure_profile,
        flow_profile=flow_profile,
        run_phase=run_phase,
        step_s=step_s,
    ):
        for r in tick.readings:
            db.add(
                SensorReading(
                    ts=tick.ts,
                    sensor_id=r["sensor_id"],
                    facility_id=tick.facility_id,
                    ch4_ppm=r["ch4_ppm"],
                    pressure_barg=r["pressure_barg"],
                    flow_kg_h=r["flow_kg_h"],
                    equipment_state=r["equipment_state"],
                    run_phase=run_phase,
                    quality=r["quality"],
                )
            )
        db.add(
            WeatherReading(
                ts=tick.ts,
                facility_id=tick.facility_id,
                wind_speed_ms=tick.weather["wind_speed_ms"],
                wind_dir_deg=tick.weather["wind_dir_deg"],
                temperature_c=tick.weather["temperature_c"],
                pressure_hpa=tick.weather["pressure_hpa"],
                stability_class=tick.weather["stability_class"],
                run_phase=run_phase,
            )
        )

        if live:
            await manager.broadcast(
                {
                    "type": "tick",
                    "ts": tick.ts.isoformat(),
                    "run_phase": run_phase,
                    "weather": tick.weather,
                    "sensors": [
                        {"tag": r["sensor_tag"], "ch4_ppm": r["ch4_ppm"]} for r in tick.readings
                    ],
                    "equipment_state": tick.equipment_states.get(layout.DEMO_SOURCE_TAG),
                    "pressure_barg": tick.readings[0]["pressure_barg"],
                    "flow_kg_h": tick.readings[0]["flow_kg_h"],
                }
            )
            await asyncio.sleep(step_s / speed)

    db.commit()


async def run_demo(speed: float = sc.DEFAULT_SPEED) -> dict:
    """The full judge-facing sequence. Idempotent: reset() first if re-running."""
    if _state["running"]:
        return {"status": "already_running", **_state}

    _state["running"] = True
    _state["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    db = SessionLocal()
    try:
        today = dt.datetime.now(dt.timezone.utc).date()
        t0 = sc.t0(today)
        pre_start = t0 - dt.timedelta(seconds=sc.PRE_ROLL_S)

        await _emit_stage("normal", "Normal operation", "Baseline methane, all sensors nominal")
        _write_baseline_history(db, pre_start, sc.PRE_ROLL_S)

        sim = SensorSimulator()

        await _emit_stage("pressure_anomaly", "Pressure anomaly", "C-03 discharge pressure begins to step down")
        await _replay_and_persist(
            db, sim, t0, sc.REPLAY_S, "demo-event",
            release_profile=lambda t: sc.release_profile(t),
            pressure_profile=lambda t: sc.pressure_profile(t),
            flow_profile=lambda t: sc.flow_profile(t),
            speed=speed, live=True,
        )

        await _emit_stage("s3_detect", "Methane detected at S3", "Nearest sensor sees elevated CH4")
        await _emit_stage("s4_detect", "Methane detected at S4", "Downwind sensor confirms the plume")
        await _emit_stage("event_confirmed", "Event confirmed", "Detection thresholds met and sustained")

        event = process_window(
            db, layout.FACILITY_ID, pre_start, t0 + dt.timedelta(seconds=sc.REPLAY_S),
            run_phase="demo-event",
        )
        if event is None:
            await _emit_stage("error", "Detection did not trigger", "Check simulator/detector tuning")
            _state["running"] = False
            return {"status": "no_event_detected"}

        _state["event_id"] = event.id
        await _emit_stage(
            "candidates", "Source candidates generated",
            "Nearby assets scored against the plume",
            {"event_id": event.id},
        )
        await _emit_stage(
            "attributed", f"{_leader_tag(db, event)} attributed",
            "Leading candidate identified", {"event_id": event.id},
        )
        await _emit_stage(
            "quantified", "Quantification completed",
            f"Peak {event.peak_emission_rate_kg_h:.1f} kg CH4/h, "
            f"{event.total_mass_kg:.2f} kg total mass (+/-{event.uncertainty_pct:.0f}%)",
            {"event_id": event.id},
        )
        await _emit_stage(
            "prioritised", "Priority calculated", f"{event.priority} priority",
            {"event_id": event.id},
        )

        await _emit_stage("investigated", "AI investigation running", "Gathering evidence")
        investigation = investigate(db, event.id)
        await _emit_stage(
            "investigated", "AI investigation completed",
            f"Probable source: {investigation.report.get('probable_source')}",
            {"event_id": event.id, "provider": investigation.provider},
        )
        await _emit_stage(
            "recommended", "Action recommended",
            investigation.report.get("recommended_inspection", ""),
            {"event_id": event.id},
        )

        _state["running"] = False
        return {"status": "ok", "event_id": event.id}
    finally:
        db.close()


def _leader_tag(db: Session, event: MethaneEvent) -> str:
    from .db.models import Equipment

    eq = db.get(Equipment, event.attributed_equipment_id) if event.attributed_equipment_id else None
    return eq.tag if eq else "source"


async def run_post_repair(event_id: str, speed: float = sc.DEFAULT_SPEED) -> dict:
    """Replay the same window with the leak fixed, then verify."""
    db = SessionLocal()
    try:
        event = db.get(MethaneEvent, event_id)
        if event is None:
            return {"status": "unknown_event"}

        today = dt.datetime.now(dt.timezone.utc).date()
        t0 = sc.t0(today) + dt.timedelta(hours=6)  # a later window, same physics
        pre_start = t0 - dt.timedelta(seconds=120)

        await _emit_stage("verifying", "Verification in progress", "Replaying sensor data with the seal repaired")

        sim = SensorSimulator()
        await _replay_and_persist(
            db, sim, pre_start, sc.POST_REPAIR_S + 120, "post-repair",
            release_profile=lambda t: sc.no_release(t),
            pressure_profile=lambda t: 0.0,
            flow_profile=lambda t: 0.0,
            speed=speed * 4, live=True,
        )

        lead_sensor_id = event.detected_by_sensor_id
        pre = load_readings(db, event.facility_id, event.started_at, event.ended_at or event.peak_at)
        pre = pre[pre["sensor_id"] == lead_sensor_id][["ts", "ch4_ppm"]]
        post = load_readings(db, event.facility_id, pre_start, pre_start + dt.timedelta(seconds=sc.POST_REPAIR_S + 120))
        post = post[post["sensor_id"] == lead_sensor_id][["ts", "ch4_ppm"]]

        resolution_time_s = (dt.datetime.now(dt.timezone.utc) - event.started_at).total_seconds()
        result = verify_repair(
            pre, post, event.baseline_ch4_ppm or 2.0, 0.12,
            event.total_mass_kg or 0.0, event.duration_s or 1.0,
            resolution_time_s, recurrence_factor=0.35,
        )

        db.add(
            RepairVerification(
                event_id=event.id,
                work_order_id=_find_work_order_id(db, event.id) or "",
                outcome=result.outcome,
                pre_mean_ppm=result.pre_mean_ppm,
                post_mean_ppm=result.post_mean_ppm,
                pre_peak_ppm=result.pre_peak_ppm,
                post_peak_ppm=result.post_peak_ppm,
                reduction_pct=result.reduction_pct,
                ch4_avoided_kg_day=result.ch4_avoided_kg_day,
                ch4_avoided_kg_year=result.ch4_avoided_kg_year,
                gas_value_retained_omr_year=result.gas_value_retained_omr_year,
                co2e_avoided_t_year=result.co2e_avoided_t_year,
                resolution_time_s=result.resolution_time_s,
                comparison_series={
                    "pre": [{"t": r.ts.isoformat(), "ppm": r.ch4_ppm} for r in pre.itertuples()],
                    "post": [{"t": r.ts.isoformat(), "ppm": r.ch4_ppm} for r in post.itertuples()],
                },
            )
        )
        if result.outcome == "REPAIR VERIFIED":
            event.status = "Closed"
        db.commit()

        await _emit_stage(
            "avoided" if result.outcome == "REPAIR VERIFIED" else "verifying",
            result.outcome,
            f"{result.reduction_pct:.0f}% reduction vs pre-repair baseline",
            {"event_id": event.id},
        )
        return {"status": "ok", "outcome": result.outcome}
    finally:
        db.close()


def _find_work_order_id(db: Session, event_id: str) -> str | None:
    wo = db.query(WorkOrder).filter(WorkOrder.event_id == event_id).first()
    return wo.id if wo else None
