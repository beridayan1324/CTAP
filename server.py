import asyncio
import websockets
import json
import base64
import binascii
import uuid
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# =======================
# CONFIGURATION
# =======================

# Must match the Client's Key exactly!
FIXED_AES_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"

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
    """Decrypts the nonce and ciphertext from the JSON payload."""
    try:
        # 1. Decode Base64 to get raw bytes
        nonce = base64.b64decode(payload['nonce'])
        ciphertext = base64.b64decode(payload['ciphertext'])

        # 2. Decrypt using AES-GCM
        # The third argument is associated_data (None in this case)
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)

        # 3. Decode bytes to string
        return plaintext_bytes.decode('utf-8')
    except Exception as e:
        return f"[DECRYPTION FAILED] {e}"

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
    print(f"[SERVER] Client connected from {websocket.remote_address}")
    connected_clients.add(websocket)
    # Default room
    current_room = "default"
    if current_room not in rooms:
        rooms[current_room] = set()
    rooms[current_room].add(websocket)
    
    try:
        async for message in websocket:
            try:
                # 1. Parse JSON packet
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
                    print(f"[SERVER] {websocket.remote_address} joined room '{current_room}'")
                    # Notify client
                    await websocket.send(json.dumps({
                        "type": "room_joined",
                        "room": current_room
                    }))
                
                elif msg_type == "CTAP_MSG":
                    # 2. Extract payload
                    encrypted_payload = data.get("payload")
                    
                    if encrypted_payload:
                        # 3. Decrypt
                        decrypted_text = decrypt_payload(encrypted_payload)
                        
                        # Check for shutdown command
                        if decrypted_text == "/shutdown":
                            print(f"[SERVER] Shutdown command received from {websocket.remote_address}")
                            stop_event.set()
                            continue
                        
                        # 4. Broadcast to all in current room
                        broadcast_message = {
                            "type": "chat_message",
                            "text": decrypted_text,
                            "timestamp": data.get('timestamp'),
                            "msg_id": data.get('msg_id'),
                            "sender": str(websocket.remote_address),
                            "room": current_room
                        }
                        
                        for client in rooms.get(current_room, set()):
                            try:
                                await client.send(json.dumps(broadcast_message))
                            except:
                                pass  # Client might have disconnected
                        
                        # 5. Also print to server console
                        print("\n" + "="*50)
                        print(f"Room:    {current_room}")
                        print(f"Time:    {data.get('timestamp')}")
                        print(f"ID:      {data.get('msg_id')}")
                        print(f"Sender:  {websocket.remote_address}")
                        print(f"Message: {decrypted_text}")
                        print("="*50)
                    else:
                        print(f"[SERVER] Received raw/unknown message: {message}")
                
                elif msg_type == "web_msg":
                    # Plain text message from web client
                    text = data.get("text", "").strip()
                    if text:
                        # Check for shutdown
                        if text == "/shutdown":
                            print(f"[SERVER] Shutdown command received from {websocket.remote_address}")
                            stop_event.set()
                            continue
                        
                        # Broadcast
                        broadcast_message = {
                            "type": "chat_message",
                            "text": text,
                            "timestamp": int(time.time()),
                            "msg_id": str(uuid.uuid4()),
                            "sender": f"Web-{websocket.remote_address}",
                            "room": current_room
                        }
                        
                        for client in rooms.get(current_room, set()):
                            try:
                                await client.send(json.dumps(broadcast_message))
                            except:
                                pass
                        
                        print("\n" + "="*50)
                        print(f"Room:    {current_room}")
                        print(f"Sender:  Web-{websocket.remote_address}")
                        print(f"Message: {text}")
                        print("="*50)

            except json.JSONDecodeError:
                print(f"[SERVER] Received non-JSON message: {message}")

    except websockets.exceptions.ConnectionClosed:
        print(f"[SERVER] Client {websocket.remote_address} disconnected")
    finally:
        connected_clients.remove(websocket)
        # Remove from room
        if current_room in rooms and websocket in rooms[current_room]:
            rooms[current_room].remove(websocket)

# =======================
# MAIN LOOP
# =======================

async def main():
    # Start the server on port 8766
    async with websockets.serve(handler, "0.0.0.0", 8766):
        print("[SERVER] Listening on ws://0.0.0.0:8766...")
        await stop_event.wait()  # Wait for shutdown
        print("[SERVER] Shutting down...")

if __name__ == "__main__":
    
    asyncio.run(main())
        