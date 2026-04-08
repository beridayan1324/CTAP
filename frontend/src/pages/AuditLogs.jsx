import React, { useState, useEffect, useContext } from 'react';
import axios from 'axios';
import { AuthContext } from '../App';

const AuditLogs = () => {
    const { token } = useContext(AuthContext);
    const [messages, setMessages] = useState([]);
    const [connections, setConnections] = useState([]);
    const [activeTab, setActiveTab] = useState('messages');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchLogs();
    }, [activeTab]);

    const fetchLogs = async () => {
        setLoading(true);
        try {
            const config = { headers: { Authorization: `Bearer ${token}` } };
            if (activeTab === 'messages') {
                const res = await axios.get('http://localhost:8766/audit/logs', config);
                setMessages(res.data);
            } else {
                const res = await axios.get('http://localhost:8766/audit/connections', config);
                setConnections(res.data);
            }
        } catch (err) {
            console.error('Failed to fetch logs', err);
        }
        setLoading(false);
    };

    return (
        <div style={{ padding: '40px', flex: 1, display: 'flex', flexDirection: 'column', boxSizing: 'border-box' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '20px', borderBottom: '1px solid var(--border-color)', paddingBottom: '15px' }}>
                <h2 style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', letterSpacing: '0.1em' }}>
                    System Audit Trail
                </h2>
                
                <div style={{ display: 'flex', gap: '10px' }}>
                    <button 
                        onClick={() => setActiveTab('messages')}
                        style={{ 
                            background: activeTab === 'messages' ? 'var(--text-primary)' : 'transparent',
                            color: activeTab === 'messages' ? 'var(--bg-color)' : 'var(--text-primary)'
                        }}
                    >
                        Message Hashes
                    </button>
                    <button 
                        onClick={() => setActiveTab('connections')}
                        style={{ 
                            background: activeTab === 'connections' ? 'var(--text-primary)' : 'transparent',
                            color: activeTab === 'connections' ? 'var(--bg-color)' : 'var(--text-primary)'
                        }}
                    >
                        Connection Events
                    </button>
                </div>
            </div>

            <div style={{ flex: 1, overflowY: 'auto' }}>
                {loading ? (
                    <p style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', opacity: 0.5 }}>[ Loading logs... ]</p>
                ) : (
                    <table className="audit-table">
                        <thead>
                            {activeTab === 'messages' ? (
                                <tr>
                                    <th>#</th>
                                    <th>Time</th>
                                    <th>Username</th>
                                    <th>Room</th>
                                    <th>Type</th>
                                    <th>SHA256 Fingerprint</th>
                                </tr>
                            ) : (
                                <tr>
                                    <th>#</th>
                                    <th>Time</th>
                                    <th>IP Address</th>
                                    <th>Event</th>
                                    <th>Room</th>
                                </tr>
                            )}
                        </thead>
                        <tbody>
                            {activeTab === 'messages' ? (
                                messages.map(m => (
                                    <tr key={m.id}>
                                        <td style={{ color: 'var(--text-secondary)' }}>{m.id}</td>
                                        <td>{new Date(m.timestamp).toLocaleString()}</td>
                                        <td>{m.sender_address}</td>
                                        <td>{m.room}</td>
                                        <td>{m.msg_type}</td>
                                        <td style={{ fontSize: '11px', opacity: 0.6 }}>{m.msg_hash}</td>
                                    </tr>
                                ))
                            ) : (
                                connections.map(c => (
                                    <tr key={c.id}>
                                        <td style={{ color: 'var(--text-secondary)' }}>{c.id}</td>
                                        <td>{new Date(c.timestamp).toLocaleString()}</td>
                                        <td>{c.client_address}</td>
                                        <td>
                                            <span style={{ 
                                                color: c.event_type.includes('SUCCESS') ? 'var(--success)' : 
                                                       c.event_type.includes('FAIL') ? 'var(--error)' : 'inherit'
                                            }}>
                                                [{c.event_type}]
                                            </span>
                                        </td>
                                        <td>{c.room}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
};

export default AuditLogs;
