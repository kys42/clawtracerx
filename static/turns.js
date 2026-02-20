/* === ocmon — shared turn rendering === */
/* Depends on app.js: fmtTokens, fmtCost, fmtSize, fmtDuration, fmtDate, truncate, escHtml, shortenPath, toolIcon */

const SYSTEM_SOURCES = new Set(['system', 'subagent_announce', 'cron_announce']);

function fmtChars(n) {
  if (!n) return '0';
  if (n < 1000) return n + 'ch';
  if (n < 1000000) return (n / 1000).toFixed(1) + 'K';
  return (n / 1000000).toFixed(2) + 'M';
}

function renderTurns(turns, compactionEvents) {
  const container = qs('#turns-container');
  let html = '';

  // Build compaction boundary: find the first in-context turn index
  let contextBoundaryIdx = -1;
  for (let i = 0; i < turns.length; i++) {
    if (turns[i].in_context && (i === 0 || !turns[i-1].in_context)) {
      contextBoundaryIdx = i;
      break;
    }
  }

  let animIdx = 0;
  for (let i = 0; i < turns.length; i++) {
    // Insert compaction divider at the context boundary
    if (i === contextBoundaryIdx && i > 0 && compactionEvents.length > 0) {
      const lastCe = compactionEvents[compactionEvents.length - 1];
      const tokensBefore = lastCe.tokens_before ? fmtTokens(lastCe.tokens_before) : '?';
      const tokensAfter  = lastCe.tokens_after  ? fmtTokens(lastCe.tokens_after)  : null;
      const hookLabel = lastCe.from_hook ? ' [hook]' : '';
      const summaryHtml = lastCe.summary ? `
        <details class="compaction-detail">
          <summary>Summary ▾</summary>
          <div class="compaction-summary-text">${escHtml(lastCe.summary)}</div>
        </details>` : '';
      html += `<div class="compaction-divider">
        <span class="compaction-line"></span>
        <div class="compaction-info">
          <span class="compaction-label">Compacted${hookLabel}: ${tokensBefore}${tokensAfter ? ' → ' + tokensAfter : ''} tokens — from turn ${i}</span>
          ${summaryHtml}
        </div>
        <span class="compaction-line"></span>
      </div>`;
    }
    html += renderTurn(turns[i], animIdx++);
  }
  container.innerHTML = html;
}

function renderTurn(t, animIdx) {
  const hasErrors = t.tool_calls.some(tc => tc.is_error);
  const isSystem = SYSTEM_SOURCES.has(t.user_source);
  const isCompacted = t.in_context === false;
  const isHighCost = (t.cost?.total || 0) > 0.10;
  const isSubagentSpawn = t.subagent_spawns && t.subagent_spawns.length > 0;

  let classes = 'turn-card';
  if (hasErrors)     classes += ' has-errors';
  if (isCompacted)   classes += ' compacted';
  if (isHighCost && !hasErrors) classes += ' high-cost';
  if (isSubagentSpawn && !hasErrors && !isHighCost) classes += ' spawns-subagent';

  const delay = (animIdx || 0) * 40;

  return `
  <div class="${classes}" id="turn-${t.index}" style="animation-delay:${delay}ms">
    <div class="turn-header" onclick="toggleTurn(${t.index})">
      <div class="turn-left">
        <span class="turn-index">Turn ${t.index}</span>
        ${isCompacted ? '<span class="badge badge-compacted">compacted</span>' : ''}
        <span class="badge badge-${t.user_source} badge-type">${t.user_source}</span>
        <span class="turn-preview">${escHtml(truncate(t.user_text.replace(/\\n/g, ' '), 80))}</span>
      </div>
      <div class="turn-stats">
        ${t.tool_calls.length ? `<span class="stat-chip tools">${t.tool_calls.length} tools</span>` : ''}
        ${t.subagent_spawns.length ? `<span class="stat-chip subagents">${t.subagent_spawns.length} subagents</span>` : ''}
        <span class="stat-chip duration">${fmtDuration(t.duration_ms)}</span>
        <span class="stat-chip cost">${fmtCost(t.cost.total || 0)}</span>
        <span class="stat-chip tokens">${fmtTokens(t.usage.totalTokens || 0)}</span>
        ${(t.cache_hit_rate > 0) ? `<span class="stat-chip cache" title="Cache hit rate">${Math.round(t.cache_hit_rate * 100)}% cache</span>` : ''}
        ${t.thinking_level ? `<span class="stat-chip thinking" title="Thinking level">💭 ${t.thinking_level}</span>` : ''}
        ${typeof showRaw === 'function' ? `<button class="btn-icon raw-btn" onclick="event.stopPropagation();showRaw(${t.index})" title="View raw JSONL">{ }</button>` : ''}
      </div>
    </div>
    <div class="turn-body" id="turn-body-${t.index}" style="display:none">
      <div class="turn-detail">
        <!-- User message -->
        <div class="msg-block user-msg">
          <div class="msg-role">User <span class="badge badge-${t.user_source} badge-type" style="font-size:10px">${t.user_source}</span></div>
          <pre class="msg-content">${escHtml(t.user_text.slice(0, 2000))}</pre>
        </div>

        <!-- Token breakdown -->
        <div class="token-bar">
          ${renderTokenBar(t.usage)}
        </div>

        <!-- Thinking -->
        ${t.thinking_text ? `
        <div class="thinking-block">
          <div class="thinking-label">Thinking</div>
          <pre class="thinking-content">${escHtml(t.thinking_text)}</pre>
        </div>` : ''}
        ${t.thinking_encrypted ? '<div class="thinking-block encrypted"><span class="thinking-label">Thinking [encrypted]</span></div>' : ''}

        <!-- Tool calls -->
        ${t.tool_calls.length ? `
        <div class="tool-calls">
          <div class="tc-header">Tool Calls</div>
          ${t.tool_calls.map(tc => renderToolCall(tc)).join('')}
        </div>` : ''}

        <!-- Subagent spawns -->
        ${t.subagent_spawns.map(s => renderSubagent(s, 0)).join('')}

        <!-- Assistant response -->
        ${t.assistant_texts.map(txt => `
        <div class="msg-block assistant-msg">
          <div class="msg-role">Assistant</div>
          <pre class="msg-content">${escHtml(txt)}</pre>
        </div>`).join('')}
      </div>
    </div>
  </div>`;
}

