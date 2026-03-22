/* === ClawTracerX — shared turn rendering === */
/* Depends on app.js: fmtTokens, fmtCost, fmtSize, fmtDuration, fmtDate, truncate, escHtml, shortenPath, toolIcon */

const SYSTEM_SOURCES = new Set(['system', 'subagent_announce', 'cron_announce']);

function renderChannelMsg(cm) {
  const platformBadge = `<span class="badge badge-${escHtml(cm.platform)}" style="font-size:10px">${escHtml(cm.platform)}</span>`;
  const senderHtml = cm.sender ? `<span class="channel-sender">${escHtml(cm.sender)}</span>` : '';
  const channelHtml = cm.channel ? `<span class="channel-ch">${escHtml(cm.channel)}</span>` : '';
  const tsHtml = cm.ts_str ? `<span class="channel-ts">${escHtml(cm.ts_str)}</span>` : '';
  const midHtml = cm.message_id ? `<span class="channel-mid">#${escHtml(cm.message_id)}</span>` : '';
  const replyHtml = cm.reply_context
    ? `<div class="channel-reply">${escHtml(cm.reply_context)}</div>` : '';
  return `<div class="channel-msg">
    <div class="channel-msg-meta">${platformBadge}${senderHtml}${channelHtml}${tsHtml}${midHtml}</div>
    ${replyHtml}
    <pre class="channel-msg-body">${escHtml(cm.actual_text || '')}</pre>
  </div>`;
}
function fmtChars(n) {
  if (!n) return '0';
  if (n < 1000) return n + _t('turns.ch');
  if (n < 1000000) return (n / 1000).toFixed(1) + 'K';
  return (n / 1000000).toFixed(2) + 'M';
}

var _turnsPageState = null; // {items, compactionEvents, contextBoundaryIdx, rendered}
var _TURNS_PAGE_SIZE = 50;

function renderTurns(turns, compactionEvents) {
  const container = qs('#turns-container');

  // Clear text buffer from previous render to prevent memory buildup
  window._textBuf = {};
  _textBufIdx = 0;

  // Build compaction boundary: find the first in-context turn index
  var contextBoundaryIdx = -1;
  for (var i = 0; i < turns.length; i++) {
    if (turns[i].in_context && (i === 0 || !turns[i-1].in_context)) {
      contextBoundaryIdx = i;
      break;
    }
  }

  // Group turns by workflow_group_id — find the first/last index of each gid
  // (groups may be non-contiguous due to cron ticks with no spawns in between)
  const workflowBounds = new Map(); // gid → {first, last}
  turns.forEach((t, i) => {
    if (t.workflow_group_id != null) {
      const gid = t.workflow_group_id;
      if (!workflowBounds.has(gid)) workflowBounds.set(gid, { first: i, last: i });
      else workflowBounds.get(gid).last = i;
    }
  });

  const items = []; // [{type:'turn', turn, startIdx} | {type:'workflow', turns, startIdx}]
  const processedWorkflows = new Set();
  i = 0;
  while (i < turns.length) {
    const t = turns[i];
    const gid = t.workflow_group_id;
    if (gid != null && !processedWorkflows.has(gid)) {
      processedWorkflows.add(gid);
      const bounds = workflowBounds.get(gid);

      // Separate workflow turns (wf==gid) from interleaved gap turns (wf==null)
      const workflowTurns = [];
      const gapTurns = [];
      for (var j = bounds.first; j <= bounds.last; j++) {
        if (turns[j].workflow_group_id === gid) workflowTurns.push({ turn: turns[j], idx: j });
        else gapTurns.push({ turn: turns[j], idx: j });
      }

      items.push({ type: 'workflow', turns: workflowTurns.map(x => x.turn), startIdx: bounds.first });
      // Gap turns (interleaved non-workflow events) appear after the workflow block
      for (const g of gapTurns) items.push({ type: 'turn', turn: g.turn, startIdx: g.idx });

      i = bounds.last + 1;
    } else if (gid != null) {
      // Already consumed
      i++;
    } else {
      items.push({ type: 'turn', turn: t, startIdx: i });
      i++;
    }
  }

  // Store state for pagination
  _turnsPageState = {
    items: items,
    compactionEvents: compactionEvents,
    contextBoundaryIdx: contextBoundaryIdx,
    rendered: 0,
  };

  // Render first page
  container.innerHTML = '';
  _renderTurnsBatch(container, _TURNS_PAGE_SIZE);
}

