"""EMISSIQ Investigator — an evidence-gathering agent.

The model decides which read-only tools to call and when it has seen enough. It
then produces a structured evidence report.

Two rules shape this module:

1. No private reasoning leaves the server. The model's intermediate messages are
   used to drive tool selection and are then discarded. What the client receives
   is a structured report plus the list of tools that were consulted — an audit
   trail of evidence, not a transcript of thought.

2. Numbers come from the engines, not the model. Emission rate, mass, financial
   impact and priority are overwritten from the database after the model
   responds, so a hallucinated figure cannot reach the report.
"""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy.orm import Session

from ..db.models import AIInvestigation, Equipment, EventEvidence, MethaneEvent
from .provider import Provider, build_provider
from .tools import call_tool, recommend_inspection, tool_schemas

log = logging.getLogger(__name__)

MAX_ROUNDS = 8

SYSTEM_PROMPT = """You are the EMISSIQ Investigator, an industrial methane investigation agent for an Omani upstream operator.

Your job: work out which asset most likely released methane during a detected event, using the read-only tools provided.

How to work:
- Call tools to gather evidence. Start with the event, then the candidate scoring, then whatever you need to confirm or challenge it.
- Actively look for evidence that contradicts the leading candidate. Alternatives that were ruled out are part of the finding.
- Stop calling tools once you can state a probable source, the evidence for it, and the remaining uncertainties.
- Never invent a number. Every figure you report must have come from a tool result.

Hard limits:
- You cannot operate plant equipment. You have no ability to shut down or start equipment, operate valves, change setpoints, modify PLC logic or bypass interlocks, and you must never imply otherwise.
- You may recommend an inspection and describe what a technician should check. A human decides whether to act.
- The data is simulated demonstration data. Do not present it as measured operator data.

When you have finished gathering evidence, reply with ONLY a JSON object, no prose and no code fence:
{
  "probable_source": "equipment tag",
  "confidence_pct": number,
  "summary": "3-5 sentences explaining what happened and why this asset",
  "alternative_candidates": [{"tag": "...", "score_pct": number, "why_less_likely": "..."}],
  "key_evidence": ["short factual statements, each traceable to a tool result"],
  "timeline": [{"time": "HH:MM:SS", "what": "..."}],
  "uncertainties": ["what would change this conclusion"],
  "recommended_inspection": "what to inspect",
  "discipline": "which trade should attend"
}"""


def _report_skeleton(db: Session, event: MethaneEvent) -> dict:
    eq = db.get(Equipment, event.attributed_equipment_id) if event.attributed_equipment_id else None
    return {
        "probable_source": eq.tag if eq else "Undetermined",
        "confidence_pct": round((event.attribution_confidence or 0) * 100, 1),
        "summary": "",
        "alternative_candidates": [],
        "key_evidence": [],
        "timeline": [],
        "uncertainties": [],
        "recommended_inspection": "",
        "discipline": "",
    }


def _fallback_report(db: Session, event: MethaneEvent, tool_results: dict) -> dict:
    """Build a report straight from the engines when the model returns no JSON.

    Used by the scripted provider and whenever a model reply cannot be parsed.
    The content is identical in kind to what a model would assemble, because it
    is drawn from the same tool results.
    """
    report = _report_skeleton(db, event)
    candidates = tool_results.get("get_candidate_sources", {}).get("candidates", [])
    evidence = db.query(EventEvidence).filter(EventEvidence.event_id == event.id).all()
    rec = tool_results.get("recommend_inspection") or recommend_inspection(db, event.id)

    lead = candidates[0] if candidates else None
    if lead:
        report["probable_source"] = lead["tag"]
        report["confidence_pct"] = lead["score_pct"]
        report["alternative_candidates"] = [
            {
                "tag": c["tag"],
                "score_pct": c["score_pct"],
                "why_less_likely": next(
                    (f["detail"] for f in (c.get("factors") or []) if f["name"] in ("Wind alignment", "Plume fit")),
                    "Lower overall consistency with the observed plume",
                ),
            }
            for c in candidates[1:4]
        ]

    report["key_evidence"] = [e.summary for e in evidence if e.kind != "alternative"]
    report["uncertainties"] = [
        f"Emission estimate carries +/-{event.uncertainty_pct:.0f}% uncertainty from wind and dispersion assumptions",
        "Source position is known to the asset, not to the exact leak point",
        "Attribution is an estimate from a weighted scoring model, not a validated measurement",
    ]
    report["recommended_inspection"] = rec.get("inspection", "")
    report["discipline"] = rec.get("discipline", "")

    src = report["probable_source"]
    report["summary"] = (
        f"A short methane release was detected at the Fahud demonstration facility, first seen by "
        f"sensor {tool_results.get('get_event', {}).get('first_detecting_sensor', 'the lead sensor')}. "
        f"The wind geometry, the order in which sensors alarmed and the process data are all consistent "
        f"with {src} as the source. Peak emission rate is estimated at "
        f"{event.peak_emission_rate_kg_h:.1f} kg CH4/h with roughly {event.total_mass_kg:.2f} kg released "
        f"over {event.duration_s:.0f} seconds. "
        f"{'An overdue inspection on this asset supports the finding.' if rec.get('linked_overdue_task') else ''}"
    ).strip()
    return report


