# Copyright (c) 2026 Reza Malik. Licensed under AGPL-3.0.
"""WebSocket manager for live dashboard updates."""

from __future__ import annotations

import json
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        """Send a message to every connected client.  Silently drops dead connections."""
        dead: list[WebSocket] = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.active_connections.discard(conn)

    @property
    def client_count(self) -> int:
        return len(self.active_connections)


manager = ConnectionManager()


@ws_router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Accept a WebSocket connection and keep it alive until the client disconnects."""
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect meaningful inbound messages; just keep-alive pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