function _renderTurnsBatch(container, count) {
  if (!_turnsPageState) return;
  var state = _turnsPageState;
  var end = Math.min(state.rendered + count, state.items.length);
  var html = '';
  var animIdx = state.rendered;

  for (var k = state.rendered; k < end; k++) {
    var item = state.items[k];
    var firstTurnIdx = item.startIdx;
    // Insert compaction divider at the context boundary
    if (firstTurnIdx === state.contextBoundaryIdx && firstTurnIdx > 0 && state.compactionEvents.length > 0) {
      var lastCe = state.compactionEvents[state.compactionEvents.length - 1];
      var tokensBefore = lastCe.tokens_before ? fmtTokens(lastCe.tokens_before) : '?';
      var tokensAfter  = lastCe.tokens_after  ? fmtTokens(lastCe.tokens_after)  : null;
      var hookLabel = lastCe.from_hook ? ' ' + _t('turns.hook') : '';
      var summaryHtml = lastCe.summary ? `
        <details class="compaction-detail">
          <summary>${_t('turns.summary')} ▾</summary>
          <div class="compaction-summary-text">${escHtml(lastCe.summary)}</div>
        </details>` : '';
      html += `<div class="compaction-divider">
        <span class="compaction-line"></span>
        <div class="compaction-info">
          <span class="compaction-label">${_t('turns.compacted')}${hookLabel}: ${tokensBefore}${tokensAfter ? ' → ' + tokensAfter : ''} ${_t('turns.tokens_from_turn')} ${firstTurnIdx}</span>
          ${summaryHtml}
        </div>
        <span class="compaction-line"></span>
      </div>`;
    }

    if (item.type === 'workflow') {
      html += renderWorkflowGroup(item.turns, animIdx);
      animIdx += item.turns.length;
    } else {
      html += renderTurn(item.turn, animIdx++);
    }
  }
  state.rendered = end;

  // Remove existing "load more" button
  var existingBtn = container.querySelector('.load-more-turns');
  if (existingBtn) existingBtn.remove();

  container.insertAdjacentHTML('beforeend', html);

  // Add "load more" button if more items remain
  var remaining = state.items.length - state.rendered;
  if (remaining > 0) {
    var btn = document.createElement('button');
    btn.className = 'btn btn-outline load-more-turns';
    btn.textContent = (_t('turns.load_more') || 'Load more turns') + ' (' + remaining + ' ' + (_t('turns.remaining') || 'remaining') + ')';
    btn.onclick = function() { _renderTurnsBatch(container, _TURNS_PAGE_SIZE); };
    container.appendChild(btn);
  }
}

