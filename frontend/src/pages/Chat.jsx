import React, { useState, useEffect, useRef, useContext } from 'react';
import { AuthContext } from '../App';

// Escape HTML to prevent XSS when rendering message text
const escapeHtml = (str) => {
    if (typeof str !== 'string') return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#x27;');
};

const HANDSHAKE_SECRET = import.meta.env.VITE_HANDSHAKE_SECRET;

const Chat = () => {
    const { username } = useContext(AuthContext);
    const [ws, setWs] = useState(null);
    const [room, setRoom] = useState('default');
    const [roomInput, setRoomInput] = useState('');
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [status, setStatus] = useState('Connecting...');
    const [serialStatus, setSerialStatus] = useState('Offline');
    const messagesEndRef = useRef(null);

    let serialPortRef = useRef(null);
    let serialReaderRef = useRef(null);

    useEffect(() => {
        let isMounted = true;
        let socket = null;
        let reconnectTimeout = null;

        const connectWs = () => {
            socket = new WebSocket('ws://localhost:8766');

            socket.onopen = () => {
                if (isMounted) setStatus('Connected');
            };

            socket.onmessage = (event) => {
                if (!isMounted) return;
                let data;
                try {
                    data = JSON.parse(event.data);
                } catch (e) {
                    console.warn('[WS] Received invalid JSON');
                    return;
                }
                if (data.type === 'auth_challenge') {
                    (async () => {
                        const secret = HANDSHAKE_SECRET || "CTAP-GLOVE-AUTH-2026";
                        const encoder = new TextEncoder();
                        const dataBuffer = encoder.encode(data.challenge + secret);
                        const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
                        const hashArray = Array.from(new Uint8Array(hashBuffer));
                        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
                        socket.send(JSON.stringify({ type: 'auth_response', hash: hashHex }));
                    })();
                } else if (data.type === 'auth_result') {
                    if (data.status === 'OK') {
                        socket.send(JSON.stringify({ type: 'join_room', room: 'default' }));
                    }
                } else if (data.type === 'chat_message') {
                    setMessages(prev => [...prev, data]);
                } else if (data.type === 'room_joined') {
                    setRoom(data.room);
                    setMessages([{ type: 'system', text: `>> Joined Room: ${escapeHtml(data.room)}` }]);
                }
            };

            socket.onclose = () => {
                if (isMounted) {
                    setStatus('Disconnected');
                    reconnectTimeout = setTimeout(connectWs, 3000);
                }
            };
            
            if (isMounted) setWs(socket);
        };

        connectWs();

        return () => {
            isMounted = false;
            if (reconnectTimeout) clearTimeout(reconnectTimeout);
            if (socket) socket.close();
            disconnectSerial();
        };
    }, []);

    const joinRoom = () => {
        if (roomInput.trim() && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'join_room', room: roomInput.trim() }));
            setRoomInput('');
        }
    };

    const sendMessage = () => {
        if (input.trim() && ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'web_msg', text: input.trim(), username }));
            setInput('');
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter') sendMessage();
    };

    const toggleSerial = async () => {
        if (serialPortRef.current) {
            await disconnectSerial();
        } else {
            await connectSerial();
        }
    };

    const connectSerial = async () => {
        try {
            const port = await navigator.serial.requestPort();
            await port.open({ baudRate: 115200 });
            serialPortRef.current = port;
            setSerialStatus('Connected');
            readSerial();
        } catch (error) {
            setSerialStatus('Error: No device');
        }
    };

    const disconnectSerial = async () => {
        if (serialReaderRef.current) {
            await serialReaderRef.current.cancel();
            serialReaderRef.current = null;
        }
        if (serialPortRef.current) {
            await serialPortRef.current.close();
            serialPortRef.current = null;
        }
        setSerialStatus('Offline');
    };

    const readSerial = async () => {
        while (serialPortRef.current && serialPortRef.current.readable) {
            const reader = serialPortRef.current.readable.getReader();
            serialReaderRef.current = reader;
            const decoder = new TextDecoder();
            try {
                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n');
                    for (const line of lines) {
                        const plaintext = line.trim();
                        if (plaintext && !plaintext.includes('CTAP') && ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ type: 'web_msg', text: plaintext, username: `DEV_${username}` }));
                        }
                    }
                }
            } finally {
                reader.releaseLock();
            }
        }
    };

    return (
        <div className="chat-layout">
            <div className="sidebar">
                <h3>Rooms</h3>
                <div style={{ display: 'flex', gap: '0' }}>
                    <input 
                        type="text" 
                        placeholder="Room Name" 
                        value={roomInput} 
                        onChange={e => setRoomInput(e.target.value)} 
                        style={{ borderRight: 'none', width: '60%' }}
                    />
                    <button onClick={joinRoom} style={{ width: '40%', padding: '0 10px' }}>Join</button>
                </div>
                <div style={{ marginTop: '5px', fontSize: '11px', color: 'var(--success)', fontFamily: 'var(--font-mono)' }}>
                    [ Current Room: {escapeHtml(room)} ]
                </div>
                
                <h3 style={{ marginTop: '40px' }}>ESP32 Hardware</h3>
                <button 
                    onClick={toggleSerial} 
                    style={{ 
                        color: serialPortRef.current ? 'var(--error)' : 'var(--text-primary)',
                        borderColor: serialPortRef.current ? 'var(--error)' : 'var(--border-color)'
                    }}
                >
                    {serialPortRef.current ? 'Disconnect' : 'Connect ESP32'}
                </button>
                <div style={{ marginTop: '5px', fontSize: '11px', fontFamily: 'var(--font-mono)', opacity: 0.7 }}>
                    State: {serialStatus}
                </div>
                
                <div style={{ 
                    marginTop: 'auto', 
                    padding: '10px', 
                    border: '1px solid var(--border-color)',
                    fontSize: '11px', 
                    textAlign: 'center',
                    fontFamily: 'var(--font-mono)',
                    color: status.includes('Connected') ? 'var(--success)' : 'var(--error)'
                }}>
                    Server: {status}
                </div>
            </div>

            <div className="messages-area">
                <div className="messages-list">
                    {messages.map((m, i) => {
                        if (m.type === 'system') {
                            return <div key={i} style={{ opacity: 0.5, fontSize: '11px', margin: '10px 0', fontFamily: 'var(--font-mono)' }}>{m.text}</div>;
                        }
                        const isOwn = m.sender === username || m.sender === `DEV_${username}`;
                        return (
                            <div key={i} className={`message-row ${isOwn ? 'own' : ''}`}>
                                <div className="message-meta">
                                    <span className="message-time">{new Date(m.timestamp * 1000).toLocaleTimeString()}</span>
                                    <span>{escapeHtml(m.sender)}</span>
                                </div>
                                <div className="message-text">&gt; {escapeHtml(m.text)}</div>
                            </div>
                        );
                    })}
                    <div ref={messagesEndRef} />
                </div>
                <div className="input-area">
                    <input 
                        type="text" 
                        placeholder="Type a message..." 
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyPress={handleKeyPress}
                        autoFocus
                    />
                    <button onClick={sendMessage}>Send</button>
                </div>
            </div>
        </div>
    );
};

export default Chat;
