/* === ClawTracerX — shared turn rendering === */
/* Depends on app.js: fmtTokens, fmtCost, fmtSize, fmtDuration, fmtDate, truncate, escHtml, shortenPath, toolIcon */

const SYSTEM_SOURCES = new Set(['system', 'subagent_announce', 'cron_announce']);
const DELIVERY_MIRROR_SOURCE = 'delivery_mirror';

function fmtChars(n) {
  if (!n) return '0';
  if (n < 1000) return n + _t('turns.ch');
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
  let i = 0;
  while (i < turns.length) {
    const t = turns[i];
    const gid = t.workflow_group_id;
    if (gid != null && !processedWorkflows.has(gid)) {
      processedWorkflows.add(gid);
      const bounds = workflowBounds.get(gid);

      // Separate workflow turns (wf==gid) from interleaved gap turns (wf==null)
      const workflowTurns = [];
      const gapTurns = [];
      for (let j = bounds.first; j <= bounds.last; j++) {
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

  let animIdx = 0;
  for (const item of items) {
    const firstTurnIdx = item.startIdx;
    // Insert compaction divider at the context boundary
    if (firstTurnIdx === contextBoundaryIdx && firstTurnIdx > 0 && compactionEvents.length > 0) {
      const lastCe = compactionEvents[compactionEvents.length - 1];
      const tokensBefore = lastCe.tokens_before ? fmtTokens(lastCe.tokens_before) : '?';
      const tokensAfter  = lastCe.tokens_after  ? fmtTokens(lastCe.tokens_after)  : null;
      const hookLabel = lastCe.from_hook ? ' ' + _t('turns.hook') : '';
      const summaryHtml = lastCe.summary ? `
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
  container.innerHTML = html;
}

function renderWorkflowGroup(turns, animIdx) {
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

  const isDeliveryMirror = t.user_source === DELIVERY_MIRROR_SOURCE;

  let classes = 'turn-card';
  if (hasErrors)          classes += ' has-errors';
  if (isCompacted)        classes += ' compacted';
  if (isHighCost && !hasErrors) classes += ' high-cost';
  if (isSubagentSpawn && !hasErrors && !isHighCost) classes += ' spawns-subagent';
  if (isDeliveryMirror)   classes += ' delivery-mirror';

  const delay = (animIdx || 0) * 40;

  // preview: delivery_mirror has no user_text — show assistant text instead
  const previewText = isDeliveryMirror
    ? (t.assistant_texts[0] || '').replace(/\n/g, ' ')
    : (t.user_text || '').replace(/\n/g, ' ');

  return `
  <div class="${classes}" id="turn-${t.index}" style="animation-delay:${delay}ms">
    <div class="turn-header" onclick="toggleTurn(${t.index})">
      <div class="turn-left">
        <span class="turn-index">${_t('turns.turn')} ${t.index}</span>
        ${isCompacted ? `<span class="badge badge-compacted">${_t('turns.compacted_label')}</span>` : ''}
        <span class="badge badge-${t.user_source} badge-type">${isDeliveryMirror ? '📨 ' + _t('turns.delivered') : t.user_source}</span>
        <span class="turn-preview">${escHtml(truncate(previewText, 80))}</span>
      </div>
      <div class="turn-stats">
        ${t.tool_calls.length ? `<span class="stat-chip tools">${t.tool_calls.length} ${_t('turns.tools')}</span>` : ''}
        ${t.subagent_spawns.length ? `<span class="stat-chip subagents">${t.subagent_spawns.length} ${_t('turns.subagents')}</span>` : ''}
        ${!isDeliveryMirror ? `<span class="stat-chip duration">${fmtDuration(t.duration_ms)}</span>` : ''}
        ${!isDeliveryMirror ? `<span class="stat-chip cost">${fmtCost(t.cost.total || 0)}</span>` : ''}
        ${!isDeliveryMirror ? `<span class="stat-chip tokens">${fmtTokens(t.usage.totalTokens || 0)}</span>` : ''}
        ${(t.cache_hit_rate > 0) ? `<span class="stat-chip cache">${Math.round(t.cache_hit_rate * 100)}% ${_t('turns.cache')}</span>` : ''}
        ${t.thinking_level ? `<span class="stat-chip thinking">💭 ${t.thinking_level}</span>` : ''}
        ${typeof showRaw === 'function' ? `<button class="btn-icon raw-btn" onclick="event.stopPropagation();showRaw(${t.index})" data-i18n-title="turns.view_raw" title="${_t('turns.view_raw')}">{ }</button>` : ''}
      </div>
    </div>
    <div class="turn-body" id="turn-body-${t.index}" style="display:none">
      <div class="turn-detail">
        ${isDeliveryMirror ? '' : `
        <!-- User message -->
        <div class="msg-block user-msg">
          <div class="msg-role">${_t('turns.user')} <span class="badge badge-${t.user_source} badge-type" style="font-size:10px">${t.user_source}</span></div>
          <pre class="msg-content">${escHtml(t.user_text.slice(0, 2000))}</pre>
        </div>`}

        <!-- Token breakdown -->
        <div class="token-bar">
          ${renderTokenBar(t.usage)}
        </div>

        <!-- Thinking -->
        ${t.thinking_text ? `
        <div class="thinking-block">
          <div class="thinking-label">${_t('turns.thinking')}</div>
          <pre class="thinking-content">${escHtml(t.thinking_text)}</pre>
        </div>` : ''}
        ${t.thinking_encrypted ? `<div class="thinking-block encrypted"><span class="thinking-label">${_t('turns.thinking_encrypted')}</span></div>` : ''}

        <!-- Tool calls -->
        ${t.tool_calls.length ? `
        <div class="tool-calls">
          <div class="tc-header">${_t('turns.tool_calls')}</div>
          ${t.tool_calls.map(tc => renderToolCall(tc)).join('')}
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

function toggleWorkflow(gid) {
  const body = qs(`#workflow-body-${gid}`);
  if (body) body.style.display = body.style.display === 'none' ? 'block' : 'none';
}
