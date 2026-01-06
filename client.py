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
WS_SERVER = "ws://10.0.0.14:8766"

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
# RECEIVE MESSAGES
# =======================

async def receive_messages(websocket, current_room):
    """Listen for incoming chat messages and display them."""
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
    """Allow user to input messages manually."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            message = await loop.run_in_executor(None, input, f"\n[{current_room[0]}] Enter message (or /join <room>, /exit, /shutdown): ")
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
                    # Encrypt
                    payload = encrypt_message(message)
                    # Construct Packet
                    packet = {
                        "type": "CTAP_MSG",
                        "msg_id": str(uuid.uuid4()),
                        "timestamp": int(time.time()),
                        "payload": payload
                    }
                    # Send
                    await websocket.send(json.dumps(packet))
                    print(f"[MANUAL] Sent!")
        except Exception as e:
            print(f"[INPUT ERROR] {e}")

# =======================
# MAIN ASYNC LOOP
# =======================

async def main():
    ser = setup_serial()
    if not ser:
        return

    print(f"[WS] Connecting to {WS_SERVER}...")

    stop_event = asyncio.Event()

    # Persistent Connection Loop
    async for websocket in websockets.connect(WS_SERVER):
        print("[WS] Connected!")
        
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

                    print(f"[SERIAL] Sending: {plaintext}")

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
