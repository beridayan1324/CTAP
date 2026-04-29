"""
Plain TCP socket (not WebSocket) for authenticated audit DB reads and updates.

Uses the :mod:`socket` module. Each client connects, sends ``AUTH <token>``,
then newline-delimited JSON commands (one response line per command).

Environment:
  CTAP_TCP_DB_PORT      — listen port (default 8767)
  CTAP_TCP_DB_BIND      — bind address (default 0.0.0.0)
  CTAP_TCP_ADMIN_SECRET — shared secret for AUTH line (change in production)
  CTAP_TCP_DB_ENABLED   — set to 0 to disable the TCP listener
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import threading
from typing import Any

from backend.database import AuditDatabase

_ALLOWED_EVT = frozenset(
    {"CONNECT", "DISCONNECT", "AUTH_SUCCESS", "AUTH_FAIL"}
)

_default_secret = "CTAP-TCP-ADMIN-DEV-CHANGE-ME"


def _auth_ok(provided: str, expected: str) -> bool:
    """Compare secrets without leaking length via SHA-256 digest compare."""
    return hmac.compare_digest(
        hashlib.sha256(provided.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


class TcpAuditDbSocketServer(threading.Thread):
    """Thread hosting ``SOCK_STREAM`` TCP accepts; each client handled in its own thread."""

    __slots__ = ("_audit", "_bind", "_port", "_secret", "_stop", "_sock")

    def __init__(self, audit: AuditDatabase, bind: str, port: int, secret: str) -> None:
        super().__init__(daemon=True, name="CTAP-TcpAuditDbSocket")
        self._audit = audit
        self._bind = bind
        self._port = port
        self._secret = secret
        self._stop = threading.Event()
        self._sock: socket.socket | None = None

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def run(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock = srv
        try:
            srv.bind((self._bind, self._port))
            srv.listen(16)
            srv.settimeout(1.0)
        except OSError as e:
            print(f"[TCP-DB] Failed to bind {self._bind}:{self._port} — {e}")
            return

        print(f"[TCP-DB] Audit socket listening on {self._bind}:{self._port} (SOCK_STREAM)")

        while not self._stop.is_set():
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(
                target=self._client_session,
                args=(conn, addr),
                daemon=True,
                name=f"TcpDbClient-{addr[0]}:{addr[1]}",
            )
            t.start()

    def _send(self, conn: socket.socket, obj: dict[str, Any]) -> None:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        conn.sendall(line.encode("utf-8"))

    def _client_session(self, conn: socket.socket, addr: tuple[Any, ...]) -> None:
        peer = f"{addr[0]}:{addr[1]}"
        try:
            buf = b""
            while b"\n" not in buf and not self._stop.is_set():
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk
                if len(buf) > 65536:
                    self._send(conn, {"ok": False, "error": "line too long"})
                    return

            line, _, rest = buf.partition(b"\n")
            first = line.decode("utf-8", errors="replace").strip()
            if not first.upper().startswith("AUTH "):
                self._send(conn, {"ok": False, "error": "first line must be: AUTH <token>"})
                return
            token = first[5:].strip()
            if not _auth_ok(token, self._secret):
                self._send(conn, {"ok": False, "error": "authentication failed"})
                return

            self._send(conn, {"ok": True, "message": "ready", "peer": peer})

            buffer = rest
            while True:
                while b"\n" not in buffer:
                    chunk = conn.recv(65536)
                    if not chunk:
                        return
                    buffer += chunk
                    if len(buffer) > 1_048_576:
                        self._send(conn, {"ok": False, "error": "request too large"})
                        return
                raw_line, _, buffer = buffer.partition(b"\n")
                cmd_text = raw_line.decode("utf-8", errors="replace").strip()
                if not cmd_text:
                    continue
                try:
                    cmd = json.loads(cmd_text)
                except json.JSONDecodeError as e:
                    self._send(conn, {"ok": False, "error": f"invalid json: {e}"})
                    continue

                ok, payload = self._run_command(cmd)
                if not ok and payload == "bye":
                    self._send(conn, {"ok": True, "message": "bye"})
                    return
                if ok:
                    self._send(conn, {"ok": True, **payload})
                else:
                    self._send(conn, {"ok": False, "error": str(payload)})
        except (OSError, ConnectionError) as e:
            print(f"[TCP-DB] Client {peer} error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass
            print(f"[TCP-DB] Client {peer} disconnected")

    def _run_command(self, cmd: dict[str, Any]) -> tuple[bool, str | dict[str, Any]]:
        op = cmd.get("op")
        if op == "quit":
            return False, "bye"

        if op == "get_logs":
            try:
                limit = int(cmd.get("limit", 100))
            except (TypeError, ValueError):
                limit = 100
            limit = max(1, min(limit, 500))
            rows = self._audit.fetch_audit_messages(limit)
            return True, {"data": rows}

        if op == "get_connections":
            try:
                limit = int(cmd.get("limit", 100))
            except (TypeError, ValueError):
                limit = 100
            limit = max(1, min(limit, 500))
            rows = self._audit.fetch_audit_connections(limit)
            return True, {"data": rows}

        if op == "insert_connection":
            client_address = str(cmd.get("client_address", "")).strip()
            event_type = str(cmd.get("event_type", "")).strip()
            room = str(cmd.get("room", "default")).strip() or "default"
            if not client_address or event_type not in _ALLOWED_EVT:
                return (
                    False,
                    "client_address required; event_type must be CONNECT|DISCONNECT|AUTH_SUCCESS|AUTH_FAIL",
                )
            if len(room) > 128:
                room = room[:128]
            self._audit.log_connection(client_address, event_type, room)
            return True, {"inserted": "connection"}

        if op == "insert_message":
            msg_id = str(cmd.get("msg_id", "")).strip()
            sender = str(cmd.get("sender_address", "")).strip()
            room = str(cmd.get("room", "default")).strip() or "default"
            msg_hash = str(cmd.get("msg_hash", "")).strip()
            msg_type = str(cmd.get("msg_type", "tcp_import")).strip() or "tcp_import"
            if not msg_id or not sender or not msg_hash:
                return False, "msg_id, sender_address, msg_hash required"
            if len(room) > 128:
                room = room[:128]
            if len(msg_type) > 32:
                msg_type = msg_type[:32]
            self._audit.log_message(msg_id, sender, room, msg_hash, msg_type)
            return True, {"inserted": "message"}

        return (
            False,
            f"unknown op: {op!r}; use get_logs, get_connections, insert_connection, insert_message, quit",
        )


_tcp_server: TcpAuditDbSocketServer | None = None
_tcp_lock = threading.Lock()


def start_tcp_db_socket_server(audit: AuditDatabase) -> TcpAuditDbSocketServer | None:
    """Start the TCP DB socket once (idempotent). Returns None if disabled."""
    global _tcp_server
    if os.environ.get("CTAP_TCP_DB_ENABLED", "1").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        print("[TCP-DB] Disabled (CTAP_TCP_DB_ENABLED=0)")
        return None
    with _tcp_lock:
        if _tcp_server is not None and _tcp_server.is_alive():
            return _tcp_server
        bind = os.environ.get("CTAP_TCP_DB_BIND", "0.0.0.0").strip()
        port = int(os.environ.get("CTAP_TCP_DB_PORT", "8767"))
        secret = os.environ.get("CTAP_TCP_ADMIN_SECRET", _default_secret)
        _tcp_server = TcpAuditDbSocketServer(audit, bind, port, secret)
        _tcp_server.start()
        return _tcp_server
