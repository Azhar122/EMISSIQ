"""Event copilot — grounded question answering inside the investigation screen.

The copilot answers from tool results and stored evidence for ONE event. It has
no general plant knowledge and is told to decline anything it cannot ground, so
it cannot become a source of invented operational advice.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import AIInvestigation, MethaneEvent
from .provider import Provider, ScriptedProvider, build_provider
from .rag import search_evidence, search_maintenance
from .tools import (
    get_candidate_sources,
    get_event,
    get_financial_impact,
    get_maintenance_history,
    get_previous_events,
    get_priority_breakdown,
    get_sensor_window,
    get_weather_window,
    recommend_inspection,
)

SUGGESTED_QUESTIONS = [
    "Why is Compressor C-03 the probable source?",
    "What happened immediately before the methane event?",
    "Has this equipment produced similar events before?",
    "What should the technician inspect first?",
    "How was the methane quantity estimated?",
    "Why is this event ranked the way it is?",
    "What is the projected financial impact?",
]

SYSTEM_PROMPT = """You are the EMISSIQ copilot inside an event investigation screen.

Answer ONLY from the CONTEXT provided below. It is the complete record for this event.

Rules:
- If the context does not contain the answer, say so plainly and name what data would be needed. Do not guess.
- Quote the actual figures from the context. Never round a number into a different one or invent one.
- Always distinguish emission RATE (kg CH4/hour) from total released MASS (kg CH4).
- Call projections projections. Daily and annual figures assume recurrence; they are not measured.
- Attribution is an estimate from a scoring model, not a validated measurement. Say so when attribution is the subject.
- You cannot operate equipment. If asked to shut something down, isolate, or change a setpoint, explain that EMISSIQ only recommends and drafts work orders, and that a human authorises any plant action.
- Two to five sentences. Plain engineering English, no preamble."""


def build_context(db: Session, event_id: str, question: str) -> dict:
    """Everything the copilot is allowed to see, assembled deterministically."""
    investigation = db.scalars(
        select(AIInvestigation)
        .where(AIInvestigation.event_id == event_id)
        .order_by(AIInvestigation.created_at.desc())
    ).first()

    return {
        "event": get_event(db, event_id),
        "sensors": get_sensor_window(db, event_id),
        "weather": get_weather_window(db, event_id),
        "candidates": get_candidate_sources(db, event_id),
        "priority": get_priority_breakdown(db, event_id),
        "impact": get_financial_impact(db, event_id),
        "maintenance": get_maintenance_history(db, event_id),
        "previous_events": get_previous_events(db, event_id),
        "recommended_inspection": recommend_inspection(db, event_id),
        # Retrieval narrows a large evidence set to what this question is about.
        "relevant_evidence": search_evidence(db, question, event_id, k=6),
        "relevant_maintenance": search_maintenance(db, question, k=3),
        "ai_investigation": investigation.report if investigation else None,
    }


def _scripted_answer(context: dict, question: str) -> str:
    """Deterministic answers for the suggested questions, used when no model is
    reachable. Every figure is read out of the same context a model would see."""
    q = question.lower()
    ev = context["event"]
    cands = context["candidates"]["candidates"]
    lead = cands[0] if cands else None

    if "probable source" in q or "why is" in q and lead and lead["tag"].lower() in q:
        top_factors = sorted(
            (lead.get("factors") or []),
            key=lambda f: f.get("contribution") or 0,
            reverse=True,
        )[:3]
        reasons = "; ".join(f["detail"] for f in top_factors)
        runner = cands[1] if len(cands) > 1 else None
        return (
            f"{lead['tag']} scores {lead['score_pct']}% against the observed plume, versus "
            f"{runner['score_pct']}% for the next candidate ({runner['tag']}). "
            f"The strongest factors are: {reasons}. "
            "This is an estimated attribution from a weighted scoring model, not a validated measurement."
        )

    if "before" in q:
        proc = [e for e in context["relevant_evidence"] if e["kind"] == "process"]
        detail = proc[0]["summary"] if proc else "no process anomaly was recorded"
        return (
            f"Before methane was detected, {detail}. The first CH4 rise was seen at "
            f"{ev['first_detecting_sensor']} at {ev['started_at']}, so the process signal led the "
            "gas detection rather than following it."
        )

    if "similar" in q or "before" in q or "previous" in q:
        prev = context["previous_events"]
        if prev["count"]:
            items = ", ".join(
                f"{e['event_id']} ({e['peak_emission_rate_kg_h']} kg/h)" for e in prev["events"][:3]
            )
            return (
                f"Yes — {prev['count']} previous event(s) are attributed to {prev['equipment_tag']}: {items}. "
                "That recurrence is one of the factors raising this event's priority."
            )
        return f"No previous methane events are attributed to {prev['equipment_tag']} in the stored record."

    if "inspect" in q or "technician" in q:
        rec = context["recommended_inspection"]
        steps = "; ".join(rec.get("steps", [])[:3])
        overdue = rec.get("linked_overdue_task")
        return (
            f"Recommended: {rec['inspection']} ({rec['discipline']}). First checks: {steps}. "
            + (f"Note that {overdue} on this asset is already overdue. " if overdue else "")
            + "EMISSIQ recommends only; the work is authorised and carried out by people."
        )

    if "quantit" in q or "estimated" in q or "quantif" in q:
        a = ev["quantification_assumptions"] or {}
        w = a.get("plume_working", {})
        return (
            f"A Gaussian plume inversion was used: the excess concentration at "
            f"{ev['first_detecting_sensor']} ({w.get('excess_ppm')} ppm above baseline) was combined with "
            f"wind speed {w.get('wind_speed_ms')} m/s and Briggs dispersion coefficients "
            f"(sigma_y {w.get('sigma_y_m')} m, sigma_z {w.get('sigma_z_m')} m at "
            f"{w.get('downwind_m')} m downwind) to solve for source strength. That gives a peak rate of "
            f"{ev['peak_emission_rate_kg_h']} kg CH4/h; integrating the profile over the event gives "
            f"{ev['total_mass_kg']} kg CH4 released. Uncertainty is +/-{ev['uncertainty_pct']}%."
        )

    if "rank" in q or "priority" in q:
        p = context["priority"]
        top = sorted(p["factors"], key=lambda f: f["contribution"], reverse=True)[:3]
        reasons = "; ".join(f"{f['name']} ({f['detail']})" for f in top)
        return (
            f"It is ranked {p['priority']} with a score of {p['score']}. The largest contributions are: "
            f"{reasons}. Priority is computed deterministically from these factors, not assigned by a model."
        )

    if "financial" in q or "cost" in q or "value" in q:
        f = context["impact"]["financial"]
        return (
            f"This event released gas worth {f['gas_value_lost_omr']} {f['currency']} at "
            f"{f['assumptions']['gas_price']}. If it recurs at the observed duty cycle, that projects to "
            f"{f['daily_loss_omr']} {f['currency']}/day and {f['annual_loss_omr']} {f['currency']}/year. "
            "The daily and annual figures are projections, not measured losses."
        )

    return (
        "I can only answer from this event's record. I have the detection timeline, sensor and weather "
        "data, candidate scoring, quantification, priority breakdown, maintenance history and financial "
        "estimate — ask about any of those."
    )


def ask(db: Session, event_id: str, question: str, provider: Provider | None = None) -> dict:
    if db.get(MethaneEvent, event_id) is None:
        raise ValueError(f"unknown event {event_id}")

    context = build_context(db, event_id, question)
    provider = provider or build_provider()

    if isinstance(provider, ScriptedProvider):
        return {
            "answer": _scripted_answer(context, question),
            "provider": "scripted",
            "grounded_in": sorted(context.keys()),
        }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"CONTEXT:\n{json.dumps(context, default=str)[:24000]}\n\nQUESTION: {question}",
        },
    ]
    try:
        response = provider.chat(messages)
        answer = (response.content or "").strip()
    except Exception:
        answer = ""

    if not answer:
        # A dead provider must not produce an empty chat bubble.
        return {
            "answer": _scripted_answer(context, question),
            "provider": "scripted (fallback)",
            "grounded_in": sorted(context.keys()),
        }

    return {"answer": answer, "provider": provider.name, "grounded_in": sorted(context.keys())}
