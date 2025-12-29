import asyncio
import websockets
import json
import time
import uuid
import base64
import os
import serial
import binascii
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# =======================
# CONFIGURATION
# =======================

SERIAL_PORT = "COM3"          # Windows: COM3 | Linux: /dev/ttyUSB0
BAUD_RATE = 115200
WS_SERVER = "ws://10.0.0.6:8765"

# 32-byte Hex Key (Must match the server's key!)
FIXED_AES_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"

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
# SERIAL SETUP
# =======================

def setup_serial():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"[SERIAL] Connected to {SERIAL_PORT}")
        return ser
    except serial.SerialException as e:
        print(f"[SERIAL ERROR] Could not connect: {e}")
        return None

# =======================
# MAIN ASYNC LOOP
# =======================

async def main():
    ser = setup_serial()
    if not ser:
        return

    print(f"[WS] Connecting to {WS_SERVER}...")

    # Persistent Connection Loop
    async for websocket in websockets.connect(WS_SERVER):
        print("[WS] Connected!")
        try:
            while True:
                # 1. Read Serial (Run in executor to avoid blocking the event loop)
                # We check if data is waiting to prevent empty reads
                if ser.in_waiting > 0:
                    line_bytes = await asyncio.get_event_loop().run_in_executor(None, ser.readline)
                    
                    try:
                        # Decode the text sent by ESP32 (e.g., "hello world")
                        plaintext = line_bytes.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        continue

                    # Ignore empty lines or debug messages
                    if not plaintext or "CTAP" in plaintext:
                        continue

                    print(f"[SERIAL] Received Text: {plaintext}")

                    # 2. Encrypt
                    payload = encrypt_message(plaintext)

                    # 3. Construct Packet
                    packet = {
                        "type": "CTAP_MSG",
                        "msg_id": str(uuid.uuid4()),
                        "timestamp": int(time.time()),
                        "payload": payload
                    }

                    # 4. Send
                    await websocket.send(json.dumps(packet))
                    print(f"[WS] Sent: {plaintext} (Encrypted)")

                else:
                    # Small sleep to prevent high CPU usage
                    await asyncio.sleep(0.01)

        except websockets.ConnectionClosed:
            print("[WS] Connection lost... retrying in 3 seconds")
            await asyncio.sleep(3)
            continue
        except Exception as e:
            print(f"[ERROR] {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[CTAP] Client stopped.")