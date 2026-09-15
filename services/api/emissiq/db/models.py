"""EMISSIQ data model.

Every row carries `is_simulated` and `data_origin`. The UI reads those flags to
decide whether to show the SIMULATED DEMO markings, so nothing in the frontend
has to assume that the data is fake — it is told.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

EMBED_DIM = 256

try:  # pgvector is present on the docker image and on Supabase
    from pgvector.sqlalchemy import Vector

    # SQLite has no vector type. The same schema then stores embeddings as JSON
    # and rag.py falls back to in-process cosine similarity.
    EmbeddingType = Vector(EMBED_DIM).with_variant(JSON, "sqlite")
except ImportError:  # pragma: no cover - portability fallback
    EmbeddingType = JSON


class UtcDateTime(TypeDecorator):
    """Timezone-aware datetimes that survive SQLite.

    Postgres stores the offset; SQLite silently drops it and hands back naive
    values, which then blow up every comparison in the pipeline. Normalising to
    UTC on the way in and re-attaching UTC on the way out keeps both backends
    behaving identically.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class SimulatedMixin:
    """Provenance flags. Simulated data must never be presentable as operator data."""

    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_origin: Mapped[str] = mapped_column(String(64), default="simulated-demo")


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class Facility(Base, SimulatedMixin):
    __tablename__ = "facilities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    name_ar: Mapped[str] = mapped_column(String(128), default="")
    region: Mapped[str] = mapped_column(String(64), default="")
    block: Mapped[str] = mapped_column(String(32), default="")
    lat: Mapped[float] = mapped_column(Float, default=0.0)
    lon: Mapped[float] = mapped_column(Float, default=0.0)
    # Schematic extent in local plant metres, used by the Live Monitoring canvas.
    extent_m: Mapped[float] = mapped_column(Float, default=400.0)

    equipment: Mapped[list["Equipment"]] = relationship(back_populates="facility")
    sensors: Mapped[list["Sensor"]] = relationship(back_populates="facility")


class Equipment(Base, SimulatedMixin):
    __tablename__ = "equipment"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"))
    tag: Mapped[str] = mapped_column(String(32))  # e.g. "C-03"
    name: Mapped[str] = mapped_column(String(128))
    equipment_type: Mapped[str] = mapped_column(String(48))  # compressor, valve, tank_vent...
    # Local plant frame in metres; x east, y north. Enough for bearing + distance.
    x_m: Mapped[float] = mapped_column(Float, default=0.0)
    y_m: Mapped[float] = mapped_column(Float, default=0.0)
    criticality: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    # Prior probability that this asset type is a methane source at all.
    leak_propensity: Mapped[float] = mapped_column(Float, default=0.3)
    operating_state: Mapped[str] = mapped_column(String(32), default="running")

    facility: Mapped[Facility] = relationship(back_populates="equipment")


class Sensor(Base, SimulatedMixin):
    __tablename__ = "sensors"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"))
    tag: Mapped[str] = mapped_column(String(32))  # e.g. "S3"
    sensor_type: Mapped[str] = mapped_column(String(32), default="ch4_point")
    x_m: Mapped[float] = mapped_column(Float, default=0.0)
    y_m: Mapped[float] = mapped_column(Float, default=0.0)
    height_m: Mapped[float] = mapped_column(Float, default=2.0)
    baseline_ppm: Mapped[float] = mapped_column(Float, default=2.0)
    noise_ppm: Mapped[float] = mapped_column(Float, default=0.12)
    status: Mapped[str] = mapped_column(String(24), default="online")

    facility: Mapped[Facility] = relationship(back_populates="sensors")


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class SensorReading(Base, SimulatedMixin):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(UtcDateTime, index=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensors.id"), index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id"), nullable=True
    )
    ch4_ppm: Mapped[float] = mapped_column(Float)
    # Process context sampled alongside the CH4 point reading.
    pressure_barg: Mapped[float | None] = mapped_column(Float, nullable=True)
    flow_kg_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    equipment_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # "baseline" | "demo-event" | "post-repair" — lets the demo reset cleanly.
    run_phase: Mapped[str] = mapped_column(String(24), default="baseline", index=True)
    quality: Mapped[float] = mapped_column(Float, default=1.0)


