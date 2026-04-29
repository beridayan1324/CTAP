"""Flask HTTP (auth + audit + UI) and WebSocket chat on port 8766."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from flask import Flask, jsonify, render_template, request
from flask_sock import Sock

from backend.crypto_utils import CTAPCrypto
from backend.database import (
    create_user,
    fetch_audit_connections,
    fetch_audit_messages,
    get_audit_db,
    get_user_by_username,
    init_database,
    log_connection,
    log_message,
)
from backend.input_validation import validate_password, validate_username
from backend.maintenance import ensure_started
from backend.rate_limit import LoginRateLimiter
from backend.room_registry import RoomRegistry
from backend.tcp_db_socket import start_tcp_db_socket_server

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(
    __name__,
    template_folder=str(FRONTEND_DIR / "templates"),
    static_folder=str(FRONTEND_DIR / "static"),
    static_url_path="/static",
)
sock = Sock(app)

app.config["JWT_SECRET"] = os.environ.get(
    "JWT_SECRET", "CTAP-SUPER-SECRET-JWT-KEY-2026"
)

crypto_service = CTAPCrypto()
room_registry = RoomRegistry()
login_limiter = LoginRateLimiter(max_events=12, window_sec=300)
MAX_WEB_MSG_LEN = 8192

init_database()
_audit = get_audit_db()
ensure_started(_audit)
start_tcp_db_socket_server(_audit)


def _client_address() -> str:
    port = request.environ.get("REMOTE_PORT")
    if port:
        return f"{request.remote_addr}:{port}"
    return str(request.remote_addr or "unknown")


def _client_ip() -> str:
    return str(request.remote_addr or "unknown")


def _verify_jwt_optional():
    auth = request.headers.get("Authorization", "")
    parts = auth.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        return jwt.decode(
            parts[1],
            app.config["JWT_SECRET"],
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        return None


@app.after_request
def security_headers(response):
    """Mitigate XSS framing, MIME sniffing, and referrer leakage."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "accelerometer=(), camera=(), geolocation=(), gyroscope=()",
    )
    return response


@app.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    ok_u, username = validate_username(data.get("username"))
    ok_p, password = validate_password(data.get("password"))
    if not ok_u:
        return jsonify(error=username), 400
    if not ok_p:
        return jsonify(error=password), 400
    try:
        h = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10))
        create_user(username, h.decode())
    except sqlite3.IntegrityError:
        return jsonify(error="Username already exists"), 400
    except sqlite3.Error:
        return jsonify(error="Database error"), 500
    return jsonify(message="User registered successfully")


@app.post("/login")
def login():
    ip = _client_ip()
    if login_limiter.is_blocked(ip):
        return jsonify(error="Too many attempts; try again later"), 429

    data = request.get_json(silent=True) or {}
    ok_u, username = validate_username(data.get("username"))
    password = data.get("password") if isinstance(data.get("password"), str) else ""
    if not ok_u:
        login_limiter.record_failure(ip)
        return jsonify(error="Invalid username or password"), 400
    if not password:
        login_limiter.record_failure(ip)
        return jsonify(error="Invalid username or password"), 400

    user = get_user_by_username(username)
    if not user:
        login_limiter.record_failure(ip)
        return jsonify(error="Invalid username or password"), 400
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8"))
    except (ValueError, TypeError):
        login_limiter.record_failure(ip)
        return jsonify(error="Invalid username or password"), 400
    if not ok:
        login_limiter.record_failure(ip)
        return jsonify(error="Invalid username or password"), 400

    login_limiter.clear(ip)
    token = jwt.encode(
        {
            "id": user["id"],
            "username": user["username"],
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
        },
        app.config["JWT_SECRET"],
        algorithm="HS256",
    )
    return jsonify(token=token, username=user["username"])


@app.get("/audit/logs")
def audit_logs():
    if _verify_jwt_optional() is None:
        return jsonify(error="Unauthenticated"), 401
    return jsonify(fetch_audit_messages())


@app.get("/audit/connections")
def audit_connections():
    if _verify_jwt_optional() is None:
        return jsonify(error="Unauthenticated"), 401
    return jsonify(fetch_audit_connections())


@app.get("/")
def landing():
    return render_template("landing.html")


@app.get("/login")
def login_page():
    return render_template("login.html")


@app.get("/register")
def register_page():
    return render_template("register.html")


@app.get("/chat")
def chat_page():
    return render_template("chat.html")


@app.get("/audit")
def audit_page():
    return render_template("audit.html")


