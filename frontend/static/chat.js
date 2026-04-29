(function () {
  const HANDSHAKE_SECRET = 'CTAP-GLOVE-AUTH-2026';
  const username = localStorage.getItem('username') || '';
  document.getElementById('nav-user').textContent = 'User: ' + username;

  document.getElementById('logout-btn').addEventListener('click', () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    location.href = '/';
  });

  const messagesList = document.getElementById('messages-list');
  const statusEl = document.getElementById('server-status');
  const serialStateEl = document.getElementById('serial-state');
  const serialToggle = document.getElementById('serial-toggle');
  const roomInput = document.getElementById('room-input');
  const currentRoomEl = document.getElementById('current-room');
  const msgInput = document.getElementById('msg-input');
  let room = 'default';

  let socket = null;
  let reconnectTimer = null;
  let serialPort = null;
  let serialReader = null;

  function setStatus(t) {
    statusEl.textContent = 'Server: ' + t;
    statusEl.style.color = t.includes('Connected') ? 'var(--success)' : 'var(--error)';
  }

  function appendSystem(text) {
    const div = document.createElement('div');
    div.className = 'message-system';
    div.textContent = text;
    messagesList.appendChild(div);
    scrollBottom();
  }

  function appendChat(m) {
    if (m.type === 'system') {
      appendSystem(m.text);
      return;
    }
    const isOwn = m.sender === username || m.sender === 'DEV_' + username;
    const row = document.createElement('div');
    row.className = 'message-row' + (isOwn ? ' own' : '');
    const ts = m.timestamp != null ? new Date(Number(m.timestamp) * 1000).toLocaleTimeString() : '';
    const meta = document.createElement('div');
    meta.className = 'message-meta';
    const tspan = document.createElement('span');
    tspan.className = 'message-time';
    tspan.textContent = ts;
    const sspan = document.createElement('span');
    sspan.textContent = m.sender || '';
    meta.appendChild(tspan);
    meta.appendChild(sspan);
    const text = document.createElement('div');
    text.className = 'message-text';
    text.textContent = '> ' + (m.text || '');
    row.appendChild(meta);
    row.appendChild(text);
    messagesList.appendChild(row);
    scrollBottom();
  }

  function scrollBottom() {
    messagesList.lastElementChild?.scrollIntoView({ behavior: 'smooth' });
  }

  async function handshakeResponse(challenge, sock) {
    const enc = new TextEncoder();
    const buf = enc.encode(challenge + HANDSHAKE_SECRET);
    const hashBuffer = await crypto.subtle.digest('SHA-256', buf);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
    sock.send(JSON.stringify({ type: 'auth_response', hash: hashHex }));
  }

  function connectWs() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = proto + '//' + location.host + '/';
    setStatus('Connecting…');
    socket = new WebSocket(url);

    socket.onopen = () => setStatus('Connected');

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'auth_challenge') {
        handshakeResponse(data.challenge, socket);
      } else if (data.type === 'auth_result') {
        if (data.status === 'OK') {
          socket.send(JSON.stringify({ type: 'join_room', room: 'default' }));
        }
      } else if (data.type === 'chat_message') {
        appendChat(data);
      } else if (data.type === 'room_joined') {
        room = data.room;
        currentRoomEl.textContent = '[ Current Room: ' + data.room + ' ]';
        messagesList.innerHTML = '';
        appendChat({ type: 'system', text: '>> Joined Room: ' + data.room });
      }
    };

    socket.onclose = () => {
      setStatus('Disconnected');
      reconnectTimer = setTimeout(connectWs, 3000);
    };
  }

  connectWs();

  document.getElementById('join-room').addEventListener('click', () => {
    const name = roomInput.value.trim();
    if (name && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'join_room', room: name }));
      roomInput.value = '';
    }
  });

  function sendMessage() {
    const text = msgInput.value.trim();
    if (text && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'web_msg', text, username }));
      msgInput.value = '';
    }
  }

  document.getElementById('send-btn').addEventListener('click', sendMessage);
  msgInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });

  async function disconnectSerial() {
    if (serialReader) {
      try {
        await serialReader.cancel();
      } catch (_) {}
      serialReader = null;
    }
    if (serialPort) {
      try {
        await serialPort.close();
      } catch (_) {}
      serialPort = null;
    }
    serialStateEl.textContent = 'State: Offline';
    serialToggle.textContent = 'Connect ESP32';
    serialToggle.style.color = 'var(--text-primary)';
    serialToggle.style.borderColor = 'var(--border-color)';
  }

  async function readSerial() {
    while (serialPort && serialPort.readable) {
      const reader = serialPort.readable.getReader();
      serialReader = reader;
      const decoder = new TextDecoder();
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          for (const line of lines) {
            const plaintext = line.trim();
            if (
              plaintext &&
              !plaintext.includes('CTAP') &&
              socket &&
              socket.readyState === WebSocket.OPEN
            ) {
              socket.send(
                JSON.stringify({
                  type: 'web_msg',
                  text: plaintext,
                  username: 'DEV_' + username,
                })
              );
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    }
  }

  async function connectSerial() {
    try {
      if (!('serial' in navigator)) {
        serialStateEl.textContent = 'State: Web Serial not supported';
        return;
      }
      const port = await navigator.serial.requestPort();
      await port.open({ baudRate: 115200 });
      serialPort = port;
      serialStateEl.textContent = 'State: Connected';
      serialToggle.textContent = 'Disconnect';
      serialToggle.style.color = 'var(--error)';
      serialToggle.style.borderColor = 'var(--error)';
      readSerial();
    } catch {
      serialStateEl.textContent = 'State: Error: No device';
    }
  }

  serialToggle.addEventListener('click', async () => {
    if (serialPort) await disconnectSerial();
    else await connectSerial();
  });

  window.addEventListener('beforeunload', () => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (socket) socket.close();
    disconnectSerial();
  });
})();
