"""Seed the demonstration dataset.

Everything written here is clearly labelled simulated. The historical events
give Analytics something real to aggregate and give the attribution engine a
genuine recurrence signal for C-03 — the "this has happened before" evidence is
read from these rows, not asserted by the UI.
"""

from __future__ import annotations

import datetime as dt
import random

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..ai.rag import embed
from ..sim import layout
from .models import (
    AIInvestigation,
    Equipment,
    EventEvidence,
    EventSourceCandidate,
    Facility,
    MaintenanceRecord,
    MethaneEvent,
    RepairVerification,
    Report,
    Sensor,
    SensorReading,
    WeatherReading,
    WorkOrder,
)
from .session import SessionLocal

TECHNICIANS = [
    "Salim Al-Balushi",
    "Fatma Al-Habsi",
    "Hamed Al-Rashdi",
    "Yusra Al-Kindi",
    "Nasser Al-Amri",
]

RNG = random.Random(20260914)


def _utc(y, m, d, hh=0, mm=0) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.timezone.utc)


def wipe(db: Session) -> None:
    """Full reset, in dependency order."""
    for model in (
        Report,
        RepairVerification,
        AIInvestigation,
        EventEvidence,
        EventSourceCandidate,
        WorkOrder,
        MethaneEvent,
        MaintenanceRecord,
        SensorReading,
        WeatherReading,
        Sensor,
        Equipment,
        Facility,
    ):
        db.execute(delete(model))
    db.commit()


def seed_assets(db: Session) -> None:
    db.add(Facility(**layout.FACILITY))
    for fid, name, name_ar, region, block, lat, lon in layout.OTHER_FACILITIES:
        db.add(
            Facility(
                id=fid, name=name, name_ar=name_ar, region=region,
                block=block, lat=lat, lon=lon, extent_m=300.0,
            )
        )

    for tag, name, typ, x, y, crit, prop, state in layout.EQUIPMENT:
        db.add(
            Equipment(
                id=layout.equipment_id(tag),
                facility_id=layout.FACILITY_ID,
                tag=tag,
                name=name,
                equipment_type=typ,
                x_m=x,
                y_m=y,
                criticality=crit,
                leak_propensity=prop,
                operating_state=state,
            )
        )

    for tag, x, y, base, noise in layout.SENSORS:
        db.add(
            Sensor(
                id=layout.sensor_id(tag),
                facility_id=layout.FACILITY_ID,
                tag=tag,
                x_m=x,
                y_m=y,
                baseline_ppm=base,
                noise_ppm=noise,
            )
        )
    db.commit()


def seed_maintenance(db: Session, today: dt.date) -> None:
    now = dt.datetime.combine(today, dt.time(6, 0), tzinfo=dt.timezone.utc)

    records = [
        # The overdue C-03 seal inspection is the maintenance evidence the
        # investigation surfaces. It is a real row, not a hardcoded string.
        ("C-03", "Dry gas seal inspection", "Mechanical", now - dt.timedelta(days=210),
         now - dt.timedelta(days=24),
         "Seal gas differential trending down at last inspection; re-inspect within 180 days.",
         True),
        ("C-03", "Compressor vibration survey", "Rotating Equipment",
         now - dt.timedelta(days=38), now + dt.timedelta(days=142),
         "Vibration within limits. Minor 1x increase on the drive end.", False),
        ("C-03", "Seal gas filter replacement", "Mechanical",
         now - dt.timedelta(days=96), now + dt.timedelta(days=84),
         "Filter elements replaced; differential restored.", False),
        ("C-02", "Dry gas seal inspection", "Mechanical",
         now - dt.timedelta(days=61), now + dt.timedelta(days=119),
         "Seals within specification.", False),
        ("V-14", "Valve stem packing check", "Instrumentation",
         now - dt.timedelta(days=45), now + dt.timedelta(days=135),
         "Packing adjusted, no measurable leakage.", False),
        ("T-02", "Tank vent PRV certification", "Mechanical",
         now - dt.timedelta(days=150), now + dt.timedelta(days=215),
         "PRV lift pressure verified on the bench.", False),
        ("SEP-01", "Level control loop calibration", "Instrumentation",
         now - dt.timedelta(days=20), now + dt.timedelta(days=160),
         "Loop calibrated, transmitter zeroed.", False),
        ("KOD-01", "Drain line integrity inspection", "Mechanical",
         now - dt.timedelta(days=75), now + dt.timedelta(days=105),
         "No wall loss detected.", False),
        ("PIG-01", "Pig launcher door seal replacement", "Mechanical",
         now - dt.timedelta(days=120), now + dt.timedelta(days=60),
         "Door seal replaced after minor weeping.", False),
    ]

    for tag, task, discipline, performed, due, notes, overdue in records:
        text_blob = f"{tag} {task} {discipline} {notes}"
        db.add(
            MaintenanceRecord(
                equipment_id=layout.equipment_id(tag),
                task=task,
                discipline=discipline,
                performed_at=performed,
                due_at=due,
                notes=notes,
                overdue=overdue,
                embedding=embed(text_blob),
            )
        )
    db.commit()


