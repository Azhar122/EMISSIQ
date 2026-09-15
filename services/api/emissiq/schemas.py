"""Pydantic request/response shapes for the API layer.

Kept separate from the ORM models so the wire format can evolve without
touching persistence, and so response shaping (e.g. rounding, renaming) lives
in one obvious place.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class WorkOrderCreate(BaseModel):
    event_id: str | None = None
    facility_id: str
    equipment_id: str | None = None
    title: str
    description: str = ""
    discipline: str = "Mechanical"
    priority: str = "Medium"
    assignee: str | None = None
    ai_drafted: bool = False


class WorkOrderStatusUpdate(BaseModel):
    status: str
    assignee: str | None = None
    note: str | None = None


class CopilotQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class DemoRunRequest(BaseModel):
    speed: float = 5.0