function renderWorkflowGroup(turns, animIdx) {
  if (!turns || !turns.length) return '';
  const firstTurn = turns[0];
  const lastTurn  = turns[turns.length - 1];
  const gid = firstTurn.workflow_group_id;

  // Aggregate stats
  const totalCost   = turns.reduce((s, t) => s + (t.cost?.total || 0), 0);
  const totalTools  = turns.reduce((s, t) => s + t.tool_calls.length, 0);
  const totalTokens = turns.reduce((s, t) => s + (t.usage?.totalTokens || 0), 0);
  const totalSpawns = turns.reduce((s, t) => s + t.subagent_spawns.length, 0);

  // Duration: wall time from first turn start to last turn end
  const firstTs = firstTurn.timestamp ? new Date(firstTurn.timestamp).getTime() : null;
  const lastTs  = lastTurn.timestamp  ? new Date(lastTurn.timestamp).getTime()  : null;
  const totalDurationMs = (firstTs && lastTs)
    ? (lastTs - firstTs) + (lastTurn.duration_ms || 0)
    : turns.reduce((s, t) => s + (t.duration_ms || 0), 0);

  // Label: extract cron job name from first turn's user_text
  let label = _t('turns.workflow');
  const cronM = firstTurn.user_text.match(/\[cron:[^\s]+ ([^\]]+)\]/);
  if (cronM) label = cronM[1];

  const innerHtml = turns.map((t, i) => renderTurn(t, animIdx + i)).join('');

  return `
  <div class="workflow-group" id="workflow-${gid}">
    <div class="workflow-header" onclick="toggleWorkflow(${gid})">
      <span class="workflow-icon">⛓</span>
      <span class="workflow-label">${escHtml(label)}</span>
      <span class="workflow-meta">${turns.length} ${_t('turns.turns')}</span>
      <div class="workflow-stats">
        ${totalTools  ? `<span class="stat-chip tools">${totalTools} ${_t('turns.tools')}</span>` : ''}
        ${totalSpawns ? `<span class="stat-chip subagents">${totalSpawns} ${_t('turns.agents')}</span>` : ''}
        <span class="stat-chip duration">${fmtDuration(totalDurationMs)}</span>
        <span class="stat-chip cost">${fmtCost(totalCost)}</span>
        <span class="stat-chip tokens">${fmtTokens(totalTokens)}</span>
      </div>
    </div>
    <div class="workflow-body" id="workflow-body-${gid}">
      ${innerHtml}
    </div>
  </div>`;
}

