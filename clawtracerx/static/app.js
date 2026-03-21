/* === ClawTracerX — shared JS utilities === */

function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return document.querySelectorAll(sel); }

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return await res.json();
}

/** Fetch with silent fallback (for backward compat — returns fallback on error). */
async function fetchJSONSafe(url, fallback) {
  try {
    return await fetchJSON(url);
  } catch (e) {
    console.error('Fetch error:', e);
    showErrorBanner(e.message, function() { return fetchJSONSafe(url, fallback); });
    return fallback !== undefined ? fallback : [];
  }
}

/** Show a dismissible error banner at the top of the content area. */
function showErrorBanner(message, retryFn) {
  var existing = document.getElementById('error-banner');
  if (existing) existing.remove();

  var banner = document.createElement('div');
  banner.id = 'error-banner';
  banner.className = 'error-banner';
  banner.setAttribute('role', 'alert');

  var msg = document.createElement('span');
  msg.className = 'error-banner-msg';
  msg.textContent = message || 'An error occurred';
  banner.appendChild(msg);

  if (retryFn) {
    var retryBtn = document.createElement('button');
    retryBtn.className = 'btn btn-sm btn-outline error-banner-retry';
    retryBtn.textContent = 'Retry';
    retryBtn.onclick = function() {
      banner.remove();
      retryFn();
    };
    banner.appendChild(retryBtn);
  }

  var dismissBtn = document.createElement('button');
  dismissBtn.className = 'btn-close error-banner-dismiss';
  dismissBtn.innerHTML = '&times;';
  dismissBtn.setAttribute('aria-label', 'Dismiss error');
  dismissBtn.onclick = function() { banner.remove(); };
  banner.appendChild(dismissBtn);

  var content = document.querySelector('.content');
  if (content) content.insertBefore(banner, content.firstChild);
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

function fmtTurnTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const mo = d.getMonth() + 1;
  const day = d.getDate();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${mo}/${day} ${hh}:${mm}`;
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
  const home = window._homeDir || '';
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

// === Text expansion modal (공통) ===
window._textBuf = {};
var _textBufIdx = 0;
var _modalRawText = '';
var _modalIsMarkdown = true;

function _storeText(text) {
  var k = _textBufIdx++;
  window._textBuf[k] = text;
  return k;
}

function makeShowFullBtn(label, title, text, threshold) {
  if (!text || text.length <= threshold) return '';
  var k = _storeText(text);
  return '<button class="tc-full-btn" onclick="event.stopPropagation();showTextModal(\''
    + escHtml(title) + '\',' + k + ')">' + escHtml(label) + '</button>';
}

async function showTextModal(title, keyOrText, opts) {
  var modal = document.getElementById('text-modal');
  if (!modal) return;
  opts = opts || {};

  var text;
  if (keyOrText && typeof keyOrText.then === 'function') {
    _modalRawText = '';
    _modalIsMarkdown = false;
    document.getElementById('text-modal-title').textContent = title;
    _refreshModalBody('Loading...');
    modal.style.display = 'flex';
    try {
      var result = await keyOrText;
      text = typeof result === 'string' ? result
           : (result.content != null ? result.content : JSON.stringify(result, null, 2));
    } catch(e) {
      text = 'Error: ' + e.message;
    }
  } else {
    text = typeof keyOrText === 'number'
         ? (window._textBuf[keyOrText] || '')
         : (keyOrText || '');
  }

  _modalRawText = text;
  _modalIsMarkdown = (opts.markdown !== false);
  document.getElementById('text-modal-title').textContent = title;
  _refreshModalBody();
  modal.style.display = 'flex';
}

function _refreshModalBody(loading) {
  var pre    = document.getElementById('text-modal-pre');
  var mdDiv  = document.getElementById('text-modal-md');
  var toggle = document.getElementById('text-modal-toggle');
  var text   = loading != null ? loading : _modalRawText;

  if (_modalIsMarkdown && !loading && typeof marked !== 'undefined') {
    pre.style.display   = 'none';
    mdDiv.style.display = 'block';
    var html = marked.parse(text);
    mdDiv.innerHTML = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(html) : html;
    if (toggle) toggle.textContent = 'Raw';
  } else {
    mdDiv.style.display = 'none';
    pre.style.display   = 'block';
    pre.textContent     = text;
    if (toggle) toggle.textContent = loading ? '…' : 'Markdown';
  }
}

function toggleModalMarkdown() {
  _modalIsMarkdown = !_modalIsMarkdown;
  _refreshModalBody();
}

function copyModalText() {
  if (!_modalRawText) return;
  var btn = document.getElementById('text-modal-copy');
  navigator.clipboard.writeText(_modalRawText).then(function() {
    if (btn) { btn.textContent = '✓ Copied'; setTimeout(function(){ btn.textContent = 'Copy'; }, 1500); }
  }).catch(function() {
    if (btn) btn.textContent = 'Copy';
  });
}

function closeTextModal() {
  var modal = document.getElementById('text-modal');
  if (modal) modal.style.display = 'none';
  _modalRawText = '';
  // Clear text buffer to prevent memory buildup
  window._textBuf = {};
  _textBufIdx = 0;
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeTextModal();
});

// === Update check ===
async function checkForUpdate() {
  if (sessionStorage.getItem('clawtracerx-update-dismissed')) return;
  const data = await fetchJSONSafe('/api/check-update', {});
  if (!data.update_available) return;
  const banner = document.getElementById('update-banner');
  if (!banner) return;
  banner.querySelector('.update-version').textContent = data.latest;
  banner.querySelector('.update-link').href = data.release_url;
  banner.style.display = 'flex';
}

function dismissUpdate() {
  var banner = document.getElementById('update-banner');
  if (banner) banner.style.display = 'none';
  sessionStorage.setItem('clawtracerx-update-dismissed', '1');
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
