# CTAP application protocol

This document describes the **clear communication protocol** between the CTAP server (Flask + WebSocket), web browser, and Python/hardware clients.

## Transports

| Channel | Format | Encryption / protection |
|---------|--------|-------------------------|
| HTTP REST | JSON | Optional **TLS** (`SSL_CERTFILE` / `SSL_KEYFILE`); passwords stored as **bcrypt**; API auth via **JWT** (HS256). |
| WebSocket (`/` on same port) | JSON text frames | Optional **TLS** (`wss://`); first message exchange is a **shared-secret handshake**; glove payload uses **AES-256-GCM** (`CTAP_MSG`). |
| **Plain TCP** (`SOCK_STREAM`, default port **8767**) | Line-based: `AUTH <token>` then JSON per line | **Not TLS** unless you terminate TLS elsewhere; protect with firewall + strong `CTAP_TCP_ADMIN_SECRET`. Used to **read and insert** audit rows in SQLite (see below). |
| Python `client.py` | Same WebSocket protocol | Same as above; serial reads from OS serial device (**system component**). |

## REST (JSON)

- `POST /register` — body: `{ "username": string, "password": string }`  
  - Username: 3–32 characters, `[a-zA-Z0-9_]`.  
  - Password: 8–128 characters.

- `POST /login` — body: `{ "username", "password" }`  
  - Success: `{ "token": string, "username": string }`.  
  - Rate-limited per IP on failures (HTTP 429 when exceeded).

- `GET /audit/logs`, `GET /audit/connections` — header: `Authorization: Bearer <JWT>`.

## TCP audit / DB socket (Python `socket` module)

Separate from WebSocket. Default **`host:8767`** (env `CTAP_TCP_DB_PORT`, `CTAP_TCP_DB_BIND`). Disable with `CTAP_TCP_DB_ENABLED=0`.

1. Connect with a plain TCP client (`socket.AF_INET`, `SOCK_STREAM`).
2. First line (UTF-8, newline-terminated): `AUTH <CTAP_TCP_ADMIN_SECRET>` (default dev secret in server logs / env docs — **change in production**).
3. Server replies with one JSON line: `{"ok": true, "message": "ready", ...}` or error.
4. Each further line is one JSON command; server replies with one JSON line.

**Commands** (`op` field):

| `op` | Purpose |
|------|---------|
| `get_logs` | Optional `limit` (1–500). Returns `{ "data": [ ...messages rows ] }`. |
| `get_connections` | Optional `limit`. Returns `{ "data": [ ...connections rows ] }`. |
| `insert_connection` | `client_address`, `event_type` (`CONNECT`\|`DISCONNECT`\|`AUTH_SUCCESS`\|`AUTH_FAIL`), optional `room`. Inserts into `connections`. |
| `insert_message` | `msg_id`, `sender_address`, `msg_hash`, optional `room`, optional `msg_type` (default `tcp_import`). Inserts into `messages`. |
| `quit` | Close session gracefully. |

**Security:** bind to `127.0.0.1` only in production (`CTAP_TCP_DB_BIND=127.0.0.1`) and use a long random `CTAP_TCP_ADMIN_SECRET`.

## WebSocket lifecycle

1. **Connect** to `ws://host:8766/` or `wss://host:8766/` (when TLS enabled).

2. **Handshake (mandatory)**  
   - Server → client: `{ "type": "auth_challenge", "challenge": "<32 hex chars>" }`  
   - Client → server: `{ "type": "auth_response", "hash": "<64 hex chars>" }`  
   - `hash` MUST equal `SHA256(challenge + HANDSHAKE_SECRET)` (hex, lowercase).  
   - Server → client: `{ "type": "auth_result", "status": "OK"|"FAIL", "message": "..." }`  
   - On `FAIL`, server closes the connection.

3. **Room**  
   - Client → server: `{ "type": "join_room", "room": "<string>" }`  
   - Server → client: `{ "type": "room_joined", "room": "<string>" }`

4. **Plain web chat**  
   - Client → server: `{ "type": "web_msg", "text": string, "username"?: string }`  
   - Server broadcasts to room: `{ "type": "chat_message", "text", "timestamp", "msg_id", "sender", "room" }`

5. **Encrypted glove / console (AES-GCM)**  
   - Client → server:
   ```json
   {
     "type": "CTAP_MSG",
     "msg_id": "<uuid>",
     "timestamp": <unix_seconds>,
     "payload": {
       "nonce": "<base64>",
       "ciphertext": "<base64 ciphertext||tag>"
     }
   }
   ```
   - Server decrypts, audits **SHA-256(plaintext)** only, broadcasts plaintext as `chat_message`.

6. **Admin / danger**  
   - Plaintext or `web_msg` text `"/shutdown"` terminates the server process (same as legacy Node server).

## Persistence

- **SQLite** (`backend/ctap_audit.db`): users, connection audit, message hashes.  
- **JSON** (`backend/data/server_runtime.json`): periodic server metadata written by the maintenance thread (uptime, pid, paths).

## Security notes

- Handshake response compared with **HMAC-style constant-time** check (`hmac.compare_digest`) to reduce timing leakage.
- HTTP security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`.
- WebSocket frames larger than 65536 bytes are ignored.
- Production: use a long random `JWT_SECRET` and enable TLS for encryption in transit on all HTTP/WebSocket traffic.
