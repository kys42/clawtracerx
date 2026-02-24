/* === ClawTracerX — shared JS utilities === */

function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return document.querySelectorAll(sel); }

async function fetchJSON(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error('Fetch error:', e);
    return [];
  }
}

function fmtTokens(n) {
  if (!n) return '0';
  if (n < 1000) return String(n);
  if (n < 1000000) return (n / 1000).toFixed(1) + 'K';
  return (n / 1000000).toFixed(2) + 'M';
}

function fmtCost(n) {
  if (!n || n <= 0) return '$0';
  if (n < 0.001) return '$' + n.toFixed(6);
  if (n < 0.01) return '$' + n.toFixed(4);
  if (n < 1) return '$' + n.toFixed(3);
  return '$' + n.toFixed(2);
}

function fmtSize(n) {
  if (!n) return '0B';
  if (n < 1024) return n + 'B';
  if (n < 1048576) return (n / 1024).toFixed(1) + 'KB';
  return (n / 1048576).toFixed(1) + 'MB';
}

function fmtDuration(ms) {
  if (ms == null || ms <= 0) return '—';
  if (ms < 1000) return ms + 'ms';
  if (ms < 60000) return (ms / 1000).toFixed(1) + 's';
  const m = Math.floor(ms / 60000);
  const s = ((ms % 60000) / 1000).toFixed(0);
  return m + 'm ' + s + 's';
}

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso;
  }
}

function truncate(s, max) {
  if (!s) return '';
  return s.length <= max ? s : s.slice(0, max) + '...';
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function shortenPath(p) {
  if (!p) return '';
  // Replace home dir
  const home = '/Users/kys';
  if (p.startsWith(home)) p = '~' + p.slice(home.length);
  // Show last 2 segments if long
  if (p.length > 60) {
    const parts = p.split('/');
    return '.../' + parts.slice(-2).join('/');
  }
  return p;
}

const TOOL_ICONS = {
  read: '\ud83d\udcc1', edit: '\u270f\ufe0f', write: '\ud83d\udcdd',
  exec: '\ud83d\udcbb', glob: '\ud83d\udd0d', grep: '\ud83d\udd0e',
  sessions_spawn: '\ud83d\udd00', sessions_send: '\ud83d\udce8',
  message: '\ud83d\udcac', broadcast: '\ud83d\udce1', fetch: '\ud83c\udf10',
  session_status: '\u2139\ufe0f', process: '\u2699\ufe0f',
  subagents: '\ud83d\udd00', sessions_history: '\ud83d\udcda',
};

function toolIcon(name) {
  for (const [key, icon] of Object.entries(TOOL_ICONS)) {
    if (name.toLowerCase().includes(key)) return icon;
  }
  return '\ud83d\udd27';
}

async function postJSON(url, data) {
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return await res.json();
  } catch (e) {
    console.error('postJSON error:', e);
    return { error: e.message };
  }
}

async function putJSON(url, data) {
  try {
    const res = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return await res.json();
  } catch (e) {
    console.error('putJSON error:', e);
    return { error: e.message };
  }
}

async function patchJSON(url, data) {
  try {
    const res = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return await res.json();
  } catch (e) {
    console.error('patchJSON error:', e);
    return { error: e.message };
  }
}
