"""
server.py — CTAP WebSocket Server
==================================
Central relay server for the CTAP (Communication Through Accessible Protocol) system.
Handles WebSocket connections, room-based message routing, AES-256-GCM decryption,
shared-secret handshake authentication, and SQLite audit trail logging.

Author: CTAP Project
Date: 2026
"""

import asyncio
import websockets
import json
import base64
import binascii
import uuid
import time
import hashlib
import sqlite3
import os
from datetime import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# =======================
# CONFIGURATION
# =======================

# Must match the Client's Key exactly!
FIXED_AES_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"

# Shared secret for handshake authentication (must match client)
HANDSHAKE_SECRET = "CTAP-GLOVE-AUTH-2026"

# Server port
SERVER_PORT = 8766

# Database file path
DB_PATH = "ctap_audit.db"

# =======================
# CRYPTO SETUP
# =======================

try:
    AES_KEY = binascii.unhexlify(FIXED_AES_KEY_HEX)
    aesgcm = AESGCM(AES_KEY)
    print("[SERVER] Crypto initialized successfully.")
except Exception as e:
    print(f"[ERROR] Invalid Key: {e}")
    exit(1)


def decrypt_payload(payload: dict) -> str:
    """
    Decrypts an AES-256-GCM encrypted payload.

    Takes a dictionary containing Base64-encoded 'nonce' and 'ciphertext',
    decodes them, and performs authenticated decryption using the shared
    AES-GCM key.

    Args:
        payload (dict): Dictionary with keys:
            - 'nonce': Base64-encoded 12-byte nonce
            - 'ciphertext': Base64-encoded ciphertext with GCM auth tag

    Returns:
        str: Decrypted plaintext message, or error string if decryption fails.
    """
    try:
        nonce = base64.b64decode(payload['nonce'])
        ciphertext = base64.b64decode(payload['ciphertext'])
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode('utf-8')
    except Exception as e:
        return f"[DECRYPTION FAILED] {e}"


# =======================
# SQLITE AUDIT TRAIL
# =======================

