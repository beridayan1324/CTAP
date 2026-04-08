"""
client.py — CTAP Python Console Client
========================================
Console-based client for the CTAP system. Reads text from an ESP32 smart glove
via serial (UART), encrypts messages with AES-256-GCM, performs shared-secret
handshake authentication, and transmits data over WebSocket to the CTAP server.

Supports:
- Serial input from ESP32 glove hardware
- Manual keyboard input
- Room-based chat
- Encrypted communication (AES-256-GCM)
- Shared-secret handshake authentication

Author: CTAP Project
Date: 2026
"""

import asyncio
import websockets
import json
import time
import uuid
import base64
import os
import hashlib
import serial
import binascii
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# =======================
# CONFIGURATION
# =======================

SERIAL_PORT = "COM3"          # Windows: COM3 | Linux: /dev/ttyUSB0
BAUD_RATE = 115200
WS_SERVER = "ws://10.0.0.14:8766"

# 32-byte Hex Key (Must match the server's key!)
FIXED_AES_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"

# Shared secret for handshake authentication (must match server)
HANDSHAKE_SECRET = "CTAP-GLOVE-AUTH-2026"

# =======================
# CRYPTO SETUP
# =======================

try:
    AES_KEY = binascii.unhexlify(FIXED_AES_KEY_HEX)
    aesgcm = AESGCM(AES_KEY)
except Exception as e:
    print(f"[ERROR] Invalid Key: {e}")
    exit(1)


def encrypt_message(plaintext: str) -> dict:
    """
    Encrypts a plaintext message using AES-256-GCM.

    Generates a random 12-byte nonce, encrypts the message with authenticated
    encryption (AES-GCM), and returns the nonce and ciphertext as Base64-encoded
    strings in a dictionary.

    Args:
        plaintext (str): The message to encrypt.

    Returns:
        dict: Dictionary with keys:
            - 'nonce': Base64-encoded 12-byte nonce
            - 'ciphertext': Base64-encoded ciphertext (includes GCM auth tag)
    """
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(
        nonce,
        plaintext.encode("utf-8"),
        None
    )
    return {
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode()
    }


# =======================
# HANDSHAKE AUTH
# =======================

async def perform_handshake(websocket):
    """
    Performs shared-secret handshake authentication with the server.

    Protocol:
    1. Receives a random challenge from the server.
    2. Computes SHA-256(challenge + HANDSHAKE_SECRET).
    3. Sends the hash back to the server.
    4. Waits for authentication result.

    This proves to the server that this client knows the shared secret
    without transmitting the secret itself (zero-knowledge proof concept).

    Args:
        websocket: The WebSocket connection to authenticate on.

    Returns:
        bool: True if handshake succeeded, False otherwise.
    """
    try:
        # Step 1: Receive challenge from server
        challenge_raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        challenge_data = json.loads(challenge_raw)

        if challenge_data.get("type") != "auth_challenge":
            print("[AUTH] Unexpected message during handshake")
            return False

        challenge = challenge_data.get("challenge")
        print(f"[AUTH] Received challenge: {challenge[:8]}...")

        # Step 2: Compute response hash
        response_hash = hashlib.sha256(
            (challenge + HANDSHAKE_SECRET).encode('utf-8')
        ).hexdigest()

        # Step 3: Send response
        await websocket.send(json.dumps({
            "type": "auth_response",
            "hash": response_hash
        }))
        print("[AUTH] Sent handshake response")

        # Step 4: Wait for result
        result_raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        result = json.loads(result_raw)

        if result.get("type") == "auth_result" and result.get("status") == "OK":
            print(f"[AUTH] ✅ {result.get('message')}")
            return True
        else:
            print(f"[AUTH] ❌ {result.get('message', 'Authentication failed')}")
            return False

    except asyncio.TimeoutError:
        print("[AUTH] Handshake timed out")
        return False
    except Exception as e:
        print(f"[AUTH] Handshake error: {e}")
        return False


# =======================
# SERIAL SETUP
# =======================

def setup_serial():
    """
    Opens a serial connection to the ESP32 glove.

    Attempts to connect to the configured SERIAL_PORT at the configured
    BAUD_RATE. Returns None if the connection fails (e.g., device not
    plugged in).

    Returns:
        serial.Serial or None: The serial connection, or None on failure.
    """
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"[SERIAL] Connected to {SERIAL_PORT}")
        return ser
    except serial.SerialException as e:
        print(f"[SERIAL ERROR] Could not connect: {e}")
        return None


# =======================
# RECEIVE MESSAGES
# =======================

async def receive_messages(websocket, current_room):
    """
    Listens for incoming chat messages from the server and displays them.

    Handles two message types:
    - 'chat_message': Displays the decrypted text with sender and timestamp
    - 'room_joined': Updates the current room reference

    Args:
        websocket: Active WebSocket connection.
        current_room (list): Mutable single-element list holding current room name.
    """
    try:
        async for message in websocket:
            data = json.loads(message)
            if data.get("type") == "chat_message":
                print(f"\n[CHAT] [{data.get('room', 'unknown')}] {data['text']}")
                print(f"        From: {data.get('sender', 'Unknown')} | Time: {data.get('timestamp')}")
            elif data.get("type") == "room_joined":
                print(f"[ROOM] Joined room: {data['room']}")
                current_room[0] = data['room']
    except Exception as e:
        print(f"[RECEIVE ERROR] {e}")