@sock.route("/")
def websocket_handler(ws):
    client_addr = _client_address()
    print(f"[SERVER] Client connected from {client_addr}")

    challenge = crypto_service.generate_challenge()
    ws.send(json.dumps({"type": "auth_challenge", "challenge": challenge}))

    try:
        raw = ws.receive(timeout=5.0)
    except Exception:
        raw = None

    if raw is None:
        log_connection(client_addr, "AUTH_FAIL")
        try:
            ws.close()
        except Exception:
            pass
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log_connection(client_addr, "AUTH_FAIL")
        try:
            ws.close()
        except Exception:
            pass
        return

    if data.get("type") != "auth_response" or not crypto_service.verify_handshake_hash(
        challenge, data.get("hash", "")
    ):
        log_connection(client_addr, "AUTH_FAIL")
        ws.send(
            json.dumps(
                {
                    "type": "auth_result",
                    "status": "FAIL",
                    "message": "Authentication failed. Invalid secret.",
                }
            )
        )
        try:
            ws.close()
        except Exception:
            pass
        return

    ws.send(
        json.dumps(
            {
                "type": "auth_result",
                "status": "OK",
                "message": "Authentication successful.",
            }
        )
    )
    log_connection(client_addr, "AUTH_SUCCESS", "default")

    current_room = "default"
    room_registry.add(current_room, ws)
    log_connection(client_addr, "CONNECT", "default")

    def leave_current_room():
        nonlocal current_room
        room_registry.discard(current_room, ws)

    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break
            if len(raw) > 65536:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "join_room":
                new_room = data.get("room") or "default"
                if not isinstance(new_room, str) or len(new_room) > 64:
                    new_room = "default"
                new_room = new_room.strip() or "default"
                room_registry.move(ws, current_room, new_room)
                current_room = new_room
                print(f"[SERVER] {client_addr} joined room '{current_room}'")
                ws.send(json.dumps({"type": "room_joined", "room": current_room}))

            elif msg_type == "CTAP_MSG":
                encrypted_payload = data.get("payload")
                if encrypted_payload:
                    decrypted_text = crypto_service.decrypt_payload(encrypted_payload)
                    msg_id = data.get("msg_id") or str(uuid.uuid4())
                    timestamp = data.get("timestamp")
                    msg_hash = crypto_service.generate_hash(decrypted_text)
                    log_message(
                        msg_id,
                        client_addr,
                        current_room,
                        msg_hash,
                        "CTAP_MSG",
                    )
                    if decrypted_text == "/shutdown":
                        print(f"[SERVER] Shutdown command received from {client_addr}")
                        os._exit(0)
                    room_registry.broadcast(
                        current_room,
                        {
                            "type": "chat_message",
                            "text": decrypted_text,
                            "timestamp": timestamp,
                            "msg_id": msg_id,
                            "sender": client_addr,
                            "room": current_room,
                        },
                    )
                    print("\n" + "=" * 50)
                    print(f"Room:    {current_room}")
                    print(f"Time:    {timestamp}")
                    print(f"ID:      {msg_id}")
                    print(f"Sender:  {client_addr}")
                    print(f"Message: {decrypted_text}")
                    print("=" * 50)

            elif msg_type == "web_msg":
                text = (data.get("text") or "").strip()
                if len(text) > MAX_WEB_MSG_LEN:
                    text = text[:MAX_WEB_MSG_LEN]
                user_name = data.get("username") or f"Web-{client_addr}"
                if isinstance(user_name, str) and len(user_name) > 64:
                    user_name = user_name[:64]
                if not isinstance(user_name, str):
                    user_name = f"Web-{client_addr}"
                if text:
                    msg_id = str(uuid.uuid4())
                    timestamp = int(time.time())
                    msg_hash = crypto_service.generate_hash(text)
                    log_message(
                        msg_id,
                        user_name,
                        current_room,
                        msg_hash,
                        "web_msg",
                    )
                    if text == "/shutdown":
                        print(f"[SERVER] Shutdown command received from {client_addr}")
                        os._exit(0)
                    room_registry.broadcast(
                        current_room,
                        {
                            "type": "chat_message",
                            "text": text,
                            "timestamp": timestamp,
                            "msg_id": msg_id,
                            "sender": user_name,
                            "room": current_room,
                        },
                    )
                    print("\n" + "=" * 50)
                    print(f"Room:    {current_room}")
                    print(f"Sender:  {user_name}")
                    print(f"Message: {text}")
                    print("=" * 50)

    finally:
        print(f"[SERVER] Client {client_addr} disconnected")
        leave_current_room()
        log_connection(client_addr, "DISCONNECT", current_room)


def _ssl_context():
    cert = os.environ.get("SSL_CERTFILE")
    key = os.environ.get("SSL_KEYFILE")
    if cert and key and os.path.isfile(cert) and os.path.isfile(key):
        return (cert, key)
    return None


if __name__ == "__main__":
    ssl = _ssl_context()
    app.run(
        host="0.0.0.0",
        port=8766,
        threaded=True,
        use_reloader=False,
        ssl_context=ssl,
    )
