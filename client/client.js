const WebSocket = require('ws');
const serialport = require('serialport');
const { ReadlineParser } = require('@serialport/parser-readline');
const crypto = require('crypto');
const readline = require('readline');
const { v4: uuidv4 } = require('uuid');

// =======================
// CONFIGURATION
// =======================
const SERIAL_PORT_NAME = "COM3"; // Or /dev/ttyUSB0
const BAUD_RATE = 115200;
const WS_SERVER = "ws://localhost:8766";
const HANDSHAKE_SECRET = "CTAP-GLOVE-AUTH-2026";
const FIXED_AES_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f";
const AES_KEY = Buffer.from(FIXED_AES_KEY_HEX, 'hex');

const encryptPayload = (plaintext) => {
    const nonce = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', AES_KEY, nonce);
    
    const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    
    const ciphertextWithTag = Buffer.concat([ciphertext, tag]);

    return {
        nonce: nonce.toString('base64'),
        ciphertext: ciphertextWithTag.toString('base64')
    };
};

const verifyHandshakeHash = (challenge) => {
    return crypto.createHash('sha256')
        .update(challenge + HANDSHAKE_SECRET)
        .digest('hex');
};

let currentRoom = 'default';

const connectWebSocket = (serialPort) => {
    console.log(`[WS] Connecting to ${WS_SERVER}...`);
    const ws = new WebSocket(WS_SERVER);

    ws.on('open', () => {
        console.log('[WS] Connected!');
    });

    ws.on('message', (message) => {
        try {
            const data = JSON.parse(message);
            if (data.type === 'auth_challenge') {
                const responseHash = verifyHandshakeHash(data.challenge);
                ws.send(JSON.stringify({ type: 'auth_response', hash: responseHash }));
                console.log('[AUTH] Sent handshake response');
            } else if (data.type === 'auth_result') {
                if (data.status === 'OK') {
                    console.log(`[AUTH] ✅ ${data.message}`);
                    ws.send(JSON.stringify({ type: 'join_room', room: currentRoom }));
                } else {
                    console.log(`[AUTH] ❌ ${data.message}`);
                }
            } else if (data.type === 'chat_message') {
                console.log(`\n[CHAT] [${data.room}] ${data.text}`);
                console.log(`        From: ${data.sender} | Time: ${data.timestamp}`);
            } else if (data.type === 'room_joined') {
                console.log(`[ROOM] Joined room: ${data.room}`);
                currentRoom = data.room;
            }
        } catch (e) {
            console.error('[WS] Message error', e);
        }
    });

    ws.on('close', () => {
        console.log('[WS] Connection closed, retrying in 3 seconds...');
        setTimeout(() => connectWebSocket(serialPort), 3000);
    });

    ws.on('error', (err) => {
        console.log('[WS] Connection error');
    });

    return ws;
};

const setupSerial = () => {
    try {
        const port = new serialport.SerialPort({ path: SERIAL_PORT_NAME, baudRate: BAUD_RATE }, (err) => {
            if (err) {
                console.log(`[SERIAL] Not connected: ${err.message}`);
            }
        });
        
        const parser = port.pipe(new ReadlineParser({ delimiter: '\n' }));
        return { port, parser };
    } catch (e) {
        console.log('[SERIAL] Error initializing serial port');
        return {};
    }
};

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

const start = () => {
    const { port, parser } = setupSerial();
    let ws = connectWebSocket(port);

    if (parser) {
        parser.on('data', (line) => {
            const plaintext = line.trim();
            if (plaintext && !plaintext.includes('CTAP')) {
                console.log(`[SERIAL] Sending: ${plaintext}`);
                const payload = encryptPayload(plaintext);
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        type: 'CTAP_MSG',
                        msg_id: uuidv4(),
                        timestamp: Math.floor(Date.now() / 1000),
                        payload
                    }));
                }
            }
        });
    }

    rl.on('line', (line) => {
        const message = line.trim();
        if (!message) return;

        if (message === '/exit') {
            console.log('[CLIENT] Exiting...');
            process.exit(0);
        } else if (message.startsWith('/join ')) {
            const roomName = message.substring(6).trim();
            if (roomName && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'join_room', room: roomName }));
                console.log(`[ROOM] Requesting to join: ${roomName}`);
            }
        } else {
            console.log(`[MANUAL] Sending: ${message}`);
            const payload = encryptPayload(message);
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'CTAP_MSG',
                    msg_id: uuidv4(),
                    timestamp: Math.floor(Date.now() / 1000),
                    payload
                }));
            }
        }
    });
};

start();
