import asyncio
import websockets

async def handler(websocket):
    print("[SERVER] Client connected!")
    try:
        async for message in websocket:
            print(f"\n[SERVER] Received Message:\n{message}")
            print("-" * 30)
    except websockets.exceptions.ConnectionClosed:
        print("[SERVER] Client disconnected")

async def main():
    # Start the server on port 8765
    async with websockets.serve(handler, "127.0.0.1", 8765):
        print("[SERVER] Listening on ws://127.0.0.1:8765...")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped.")