def init_database():
    """
    Initializes the SQLite audit trail database.

    Creates two tables if they don't exist:
    - connections: Logs every client connection/disconnection event
    - messages: Logs metadata and SHA-256 hash of every message (not plaintext)

    Returns:
        sqlite3.Connection: Active database connection.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_address TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('CONNECT', 'DISCONNECT', 'AUTH_SUCCESS', 'AUTH_FAIL')),
            room TEXT DEFAULT 'default',
            timestamp TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id TEXT UNIQUE NOT NULL,
            sender_address TEXT NOT NULL,
            room TEXT NOT NULL,
            msg_hash TEXT NOT NULL,
            msg_type TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    conn.commit()
    print("[DB] Audit trail database initialized.")
    return conn


def log_connection(db_conn, client_address, event_type, room="default"):
    """
    Logs a connection event to the audit trail.

    Args:
        db_conn (sqlite3.Connection): Database connection.
        client_address (str): Client IP:port string.
        event_type (str): One of 'CONNECT', 'DISCONNECT', 'AUTH_SUCCESS', 'AUTH_FAIL'.
        room (str): Current room name. Defaults to 'default'.
    """
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            "INSERT INTO connections (client_address, event_type, room, timestamp) VALUES (?, ?, ?, ?)",
            (str(client_address), event_type, room, datetime.now().isoformat())
        )
        db_conn.commit()
    except sqlite3.Error as e:
        print(f"[DB ERROR] Failed to log connection: {e}")


def log_message(db_conn, msg_id, sender_address, room, msg_content, msg_type):
    """
    Logs a message event to the audit trail.

    Stores a SHA-256 hash of the message content for forensic verification
    without storing sensitive plaintext data.

    Args:
        db_conn (sqlite3.Connection): Database connection.
        msg_id (str): Unique message identifier (UUID).
        sender_address (str): Sender's IP:port string.
        room (str): Room where the message was sent.
        msg_content (str): Raw message text (hashed before storage).
        msg_type (str): Message type ('CTAP_MSG' or 'web_msg').
    """
    try:
        msg_hash = hashlib.sha256(msg_content.encode('utf-8')).hexdigest()
        cursor = db_conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO messages (msg_id, sender_address, room, msg_hash, msg_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, str(sender_address), room, msg_hash, msg_type, datetime.now().isoformat())
        )
        db_conn.commit()
    except sqlite3.Error as e:
        print(f"[DB ERROR] Failed to log message: {e}")


# =======================
# HANDSHAKE AUTH
# =======================

async def verify_handshake(websocket):
    """
    Performs shared-secret handshake authentication with a connecting client.

    Protocol:
    1. Server sends a random challenge (16-byte hex nonce).
    2. Client must respond with SHA-256(challenge + HANDSHAKE_SECRET).
    3. Server verifies the hash. If it matches, authentication succeeds.

    This prevents unauthorized clients from connecting without knowledge
    of the shared secret, adding an authentication layer on top of AES encryption.

    Args:
        websocket: The WebSocket connection to authenticate.

    Returns:
        bool: True if handshake succeeded, False otherwise.
    """
    try:
        # Step 1: Generate and send challenge
        challenge = os.urandom(16).hex()
        await websocket.send(json.dumps({
            "type": "auth_challenge",
            "challenge": challenge
        }))

        # Step 2: Wait for response (5 second timeout)
        response_raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        response = json.loads(response_raw)

        if response.get("type") != "auth_response":
            return False

        # Step 3: Verify the hash
        expected_hash = hashlib.sha256(
            (challenge + HANDSHAKE_SECRET).encode('utf-8')
        ).hexdigest()

        if response.get("hash") == expected_hash:
            print(f"[AUTH] Handshake SUCCESS for {websocket.remote_address}")
            return True
        else:
            print(f"[AUTH] Handshake FAILED for {websocket.remote_address} — bad hash")
            return False

    except asyncio.TimeoutError:
        print(f"[AUTH] Handshake TIMEOUT for {websocket.remote_address}")
        return False
    except Exception as e:
        print(f"[AUTH] Handshake ERROR for {websocket.remote_address}: {e}")
        return False


# =======================
# GLOBAL STATE
# =======================

connected_clients = set()
rooms = {}  # room_name -> set of websockets
stop_event = asyncio.Event()

# =======================
# WEBSOCKET HANDLER
# =======================

async def handler(websocket):
    """
    Main WebSocket connection handler.

    Manages the full lifecycle of a client connection:
    1. Performs shared-secret handshake authentication
    2. Assigns client to default room
    3. Processes incoming messages (join_room, CTAP_MSG, web_msg)
    4. Broadcasts messages to room members
    5. Logs all events to SQLite audit trail
    6. Handles disconnection and cleanup

    Args:
        websocket: The incoming WebSocket connection.
    """
    client_addr = str(websocket.remote_address)
    print(f"[SERVER] Client connected from {client_addr}")

    # --- HANDSHAKE AUTHENTICATION ---
    auth_ok = await verify_handshake(websocket)
    log_connection(db, client_addr, "AUTH_SUCCESS" if auth_ok else "AUTH_FAIL")

    if not auth_ok:
        await websocket.send(json.dumps({
            "type": "auth_result",
            "status": "FAIL",
            "message": "Authentication failed. Invalid secret."
        }))
        await websocket.close()
        return

    await websocket.send(json.dumps({
        "type": "auth_result",
        "status": "OK",
        "message": "Authentication successful."
    }))

    # --- CONNECTION SETUP ---
    connected_clients.add(websocket)
    log_connection(db, client_addr, "CONNECT")

    current_room = "default"
    if current_room not in rooms:
        rooms[current_room] = set()
    rooms[current_room].add(websocket)

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "join_room":
                    new_room = data.get("room", "default")
                    # Leave current room
                    if current_room in rooms and websocket in rooms[current_room]:
                        rooms[current_room].remove(websocket)
                    # Join new room
                    current_room = new_room
                    if current_room not in rooms:
                        rooms[current_room] = set()
                    rooms[current_room].add(websocket)
                    print(f"[SERVER] {client_addr} joined room '{current_room}'")
                    # Notify client
                    await websocket.send(json.dumps({
                        "type": "room_joined",
                        "room": current_room
                    }))

                elif msg_type == "CTAP_MSG":
                    encrypted_payload = data.get("payload")

                    if encrypted_payload:
                        decrypted_text = decrypt_payload(encrypted_payload)

                        # Log to audit trail
                        msg_id = data.get('msg_id', str(uuid.uuid4()))
                        log_message(db, msg_id, client_addr, current_room, decrypted_text, "CTAP_MSG")

                        # Check for shutdown command
                        if decrypted_text == "/shutdown":
                            print(f"[SERVER] Shutdown command received from {client_addr}")
                            stop_event.set()
                            continue

                        # Broadcast to all in current room
                        broadcast_message = {
                            "type": "chat_message",
                            "text": decrypted_text,
                            "timestamp": data.get('timestamp'),
                            "msg_id": msg_id,
                            "sender": client_addr,
                            "room": current_room
                        }

                        for client in rooms.get(current_room, set()):
                            try:
                                await client.send(json.dumps(broadcast_message))
                            except:
                                pass

                        # Print to server console
                        print("\n" + "=" * 50)
                        print(f"Room:    {current_room}")
                        print(f"Time:    {data.get('timestamp')}")
                        print(f"ID:      {msg_id}")
                        print(f"Sender:  {client_addr}")
                        print(f"Message: {decrypted_text}")
                        print("=" * 50)
                    else:
                        print(f"[SERVER] Received raw/unknown message: {message}")

                elif msg_type == "web_msg":
                    text = data.get("text", "").strip()
                    if text:
                        msg_id = str(uuid.uuid4())
                        log_message(db, msg_id, f"Web-{client_addr}", current_room, text, "web_msg")

                        if text == "/shutdown":
                            print(f"[SERVER] Shutdown command received from {client_addr}")
                            stop_event.set()
                            continue

                        broadcast_message = {
                            "type": "chat_message",
                            "text": text,
                            "timestamp": int(time.time()),
                            "msg_id": msg_id,
                            "sender": f"Web-{client_addr}",
                            "room": current_room
                        }

                        for client in rooms.get(current_room, set()):
                            try:
                                await client.send(json.dumps(broadcast_message))
                            except:
                                pass

                        print("\n" + "=" * 50)
                        print(f"Room:    {current_room}")
                        print(f"Sender:  Web-{client_addr}")
                        print(f"Message: {text}")
                        print("=" * 50)

            except json.JSONDecodeError:
                print(f"[SERVER] Received non-JSON message: {message}")

    except websockets.exceptions.ConnectionClosed:
        print(f"[SERVER] Client {client_addr} disconnected")
    finally:
        connected_clients.discard(websocket)
        log_connection(db, client_addr, "DISCONNECT", current_room)
        if current_room in rooms and websocket in rooms[current_room]:
            rooms[current_room].remove(websocket)


# =======================
# MAIN LOOP
# =======================

async def main():
    """
    Main entry point for the CTAP server.

    Initializes the SQLite audit database, starts the WebSocket server
    on all interfaces at the configured port, and waits for a shutdown signal.
    """
    global db
    db = init_database()

    async with websockets.serve(handler, "0.0.0.0", SERVER_PORT):
        print(f"[SERVER] Listening on ws://0.0.0.0:{SERVER_PORT}...")
        print(f"[SERVER] Handshake auth: ENABLED")
        print(f"[SERVER] Audit trail DB: {DB_PATH}")
        await stop_event.wait()
        print("[SERVER] Shutting down...")

    db.close()
    print("[DB] Database connection closed.")


if __name__ == "__main__":
    asyncio.run(main())