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
app.use(cors());
app.use(express.json());

const JWT_SECRET = process.env.JWT_SECRET || 'CTAP-SUPER-SECRET-JWT-KEY-2026';
const SERVER_PORT = 8766;

let db;

// =======================
// REST API (Auth & Audit)
// =======================
app.post('/register', (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) return res.status(400).json({ error: 'Username and password required' });

    bcrypt.hash(password, 10, (err, hash) => {
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

app.post('/login', (req, res) => {
    const { username, password } = req.body;
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

const queryDbSocket = (command) => {
    return new Promise((resolve, reject) => {
        const net = require('net');
        const client = new net.Socket();
        let buffer = '';
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

app.get('/audit/logs', verifyToken, async (req, res) => {
    try {
        const data = await queryDbSocket('GET_LOGS');
        res.json(data);
    } catch (e) {
        res.status(500).json({ error: 'Database error' });
    }
});

app.get('/audit/connections', verifyToken, async (req, res) => {
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
const wss = new WebSocket.Server({ server });

const connectedClients = new Set();
const rooms = {}; // room_name -> set of websockets

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
            const data = JSON.parse(message);
            const msgType = data.type;

            // Handle Handshake Response
            if (msgType === 'auth_response' && !ws.isHandshakeAuthenticated) {
                const responseHash = data.hash;
                if (verifyHandshakeHash(challenge, responseHash)) {
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
                const newRoom = data.room || 'default';
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
                if (encryptedPayload) {
                    const decryptedText = decryptPayload(encryptedPayload);
                    const msgId = data.msg_id || uuidv4();
                    const timestamp = data.timestamp || Math.floor(Date.now() / 1000);
                    
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
                const text = (data.text || '').trim();
                const userName = (data.username || `Web-${clientAddress}`);
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
            console.error(`[SERVER] Received invalid message: ${message}`, e);
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
        console.error(`[TCP] Socket error:`, err.message);
    });
});

initDatabase().then((database) => {
    db = database;
    server.listen(SERVER_PORT, '0.0.0.0', () => {
        console.log(`[SERVER] Listening on http://0.0.0.0:${SERVER_PORT}...`);
        console.log(`[SERVER] WebSocket Handshake auth: ENABLED`);
        console.log(`[SERVER] Audit trail DB: local sqlite3`);
    });

    tcpServer.listen(8767, '0.0.0.0', () => {
        console.log(`[TCP SERVER] Raw socket interface listening on port 8767`);
    });
}).catch(err => {
    console.error('Failed to initialize db', err);
    process.exit(1);
});
