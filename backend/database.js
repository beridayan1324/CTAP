const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const DB_PATH = path.join(__dirname, 'ctap_audit.db');

const initDatabase = () => {
    return new Promise((resolve, reject) => {
        const db = new sqlite3.Database(DB_PATH, (err) => {
            if (err) {
                console.error('[DB ERROR] Failed to connect to database:', err);
                return reject(err);
            }
            console.log('[DB] Connected to SQLite database.');

            db.serialize(() => {
                db.run(`
                    CREATE TABLE IF NOT EXISTS connections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_address TEXT NOT NULL,
                        event_type TEXT NOT NULL CHECK(event_type IN ('CONNECT', 'DISCONNECT', 'AUTH_SUCCESS', 'AUTH_FAIL')),
                        room TEXT DEFAULT 'default',
                        timestamp TEXT NOT NULL
                    )
                `);

                db.run(`
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        msg_id TEXT UNIQUE NOT NULL,
                        sender_address TEXT NOT NULL,
                        room TEXT NOT NULL,
                        msg_hash TEXT NOT NULL,
                        msg_type TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                `);

                db.run(`
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL
                    )
                `, () => {
                    resolve(db);
                });
            });
        });
    });
};

const logConnection = (db, clientAddress, eventType, room = 'default') => {
    const timestamp = new Date().toISOString();
    db.run(
        'INSERT INTO connections (client_address, event_type, room, timestamp) VALUES (?, ?, ?, ?)',
        [String(clientAddress), eventType, room, timestamp],
        (err) => {
            if (err) console.error('[DB ERROR] Failed to log connection:', err);
        }
    );
};

const logMessage = (db, msgId, senderAddress, room, msgHash, msgType) => {
    const timestamp = new Date().toISOString();
    db.run(
        'INSERT OR IGNORE INTO messages (msg_id, sender_address, room, msg_hash, msg_type, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
        [msgId, String(senderAddress), room, msgHash, msgType, timestamp],
        (err) => {
            if (err) console.error('[DB ERROR] Failed to log message:', err);
        }
    );
};

module.exports = {
    initDatabase,
    logConnection,
    logMessage
};