function renderTurn(t, animIdx) {
  const hasErrors = t.tool_calls.some(tc => tc.is_error);
  const isSystem = SYSTEM_SOURCES.has(t.user_source);
  const isCompacted = t.in_context === false;
  const isHighCost = (t.cost?.total || 0) > 0.10;
  const isSubagentSpawn = t.subagent_spawns && t.subagent_spawns.length > 0;

  let classes = 'turn-card';
  if (hasErrors)          classes += ' has-errors';
  if (isCompacted)        classes += ' compacted';
  if (isHighCost && !hasErrors) classes += ' high-cost';
  if (isSubagentSpawn && !hasErrors && !isHighCost) classes += ' spawns-subagent';

  const delay = (animIdx || 0) * 40;

  let previewText;
  if (t.channel_meta) {
    const cm = t.channel_meta;
    previewText = (cm.sender ? cm.sender + ': ' : '') +
                  (cm.actual_text || '').replace(/\n/g, ' ');
  } else {
    previewText = (t.user_text || '').replace(/\n/g, ' ');
  }

  return `
  <div class="${classes}" id="turn-${t.index}" data-source="${escHtml(t.user_source)}" style="animation-delay:${delay}ms">
    <div class="turn-header" onclick="toggleTurn(${t.index})">
      <div class="turn-left">
        <span class="turn-index">${_t('turns.turn')} ${t.index}</span>
        ${t.timestamp ? `<span class="turn-timestamp">${fmtTurnTime(t.timestamp)}</span>` : ''}
        ${isCompacted ? `<span class="badge badge-compacted">${_t('turns.compacted_label')}</span>` : ''}
        <span class="badge badge-${escHtml(t.user_source)} badge-type">${escHtml(t.user_source)}</span>
        <span class="turn-preview">${escHtml(truncate(previewText, 80))}</span>
      </div>
      <div class="turn-stats">
        ${t.tool_calls.length ? `<span class="stat-chip tools">${t.tool_calls.length} ${_t('turns.tools')}</span>` : ''}
        ${t.subagent_spawns.length ? `<span class="stat-chip subagents">${t.subagent_spawns.length} ${_t('turns.subagents')}</span>` : ''}
        <span class="stat-chip duration">${fmtDuration(t.duration_ms)}</span>
        <span class="stat-chip cost">${fmtCost(t.cost?.total || 0)}</span>
        <span class="stat-chip tokens">${fmtTokens(t.usage?.totalTokens || 0)}</span>
        ${(t.cache_hit_rate > 0) ? `<span class="stat-chip cache">${Math.round(t.cache_hit_rate * 100)}% ${_t('turns.cache')}</span>` : ''}
        ${t.thinking_level ? `<span class="stat-chip thinking">💭 ${t.thinking_level}</span>` : ''}
        ${typeof showRaw === 'function' ? `<button class="btn-icon raw-btn" onclick="event.stopPropagation();showRaw(${t.index})" data-i18n-title="turns.view_raw" title="${_t('turns.view_raw')}" aria-label="${_t('turns.view_raw')}">{ }</button>` : ''}
      </div>
    </div>
    <div class="turn-body collapsed" id="turn-body-${t.index}">
      <div class="turn-detail">
        <!-- User message -->
        <div class="msg-block user-msg">
          <div class="msg-role">${_t('turns.user')} <span class="badge badge-${escHtml(t.user_source)} badge-type" style="font-size:10px">${escHtml(t.user_source)}</span></div>
          ${t.channel_meta
            ? renderChannelMsg(t.channel_meta)
            : `<pre class="msg-content">${escHtml(t.user_text.slice(0, 2000))}</pre>
               ${t.user_text.length > 2000 && typeof openFullUserText === 'function'
                 ? `<button class="tc-full-btn" onclick="openFullUserText(${t.index})">${_t('turns.show_full')} (${fmtSize(t.user_text.length)})</button>`
                 : ''}`
          }
        </div>

        <!-- Token breakdown -->
        <div class="token-bar">
          ${renderTokenBar(t.usage)}
        </div>

        <!-- Thinking + Tool calls (interleaved by round, merged headers) -->
        ${(() => {
          const roundTcs = {};
          for (const tc of t.tool_calls) {
            const r = tc.round_idx ?? 0;
            (roundTcs[r] = roundTcs[r] || []).push(tc);
          }
          let html = '';
          if (t.thinking_blocks && t.thinking_blocks.length > 0) {
            const maxR = Math.max(
              t.thinking_blocks.length - 1,
              ...Object.keys(roundTcs).map(Number),
              0
            );
            // Accumulate tool calls across rounds; flush when thinking appears or at end
            let pendingTcs = [];
            for (let r = 0; r <= maxR; r++) {
              const th = t.thinking_blocks[r];
              const tcs = roundTcs[r] || [];
              if (th) {
                // Flush accumulated tool calls before this thinking block
                if (pendingTcs.length) {
                  html += `
                  <div class="tool-calls">
                    <div class="tc-header">${_t('turns.tool_calls')}</div>
                    ${pendingTcs.map(tc => renderToolCall(tc)).join('')}
                  </div>`;
                  pendingTcs = [];
                }
                html += `
                <div class="thinking-block">
                  <div class="thinking-label">${_t('turns.thinking')}</div>
                  <pre class="thinking-content">${escHtml(th)}</pre>
                </div>`;
              }
              if (tcs.length) pendingTcs.push(...tcs);
            }
            // Flush remaining tool calls
            if (pendingTcs.length) {
              html += `
              <div class="tool-calls">
                <div class="tc-header">${_t('turns.tool_calls')}</div>
                ${pendingTcs.map(tc => renderToolCall(tc)).join('')}
              </div>`;
            }
          } else {
            if (t.thinking_text) html += `
            <div class="thinking-block">
              <div class="thinking-label">${_t('turns.thinking')}</div>
              <pre class="thinking-content">${escHtml(t.thinking_text)}</pre>
            </div>`;
            if (t.tool_calls.length) html += `
            <div class="tool-calls">
              <div class="tc-header">${_t('turns.tool_calls')}</div>
              ${t.tool_calls.map(tc => renderToolCall(tc)).join('')}
            </div>`;
          }
          if (t.thinking_encrypted) html += `<div class="thinking-block encrypted"><span class="thinking-label">${_t('turns.thinking_encrypted')}</span></div>`;
          return html;
        })()}

        <!-- Delivery mirror tags (merged from delivery-mirror events) -->
        ${(t.delivery_texts && t.delivery_texts.length) ? `
        <div class="delivery-tags">
          ${t.delivery_texts.map(dt => `<span class="delivery-tag">📨 ${escHtml(dt)}</span>`).join('')}
        </div>` : ''}

        <!-- Subagent spawns -->
        ${t.subagent_spawns.map(s => renderSubagent(s, 0)).join('')}

        <!-- Assistant response -->
        ${t.assistant_texts.map(txt => `
        <div class="msg-block assistant-msg">
          <div class="msg-role">${_t('turns.assistant')}</div>
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

  // "Show full" for truncated args
  let argFullBtns = '';
  if (tc.arguments_truncated) {
    for (const [k, origLen] of Object.entries(tc.arguments_truncated)) {
      const label = `${_t('turns.show_full')} (${k}, ${fmtSize(origLen)})`;
      argFullBtns += typeof openFullContent === 'function'
        ? `<button class="tc-full-btn" onclick="event.stopPropagation();openFullContent('${escHtml(tc.id)}','${escHtml(k)}')">${label}</button> `
        : '';
    }
  }

  // "Show full" for large result
  const resultFullBtn = (tc.result_size > 500 && typeof openFullContent === 'function')
    ? `<button class="tc-full-btn" onclick="event.stopPropagation();openFullContent('${escHtml(tc.id)}','result')">${_t('turns.show_full')} (${fmtSize(tc.result_size)})</button>`
    : '';

  return `
  <div class="tc-row ${errorClass}" data-category="${category}" onclick="toggleTcResult(this)">
    <span class="tc-icon">${icon}</span>
    <span class="tc-name">${tc.name}</span>
    <span class="tc-args">${escHtml(argSummary)}</span>
    ${durStr}${sizeStr}
    ${tc.is_error ? '<span class="tc-err-badge">ERROR</span>' : ''}
    ${argFullBtns ? `<div onclick="event.stopPropagation()">${argFullBtns}</div>` : ''}
    <div class="tc-result collapsed">
      <pre>${escHtml(tc.result_text)}</pre>
      ${resultFullBtn}
    </div>
  </div>`;
}

