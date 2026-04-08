import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Chat from './pages/Chat';
import AuditLogs from './pages/AuditLogs';

export const AuthContext = React.createContext(null);

const App = () => {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [username, setUsername] = useState(localStorage.getItem('username'));

  const login = (newToken, newUser) => {
    localStorage.setItem('token', newToken);
    localStorage.setItem('username', newUser);
    setToken(newToken);
    setUsername(newUser);
  };

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    setToken(null);
    setUsername(null);
  };

  return (
    <AuthContext.Provider value={{ token, username, login, logout }}>
      <BrowserRouter>
        {token && <NavBar logout={logout} username={username} />}
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={!token ? <Login /> : <Navigate to="/chat" />} />
          <Route path="/register" element={!token ? <Register /> : <Navigate to="/chat" />} />
          <Route path="/chat" element={token ? <Chat /> : <Navigate to="/login" />} />
          <Route path="/audit" element={token ? <AuditLogs /> : <Navigate to="/login" />} />
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  );
};

const NavBar = ({ logout, username }) => {
  return (
    <nav className="nav-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '30px' }}>
        <div style={{ fontWeight: 600, letterSpacing: '0.1em' }}><Link to="/chat" style={{color: 'white'}}>CTAP Chat</Link></div>
        <Link to="/chat">Chat Room</Link>
        <Link to="/audit">Audit Logs</Link>
      </div>
      <div className="nav-links">
        <span style={{color: 'var(--text-secondary)'}}>User: {username}</span>
        <button onClick={logout} style={{ padding: '6px 12px', fontSize: '11px' }}>
          Logout
        </button>
      </div>
    </nav>
  );
};

export default App;
