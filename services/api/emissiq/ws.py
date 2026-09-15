"""WebSocket fan-out for live telemetry and demo progress."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        # Late joiners get the last frame immediately instead of a blank screen.
        self.last_tick: dict | None = None
        self.last_stage: dict | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        for frame in (self.last_stage, self.last_tick):
            if frame:
                await self._send(ws, frame)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        if message.get("type") == "tick":
            self.last_tick = message
        elif message.get("type") == "stage":
            self.last_stage = message

        async with self._lock:
            clients = list(self._clients)

        dead = []
        for ws in clients:
            if not await self._send(ws, message):
                dead.append(ws)
        if dead:
            async with self._lock:
                self._clients.difference_update(dead)

    @staticmethod
    async def _send(ws: WebSocket, message: dict) -> bool:
        try:
            await ws.send_text(json.dumps(message, default=str))
            return True
        except Exception:
            return False

    def reset(self) -> None:
        self.last_tick = None
        self.last_stage = None


manager = ConnectionManager()