function extractAgentId(childSessionKey) {
  // Format: agent:{agentId}:{type}:{uuid}
  if (!childSessionKey) return null;
  const parts = childSessionKey.split(':');
  return (parts.length >= 2 && parts[0] === 'agent') ? parts[1] : null;
}

function renderSubagent(s, depth) {
  const outcomeClass = s.outcome === 'ok' ? 'outcome-ok' : (s.outcome === 'unknown' ? 'outcome-unknown' : 'outcome-error');
  const durStr = s.duration_ms ? fmtDuration(s.duration_ms) : '?';
  const costStr = s.cost_usd != null ? fmtCost(s.cost_usd) : '?';
  const tokensStr = s.total_tokens != null ? fmtTokens(s.total_tokens) : '?';
  const indent = depth > 0 ? `style="margin-left:${depth * 16}px"` : '';

  // Agent identification from child_session_key
  const agentId = extractAgentId(s.child_session_key);
  const isNamedAgent = agentId && agentId !== 'main';
  const agentBadge = isNamedAgent
    ? `<span class="badge badge-agent-named">🤖 ${escHtml(agentId)}</span>`
    : `<span class="badge badge-agent-sub">${_t('turns.sub_session')}</span>`;

  let childHtml = '';
  if (s.child_turns && s.child_turns.length) {
    // Expand child turns immediately — no secondary click needed
    childHtml = `
    <div class="subagent-children">
      <div class="subagent-children-label">${s.child_turns.length} ${_t('turns.child_turns')}</div>
      <div class="subagent-turns">
        ${s.child_turns.map(ct => renderChildTurn(ct, depth + 1)).join('')}
      </div>
    </div>`;
  } else if (s.announce_stats) {
    const as = s.announce_stats;
    childHtml = `
    <div class="subagent-announce-stats">
      <span class="dim">${_t('turns.from_announce')}</span>
      ${_t('turns.runtime')} ${fmtDuration(as.runtime_ms)}
      &middot; ${fmtTokens(as.total_tokens)} ${_t('turns.tokens')}
      (${_t('turns.in')} ${fmtTokens(as.input_tokens)} / ${_t('turns.out')} ${fmtTokens(as.output_tokens)})
    </div>`;
  }

  return `
  <div class="subagent-block" ${indent}>
    <div class="subagent-header" onclick="toggleSubagent(this)">
      <span class="subagent-icon">&#x1f500;</span>
      ${agentBadge}
      <span class="subagent-label">${escHtml(s.label || _t('turns.subagent'))}</span>
      <span class="badge ${outcomeClass}">${s.outcome}</span>
      <span class="subagent-stats">${durStr} &middot; ${costStr} &middot; ${tokensStr} ${_t('turns.tokens')}</span>
      ${s.child_session_id ? `<a href="/session/${s.child_session_id}" class="btn btn-sm" onclick="event.stopPropagation()">${_t('turns.open_session')}</a>` : ''}
    </div>
    <div class="subagent-body collapsed">
      <div class="subagent-task">
        ${escHtml(truncate(s.task, 300))}
        ${makeShowFullBtn(_t('turns.show_full'), _t('turns.subagent_task'), s.task, 300)}
      </div>
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
      <span class="child-turn-idx">${_t('turns.turn')} ${ct.index}</span>
      <span class="dim">${ct.tool_calls.length} ${_t('turns.child_tools')}</span>
      <span class="dim">${fmtDuration(ct.duration_ms)}</span>
      <span class="dim">${fmtCost(ct.cost?.total || 0)}</span>
      ${ct.user_source && ct.user_source !== 'chat' ? `<span class="badge badge-${ct.user_source}" style="font-size:9px">${ct.user_source}</span>` : ''}
    </div>
    <div class="child-turn-body">
      ${ct.thinking_text ? `
      <div class="thinking-block">
        <div class="thinking-label">${_t('turns.thinking')}</div>
        <pre class="thinking-content">${escHtml(truncate(ct.thinking_text, 1000))}</pre>
        ${makeShowFullBtn(_t('turns.show_full'), _t('turns.thinking'), ct.thinking_text, 1000)}
      </div>` : ''}
      ${ct.tool_calls.map(tc => renderToolCall(tc)).join('')}
      ${nestedSubagents}
      ${ct.assistant_texts.map(txt => `
        <pre class="child-response">${escHtml(truncate(txt, 500))}</pre>
        ${makeShowFullBtn(_t('turns.show_full'), _t('turns.assistant'), txt, 500)}
      `).join('')}
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
      <div class="token-seg input" style="width:${input/total*100}%" title="${_t('turns.input')} ${fmtTokens(input)}"></div>
      <div class="token-seg cache" style="width:${cache/total*100}%" title="${_t('turns.cache_label')} ${fmtTokens(cache)}"></div>
      <div class="token-seg output" style="width:${output/total*100}%" title="${_t('turns.output')} ${fmtTokens(output)}"></div>
    </div>
    <div class="token-legend">
      <span class="legend-item"><span class="dot input"></span>${_t('turns.input')} ${fmtTokens(input)}</span>
      <span class="legend-item"><span class="dot cache"></span>${_t('turns.cache_label')} ${fmtTokens(cache)}</span>
      <span class="legend-item"><span class="dot output"></span>${_t('turns.output')} ${fmtTokens(output)}</span>
    </div>
  `;
}

function toggleTurn(idx) {
  const body = qs(`#turn-body-${idx}`);
  body.classList.toggle('collapsed');
}

function toggleSubagent(headerEl) {
  const body = headerEl.nextElementSibling;
  if (body) body.classList.toggle('collapsed');
}

function toggleTcResult(el) {
  const result = el.querySelector('.tc-result');
  if (result) result.classList.toggle('collapsed');
}

function toggleEl(el) {
  if (el) el.classList.toggle('collapsed');
}

function toggleWorkflow(gid) {
  const body = qs(`#workflow-body-${gid}`);
  if (body) body.classList.toggle('collapsed');
}
