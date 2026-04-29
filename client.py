"""
client.py — CTAP Python Console Client
========================================
Console-based client for the CTAP system. OOP structure: :class:`GloveTransportCrypto`,
:class:`CTAPHardwareClient`. Reads from serial (UART), encrypts with AES-256-GCM,
handshakes with shared secret, sends over WebSocket.

Author: CTAP Project
Date: 2026
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import os
import time
import uuid

import serial
import websockets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# =======================
# CONFIGURATION
# =======================

SERIAL_PORT = "COM3"  # Windows: COM3 | Linux: /dev/ttyUSB0
BAUD_RATE = 115200
WS_SERVER = "ws://10.0.0.14:8766"

FIXED_AES_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
HANDSHAKE_SECRET = "CTAP-GLOVE-AUTH-2026"


class GloveTransportCrypto:
    """AES-256-GCM for CTAP_MSG payloads (matches server :class:`backend.crypto_utils.CTAPCrypto`)."""

    __slots__ = ("_aesgcm",)

    def __init__(self, key_hex: str) -> None:
        key = binascii.unhexlify(key_hex)
        self._aesgcm = AESGCM(key)

    def encrypt_message(self, plaintext: str) -> dict:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(
            nonce,
            plaintext.encode("utf-8"),
            None,
        )
        return {
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }


class CTAPHardwareClient:
    """Server client: serial + WebSocket session with handshake and room commands."""

    __slots__ = (
        "_crypto",
        "_handshake_secret",
        "baud",
        "serial_port",
        "ws_server",
    )

    def __init__(
        self,
        ws_server: str,
        serial_port: str,
        baud: int,
        key_hex: str,
        handshake_secret: str,
    ) -> None:
        self.ws_server = ws_server
        self.serial_port = serial_port
        self.baud = baud
        self._crypto = GloveTransportCrypto(key_hex)
        self._handshake_secret = handshake_secret

    def setup_serial(self):
        try:
            ser = serial.Serial(self.serial_port, self.baud, timeout=1)
            print(f"[SERIAL] Connected to {self.serial_port}")
            return ser
        except serial.SerialException as e:
            print(f"[SERIAL ERROR] Could not connect: {e}")
            return None

    async def _perform_handshake(self, websocket) -> bool:
        try:
            challenge_raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            challenge_data = json.loads(challenge_raw)

            if challenge_data.get("type") != "auth_challenge":
                print("[AUTH] Unexpected message during handshake")
                return False

            challenge = challenge_data.get("challenge")
            print(f"[AUTH] Received challenge: {challenge[:8]}...")

            response_hash = hashlib.sha256(
                (challenge + self._handshake_secret).encode("utf-8")
            ).hexdigest()

            await websocket.send(
                json.dumps({"type": "auth_response", "hash": response_hash})
            )
            print("[AUTH] Sent handshake response")

            result_raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            result = json.loads(result_raw)

            if result.get("type") == "auth_result" and result.get("status") == "OK":
                print(f"[AUTH] ✅ {result.get('message')}")
                return True
            print(f"[AUTH] ❌ {result.get('message', 'Authentication failed')}")
            return False

        except asyncio.TimeoutError:
            print("[AUTH] Handshake timed out")
            return False
        except Exception as e:
            print(f"[AUTH] Handshake error: {e}")
            return False

    async def _receive_messages(self, websocket, current_room: list):
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("type") == "chat_message":
                    print(f"\n[CHAT] [{data.get('room', 'unknown')}] {data['text']}")
                    print(
                        f"        From: {data.get('sender', 'Unknown')} | Time: {data.get('timestamp')}"
                    )
                elif data.get("type") == "room_joined":
                    print(f"[ROOM] Joined room: {data['room']}")
                    current_room[0] = data["room"]
        except Exception as e:
            print(f"[RECEIVE ERROR] {e}")

    async def _send_manual_messages(self, websocket, current_room: list, stop_event: asyncio.Event):
        loop = asyncio.get_event_loop()
        while True:
            try:
                message = await loop.run_in_executor(
                    None,
                    input,
                    f"\n[{current_room[0]}] Enter message (or /join <room>, /exit, /shutdown): ",
                )
                message = message.strip()
                if message:
                    if message == "/exit":
                        print("[CLIENT] Exiting...")
                        stop_event.set()
                        break
                    if message.startswith("/join "):
                        room_name = message[6:].strip()
                        if room_name:
                            await websocket.send(
                                json.dumps({"type": "join_room", "room": room_name})
                            )
                            print(f"[ROOM] Requesting to join: {room_name}")
                        else:
                            print("[ERROR] Invalid room name")
                    else:
                        print(f"[MANUAL] Sending: {message}")
                        payload = self._crypto.encrypt_message(message)
                        packet = {
                            "type": "CTAP_MSG",
                            "msg_id": str(uuid.uuid4()),
                            "timestamp": int(time.time()),
                            "payload": payload,
                        }
                        await websocket.send(json.dumps(packet))
                        print("[MANUAL] Sent!")
            except Exception as e:
                print(f"[INPUT ERROR] {e}")

    async def run(self) -> None:
        ser = self.setup_serial()
        if not ser:
            return

        print(f"[WS] Connecting to {self.ws_server}...")
        stop_event = asyncio.Event()

        async for websocket in websockets.connect(self.ws_server):
            print("[WS] Connected!")

            auth_ok = await self._perform_handshake(websocket)
            if not auth_ok:
                print("[CLIENT] Authentication failed. Retrying in 5 seconds...")
                await asyncio.sleep(5)
                continue

            current_room = ["default"]
            await websocket.send(
                json.dumps({"type": "join_room", "room": current_room[0]})
            )

            receive_task = asyncio.create_task(
                self._receive_messages(websocket, current_room)
            )
            manual_task = asyncio.create_task(
                self._send_manual_messages(websocket, current_room, stop_event)
            )

            try:
                while not stop_event.is_set():
                    if ser.in_waiting > 0:
                        line_bytes = await asyncio.get_event_loop().run_in_executor(
                            None, ser.readline
                        )

                        try:
                            plaintext = line_bytes.decode("utf-8").strip()
                        except UnicodeDecodeError:
                            continue

                        if not plaintext or "CTAP" in plaintext:
                            continue

                        print(f"[SERIAL] Sending: {plaintext}")
                        payload = self._crypto.encrypt_message(plaintext)
                        packet = {
                            "type": "CTAP_MSG",
                            "msg_id": str(uuid.uuid4()),
                            "timestamp": int(time.time()),
                            "payload": payload,
                        }
                        await websocket.send(json.dumps(packet))
                        print("[WS] Sent encrypted message")

                    else:
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

            if stop_event.is_set():
                print("[CLIENT] Disconnecting...")
                break


try:
    _KEY_CHECK = binascii.unhexlify(FIXED_AES_KEY_HEX)
    AESGCM(_KEY_CHECK)
except Exception as _e:
    print(f"[ERROR] Invalid Key: {_e}")
    raise SystemExit(1) from _e


async def main():
    client = CTAPHardwareClient(
        WS_SERVER,
        SERIAL_PORT,
        BAUD_RATE,
        FIXED_AES_KEY_HEX,
        HANDSHAKE_SECRET,
    )
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