# =======================
# SEND MANUAL MESSAGES
# =======================

async def send_manual_messages(websocket, current_room, stop_event):
    """
    Interactive input loop for sending manual messages from the keyboard.

    Commands:
    - /join <room>  : Switch to a different chat room
    - /exit         : Disconnect and quit
    - /shutdown     : Send shutdown command to server
    - Any other text: Encrypt and send as CTAP_MSG

    Args:
        websocket: Active WebSocket connection.
        current_room (list): Mutable single-element list holding current room name.
        stop_event (asyncio.Event): Event to signal the main loop to stop.
    """
    loop = asyncio.get_event_loop()
    while True:
        try:
            message = await loop.run_in_executor(
                None, input,
                f"\n[{current_room[0]}] Enter message (or /join <room>, /exit, /shutdown): "
            )
            message = message.strip()
            if message:
                if message == "/exit":
                    print("[CLIENT] Exiting...")
                    stop_event.set()
                    break
                elif message.startswith("/join "):
                    room_name = message[6:].strip()
                    if room_name:
                        join_packet = {
                            "type": "join_room",
                            "room": room_name
                        }
                        await websocket.send(json.dumps(join_packet))
                        print(f"[ROOM] Requesting to join: {room_name}")
                    else:
                        print("[ERROR] Invalid room name")
                else:
                    print(f"[MANUAL] Sending: {message}")
                    payload = encrypt_message(message)
                    packet = {
                        "type": "CTAP_MSG",
                        "msg_id": str(uuid.uuid4()),
                        "timestamp": int(time.time()),
                        "payload": payload
                    }
                    await websocket.send(json.dumps(packet))
                    print(f"[MANUAL] Sent!")
        except Exception as e:
            print(f"[INPUT ERROR] {e}")


# =======================
# MAIN ASYNC LOOP
# =======================

async def main():
    """
    Main entry point for the CTAP client.

    Connects to the ESP32 glove via serial, then establishes a persistent
    WebSocket connection to the CTAP server. Performs handshake authentication,
    then runs three concurrent tasks:
    1. Serial reader: reads from ESP32, encrypts, sends to server
    2. Message receiver: listens for chat messages from server
    3. Manual input: allows keyboard input for testing/chat

    Includes automatic reconnection on connection loss.
    """
    ser = setup_serial()
    if not ser:
        return

    print(f"[WS] Connecting to {WS_SERVER}...")

    stop_event = asyncio.Event()

    # Persistent Connection Loop
    async for websocket in websockets.connect(WS_SERVER):
        print("[WS] Connected!")

        # --- HANDSHAKE AUTHENTICATION ---
        auth_ok = await perform_handshake(websocket)
        if not auth_ok:
            print("[CLIENT] Authentication failed. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            continue

        # Current room as mutable list
        current_room = ["default"]

        # Join default room
        join_packet = {
            "type": "join_room",
            "room": current_room[0]
        }
        await websocket.send(json.dumps(join_packet))

        # Start receiving messages
        receive_task = asyncio.create_task(receive_messages(websocket, current_room))
        # Start manual input
        manual_task = asyncio.create_task(send_manual_messages(websocket, current_room, stop_event))

        try:
            while not stop_event.is_set():
                # Read Serial (Run in executor to avoid blocking the event loop)
                if ser.in_waiting > 0:
                    line_bytes = await asyncio.get_event_loop().run_in_executor(None, ser.readline)

                    try:
                        plaintext = line_bytes.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        continue

                    # Ignore empty lines or debug messages
                    if not plaintext or "CTAP" in plaintext:
                        continue

                    print(f"[SERIAL] Sending: {plaintext}")

                    # Encrypt
                    payload = encrypt_message(plaintext)

                    # Construct Packet
                    packet = {
                        "type": "CTAP_MSG",
                        "msg_id": str(uuid.uuid4()),
                        "timestamp": int(time.time()),
                        "payload": payload
                    }

                    # Send
                    await websocket.send(json.dumps(packet))
                    print(f"[WS] Sent encrypted message")

                else:
                    # Small sleep to prevent high CPU usage
                    await asyncio.sleep(0.01)

        except websockets.ConnectionClosed:
            if not stop_event.is_set():
                print("[WS] Connection lost... retrying in 3 seconds")
                await asyncio.sleep(3)
                continue
        except Exception as e:
            if not stop_event.is_set():
                print(f"[ERROR] {e}")
                await asyncio.sleep(1)
                continue
        finally:
            receive_task.cancel()
            manual_task.cancel()
            try:
                await receive_task
                await manual_task
            except asyncio.CancelledError:
                pass

        # If stop event is set, break the connection loop
        if stop_event.is_set():
            print("[CLIENT] Disconnecting...")
            break


if __name__ == "__main__":
    asyncio.run(main())
