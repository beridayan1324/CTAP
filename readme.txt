# CTAP - Glove Communication System

## Project Overview

This project enables a smart glove to transmit text wirelessly to a remote display server securely. The glove captures finger taps, converts them into text (via ESP32), and sends the data to a Python client. The client encrypts the message and transmits it over WebSocket to a central server for display.

---

## Prerequisites

* **Hardware:**
* ESP32 with 4 Piezo sensors (CTAP Glove).
* Two Computers (PC #1 for Server, PC #2 for Client).
* USB Cable.


* **Software:**
* Python 3.7 or higher.
* WiFi connection (Both PCs must be on the same network).



---

## Installation

1. **Clone or Download** the project files to both computers.
2. **Install Dependencies:**
Open your terminal/command prompt in the project folder and run:
```bash
pip install pyserial websockets cryptography

```


*(Or if you have a `requirements.txt` file: `pip install -r requirements.txt`)*

---

## How to Run the Project

### Step 1: Start the Server (PC #1)

The server acts as the "Receiver." It waits for messages from the glove, decrypts them, and displays the text.

1. **Find the Local IP Address** of this computer:
* **Windows:** Open Command Prompt, type `ipconfig`, and copy the **IPv4 Address** (e.g., `10.0.0.6`).
* **Mac/Linux:** Open Terminal, type `ifconfig` or `ip a`.


2. **Run the Server Script:**
python server.py

3. **Verify:** You should see the message:
`[SERVER] Listening on 0.0.0.0:8765...`

### Step 2: Start the Client (PC #2)

The client connects to the glove, encrypts the text, and sends it to the server.

1. **Connect the Glove** to PC #2 via USB.
2. **Identify the COM Port:**
* **Windows:** Check Device Manager (e.g., `COM3`, `COM4`).
* **Linux/Mac:** Check `/dev/ttyUSB0` or similar.


3. **Configure the Client Script:**
Open `client.py` in a text editor and update these lines:
```python
# IP Address of PC #1 (Server)
WS_SERVER = "ws://10.0.0.6:8765" 

# USB Port for the Glove
SERIAL_PORT = "COM3" 

```


4. **Run the Client Script:**
python client.py
5. **Verify:** You should see `[SERIAL] Connected` and `[WS] Connected!`.

---

## Glove Controls

The glove translates binary finger combinations into English letters.

### Finger Mapping (Binary to Text)

* **Right Finger (001):** `a`
* **Middle Finger (010):** `b`
* **Left Finger (100):** `c`
* **Left + Right (101):** `d`
* **Middle + Right (011):** `e`
* **Left + Middle (110):** `f`
* **All Three (111):** `g`

### Control Sensor (4th Sensor)

* **1 Tap:** Adds a **Space** to the sentence.
* **3 Rapid Taps:** **SEND** the message to the server.

---

## Troubleshooting

* **Connection Refused:**
* Ensure PC #1 (Server) has the Firewall configured to allow port `8765`.
* Ensure the `WS_SERVER` IP in `client.py` matches PC #1 exactly.


* **Serial Error:**
* Check if the Glove is plugged in.
* Ensure no other program (like Arduino IDE serial monitor) is using the port.


* **Decryption Failed:**
* Ensure both `server.py` and `client.py` are using the exact same `FIXED_AES_KEY_HEX`.
