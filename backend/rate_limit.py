"""Simple sliding-window rate limiter for brute-force mitigation (login)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, DefaultDict


class LoginRateLimiter:
    """Tracks failed login timestamps per IP; blocks when threshold exceeded."""

    __slots__ = ("_lock", "_failures", "max_events", "window_sec")

    def __init__(self, max_events: int = 12, window_sec: float = 300.0) -> None:
        self._lock = threading.Lock()
        self._failures: DefaultDict[str, Deque[float]] = defaultdict(deque)
        self.max_events = max_events
        self.window_sec = window_sec

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._failures[key]
            while q and now - q[0] > self.window_sec:
                q.popleft()
            return len(q) >= self.max_events

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._failures[key]
            q.append(now)
            while q and now - q[0] > self.window_sec:
                q.popleft()

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
