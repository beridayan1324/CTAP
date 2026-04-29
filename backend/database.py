"""SQLite audit DB and users; matches legacy schema. OOP facade: :class:`AuditDatabase`."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
DB_PATH = str(BACKEND_DIR / "ctap_audit.db")
DATA_DIR = BACKEND_DIR / "data"
RUNTIME_META_PATH = DATA_DIR / "server_runtime.json"


class AuditDatabase:
    """Thread-safe SQLite access for users and audit tables."""

    __slots__ = ("_conn", "_lock", "_path")

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def get_sqlite_connection(self) -> sqlite3.Connection:
        return self._connection()

    def init_schema(self) -> sqlite3.Connection:
        with self._lock:
            conn = self._connection()
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_address TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(event_type IN ('CONNECT', 'DISCONNECT', 'AUTH_SUCCESS', 'AUTH_FAIL')),
                    room TEXT DEFAULT 'default',
                    timestamp TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg_id TEXT UNIQUE NOT NULL,
                    sender_address TEXT NOT NULL,
                    room TEXT NOT NULL,
                    msg_hash TEXT NOT NULL,
                    msg_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
                """
            )
            conn.commit()
            print("[DB] Connected to SQLite database.")
        return self._connection()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {k: row[k] for k in row.keys()}

    def log_connection(self, client_address: str, event_type: str, room: str = "default") -> None:
        with self._lock:
            conn = self._connection()
            conn.execute(
                "INSERT INTO connections (client_address, event_type, room, timestamp) VALUES (?, ?, ?, ?)",
                (str(client_address), event_type, room, datetime.now().isoformat()),
            )
            conn.commit()

    def log_message(
        self,
        msg_id: str,
        sender_address: str,
        room: str,
        msg_hash: str,
        msg_type: str,
    ) -> None:
        with self._lock:
            conn = self._connection()
            conn.execute(
                "INSERT OR IGNORE INTO messages (msg_id, sender_address, room, msg_hash, msg_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (msg_id, str(sender_address), room, msg_hash, msg_type, datetime.now().isoformat()),
            )
            conn.commit()

    def create_user(self, username: str, password_hash: str) -> None:
        with self._lock:
            conn = self._connection()
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password_hash),
            )
            conn.commit()

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connection()
            cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def fetch_audit_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connection()
            cur = conn.execute(
                "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def fetch_audit_connections(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connection()
            cur = conn.execute(
                "SELECT * FROM connections ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def checkpoint_wal(self) -> None:
        """Reduces WAL size; safe no-op if not in WAL mode."""
        with self._lock:
            conn = self._connection()
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except sqlite3.Error:
                pass
            conn.commit()

    def write_runtime_meta_json(self, uptime_sec: float) -> None:
        """Persist lightweight JSON status for rubric (files + DB)."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        meta = {
            "uptime_sec": round(uptime_sec, 3),
            "database_path": self._path,
            "pid": __import__("os").getpid(),
            "updated_iso": datetime.now().isoformat(),
        }
        tmp = RUNTIME_META_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        tmp.replace(RUNTIME_META_PATH)


_audit_singleton: AuditDatabase | None = None
_audit_lock = threading.Lock()


def get_audit_db() -> AuditDatabase:
    global _audit_singleton
    with _audit_lock:
        if _audit_singleton is None:
            _audit_singleton = AuditDatabase(DB_PATH)
            _audit_singleton.init_schema()
        return _audit_singleton


def init_database() -> sqlite3.Connection:
    """Ensure singleton is initialized and return the SQLite connection."""
    audit = get_audit_db()
    return audit.get_sqlite_connection()


def log_connection(client_address: str, event_type: str, room: str = "default") -> None:
    get_audit_db().log_connection(client_address, event_type, room)


def log_message(
    msg_id: str,
    sender_address: str,
    room: str,
    msg_hash: str,
    msg_type: str,
) -> None:
    get_audit_db().log_message(msg_id, sender_address, room, msg_hash, msg_type)


def create_user(username: str, password_hash: str) -> None:
    get_audit_db().create_user(username, password_hash)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    return get_audit_db().get_user_by_username(username)


def fetch_audit_messages(limit: int = 100) -> list[dict[str, Any]]:
    return get_audit_db().fetch_audit_messages(limit)


def fetch_audit_connections(limit: int = 100) -> list[dict[str, Any]]:
    return get_audit_db().fetch_audit_connections(limit)
