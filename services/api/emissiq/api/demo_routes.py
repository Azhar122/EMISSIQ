from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import demo as demo_module
from ..schemas import DemoRunRequest
from .deps import get_db

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/state")
def get_state():
    return demo_module.state()


@router.post("/reset")
def reset(db: Session = Depends(get_db)):
    demo_module.reset_demo_data(db)
    return {"status": "reset"}


@router.post("/run")
async def run(body: DemoRunRequest = DemoRunRequest()):
    # Fire-and-forget: progress streams over the WebSocket, this call returns
    # immediately so the UI can start showing stage 1 right away.
    asyncio.create_task(demo_module.run_demo(speed=body.speed))
    return {"status": "started"}