function getToolCategory(name) {
  const n = name.toLowerCase();
  if (/read|write|edit|glob|notebook/.test(n)) return 'file';
  if (/bash|exec|run|process|command/.test(n)) return 'exec';
  if (/grep|search|fetch|web/.test(n)) return 'search';
  return 'other';
}

function renderToolCall(tc) {
  const icon = toolIcon(tc.name);
  const category = getToolCategory(tc.name);
  const errorClass = tc.is_error ? 'tc-error' : '';
  const durStr = tc.duration_ms != null ? `<span class="tc-dur">${fmtDuration(tc.duration_ms)}</span>` : '';
  const sizeStr = tc.result_size > 500 ? `<span class="tc-size">${fmtSize(tc.result_size)}</span>` : '';

  let argSummary = '';
  if (tc.arguments.file_path) argSummary = shortenPath(tc.arguments.file_path);
  else if (tc.arguments.command) argSummary = truncate(tc.arguments.command, 80);
  else if (tc.arguments.pattern) argSummary = tc.arguments.pattern;

  return `
  <div class="tc-row ${errorClass}" data-category="${category}" onclick="toggleTcResult(this)">
    <span class="tc-icon">${icon}</span>
    <span class="tc-name">${tc.name}</span>
    <span class="tc-args">${escHtml(argSummary)}</span>
    ${durStr}${sizeStr}
    ${tc.is_error ? '<span class="tc-err-badge">ERROR</span>' : ''}
    <div class="tc-result" style="display:none">
      <pre>${escHtml(tc.result_text)}</pre>
    </div>
  </div>`;
}

