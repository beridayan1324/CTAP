# CTAP Chat System

A real-time chat application with room support, featuring both web and Python clients with serial input capability.

## Features

- **Real-time messaging** with WebSocket connections
- **Room-based chat** - join/create different chat rooms
- **Web interface** with modern UI
- **Serial input support** for hardware integration (ESP32)
- **Encrypted communication** for Python clients
- **Cross-platform** - works on desktop and mobile

## Setup

1. **Install dependencies:**
   ```bash
   pip install websockets cryptography pyserial
   ```

2. **Start the server:**
   ```bash
   python server.py
   ```

3. **Start the web server (for web interface):**
   ```bash
   python -m http.server 8000
   ```

## Usage

### Web Interface
- Open `http://localhost:8000` in a Chrome-based browser
- Join a room by entering the room name
- Connect to serial port (ESP32) using the "Connect Serial" button
- Send messages manually or receive from serial

### Python Client
- Run `python client.py` for console-based client with serial support
- Use `/join <room>` to switch rooms
- Type `/exit` to quit, `/shutdown` to stop server

## Serial Setup

- Connect your ESP32 to COM3 (Windows) or /dev/ttyUSB0 (Linux)
- Baud rate: 115200
- Messages sent from ESP32 will appear in chat

## Browser Requirements

- **Web Serial API** requires Chrome, Edge, or Opera
- Enable "Experimental Web Platform features" in chrome://flags for Serial API

## Architecture

- **server.py**: WebSocket server handling connections, rooms, and message routing
- **client.py**: Python client with encryption and serial reading
- **index.html**: Web-based chat interface with Serial API integration