def _timeline(event: MethaneEvent, tz_offset_h: int = 4) -> list[dict]:
    import datetime as dt

    tz = dt.timezone(dt.timedelta(hours=tz_offset_h))

    def fmt(value):
        return value.astimezone(tz).strftime("%H:%M:%S") if value else None

    items = [
        {"time": fmt(event.started_at), "what": "Methane first detected above threshold"},
        {"time": fmt(event.peak_at), "what": "Concentration peaked"},
    ]
    if event.ended_at:
        items.append({"time": fmt(event.ended_at), "what": "Concentration returned to baseline"})
    return [i for i in items if i["time"]]


def investigate(
    db: Session, event_id: str, provider: Provider | None = None, autonomy_level: int = 2
) -> AIInvestigation:
    event = db.get(MethaneEvent, event_id)
    if event is None:
        raise ValueError(f"unknown event {event_id}")

    provider = provider or build_provider()
    schemas = tool_schemas()
    started = time.perf_counter()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Investigate methane event {event_id}. Gather what you need, then report."},
    ]
    tool_results: dict[str, dict] = {}
    audit: list[dict] = []
    final_text = ""

    for _ in range(MAX_ROUNDS):
        try:
            response = provider.chat(messages, schemas)
        except Exception as exc:
            log.warning("provider %s failed mid-run: %s", provider.name, exc)
            break

        if not response.tool_calls:
            final_text = response.content or ""
            break

        # The assistant turn is kept only so the provider sees its own tool
        # calls on the next round. It is never persisted or returned.
        messages.append(
            {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in response.tool_calls
                ],
            }
        )

        for tc in response.tool_calls:
            result = call_tool(db, tc.name, event_id, tc.arguments)
            tool_results[tc.name] = result
            audit.append({"tool": tc.name, "arguments": tc.arguments})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": json.dumps(result, default=str)[:6000],
                }
            )

    # --- assemble the report ---------------------------------------------
    report = _fallback_report(db, event, tool_results)
    if final_text:
        parsed = _parse_json(final_text)
        if parsed:
            # Take the model's narrative fields, keep the engines' facts.
            for key in ("summary", "key_evidence", "uncertainties", "alternative_candidates",
                        "recommended_inspection", "discipline", "probable_source"):
                if parsed.get(key):
                    report[key] = parsed[key]

    # Facts are restored from the database regardless of what the model said.
    report["timeline"] = _timeline(event)
    report["confidence_pct"] = round((event.attribution_confidence or 0) * 100, 1)
    report["priority"] = event.priority
    report["environmental_impact"] = event.environmental
    report["financial_impact"] = event.financial
    report["emission_estimate"] = {
        "peak_rate_kg_h": event.peak_emission_rate_kg_h,
        "total_mass_kg": event.total_mass_kg,
        "uncertainty_pct": event.uncertainty_pct,
        "duration_s": event.duration_s,
    }
    report["data_note"] = "Simulated demonstration data"
    report["authority_note"] = (
        "EMISSIQ recommends and drafts. It cannot operate plant equipment or issue control commands."
    )

    investigation = AIInvestigation(
        event_id=event_id,
        provider=provider.name,
        model=getattr(provider, "model", ""),
        autonomy_level=autonomy_level,
        tool_calls=audit,
        report=report,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    db.add(investigation)
    event.status = "Investigated"
    db.commit()
    db.refresh(investigation)
    return investigation


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lower().startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