function renderSubagent(s, depth) {
  const outcomeClass = s.outcome === 'ok' ? 'outcome-ok' : (s.outcome === 'unknown' ? 'outcome-unknown' : 'outcome-error');
  const durStr = s.duration_ms ? fmtDuration(s.duration_ms) : '?';
  const costStr = s.cost_usd != null ? fmtCost(s.cost_usd) : '?';
  const tokensStr = s.total_tokens != null ? fmtTokens(s.total_tokens) : '?';
  const indent = depth > 0 ? `style="margin-left:${depth * 16}px"` : '';

  let childHtml = '';
  if (s.child_turns && s.child_turns.length) {
    childHtml = `
    <div class="subagent-children">
      <div class="subagent-children-header" onclick="event.stopPropagation();toggleEl(this.nextElementSibling)">
        ${s.child_turns.length} turns in child session (click to expand)
      </div>
      <div class="subagent-turns" style="display:none">
        ${s.child_turns.map(ct => renderChildTurn(ct, depth + 1)).join('')}
      </div>
    </div>`;
  } else if (s.announce_stats) {
    const as = s.announce_stats;
    childHtml = `
    <div class="subagent-announce-stats">
      <span class="dim">From announce:</span>
      runtime ${fmtDuration(as.runtime_ms)}
      &middot; ${fmtTokens(as.total_tokens)} tokens
      (in ${fmtTokens(as.input_tokens)} / out ${fmtTokens(as.output_tokens)})
    </div>`;
  }

  return `
  <div class="subagent-block" ${indent}>
    <div class="subagent-header" onclick="toggleSubagent(this)">
      <span class="subagent-icon">&#x1f500;</span>
      <span class="subagent-label">${escHtml(s.label || 'subagent')}</span>
      <span class="badge ${outcomeClass}">${s.outcome}</span>
      <span class="subagent-stats">${durStr} &middot; ${costStr} &middot; ${tokensStr} tokens</span>
      ${s.child_session_id ? `<a href="/session/${s.child_session_id}" class="btn btn-sm" onclick="event.stopPropagation()">Open Session</a>` : ''}
    </div>
    <div class="subagent-body" style="display:none">
      <div class="subagent-task">${escHtml(truncate(s.task, 300))}</div>
      ${childHtml}
    </div>
  </div>`;
}

function renderChildTurn(ct, depth) {
  const hasErrors = ct.tool_calls.some(tc => tc.is_error);
  const errorClass = hasErrors ? ' has-errors' : '';

  const nestedSubagents = ct.subagent_spawns
    ? ct.subagent_spawns.map(s => renderSubagent(s, depth)).join('')
    : '';

  return `
  <div class="child-turn${errorClass}">
    <div class="child-turn-header" onclick="toggleEl(this.nextElementSibling)">
      <span class="child-turn-idx">Turn ${ct.index}</span>
      <span class="dim">${ct.tool_calls.length} tools</span>
      <span class="dim">${fmtDuration(ct.duration_ms)}</span>
      <span class="dim">${fmtCost(ct.cost?.total || 0)}</span>
      ${ct.user_source && ct.user_source !== 'chat' ? `<span class="badge badge-${ct.user_source}" style="font-size:9px">${ct.user_source}</span>` : ''}
    </div>
    <div class="child-turn-body" style="display:none">
      ${ct.thinking_text ? `
      <div class="thinking-block">
        <div class="thinking-label">Thinking</div>
        <pre class="thinking-content">${escHtml(truncate(ct.thinking_text, 1000))}</pre>
      </div>` : ''}
      ${ct.tool_calls.map(tc => renderToolCall(tc)).join('')}
      ${nestedSubagents}
      ${ct.assistant_texts.map(txt => `<pre class="child-response">${escHtml(truncate(txt, 500))}</pre>`).join('')}
    </div>
  </div>`;
}

function renderTokenBar(usage) {
  const input = usage.input || 0;
  const output = usage.output || 0;
  const cache = usage.cacheRead || 0;
  const total = input + output + cache || 1;
  return `
    <div class="token-segments">
      <div class="token-seg input" style="width:${input/total*100}%" title="Input: ${fmtTokens(input)}"></div>
      <div class="token-seg cache" style="width:${cache/total*100}%" title="Cache: ${fmtTokens(cache)}"></div>
      <div class="token-seg output" style="width:${output/total*100}%" title="Output: ${fmtTokens(output)}"></div>
    </div>
    <div class="token-legend">
      <span class="legend-item"><span class="dot input"></span>In: ${fmtTokens(input)}</span>
      <span class="legend-item"><span class="dot cache"></span>Cache: ${fmtTokens(cache)}</span>
      <span class="legend-item"><span class="dot output"></span>Out: ${fmtTokens(output)}</span>
    </div>
  `;
}

function toggleTurn(idx) {
  const body = qs(`#turn-body-${idx}`);
  body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

function toggleSubagent(headerEl) {
  const body = headerEl.nextElementSibling;
  if (body) body.style.display = body.style.display === 'none' ? 'block' : 'none';
}

function toggleTcResult(el) {
  const result = el.querySelector('.tc-result');
  if (result) result.style.display = result.style.display === 'none' ? 'block' : 'none';
}

function toggleEl(el) {
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
