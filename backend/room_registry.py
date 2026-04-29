"""Thread-safe registry of WebSocket clients per chat room (multi-client server)."""

from __future__ import annotations

import json
import threading
from typing import Any


class RoomRegistry:
    """Maps room names to sets of WebSocket connections; all mutations are serialized."""

    __slots__ = ("_lock", "_rooms")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: dict[str, set[Any]] = {}

    def add(self, room: str, ws: Any) -> None:
        with self._lock:
            if room not in self._rooms:
                self._rooms[room] = set()
            self._rooms[room].add(ws)

    def discard(self, room: str, ws: Any) -> None:
        with self._lock:
            bucket = self._rooms.get(room)
            if bucket and ws in bucket:
                bucket.discard(ws)

    def move(self, ws: Any, old_room: str, new_room: str) -> None:
        with self._lock:
            old = self._rooms.get(old_room)
            if old and ws in old:
                old.discard(ws)
            if new_room not in self._rooms:
                self._rooms[new_room] = set()
            self._rooms[new_room].add(ws)

    def broadcast(self, room: str, payload: dict) -> None:
        body = json.dumps(payload)
        with self._lock:
            targets = list(self._rooms.get(room, set()))
        for client in targets:
            try:
                client.send(body)
            except Exception:
                pass

    def room_count(self) -> int:
        with self._lock:
            return len(self._rooms)