class WeatherReading(Base, SimulatedMixin):
    __tablename__ = "weather_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(UtcDateTime, index=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    wind_speed_ms: Mapped[float] = mapped_column(Float)
    # Meteorological convention: direction the wind is coming FROM, degrees true.
    wind_dir_deg: Mapped[float] = mapped_column(Float)
    temperature_c: Mapped[float] = mapped_column(Float, default=32.0)
    pressure_hpa: Mapped[float] = mapped_column(Float, default=1006.0)
    stability_class: Mapped[str] = mapped_column(String(2), default="D")
    run_phase: Mapped[str] = mapped_column(String(24), default="baseline", index=True)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class MethaneEvent(Base, SimulatedMixin):
    __tablename__ = "methane_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # EVT-2026-00142
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    detected_by_sensor_id: Mapped[str | None] = mapped_column(
        ForeignKey("sensors.id"), nullable=True
    )
    attributed_equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id"), nullable=True
    )

    started_at: Mapped[dt.datetime] = mapped_column(UtcDateTime)
    peak_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    ended_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)

    peak_ch4_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_ch4_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_zscore: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Quantification — rate and mass are distinct quantities and never merged.
    peak_emission_rate_kg_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_mass_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantification_assumptions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    detection_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    attribution_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_quality: Mapped[float | None] = mapped_column(Float, nullable=True)

    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority_factors: Mapped[list | None] = mapped_column(JSON, nullable=True)

    financial: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    environmental: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    severity: Mapped[str] = mapped_column(String(16), default="Normal")
    status: Mapped[str] = mapped_column(String(24), default="New")
    run_phase: Mapped[str] = mapped_column(String(24), default="historical", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=_now)

    candidates: Mapped[list["EventSourceCandidate"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["EventEvidence"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventSourceCandidate(Base, SimulatedMixin):
    __tablename__ = "event_source_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("methane_events.id"), index=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float)  # 0..1, normalised weighted score
    # Per-factor contributions so the UI can show the arithmetic, not a verdict.
    factors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    bearing_alignment_deg: Mapped[float | None] = mapped_column(Float, nullable=True)

    event: Mapped[MethaneEvent] = relationship(back_populates="candidates")


class EventEvidence(Base, SimulatedMixin):
    __tablename__ = "event_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("methane_events.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # wind | sequence | process | history | maintenance
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    supports_equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id"), nullable=True
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    embedding = mapped_column(EmbeddingType, nullable=True)

    event: Mapped[MethaneEvent] = relationship(back_populates="evidence")


class AIInvestigation(Base, SimulatedMixin):
    __tablename__ = "ai_investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("methane_events.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64), default="")
    autonomy_level: Mapped[int] = mapped_column(Integer, default=2)
    # Which read-only tools the agent chose to call, in order. This is an audit
    # trail of evidence gathering, not chain-of-thought.
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    report: Mapped[dict] = mapped_column(JSON)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=_now)


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class MaintenanceRecord(Base, SimulatedMixin):
    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey("equipment.id"), index=True)
    performed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    due_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    task: Mapped[str] = mapped_column(String(128))
    discipline: Mapped[str] = mapped_column(String(48), default="Mechanical")
    notes: Mapped[str] = mapped_column(Text, default="")
    overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding = mapped_column(EmbeddingType, nullable=True)


class WorkOrder(Base, SimulatedMixin):
    __tablename__ = "work_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # WO-2026-0142
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("methane_events.id"), nullable=True, index=True
    )
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"))
    equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(192))
    description: Mapped[str] = mapped_column(Text, default="")
    discipline: Mapped[str] = mapped_column(String(48), default="Mechanical")
    priority: Mapped[str] = mapped_column(String(16), default="Medium")
    # Open -> Assigned -> In Progress -> Repair Completed -> Verification -> Closed
    status: Mapped[str] = mapped_column(String(24), default="Open")
    assignee: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_by: Mapped[str] = mapped_column(String(96), default="EMISSIQ (drafted)")
    # True when the agent drafted it; a human still had to press the button.
    ai_drafted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=_now)
    repair_completed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    closed_at: Mapped[dt.datetime | None] = mapped_column(UtcDateTime, nullable=True)
    audit_trail: Mapped[list | None] = mapped_column(JSON, nullable=True)


class RepairVerification(Base, SimulatedMixin):
    __tablename__ = "repair_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("methane_events.id"), index=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.id"))
    verified_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=_now)
    outcome: Mapped[str] = mapped_column(String(32))  # REPAIR VERIFIED | EMISSION STILL DETECTED
    pre_mean_ppm: Mapped[float] = mapped_column(Float)
    post_mean_ppm: Mapped[float] = mapped_column(Float)
    pre_peak_ppm: Mapped[float] = mapped_column(Float)
    post_peak_ppm: Mapped[float] = mapped_column(Float)
    reduction_pct: Mapped[float] = mapped_column(Float)
    ch4_avoided_kg_day: Mapped[float] = mapped_column(Float, default=0.0)
    ch4_avoided_kg_year: Mapped[float] = mapped_column(Float, default=0.0)
    gas_value_retained_omr_year: Mapped[float] = mapped_column(Float, default=0.0)
    co2e_avoided_t_year: Mapped[float] = mapped_column(Float, default=0.0)
    resolution_time_s: Mapped[float] = mapped_column(Float, default=0.0)
    comparison_series: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Report(Base, SimulatedMixin):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # RPT-EVT-...-1
    event_id: Mapped[str] = mapped_column(ForeignKey("methane_events.id"), index=True)
    generated_at: Mapped[dt.datetime] = mapped_column(UtcDateTime, default=_now)
    generated_by: Mapped[str] = mapped_column(String(96), default="EMISSIQ")
    # Immutable snapshot: the report must not change when the event does.
    snapshot: Mapped[dict] = mapped_column(JSON)
