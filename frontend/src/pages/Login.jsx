import React, { useState, useContext } from 'react';
import axios from 'axios';
import { useNavigate, Link } from 'react-router-dom';
import { AuthContext } from '../App';

const Login = () => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const { login } = useContext(AuthContext);
    const navigate = useNavigate();

    const handleLogin = async (e) => {
        e.preventDefault();
        try {
            const res = await axios.post('http://localhost:8766/login', { username, password });
            login(res.data.token, res.data.username);
            navigate('/chat');
        } catch (err) {
            setError(err.response?.data?.error || 'Login failed');
        }
    };

    return (
        <div className="auth-container">
            <form className="technical-panel" onSubmit={handleLogin}>
                <h2>Log In</h2>
                {error && <p className="error-text">[{error}]</p>}
                
                <input 
                    type="text" 
                    placeholder="Username" 
                    value={username} 
                    onChange={e => setUsername(e.target.value)} 
                    required 
                />
                
                <input 
                    type="password" 
                    placeholder="Password" 
                    value={password} 
                    onChange={e => setPassword(e.target.value)} 
                    required 
                />
                
                <button type="submit" style={{marginTop: '10px'}}>Sign In</button>
                
                <div style={{ textAlign: 'center', fontSize: '11px', marginTop: '10px', fontFamily: 'var(--font-mono)' }}>
                    No account? <Link to="/register" style={{ color: 'var(--text-primary)', textDecoration: 'underline' }}>Register</Link>
                </div>
            </form>
        </div>
    );
};

export default Login;
