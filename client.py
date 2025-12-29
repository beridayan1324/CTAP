import serial
import asyncio
import websockets
import json
import time
import uuid
import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# =======================
# CONFIG
# =======================

SERIAL_PORT = "COM3"          # Windows: COM3 | Linux: /dev/ttyUSB0
BAUD_RATE = 115200
WS_SERVER = "ws://127.0.0.1:8765"

# =======================
# BINARY → HEBREW MAPPING
# =======================

BINARY_MAP = {
    "00001": "א",
    "00010": "ב",
    "00011": "ג",
    "00100": "ד",
    "00101": "ה",
    "00110": "ו",
    "00111": "ז",
    "01000": "ח",
    "01001": "ט",
    "01010": "י",
    "01011": "כ",
    "01100": "ל",
    "01101": "מ",
    "01110": "נ",
    "01111": "ס",
    "10000": "ע",
    "10001": "פ",
    "10010": "צ",
    "10011": "ק",
    "10100": "ר",
    "10101": "ש",
    "10110": "ת",
    "11111": " "   # space
}

# =======================
# AES ENCRYPTION
# =======================

AES_KEY = AESGCM.generate_key(bit_length=128)
aesgcm = AESGCM(AES_KEY)

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
# ==========================================
# SERIAL SETUP
# ==========================================
ser = serial.Serial(
    port=SERIAL_PORT,
    baudrate=BAUD_RATE,
    timeout=1
)
print("[CTAP] Serial connected")

def read_binary_sentence():
    try:
        line = ser.readline().decode().strip()
        if not line:
            return None
        # Example input: "00011 00001"
        return line.split()
    except Exception as e:
        print("[SERIAL ERROR]", e)
        return None
# =======================
# BINARY → TEXT
# =======================

def binary_to_text(binary_list):
    chars = []
    for b in binary_list:
        if b in BINARY_MAP:
            chars.append(BINARY_MAP[b])
        else:
            print("[WARN] Unknown binary:", b)
    return "".join(chars)


# =======================
# WEBSOCKET SEND
# =======================

async def send_ws_message(encrypted_payload):
    async with websockets.connect(WS_SERVER) as ws:
        packet = {
            "type": "CTAP_MSG",
            "msg_id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "payload": encrypted_payload
        }

        await ws.send(json.dumps(packet))
        print("[CTAP] Encrypted message sent")


# =======================
# MAIN LOOP
# =======================

async def main():
    print("[CTAP] Client running")

    while True:
        binary_sentence = read_binary_sentence()
        if not binary_sentence:
            await asyncio.sleep(0.01)
            continue

        print("[CTAP] Binary:", binary_sentence)

        plaintext = binary_to_text(binary_sentence)
        if not plaintext:
            continue

        print("[CTAP] Plaintext:", plaintext)

        encrypted = encrypt_message(plaintext)
        print("[CTAP] Encrypted payload ready")

        await send_ws_message(encrypted)


if __name__ == "__main__":
    asyncio.run(main())
