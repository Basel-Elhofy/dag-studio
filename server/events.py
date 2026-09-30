"""Async event bus used to stream run progress to connected UI clients."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any


class EventBus:
    """Pub/sub hub. Every executor/agent event is published here and
    fanned out to all connected WebSocket subscribers."""

    def __init__(self, history_limit: int = 2000) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self.history: list[dict[str, Any]] = []
        self._history_limit = history_limit

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def publish(self, event_type: str, **payload: Any) -> None:
        event = {
            "type": event_type,
            "ts": time.time(),
            **payload,
        }
        self.history.append(event)
        if len(self.history) > self._history_limit:
            del self.history[: len(self.history) - self._history_limit]
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self.history)


BUS = EventBus()
