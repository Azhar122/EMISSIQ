"""EMISSIQ FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api import analytics, datasources, demo_routes, equipment, events, facilities, reports, workorders
from .db.init import init_db
from .ws import manager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("emissiq")

app = FastAPI(title="EMISSIQ API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon prototype; tighten before any real deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(facilities.router)
app.include_router(equipment.router)
app.include_router(events.router)
app.include_router(workorders.router)
app.include_router(analytics.router)
app.include_router(datasources.router)
app.include_router(demo_routes.router)
app.include_router(reports.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    log.info("EMISSIQ API ready")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "emissiq-api"}


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            # This socket is broadcast-only from the server's side; drain
            # whatever the client sends (pings, keepalives) without acting on it.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
