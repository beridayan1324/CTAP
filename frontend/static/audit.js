(function () {
  const token = localStorage.getItem('token');
  const username = localStorage.getItem('username') || '';
  document.getElementById('audit-user').textContent = 'User: ' + username;
  document.getElementById('audit-logout').addEventListener('click', () => {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    location.href = '/';
  });

  let activeTab = 'messages';
  const loading = document.getElementById('audit-loading');
  const wrap = document.getElementById('audit-table-wrap');
  const tabMsg = document.getElementById('tab-messages');
  const tabConn = document.getElementById('tab-connections');

  function setTabs() {
    tabMsg.classList.toggle('active', activeTab === 'messages');
    tabConn.classList.toggle('active', activeTab === 'connections');
  }

  function esc(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  async function fetchLogs() {
    loading.style.display = 'block';
    wrap.style.display = 'none';
    loading.textContent = '[ Loading logs... ]';
    setTabs();
    try {
      const path = activeTab === 'messages' ? '/audit/logs' : '/audit/connections';
      const res = await fetch(path, {
        headers: { Authorization: 'Bearer ' + token },
      });
      if (res.status === 401) {
        location.href = '/login';
        return;
      }
      const rows = await res.json();
      let thead;
      if (activeTab === 'messages') {
        thead =
          '<tr><th>#</th><th>Time</th><th>Username</th><th>Room</th><th>Type</th><th>SHA256 Fingerprint</th></tr>';
        wrap.innerHTML =
          '<table class="audit-table"><thead>' +
          thead +
          '</thead><tbody>' +
          rows
            .map(
              (m) =>
                '<tr><td style="color:var(--text-secondary)">' +
                esc(m.id) +
                '</td><td>' +
                esc(new Date(m.timestamp).toLocaleString()) +
                '</td><td>' +
                esc(m.sender_address) +
                '</td><td>' +
                esc(m.room) +
                '</td><td>' +
                esc(m.msg_type) +
                '</td><td style="font-size:11px;opacity:0.6">' +
                esc(m.msg_hash) +
                '</td></tr>'
            )
            .join('') +
          '</tbody></table>';
      } else {
        thead = '<tr><th>#</th><th>Time</th><th>IP Address</th><th>Event</th><th>Room</th></tr>';
        wrap.innerHTML =
          '<table class="audit-table"><thead>' +
          thead +
          '</thead><tbody>' +
          rows
            .map((c) => {
              const ev = String(c.event_type || '');
              const col =
                ev.includes('SUCCESS')
                  ? 'var(--success)'
                  : ev.includes('FAIL')
                    ? 'var(--error)'
                    : 'inherit';
              return (
                '<tr><td style="color:var(--text-secondary)">' +
                esc(c.id) +
                '</td><td>' +
                esc(new Date(c.timestamp).toLocaleString()) +
                '</td><td>' +
                esc(c.client_address) +
                '</td><td><span style="color:' +
                col +
                '">[' +
                esc(ev) +
                ']</span></td><td>' +
                esc(c.room) +
                '</td></tr>'
              );
            })
            .join('') +
          '</tbody></table>';
      }
    } catch {
      loading.textContent = '[ Failed to load ]';
      return;
    }
    loading.style.display = 'none';
    wrap.style.display = 'block';
  }

  tabMsg.addEventListener('click', () => {
    activeTab = 'messages';
    fetchLogs();
  });
  tabConn.addEventListener('click', () => {
    activeTab = 'connections';
    fetchLogs();
  });

  fetchLogs();
})();