# Historical events. Two on C-03 so recurrence is a measured fact; the rest give
# Analytics a portfolio to compare. (tag, days_ago, hour, rate kg/h, duration s,
# severity, status, facility)
HISTORY = [
    ("C-03", 128, 14, 11.4, 260, "High", "Closed", layout.FACILITY_ID),
    ("C-03", 61, 9, 7.8, 180, "High", "Closed", layout.FACILITY_ID),
    ("V-14", 96, 11, 3.1, 420, "Medium", "Closed", layout.FACILITY_ID),
    ("SEP-01", 82, 7, 2.1, 900, "Normal", "Closed", layout.FACILITY_ID),
    ("T-02", 74, 16, 4.6, 340, "Medium", "Closed", layout.FACILITY_ID),
    ("C-02", 47, 13, 9.1, 240, "High", "Closed", layout.FACILITY_ID),
    ("KOD-01", 35, 5, 1.8, 600, "Normal", "Closed", layout.FACILITY_ID),
    ("PIG-01", 22, 10, 5.2, 150, "Medium", "Closed", layout.FACILITY_ID),
    (None, 118, 8, 6.3, 300, "Medium", "Closed", "FAC-NIMR"),
    (None, 90, 15, 12.7, 220, "High", "Closed", "FAC-NIMR"),
    (None, 57, 12, 3.9, 480, "Medium", "Closed", "FAC-YIBAL"),
    (None, 29, 6, 8.4, 270, "High", "Closed", "FAC-MARMUL"),
]


def seed_history(db: Session, today: dt.date) -> None:
    from ..engines.financial import environmental_impact, financial_impact
    from ..engines.priority import score_priority

    base = dt.datetime.combine(today, dt.time(0, 0), tzinfo=dt.timezone.utc)
    counter = 0

    for tag, days_ago, hour, rate, duration, severity, status, facility_id in HISTORY:
        counter += 1
        started = base - dt.timedelta(days=days_ago) + dt.timedelta(hours=hour)
        year = started.year
        event_id = f"EVT-{year}-{counter:05d}"

        # Mass is the rate held over the event duration — a rate and a mass, kept
        # distinct, exactly as the live pipeline reports them.
        mass = rate * duration / 3600.0
        fin = financial_impact(mass, duration, rate, 0.35)
        env = environmental_impact(mass, duration, 0.35)
        equipment_id = layout.equipment_id(tag) if tag else None
        criticality = next(
            (e[5] for e in layout.EQUIPMENT if e[0] == tag), 0.5
        )
        prio = score_priority(rate, mass, duration, fin.annual_loss_omr, 0,
                              criticality, 0.9, 0.85)

        db.add(
            MethaneEvent(
                id=event_id,
                facility_id=facility_id,
                attributed_equipment_id=equipment_id,
                detected_by_sensor_id=layout.sensor_id("S3") if equipment_id else None,
                started_at=started,
                peak_at=started + dt.timedelta(seconds=duration * 0.4),
                ended_at=started + dt.timedelta(seconds=duration),
                duration_s=float(duration),
                peak_ch4_ppm=round(2.0 + rate * 3.6, 2),
                baseline_ch4_ppm=2.0,
                peak_zscore=round(rate * 28.0, 1),
                peak_emission_rate_kg_h=rate,
                total_mass_kg=round(mass, 4),
                uncertainty_pct=53.4,
                quantification_assumptions={
                    "model": "Gaussian plume inversion (Briggs open-country sigma curves)",
                    "validation_status": "Screening estimate — NOT a validated measurement",
                    "note": "Historical demonstration record",
                },
                detection_confidence=0.9,
                attribution_confidence=0.85,
                data_quality=0.98,
                priority=prio.priority,
                priority_score=prio.score,
                priority_factors=prio.factors,
                financial=fin.as_dict(),
                environmental=env.as_dict(),
                severity=severity,
                status=status,
                run_phase="historical",
            )
        )
        # No relationship() links these tables, so the unit of work may not order
        # the INSERTs by foreign key. Postgres enforces FKs; flush parents first.
        db.flush()

        if equipment_id:
            wo_id = f"WO-{year}-{counter:04d}"
            opened = started + dt.timedelta(minutes=12)
            closed = opened + dt.timedelta(hours=RNG.uniform(4, 30))
            db.add(
                WorkOrder(
                    id=wo_id,
                    event_id=event_id,
                    facility_id=facility_id,
                    equipment_id=equipment_id,
                    title=f"Investigate methane release at {tag}",
                    description="Historical demonstration work order.",
                    discipline="Mechanical",
                    priority=prio.priority,
                    status="Closed",
                    assignee=RNG.choice(TECHNICIANS),
                    created_by="EMISSIQ (drafted)",
                    ai_drafted=True,
                    created_at=opened,
                    updated_at=closed,
                    repair_completed_at=closed - dt.timedelta(hours=1),
                    closed_at=closed,
                    audit_trail=[
                        {"at": opened.isoformat(), "actor": "EMISSIQ", "action": "Work order drafted from event"},
                        {"at": closed.isoformat(), "actor": "Operations", "action": "Closed after verification"},
                    ],
                )
            )
            db.flush()
            db.add(
                RepairVerification(
                    event_id=event_id,
                    work_order_id=wo_id,
                    verified_at=closed,
                    outcome="REPAIR VERIFIED",
                    pre_mean_ppm=round(2.0 + rate * 1.4, 2),
                    post_mean_ppm=2.04,
                    pre_peak_ppm=round(2.0 + rate * 3.6, 2),
                    post_peak_ppm=2.31,
                    reduction_pct=97.4,
                    ch4_avoided_kg_day=round(mass / (duration / 3600.0) * 24 * 0.35, 2),
                    ch4_avoided_kg_year=round(mass / (duration / 3600.0) * 24 * 365 * 0.35, 1),
                    gas_value_retained_omr_year=fin.annual_loss_omr,
                    co2e_avoided_t_year=env.co2e_t_year_if_recurring_100yr,
                    resolution_time_s=(closed - opened).total_seconds(),
                )
            )
    db.commit()


def seed_all(today: dt.date | None = None) -> None:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    db = SessionLocal()
    try:
        wipe(db)
        seed_assets(db)
        seed_maintenance(db, today)
        seed_history(db, today)
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
    print("seeded demonstration dataset (all rows flagged simulated)")
