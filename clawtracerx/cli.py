"""
ClawTracerX CLI — Command-line interface for OpenClaw agent monitoring.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from clawtracerx.session_parser import (
    AGENTS_DIR,
    KST,
    _truncate,
    _ts_to_dt,
    get_raw_turn_lines,
    list_sessions,
    load_cron_runs,
    load_subagent_runs,
    parse_session,
)

# --- ANSI colors ---
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
GRAY = "\033[90m"

# Tool icons
TOOL_ICONS = {
    "read": "📁", "edit": "✏️ ", "write": "📝", "exec": "💻",
    "glob": "🔍", "grep": "🔎", "sessions_spawn": "🔀",
    "sessions_send": "📨", "message": "💬", "broadcast": "📡",
    "fetch": "🌐", "web_search": "🌐",
}


def _icon(tool_name: str) -> str:
    for key, icon in TOOL_ICONS.items():
        if key in tool_name.lower():
            return icon
    return "🔧"


def _fmt_duration(ms: Optional[int]) -> str:
    if ms is None:
        return ""
    if ms < 1000:
        return f"{ms}ms"
    if ms < 60000:
        return f"{ms/1000:.1f}s"
    minutes = ms // 60000
    secs = (ms % 60000) / 1000
    return f"{minutes}m {secs:.0f}s"


def _fmt_cost(cost: float) -> str:
    if cost <= 0:
        return "$0"
    if cost < 0.001:
        return f"${cost:.6f}"
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.3f}"


def _fmt_tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 1000000:
        return f"{n/1000:.1f}K"
    return f"{n/1000000:.2f}M"


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n/1024:.1f}KB"
    return f"{n/(1024*1024):.1f}MB"


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "?"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# --- Commands ---

def cmd_sessions(agent: str = "all", last_n: int = 20, session_type: Optional[str] = None):
    """List sessions."""
    sessions = list_sessions(
        agent_id=None if agent == "all" else agent,
        last_n=last_n,
        session_type=session_type,
    )

    if not sessions:
        print(f"{DIM}No sessions found.{RESET}")
        return

    # Header
    print(f"\n{BOLD}{'ID':<12} {'Agent':<10} {'Type':<10} {'Model':<20} {'Turns':>5} {'Tokens':>8} {'Cost':>8} {'Size':>7} {'Date'}{RESET}")
    print("─" * 100)

    for s in sessions:
        sid = s["session_id"][:10]
        stype = s.get("type", "?")
        type_color = {"cron": CYAN, "heartbeat": MAGENTA, "subagent": YELLOW, "chat": GREEN}.get(stype, WHITE)

        print(
            f"{BLUE}{sid:<12}{RESET} "
            f"{s['agent_id']:<10} "
            f"{type_color}{stype:<10}{RESET} "
            f"{s.get('model', '?')[:20]:<20} "
            f"{s.get('turns', 0):>5} "
            f"{_fmt_tokens(s.get('tokens', 0)):>8} "
            f"{_fmt_cost(s.get('cost', 0)):>8} "
            f"{_fmt_size(s.get('file_size', 0)):>7} "
            f"{_fmt_dt(s.get('modified', s.get('started_at')))}"
        )

    print(f"\n{DIM}Total: {len(sessions)} sessions{RESET}\n")


def cmd_analyze(session_ref: str, no_subagents: bool = False):
    """Analyze a session in detail."""
    file_path = _resolve_session(session_ref)
    if not file_path:
        print(f"{RED}Session not found: {session_ref}{RESET}")
        return

    analysis = parse_session(file_path, recursive_subagents=not no_subagents)
    _print_analysis(analysis, depth=0)


def _print_analysis(analysis, depth: int = 0):
    """Print a full session analysis."""
    indent = "  " * depth
    prefix = f"{indent}{'│ ' if depth > 0 else ''}"

    # Header
    print(f"\n{prefix}{BOLD}{'═' * 60}{RESET}")
    print(f"{prefix}{BOLD}Session: {CYAN}{analysis.session_id[:12]}{RESET} {BOLD}({analysis.agent_id}){RESET}")
    print(f"{prefix}Started: {_fmt_dt(analysis.started_at)} | Model: {YELLOW}{analysis.model}{RESET} | Provider: {analysis.provider}")
    print(f"{prefix}Type: {analysis.session_type} | CWD: {DIM}{analysis.cwd}{RESET}")
    if analysis.compactions > 0:
        print(f"{prefix}{DIM}Compactions: {analysis.compactions}{RESET}")

    # Context injection info (from sessions.json)
    if analysis.context:
        ctx = analysis.context
        print(f"{prefix}System Prompt: {_fmt_size(ctx.system_prompt_chars)} "
              f"(project: {_fmt_size(ctx.project_context_chars)}, "
              f"other: {_fmt_size(ctx.non_project_context_chars)})")

        files_str = []
        for f in ctx.injected_files:
            status = "MISSING" if f.missing else ("TRUNC" if f.truncated else "ok")
            files_str.append(f"{f.name}({_fmt_size(f.injected_chars)},{status})")
        if files_str:
            print(f"{prefix}Context Files: {', '.join(files_str)}")

        if ctx.skills:
            skills_str = ", ".join(s.name for s in ctx.skills)
            print(f"{prefix}Skills: {skills_str}")

    print(f"{prefix}{BOLD}{'═' * 60}{RESET}")

    for turn in analysis.turns:
        _print_turn(turn, prefix)

    # Summary
    print(f"\n{prefix}{BOLD}{'═' * 60}{RESET}")
    print(f"{prefix}{BOLD}Summary{RESET}")
    print(f"{prefix}  Turns: {len(analysis.turns)} | Duration: {_fmt_duration(analysis.total_duration_ms)} | Cost: {GREEN}{_fmt_cost(analysis.total_cost)}{RESET}")

    if analysis.compaction_events:
        for i, ce in enumerate(analysis.compaction_events):
            summary_preview = _truncate(ce.summary.replace("\n", " "), 100) if ce.summary else ""
            after_str = f" → {_fmt_tokens(ce.tokens_after)}" if ce.tokens_after else ""
            print(f"{prefix}  Compaction #{i+1}: {_fmt_tokens(ce.tokens_before)} tokens{after_str}"
                  + (f" — {DIM}{summary_preview}{RESET}" if summary_preview else ""))

    total_input = sum(t.usage.get("input", 0) for t in analysis.turns)
    total_output = sum(t.usage.get("output", 0) for t in analysis.turns)
    total_cache = sum(t.usage.get("cacheRead", 0) for t in analysis.turns)
    print(f"{prefix}  Tokens: in={_fmt_tokens(total_input)} out={_fmt_tokens(total_output)} cache={_fmt_tokens(total_cache)} total={_fmt_tokens(analysis.total_tokens)}")

    # Tool usage summary
    tool_counts = {}
    error_count = 0
    for turn in analysis.turns:
        for tc in turn.tool_calls:
            tool_counts[tc.name] = tool_counts.get(tc.name, 0) + 1
            if tc.is_error:
                error_count += 1
    if tool_counts:
        tools_str = ", ".join(f"{name}×{count}" for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]))
        print(f"{prefix}  Tools: {tools_str}")
        if error_count:
            print(f"{prefix}  {RED}Errors: {error_count}{RESET}")

    # Subagent summary
    total_spawns = sum(len(t.subagent_spawns) for t in analysis.turns)
    if total_spawns:
        ok = sum(1 for t in analysis.turns for s in t.subagent_spawns if s.outcome == "ok")
        err = total_spawns - ok
        print(f"{prefix}  Subagents: {total_spawns} (success: {GREEN}{ok}{RESET}, error: {RED}{err}{RESET})")

    print()


def _print_turn(turn, prefix: str):
    """Print a single turn."""
    print(f"\n{prefix}{BOLD}── Turn {turn.index} {'─' * 48}{RESET}")

    # User message
    source_str = ""
    if turn.user_source != "chat":
        source_str = f" ({turn.user_source})"
    user_preview = _truncate(turn.user_text.replace("\n", " "), 100)
    print(f"{prefix}  📩 {BLUE}User{source_str}{RESET}")
    if user_preview and user_preview != "[implicit]":
        print(f"{prefix}     {DIM}\"{user_preview}\"{RESET}")

    # Assistant
    cost_str = _fmt_cost(turn.cost.get("total", 0))
    dur_str = _fmt_duration(turn.duration_ms)
    stats_parts = []
    if dur_str:
        stats_parts.append(f"⏱ {dur_str}")
    stats_parts.append(f"💰 {cost_str}")
    stats_str = "  ".join(stats_parts)

    print(f"\n{prefix}  🤖 {BOLD}Assistant{RESET}  {GRAY}{stats_str}{RESET}")

    # Token details
    token_parts = []
    for k, label in [("input", "in"), ("output", "out"), ("cacheRead", "cache"), ("totalTokens", "total")]:
        v = turn.usage.get(k, 0)
        if v > 0:
            token_parts.append(f"{label}={_fmt_tokens(v)}")
    if turn.cache_hit_rate > 0:
        token_parts.append(f"cache_hit={turn.cache_hit_rate:.0%}")
    if token_parts:
        print(f"{prefix}     Tokens: {', '.join(token_parts)}")

    # Thinking
    if turn.thinking_text:
        preview = _truncate(turn.thinking_text.replace("\n", " "), 120)
        print(f"{prefix}     {MAGENTA}Thinking: \"{preview}\"{RESET}")
    elif turn.thinking_encrypted:
        print(f"{prefix}     {DIM}Thinking: [encrypted]{RESET}")

    # Tool calls
    for tc in turn.tool_calls:
        _print_tool_call(tc, prefix + "     ")

    # Subagent spawns (with recursive child turns)
    for spawn in turn.subagent_spawns:
        _print_subagent(spawn, prefix + "     ")

    # Assistant text (final response)
    for text in turn.assistant_texts:
        preview = _truncate(text.replace("\n", " "), 150)
        if preview:
            print(f"{prefix}     💬 {DIM}\"{preview}\"{RESET}")


def _print_tool_call(tc, prefix: str):
    """Print a tool call."""
    icon = _icon(tc.name)
    dur_str = ""
    if tc.duration_ms is not None:
        dur_str = f"  {GRAY}{_fmt_duration(tc.duration_ms)}{RESET}"

    # Concise argument display
    arg_str = ""
    if tc.name in ("read", "write", "edit"):
        fp = tc.arguments.get("file_path", "")
        if fp:
            # Shorten home dir
            fp = fp.replace(str(Path.home()), "~")
            arg_str = f"({fp})"
    elif tc.name == "exec":
        cmd = tc.arguments.get("command", "")
        arg_str = f"({_truncate(cmd, 60)})"
    elif tc.name == "glob":
        pattern = tc.arguments.get("pattern", "")
        arg_str = f"({pattern})"
    elif tc.name == "grep":
        pattern = tc.arguments.get("pattern", "")
        arg_str = f"({_truncate(pattern, 40)})"
    elif tc.name == "sessions_spawn":
        label = tc.arguments.get("label", "")
        arg_str = f"({label})" if label else ""

    error_str = f"  {RED}ERROR{RESET}" if tc.is_error else ""
    size_str = f"  {DIM}{_fmt_size(tc.result_size)}{RESET}" if tc.result_size > 500 else ""

    print(f"{prefix}├─ {icon} {CYAN}{tc.name}{RESET}{arg_str}{dur_str}{size_str}{error_str}")


def _print_subagent(spawn, prefix: str):
    """Print a subagent spawn with its child turns."""
    dur_str = _fmt_duration(spawn.duration_ms) if spawn.duration_ms else "?"
    cost_str = _fmt_cost(spawn.cost_usd) if spawn.cost_usd else "?"
    tokens_str = _fmt_tokens(spawn.total_tokens) if spawn.total_tokens else "?"
    outcome_color = GREEN if spawn.outcome == "ok" else RED

    print(f"{prefix}├─ 🔀 {BOLD}{YELLOW}subagent{RESET} → {spawn.label or spawn.child_session_id or '?'}")
    print(f"{prefix}│     task: {DIM}\"{_truncate(spawn.task, 100)}\"{RESET}")
    print(f"{prefix}│     {outcome_color}{spawn.outcome}{RESET} | {dur_str} | {cost_str} | {tokens_str} tokens")

    if spawn.child_turns:
        for child_turn in spawn.child_turns:
            for tc in child_turn.tool_calls:
                _print_tool_call(tc, prefix + "│     ")
            for text in child_turn.assistant_texts:
                preview = _truncate(text.replace("\n", " "), 100)
                if preview:
                    print(f"{prefix}│     💬 {DIM}\"{preview}\"{RESET}")
        print(f"{prefix}│     ✅ Done ({len(spawn.child_turns)} turns)")


def cmd_raw(session_ref: str, turn_index: int):
    """Show raw JSONL for a specific turn."""
    file_path = _resolve_session(session_ref)
    if not file_path:
        print(f"{RED}Session not found: {session_ref}{RESET}")
        return

    raw_lines = get_raw_turn_lines(file_path, turn_index)
    if not raw_lines:
        print(f"{RED}Turn {turn_index} not found.{RESET}")
        return

    print(f"\n{BOLD}Raw JSONL — Turn {turn_index} ({len(raw_lines)} entries){RESET}\n")
    for i, entry in enumerate(raw_lines):
        print(f"{GRAY}--- entry {i} ---{RESET}")
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    print()


def cmd_crons(last_n: int = 20, job: Optional[str] = None):
    """Show cron run history."""
    runs = load_cron_runs(job_id=job, last_n=last_n)
    if not runs:
        print(f"{DIM}No cron runs found.{RESET}")
        return

    print(f"\n{BOLD}{'Job':<25} {'Agent':<8} {'Status':<8} {'Session':<12} {'Date'}{RESET}")
    print("─" * 80)

    for run in runs:
        status_color = GREEN if run.status == "ok" else RED
        dt = _ts_to_dt(run.ts)
        print(
            f"{run.job_name[:24]:<25} "
            f"{run.agent_id:<8} "
            f"{status_color}{run.status:<8}{RESET} "
            f"{BLUE}{run.session_id[:10]:<12}{RESET} "
            f"{_fmt_dt(dt)}"
        )
        if run.error:
            print(f"  {RED}{_truncate(run.error, 120)}{RESET}")
        elif run.summary:
            print(f"  {DIM}{_truncate(run.summary, 120)}{RESET}")

    print(f"\n{DIM}Total: {len(runs)} runs{RESET}\n")


def cmd_subagents(parent: Optional[str] = None, last_n: int = 20):
    """Show subagent runs."""
    runs = load_subagent_runs()
    if not runs:
        print(f"{DIM}No subagent runs found.{RESET}")
        return

    items = list(runs.values())
    items.sort(key=lambda r: r.get("createdAt", 0), reverse=True)

    if parent:
        items = [r for r in items if parent in r.get("requesterSessionKey", "")]

    items = items[:last_n]

    print(f"\n{BOLD}{'Label':<35} {'Outcome':<8} {'Duration':>10} {'Parent':<15} {'Date'}{RESET}")
    print("─" * 95)

    for run in items:
        label = run.get("label", run.get("runId", "?")[:10])[:34]
        outcome = run.get("outcome", {})
        status = outcome.get("status", "?") if isinstance(outcome, dict) else str(outcome)
        status_color = GREEN if status == "ok" else RED

        started = run.get("startedAt", 0)
        ended = run.get("endedAt", 0)
        dur = _fmt_duration(ended - started) if started and ended else "?"

        req_key = run.get("requesterSessionKey", "")
        # Extract agent from key
        parts = req_key.split(":")
        parent_label = parts[1] if len(parts) >= 2 else "?"
        parent_type = parts[2] if len(parts) >= 3 else ""
        parent_str = f"{parent_label}/{parent_type}"

        dt = _ts_to_dt(started)

        print(
            f"{label:<35} "
            f"{status_color}{status:<8}{RESET} "
            f"{dur:>10} "
            f"{parent_str:<15} "
            f"{_fmt_dt(dt)}"
        )

    print(f"\n{DIM}Total: {len(items)} runs{RESET}\n")


def cmd_cost(period: str = "today", agent: str = "all"):
    """Show cost summary."""
    sessions = list_sessions(
        agent_id=None if agent == "all" else agent,
        last_n=500,
    )

    now = datetime.now(KST)
    if period == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    else:
        cutoff = datetime.min.replace(tzinfo=KST)

    # Filter by period
    filtered = [s for s in sessions if s.get("modified", datetime.min.replace(tzinfo=KST)) >= cutoff]

    if not filtered:
        print(f"{DIM}No sessions in period '{period}'.{RESET}")
        return

    # Aggregate by agent
    by_agent = {}
    by_type = {}
    by_model = {}
    total_cost = 0
    total_tokens = 0

    for s in filtered:
        aid = s["agent_id"]
        stype = s.get("type", "chat")
        model = s.get("model", "unknown")
        cost = s.get("cost", 0)
        tokens = s.get("tokens", 0)

        by_agent[aid] = by_agent.get(aid, 0) + cost
        by_type[stype] = by_type.get(stype, 0) + cost
        by_model[model] = by_model.get(model, 0) + cost
        total_cost += cost
        total_tokens += tokens

    print(f"\n{BOLD}Cost Summary — {period} ({_fmt_dt(cutoff)} ~ now){RESET}")
    print(f"{'─' * 50}")

    print(f"\n{BOLD}By Agent:{RESET}")
    for aid, cost in sorted(by_agent.items(), key=lambda x: -x[1]):
        bar_len = int(cost / max(total_cost, 0.001) * 30)
        bar = "█" * bar_len
        print(f"  {aid:<12} {GREEN}{_fmt_cost(cost):>8}{RESET}  {CYAN}{bar}{RESET}")

    print(f"\n{BOLD}By Type:{RESET}")
    for stype, cost in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {stype:<12} {GREEN}{_fmt_cost(cost):>8}{RESET}")

    print(f"\n{BOLD}By Model:{RESET}")
    for model, cost in sorted(by_model.items(), key=lambda x: -x[1]):
        print(f"  {model[:25]:<25} {GREEN}{_fmt_cost(cost):>8}{RESET}")

    print(f"\n{BOLD}Total: {GREEN}{_fmt_cost(total_cost)}{RESET} | Tokens: {_fmt_tokens(total_tokens)} | Sessions: {len(filtered)}")
    print()


# --- Session resolver ---

def _resolve_session(ref: str) -> Optional[Path]:
    """Resolve a session reference to a file path.
    Accepts: full path, session UUID (prefix), agent:uuid format.
    """
    ref_path = Path(ref)
    if ref_path.exists() and ref_path.suffix == ".jsonl":
        return ref_path

    # Try agent:uuid format
    if ":" in ref:
        parts = ref.split(":", 1)
        agent_id, session_prefix = parts
        sessions_dir = AGENTS_DIR / agent_id / "sessions"
        if sessions_dir.exists():
            for f in sessions_dir.glob(f"{session_prefix}*.jsonl"):
                return f
        return None

    # Try UUID prefix search across all agents
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            continue
        for f in sessions_dir.glob(f"{ref}*.jsonl"):
            return f

    return None


def cmd_context(session_ref: str):
    """Show detailed context injection info for a session."""
    file_path = _resolve_session(session_ref)
    if not file_path:
        print(f"{RED}Session not found: {session_ref}{RESET}")
        return

    analysis = parse_session(file_path, recursive_subagents=False)

    print(f"\n{BOLD}Context Injection for session {CYAN}{analysis.session_id[:10]}{RESET} {BOLD}({analysis.agent_id}){RESET}")
    print("=" * 60)

    if not analysis.context:
        print(f"{DIM}No context metadata available (sessions.json not found or no match).{RESET}")
        return

    ctx = analysis.context

    # System prompt
    print(f"System Prompt: {BOLD}{_fmt_size(ctx.system_prompt_chars)}{RESET} "
          f"(project: {_fmt_size(ctx.project_context_chars)}, "
          f"other: {_fmt_size(ctx.non_project_context_chars)})")
    if ctx.bootstrap_max_chars:
        workspace_str = f" | Workspace: {DIM}{ctx.workspace_dir}{RESET}" if ctx.workspace_dir else ""
        print(f"Bootstrap Max: {ctx.bootstrap_max_chars:,} chars{workspace_str}")
    if ctx.sandbox_mode:
        print(f"Sandbox: {ctx.sandbox_mode}")

    # Injected files
    if ctx.injected_files:
        print(f"\n{BOLD}Injected Files:{RESET}")
        for f in ctx.injected_files:
            if f.missing:
                status = f"{RED}MISSING{RESET}"
                size_str = ""
            elif f.truncated:
                status = f"{YELLOW}TRUNC{RESET}"
                size_str = f"  {_fmt_size(f.injected_chars)}"
            else:
                status = f"{GREEN}ok{RESET}"
                size_str = f"  {_fmt_size(f.injected_chars)}"
            print(f"  {f.name:<20}{size_str:<10}  {status}")

    # Skills
    if ctx.skills:
        total_skill_chars = sum(s.block_chars for s in ctx.skills)
        print(f"\n{BOLD}Skills ({_fmt_size(total_skill_chars)}):{RESET}")
        for s in ctx.skills:
            print(f"  {s.name:<30}  {s.block_chars:,} chars")

    # Tools
    if ctx.tools:
        total_tool_chars = sum(t.summary_chars + t.schema_chars for t in ctx.tools)
        print(f"\n{BOLD}Tools ({_fmt_size(total_tool_chars)}):{RESET}")
        for t in ctx.tools:
            print(f"  {t.name:<30}  {t.summary_chars}+{t.schema_chars} chars")

    # Session token summary
    parts = []
    if analysis.context_tokens:
        parts.append(f"context={_fmt_tokens(analysis.context_tokens)}")
    if analysis.session_compaction_count:
        parts.append(f"compactions={analysis.session_compaction_count}")
    if analysis.memory_flush_at:
        parts.append(f"memory_flush={_fmt_dt(analysis.memory_flush_at)}")
    if parts:
        print(f"\n{BOLD}Session Tokens:{RESET} {', '.join(parts)}")

    print()
