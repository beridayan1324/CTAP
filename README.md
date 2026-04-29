# CTAP Chat System

A real-time chat application with room support, web UI (Flask + Jinja2), and Python clients with serial input.

## Features

- **Real-time messaging** with WebSocket connections
- **Room-based chat** — join different chat rooms
- **Web interface** — HTML/CSS served by Flask; minimal JavaScript for WebSocket and Web Serial API
- **REST auth** — register, login (JWT), audit log views for authenticated users
- **Serial input** for hardware integration (ESP32) from the browser or via `client.py`
- **Encrypted glove traffic** — AES-256-GCM for `CTAP_MSG` from hardware clients
- **Cross-platform** — desktop and mobile browsers (serial requires Chromium-based browser)

## Setup

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Start the server** (HTTP, Web UI, WebSocket, and API on port **8766**):

   ```bash
   flask --app backend.app run --host 0.0.0.0 --port 8766
   ```

   Or:

   ```bash
   python -m backend.app
   ```

   Or the compatibility wrapper:

   ```bash
   python server.py
   ```

3. Open **http://localhost:8766/** in your browser (same origin as the API and WebSocket).

## Usage

### Web interface

- Register or log in, then use Chat and Audit Log pages.
- Join a room from the sidebar.
- Connect an ESP32 with **Connect ESP32** (Web Serial) where supported.

### Python client

- Run `python client.py` for a console client with serial and encryption.
- Set `WS_SERVER` in `client.py` to match your host (e.g. `ws://localhost:8766`).
- Use `/join <room>` to switch rooms, `/exit` to quit, `/shutdown` to stop the server process.

## Configuration

- **JWT**: set environment variable `JWT_SECRET` for production (defaults match the previous dev key).
- **SQLite**: database file is [backend/ctap_audit.db](backend/ctap_audit.db) (users + audit tables).
- **TCP audit socket** (plain `socket`, not WebSocket): listens on **8767** by default. Set `CTAP_TCP_ADMIN_SECRET` to a strong value; use `CTAP_TCP_DB_BIND=127.0.0.1` on production machines. See [PROTOCOL.md](PROTOCOL.md). Set `CTAP_TCP_DB_ENABLED=0` to turn it off.

## Browser requirements

- **Web Serial API** requires Chrome, Edge, or Opera.

## Architecture

- **[backend/app.py](backend/app.py)**: Flask — REST, WebSocket `/`, static files, Jinja templates under `frontend/`
- **[backend/database.py](backend/database.py)**, **[backend/crypto_utils.py](backend/crypto_utils.py)**: SQLite audit, AES-GCM, handshake hashing
- **[client.py](client.py)**: Python hardware/console client
- **[frontend/templates](frontend/templates)**, **[frontend/static](frontend/static)**: UI (HTML/CSS/JS)
- **[backend/tcp_db_socket.py](backend/tcp_db_socket.py)**: TCP `SOCK_STREAM` listener for authenticated DB audit reads/writes (port 8767)
- **[PROTOCOL.md](PROTOCOL.md)**: Wire format and security overview

## TLS / HTTPS and WSS

For **encrypted traffic on the wire** (TLS), set PEM paths and start the app:

```bash
set SSL_CERTFILE=c:\path\cert.pem
set SSL_KEYFILE=c:\path\key.pem
python server.py
```

Browsers and `wss://` clients must use the matching hostname/SNI. For local dev you can use [mkcert](https://github.com/FiloSottile/mkcert) or OpenSSL. Without these variables, the server listens in cleartext (dev default).

## Course / rubric coverage (תכנון פרויקט)

| Requirement | Where in CTAP |
|-------------|----------------|
| **≥2 OOP classes** | Server: `AuditDatabase`, `CTAPCrypto`, `RoomRegistry`, `LoginRateLimiter`, `ServerMaintenanceThread`; Client: `GloveTransportCrypto`, `CTAPHardwareClient` |
| **Server + client** | `backend/app.py` (Flask server), `client.py` (WebSocket + serial client), browser UI |
| **Multi-client server** | `RoomRegistry` + WebSocket broadcast to all sockets in a room |
| **Clear protocol** | **[PROTOCOL.md](PROTOCOL.md)** — message types, handshake, REST |
| **Threads** | `ServerMaintenanceThread` (`backend/maintenance.py`); Flask `threaded=True`; locks in DB / rooms / rate limiter |
| **Files / API / system** | REST API, SQLite file, JSON `backend/data/server_runtime.json`, **plain TCP socket** on 8767 ([`tcp_db_socket.py`](backend/tcp_db_socket.py)), serial port (OS), optional TLS files |
| **Plain TCP (not only WebSocket)** | `socket.SOCK_STREAM` audit/DB command interface — see [PROTOCOL.md](PROTOCOL.md) |
| **Sensitive data encryption** | bcrypt (passwords), AES-256-GCM (`CTAP_MSG`), JWT for sessions |
| **Security hardening** | Rate limit on login, input validation, security headers, timing-safe handshake compare, max message sizes |
| **TLS or other transport crypto** | Optional **TLS** for HTTP + WS; in addition, **AES-GCM** on glove payloads |
| **Interactive UI** | Jinja templates + chat / audit / auth pages (`frontend/`) |
| **DB or JSON persistence** | SQLite `ctap_audit.db` + periodic JSON metadata |
