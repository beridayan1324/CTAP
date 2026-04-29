"""Background thread: DB WAL checkpoint + JSON runtime metadata (files / persistence)."""

from __future__ import annotations

import threading
import time

from backend.database import AuditDatabase

_START_TIME = time.monotonic()


class ServerMaintenanceThread(threading.Thread):
    """Daemon thread periodically checkpoints SQLite and writes a small JSON status file."""

    __slots__ = ("_audit", "_interval", "_stop")

    def __init__(self, audit: AuditDatabase, interval_sec: float = 60.0) -> None:
        super().__init__(daemon=True, name="CTAP-ServerMaintenance")
        self._audit = audit
        self._interval = interval_sec
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._audit.checkpoint_wal()
                self._audit.write_runtime_meta_json(_uptime_sec())
            except Exception as exc:
                print(f"[MAINT] {exc}")

    def stop(self) -> None:
        self._stop.set()


def _uptime_sec() -> float:
    return time.monotonic() - _START_TIME


def ensure_started(audit: AuditDatabase) -> ServerMaintenanceThread:
    """Idempotent start from app factory / module init."""
    t = getattr(ensure_started, "_thread", None)
    if t is not None and t.is_alive():
        return t
    t = ServerMaintenanceThread(audit)
    t.start()
    setattr(ensure_started, "_thread", t)
    return t
