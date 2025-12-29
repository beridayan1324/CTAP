import asyncio
import websockets
import json
import base64
import binascii
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
# WEBSOCKET HANDLER
# =======================

async def handler(websocket):
    print(f"[SERVER] Client connected from {websocket.remote_address}")
    try:
        async for message in websocket:
            try:
                # 1. Parse JSON packet
                data = json.loads(message)
                
                # 2. Extract payload
                encrypted_payload = data.get("payload")
                
                if encrypted_payload:
                    # 3. Decrypt
                    decrypted_text = decrypt_payload(encrypted_payload)
                    
                    # 4. Print Result
                    print("\n" + "="*30)
                    print(f"Time:    {data.get('timestamp')}")
                    print(f"ID:      {data.get('msg_id')}")
                    print(f"Message: {decrypted_text}")
                    print("="*30)
                else:
                    print(f"[SERVER] Received raw/unknown message: {message}")

            except json.JSONDecodeError:
                print(f"[SERVER] Received non-JSON message: {message}")

    except websockets.exceptions.ConnectionClosed:
        print("[SERVER] Client disconnected")

# =======================
# MAIN LOOP
# =======================

async def main():
    # Start the server on port 8765
    async with websockets.serve(handler, "0.0.0.0", 8765):
        print("[SERVER] Listening on ws://0.0.0.0:8765...")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")