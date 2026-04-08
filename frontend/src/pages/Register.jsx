import React, { useState, useContext } from 'react';
import axios from 'axios';
import { useNavigate, Link } from 'react-router-dom';
import { AuthContext } from '../App';

const Register = () => {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const { login } = useContext(AuthContext);
    const navigate = useNavigate();

    const handleRegister = async (e) => {
        e.preventDefault();
        if (password !== confirmPassword) {
            setError('PASSWORDS DO NOT MATCH');
            return;
        }
        try {
            await axios.post('http://localhost:8766/register', { username, password });
            const res = await axios.post('http://localhost:8766/login', { username, password });
            login(res.data.token, res.data.username);
            navigate('/chat');
        } catch (err) {
            setError(err.response?.data?.error || 'REGISTRATION_FAIL');
        }
    };

    return (
        <div className="auth-container">
            <form className="technical-panel" onSubmit={handleRegister}>
                <h2>Register Account</h2>
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

                <input 
                    type="password" 
                    placeholder="Confirm Password" 
                    value={confirmPassword} 
                    onChange={e => setConfirmPassword(e.target.value)} 
                    required 
                />
                
                <button type="submit" style={{marginTop: '10px'}}>Register</button>
                
                <div style={{ textAlign: 'center', fontSize: '11px', marginTop: '10px', fontFamily: 'var(--font-mono)' }}>
                    Already have an account? <Link to="/login" style={{ color: 'var(--text-primary)', textDecoration: 'underline' }}>Log In</Link>
                </div>
            </form>
        </div>
    );
};

export default Register;
