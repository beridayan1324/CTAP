require('dotenv').config();
const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const cors = require('cors');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');
const { initDatabase, logConnection, logMessage } = require('./database');
const { decryptPayload, verifyHandshakeHash, generateChallenge, generateHash } = require('./cryptoUtils');

const app = express();

// Restrict CORS to known origins
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || 'http://localhost:5173').split(',');
app.use(cors({
    origin: (origin, callback) => {
        // Allow requests with no origin (e.g. mobile apps, curl) only in dev
        if (!origin || ALLOWED_ORIGINS.includes(origin)) {
            callback(null, true);
        } else {
            callback(new Error('Not allowed by CORS'));
        }
    },
    methods: ['GET', 'POST'],
    allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(express.json({ limit: '16kb' }));

const JWT_SECRET = process.env.JWT_SECRET;
if (!JWT_SECRET) {
    throw new Error('[FATAL] JWT_SECRET environment variable is not set');
}
const SERVER_PORT = process.env.SERVER_PORT || 8766;

// Simple in-memory rate limiter
const rateLimitMap = new Map();
const RATE_LIMIT_WINDOW_MS = 60 * 1000; // 1 minute
const RATE_LIMIT_MAX = 10;

const rateLimit = (req, res, next) => {
    const ip = req.socket.remoteAddress;
    const now = Date.now();
    const entry = rateLimitMap.get(ip) || { count: 0, start: now };
    if (now - entry.start > RATE_LIMIT_WINDOW_MS) {
        entry.count = 1;
        entry.start = now;
    } else {
        entry.count++;
    }
    rateLimitMap.set(ip, entry);
    if (entry.count > RATE_LIMIT_MAX) {
        return res.status(429).json({ error: 'Too many requests, please try again later.' });
    }
    next();
};

let db;

// Input validation helpers
const USERNAME_REGEX = /^[a-zA-Z0-9_\-]{3,32}$/;
const PASSWORD_MIN_LEN = 8;
const PASSWORD_MAX_LEN = 128;

// =======================
// REST API (Auth & Audit)
// =======================
app.post('/register', rateLimit, (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) return res.status(400).json({ error: 'Username and password required' });

    if (!USERNAME_REGEX.test(username)) {
        return res.status(400).json({ error: 'Username must be 3-32 alphanumeric characters (underscores and hyphens allowed)' });
    }
    if (typeof password !== 'string' || password.length < PASSWORD_MIN_LEN || password.length > PASSWORD_MAX_LEN) {
        return res.status(400).json({ error: `Password must be between ${PASSWORD_MIN_LEN} and ${PASSWORD_MAX_LEN} characters` });
    }

    bcrypt.hash(password, 12, (err, hash) => {
        if (err) return res.status(500).json({ error: 'Error hashing password' });

        db.run('INSERT INTO users (username, password) VALUES (?, ?)', [username, hash], function (err) {
            if (err) {
                if (err.message.includes('UNIQUE')) return res.status(400).json({ error: 'Username already exists' });
                return res.status(500).json({ error: 'Database error' });
            }
            res.json({ message: 'User registered successfully' });
        });
    });
});

app.post('/login', rateLimit, (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) return res.status(400).json({ error: 'Username and password required' });

    if (!USERNAME_REGEX.test(username)) {
        return res.status(400).json({ error: 'Invalid username or password' });
    }
    if (typeof password !== 'string' || password.length < PASSWORD_MIN_LEN || password.length > PASSWORD_MAX_LEN) {
        return res.status(400).json({ error: 'Invalid username or password' });
    }

    db.get('SELECT * FROM users WHERE username = ?', [username], (err, user) => {
        if (err || !user) return res.status(400).json({ error: 'Invalid username or password' });

        bcrypt.compare(password, user.password, (err, isMatch) => {
            if (err || !isMatch) return res.status(400).json({ error: 'Invalid username or password' });

            const token = jwt.sign({ id: user.id, username: user.username }, JWT_SECRET, { expiresIn: '1d' });
            res.json({ token, username: user.username });
        });
    });
});

const verifyToken = (req, res, next) => {
    const token = req.headers['authorization']?.split(' ')[1];
    if (!token) return res.status(401).json({ error: 'Unauthenticated' });
    jwt.verify(token, JWT_SECRET, (err, decoded) => {
        if (err) return res.status(401).json({ error: 'Invalid token' });
        req.user = decoded;
        next();
    });
};

// Admin role check middleware
const requireAdmin = (req, res, next) => {
    if (!req.user || req.user.role !== 'admin') {
        return res.status(403).json({ error: 'Forbidden: admin access required' });
    }
    next();
};

const queryDbSocket = (command) => {
    return new Promise((resolve, reject) => {
        const net = require('net');
        const client = new net.Socket();
        let buffer = '';
        // Only allow specific whitelisted commands
        const ALLOWED_COMMANDS = ['GET_LOGS', 'GET_CONNS'];
        if (!ALLOWED_COMMANDS.includes(command)) {
            return reject(new Error('Invalid command'));
        }
        client.connect(8767, '127.0.0.1', () => {
            client.write(command + '\n');
        });
        client.on('data', (data) => {
            buffer += data.toString();
        });
        client.on('end', () => {
            try {
                const jsonStart = buffer.indexOf('[');
                if (jsonStart !== -1) {
                    resolve(JSON.parse(buffer.substring(jsonStart)));
                } else {
                    resolve([]);
                }
            } catch (e) {
                reject(e);
            }
        });
        client.on('error', reject);
    });
};

app.get('/audit/logs', verifyToken, requireAdmin, async (req, res) => {
    try {
        const data = await queryDbSocket('GET_LOGS');
        res.json(data);
    } catch (e) {
        res.status(500).json({ error: 'Database error' });
    }
});

app.get('/audit/connections', verifyToken, requireAdmin, async (req, res) => {
    try {
        const data = await queryDbSocket('GET_CONNS');
        res.json(data);
    } catch (e) {
        res.status(500).json({ error: 'Database error' });
    }
});

// =======================
// WEBSOCKET SERVER
// =======================
const server = http.createServer(app);
const wss = new WebSocket.Server({
    server,
    verifyClient: (info) => {
        const origin = info.origin || info.req.headers['origin'];
        if (!origin || ALLOWED_ORIGINS.includes(origin)) {
            return true;
        }
        return false;
    }
});

const connectedClients = new Set();
const rooms = {}; // room_name -> set of websockets

const ROOM_NAME_REGEX = /^[a-zA-Z0-9_\-]{1,64}$/;
const MAX_MESSAGE_LENGTH = 4096;

wss.on('connection', async (ws, req) => {
    const clientAddress = req.socket.remoteAddress + ':' + req.socket.remotePort;
    console.log(`[SERVER] Client connected from ${clientAddress}`);
    
    // Auth State
    ws.isHandshakeAuthenticated = false;

    // Send handshake challenge immediately
    const challenge = generateChallenge();
    ws.send(JSON.stringify({ type: 'auth_challenge', challenge }));

    // Timeout handshake
    const authTimeout = setTimeout(() => {
        if (!ws.isHandshakeAuthenticated) {
            console.log(`[AUTH] Handshake TIMEOUT for ${clientAddress}`);
            logConnection(db, clientAddress, 'AUTH_FAIL');
            ws.close();
        }
    }, 5000);

    let currentRoom = 'default';
    connectedClients.add(ws);

    if (!rooms[currentRoom]) rooms[currentRoom] = new Set();
    rooms[currentRoom].add(ws);

    ws.on('message', (message) => {
        try {
            // Guard against oversized messages
            if (message.length > MAX_MESSAGE_LENGTH * 2) {
                console.warn(`[SERVER] Oversized message from ${clientAddress}, ignoring.`);
                return;
            }

            let data;
            try {
                data = JSON.parse(message);
            } catch (parseErr) {
                console.warn(`[SERVER] Invalid JSON from ${clientAddress}`);
                return;
            }

            if (typeof data !== 'object' || data === null || Array.isArray(data)) {
                console.warn(`[SERVER] Unexpected message shape from ${clientAddress}`);
                return;
            }

            const msgType = data.type;

            // Handle Handshake Response
            if (msgType === 'auth_response' && !ws.isHandshakeAuthenticated) {
                const responseHash = data.hash;
                if (typeof responseHash === 'string' && verifyHandshakeHash(challenge, responseHash)) {
                    ws.isHandshakeAuthenticated = true;
                    clearTimeout(authTimeout);
                    console.log(`[AUTH] Handshake SUCCESS for ${clientAddress}`);
                    ws.send(JSON.stringify({ type: 'auth_result', status: 'OK', message: 'Authentication successful.' }));
                    logConnection(db, clientAddress, 'AUTH_SUCCESS', currentRoom);
                    logConnection(db, clientAddress, 'CONNECT', currentRoom);
                } else {
                    console.log(`[AUTH] Handshake FAILED for ${clientAddress} - bad hash`);
                    ws.send(JSON.stringify({ type: 'auth_result', status: 'FAIL', message: 'Authentication failed. Invalid secret.' }));
                    ws.close();
                }
                return;
            }

            if (!ws.isHandshakeAuthenticated) return;

            // Normal Messaging
            if (msgType === 'join_room') {
                const newRoom = (data.room || 'default').toString().trim();
                if (!ROOM_NAME_REGEX.test(newRoom)) {
                    ws.send(JSON.stringify({ type: 'error', message: 'Invalid room name.' }));
                    return;
                }
                if (rooms[currentRoom] && rooms[currentRoom].has(ws)) {
                    rooms[currentRoom].delete(ws);
                }
                currentRoom = newRoom;
                if (!rooms[currentRoom]) rooms[currentRoom] = new Set();
                rooms[currentRoom].add(ws);
                console.log(`[SERVER] ${clientAddress} joined room '${currentRoom}'`);
                ws.send(JSON.stringify({ type: 'room_joined', room: currentRoom }));
            } 
            else if (msgType === 'CTAP_MSG') {
                const encryptedPayload = data.payload;
                if (encryptedPayload && typeof encryptedPayload === 'object') {
                    const decryptedText = decryptPayload(encryptedPayload);
                    if (typeof decryptedText !== 'string' || decryptedText.length > MAX_MESSAGE_LENGTH) {
                        console.warn(`[SERVER] Decrypted message too long or invalid from ${clientAddress}`);
                        return;
                    }
                    const msgId = typeof data.msg_id === 'string' ? data.msg_id.substring(0, 64) : uuidv4();
                    const timestamp = typeof data.timestamp === 'number' ? data.timestamp : Math.floor(Date.now() / 1000);
                    
                    const msgHash = generateHash(decryptedText);
                    logMessage(db, msgId, clientAddress, currentRoom, msgHash, 'CTAP_MSG');

                    if (decryptedText === '/shutdown') {
                        console.log(`[SERVER] Shutdown command received from ${clientAddress}`);
                        process.exit(0);
                    }

                    const broadcastMessage = {
                        type: 'chat_message',
                        text: decryptedText,
                        timestamp,
                        msg_id: msgId,
                        sender: clientAddress,
                        room: currentRoom
                    };

                    for (const client of rooms[currentRoom] || []) {
                        if (client.readyState === WebSocket.OPEN) {
                            client.send(JSON.stringify(broadcastMessage));
                        }
                    }

                    console.log(`\n==================================================`);
                    console.log(`Room:    ${currentRoom}`);
                    console.log(`Time:    ${timestamp}`);
                    console.log(`ID:      ${msgId}`);
                    console.log(`Sender:  ${clientAddress}`);
                    console.log(`Message: ${decryptedText}`);
                    console.log(`==================================================`);
                }
            }
            else if (msgType === 'web_msg') {
                const text = (typeof data.text === 'string' ? data.text : '').trim().substring(0, MAX_MESSAGE_LENGTH);
                const rawUsername = typeof data.username === 'string' ? data.username : `Web-${clientAddress}`;
                const userName = rawUsername.substring(0, 64);
                if (text) {
                    const msgId = uuidv4();
                    const timestamp = Math.floor(Date.now() / 1000);
                    const msgHash = generateHash(text);
                    logMessage(db, msgId, userName, currentRoom, msgHash, 'web_msg');

                    if (text === '/shutdown') {
                        console.log(`[SERVER] Shutdown command received from ${clientAddress}`);
                        process.exit(0);
                    }

                    const broadcastMessage = {
                        type: 'chat_message',
                        text: text,
                        timestamp,
                        msg_id: msgId,
                        sender: userName,
                        room: currentRoom
                    };

                    for (const client of rooms[currentRoom] || []) {
                        if (client.readyState === WebSocket.OPEN) {
                            client.send(JSON.stringify(broadcastMessage));
                        }
                    }

                    console.log(`\n==================================================`);
                    console.log(`Room:    ${currentRoom}`);
                    console.log(`Sender:  ${userName}`);
                    console.log(`Message: ${text}`);
                    console.log(`==================================================`);
                }
            }
        } catch (e) {
            console.error(`[SERVER] Error processing message from ${clientAddress}:`, e.message);
        }
    });

    ws.on('close', () => {
        console.log(`[SERVER] Client ${clientAddress} disconnected`);
        connectedClients.delete(ws);
        logConnection(db, clientAddress, 'DISCONNECT', currentRoom);
        if (rooms[currentRoom] && rooms[currentRoom].has(ws)) {
            rooms[currentRoom].delete(ws);
        }
    });
});

const net = require('net');

const tcpServer = net.createServer((socket) => {
    // Only accept connections from localhost
    if (socket.remoteAddress !== '127.0.0.1' && socket.remoteAddress !== '::1' && socket.remoteAddress !== '::ffff:127.0.0.1') {
        socket.destroy();
        return;
    }
    console.log(`[TCP] Client connected from ${socket.remoteAddress}:${socket.remotePort}`);
    socket.write('CTAP_SYS RAW DB SOCKET UPLINK\n');
    socket.write('Commands: GET_LOGS, GET_CONNS, EXIT\n');
    
    socket.on('data', (data) => {
        try {
            const command = data.toString().trim();
            if (command === 'GET_LOGS') {
                db.all('SELECT * FROM messages ORDER BY timestamp DESC LIMIT 100', (err, rows) => {
                    if (err) return socket.write(`ERROR: ${err.message}\n`);
                    socket.write(JSON.stringify(rows) + '\n');
                    socket.end();
                });
            } else if (command === 'GET_CONNS') {
                db.all('SELECT * FROM connections ORDER BY timestamp DESC LIMIT 100', (err, rows) => {
                    if (err) return socket.write(`ERROR: ${err.message}\n`);
                    socket.write(JSON.stringify(rows) + '\n');
                    socket.end();
                });
            } else if (command === 'QUIT' || command === 'EXIT') {
                socket.end('Goodbye.\n');
            } else {
                socket.write('COMMAND_UNKNOWN. Try: GET_LOGS, GET_CONNS, EXIT\n');
            }
        } catch (e) {
            socket.write('ERROR: Invalid data\n');
        }
    });

    socket.on('close', () => {
        console.log(`[TCP] Client disconnected`);
    });

    socket.on('error', (err) => {
        console.error(`[TCP] Socket error: ${err.message}`);
    });
});

initDatabase().then((database) => {
    db = database;
    server.listen(SERVER_PORT, () => {
        console.log(`[SERVER] HTTP/WS server running on port ${SERVER_PORT}`);
    });
    tcpServer.listen(8767, '127.0.0.1', () => {
        console.log(`[TCP] Internal DB socket listening on 127.0.0.1:8767`);
    });
}).catch((err) => {
    console.error('[FATAL] Failed to initialize database:', err);
    process.exit(1);
});
