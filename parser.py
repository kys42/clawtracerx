"""
ocmon parser — OpenClaw session JSONL parser.

Parses session transcripts into structured Turn objects
with tool calls, subagent spawns, token usage, and cost tracking.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Union

KST = timezone(timedelta(hours=9))
OPENCLAW_DIR = Path.home() / ".openclaw"
AGENTS_DIR = OPENCLAW_DIR / "agents"
SUBAGENTS_FILE = OPENCLAW_DIR / "subagents" / "runs.json"
CRON_JOBS_FILE = OPENCLAW_DIR / "cron" / "jobs.json"
CRON_RUNS_DIR = OPENCLAW_DIR / "cron" / "runs"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    result_text: str = ""
    result_size: int = 0
    duration_ms: Optional[int] = None
    is_error: bool = False
    status: str = ""


@dataclass
class SubagentSpawn:
    run_id: str
    label: str
    task: str
    child_session_key: str
    child_session_id: Optional[str] = None
    child_turns: list = field(default_factory=list)
    duration_ms: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    outcome: str = "unknown"


@dataclass
class Turn:
    index: int
    user_text: str = ""
    user_source: str = "chat"
    assistant_texts: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    subagent_spawns: list = field(default_factory=list)
    thinking_text: Optional[str] = None
    thinking_encrypted: bool = False
    model: str = ""
    provider: str = ""
    api: str = ""
    usage: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    stop_reason: str = ""
    duration_ms: int = 0
    timestamp: Optional[datetime] = None
    raw_lines: list = field(default_factory=list)


@dataclass
class SessionAnalysis:
    session_id: str
    agent_id: str
    session_type: str = "chat"
    started_at: Optional[datetime] = None
    cwd: str = ""
    model: str = ""
    provider: str = ""
    turns: list = field(default_factory=list)
    total_cost: float = 0.0
    total_tokens: int = 0
    total_duration_ms: int = 0
    compactions: int = 0
    file_path: str = ""


@dataclass
class CronRun:
    ts: int
    job_id: str
    job_name: str = ""
    action: str = ""
    status: str = ""
    summary: str = ""
    error: str = ""
    session_id: str = ""
    session_key: str = ""
    agent_id: str = ""
    duration_ms: int = 0


# --- Helpers ---

def _ts_to_dt(ts) -> Optional[datetime]:
    """Convert ms-epoch int or ISO string to datetime (KST)."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts / 1000, tz=KST)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.astimezone(KST)
        except (ValueError, TypeError):
            return None
    return None


def _truncate(text: str, max_len: int = 200) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _detect_source(user_text: str) -> str:
    """Detect user message source from text prefix."""
    if not user_text:
        return "chat"
    if user_text.startswith("[cron:"):
        return "cron"
    if user_text.startswith("[System Message]"):
        if "subagent" in user_text.lower():
            return "subagent_announce"
        return "system"
    if user_text.startswith("[heartbeat"):
        return "heartbeat"
    # Heartbeat prompt patterns
    if "HEARTBEAT.md" in user_text or "heartbeat" in user_text.lower():
        return "heartbeat"
    return "chat"


def _extract_session_id_from_key(session_key: str) -> Optional[str]:
    """Extract UUID from session key like 'agent:main:subagent:de0b2c55-...'"""
    parts = session_key.split(":")
    if len(parts) >= 4:
        return parts[-1]
    return None


# --- Subagent registry ---

_subagent_cache = None

def load_subagent_runs() -> dict:
    global _subagent_cache
    if _subagent_cache is not None:
        return _subagent_cache
    if not SUBAGENTS_FILE.exists():
        _subagent_cache = {}
        return _subagent_cache
    with open(SUBAGENTS_FILE) as f:
        data = json.load(f)
    _subagent_cache = data.get("runs", {})
    return _subagent_cache


def get_subagent_run(run_id: str) -> Optional[dict]:
    runs = load_subagent_runs()
    return runs.get(run_id)


def find_subagent_child_session(child_session_key: str) -> Optional[Path]:
    """Find the JSONL file for a child session key."""
    session_id = _extract_session_id_from_key(child_session_key)
    if not session_id:
        return None
    # Search all agent session dirs
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            continue
        for f in sessions_dir.iterdir():
            if f.name.startswith(session_id) and f.suffix == ".jsonl":
                return f
    return None


# --- Cron ---

def load_cron_jobs() -> dict:
    """Load cron job definitions. Returns {jobId: job_dict}."""
    if not CRON_JOBS_FILE.exists():
        return {}
    with open(CRON_JOBS_FILE) as f:
        data = json.load(f)
    jobs = {}
    for job in data if isinstance(data, list) else data.get("jobs", []):
        jid = job.get("id") or job.get("jobId", "")
        if jid:
            jobs[jid] = job
    return jobs


def load_cron_runs(job_id: Optional[str] = None, last_n: int = 50) -> list:
    """Load cron run logs. Returns list of CronRun sorted by ts desc."""
    if not CRON_RUNS_DIR.exists():
        return []
    jobs = load_cron_jobs()
    results = []
    files = list(CRON_RUNS_DIR.glob("*.jsonl"))
    for f in files:
        fid = f.stem
        if job_id and fid != job_id:
            continue
        job_name = jobs.get(fid, {}).get("label", jobs.get(fid, {}).get("name", fid[:8]))
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("action") != "finished":
                    continue
                sk = d.get("sessionKey", "")
                agent_id = ""
                if sk:
                    parts = sk.split(":")
                    if len(parts) >= 2:
                        agent_id = parts[1]
                results.append(CronRun(
                    ts=d.get("ts", 0),
                    job_id=fid,
                    job_name=job_name,
                    action=d.get("action", ""),
                    status=d.get("status", ""),
                    summary=_truncate(d.get("summary", ""), 300),
                    error=_truncate(d.get("error", ""), 300),
                    session_id=d.get("sessionId", ""),
                    session_key=sk,
                    agent_id=agent_id,
                ))
    results.sort(key=lambda r: r.ts, reverse=True)
    return results[:last_n]


# --- Session parsing ---

def parse_session(file_path: str | Path, recursive_subagents: bool = True) -> SessionAnalysis:
    """Parse a session JSONL file into a SessionAnalysis."""
    file_path = Path(file_path)
    lines = []
    with open(file_path) as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                lines.append(json.loads(raw_line))
            except json.JSONDecodeError:
                continue

    # Detect agent_id from path
    agent_id = "unknown"
    parts = file_path.parts
    try:
        agents_idx = parts.index("agents")
        if agents_idx + 1 < len(parts):
            agent_id = parts[agents_idx + 1]
    except ValueError:
        pass

    session_id = file_path.stem.split("-topic-")[0]

    analysis = SessionAnalysis(
        session_id=session_id,
        agent_id=agent_id,
        file_path=str(file_path),
    )

    # First pass: extract metadata
    current_model = ""
    current_provider = ""
    current_api = ""

    for entry in lines:
        etype = entry.get("type")
        if etype == "session":
            analysis.started_at = _ts_to_dt(entry.get("timestamp"))
            analysis.cwd = entry.get("cwd", "")
        elif etype == "model_change":
            current_model = entry.get("modelId", "")
            current_provider = entry.get("provider", "")
        elif etype == "compaction":
            analysis.compactions += 1

    analysis.model = current_model
    analysis.provider = current_provider

    # Second pass: build turns
    # A turn starts with a user message and includes all assistant messages + tool results
    # until the next user message
    turns = []
    current_turn = None
    pending_tool_calls = {}  # id -> ToolCall
    turn_raw_lines = []

    for entry in lines:
        etype = entry.get("type")

        if etype == "model_change":
            current_model = entry.get("modelId", "")
            current_provider = entry.get("provider", "")
            current_api = ""

        if etype != "message":
            continue

        msg = entry.get("message", {})
        role = msg.get("role", "")
        ts = _ts_to_dt(msg.get("timestamp") or entry.get("timestamp"))

        if role == "user":
            # Finalize previous turn
            if current_turn is not None:
                current_turn.raw_lines = turn_raw_lines
                _finalize_turn(current_turn, pending_tool_calls)
                turns.append(current_turn)

            # Start new turn
            user_text = ""
            content = msg.get("content", [])
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        user_text += c.get("text", "")
                    elif isinstance(c, str):
                        user_text += c
            elif isinstance(content, str):
                user_text = content

            source = _detect_source(user_text)

            current_turn = Turn(
                index=len(turns),
                user_text=user_text,
                user_source=source,
                timestamp=ts,
                model=current_model,
                provider=current_provider,
                api=current_api,
            )
            pending_tool_calls = {}
            turn_raw_lines = [entry]

        elif role == "assistant":
            if current_turn is None:
                # Assistant message without prior user - create implicit turn
                current_turn = Turn(
                    index=len(turns),
                    user_text="[implicit]",
                    user_source="system",
                    timestamp=ts,
                    model=current_model,
                    provider=current_provider,
                    api=current_api,
                )
                pending_tool_calls = {}
                turn_raw_lines = []

            turn_raw_lines.append(entry)
            content = msg.get("content", [])

            # Update model info from this message
            if msg.get("model"):
                current_turn.model = msg["model"]
                current_model = msg["model"]
            if msg.get("provider"):
                current_turn.provider = msg["provider"]
                current_provider = msg["provider"]
            if msg.get("api"):
                current_turn.api = msg["api"]
                current_api = msg["api"]

            current_turn.stop_reason = msg.get("stopReason", "")

            # Accumulate usage
            usage = msg.get("usage", {})
            if usage:
                for k in ("input", "output", "cacheRead", "cacheWrite", "totalTokens"):
                    current_turn.usage[k] = current_turn.usage.get(k, 0) + usage.get(k, 0)
                msg_cost = usage.get("cost", {})
                if msg_cost:
                    for k in ("input", "output", "cacheRead", "cacheWrite", "total"):
                        current_turn.cost[k] = current_turn.cost.get(k, 0) + msg_cost.get(k, 0)

            # Parse content items
            if isinstance(content, list):
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    ctype = c.get("type")

                    if ctype == "text":
                        current_turn.assistant_texts.append(c.get("text", ""))

                    elif ctype == "thinking":
                        thinking_text = c.get("thinking", "")
                        if thinking_text:
                            if current_turn.thinking_text:
                                current_turn.thinking_text += "\n" + thinking_text
                            else:
                                current_turn.thinking_text = thinking_text
                        sig = c.get("thinkingSignature")
                        if sig and isinstance(sig, str) and "encrypted" in sig.lower():
                            current_turn.thinking_encrypted = True
                        elif sig and isinstance(sig, dict):
                            current_turn.thinking_encrypted = True
                        elif sig and not thinking_text:
                            current_turn.thinking_encrypted = True

                    elif ctype == "toolCall":
                        tc = ToolCall(
                            id=c.get("id", ""),
                            name=c.get("name", ""),
                            arguments=c.get("arguments", {}),
                        )
                        pending_tool_calls[tc.id] = tc
                        current_turn.tool_calls.append(tc)

        elif role == "toolResult":
            if current_turn is None:
                continue
            turn_raw_lines.append(entry)
            tc_id = msg.get("toolCallId", "")
            tool_name = msg.get("toolName", "")
            details = msg.get("details", {})
            is_error = msg.get("isError", False)

            result_text = ""
            content = msg.get("content", [])
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        result_text += c.get("text", "")

            result_size = len(result_text)
            duration_ms = details.get("durationMs")
            status = details.get("status", "")

            # Check for error in details
            if details.get("error") or details.get("status") == "error":
                is_error = True

            # Match to pending tool call
            if tc_id in pending_tool_calls:
                tc = pending_tool_calls[tc_id]
                tc.result_text = _truncate(result_text, 500)
                tc.result_size = result_size
                tc.duration_ms = duration_ms
                tc.is_error = is_error
                tc.status = status
            else:
                # Orphan result - still record it
                tc = ToolCall(
                    id=tc_id,
                    name=tool_name,
                    arguments={},
                    result_text=_truncate(result_text, 500),
                    result_size=result_size,
                    duration_ms=duration_ms,
                    is_error=is_error,
                    status=status,
                )
                current_turn.tool_calls.append(tc)

            # Check if this is a sessions_spawn result
            if tool_name == "sessions_spawn":
                child_key = details.get("childSessionKey", "")
                run_id = details.get("runId", "")
                if child_key or run_id:
                    # Get spawn arguments from matching toolCall
                    spawn_args = {}
                    if tc_id in pending_tool_calls:
                        spawn_args = pending_tool_calls[tc_id].arguments

                    spawn = SubagentSpawn(
                        run_id=run_id,
                        label=spawn_args.get("label", ""),
                        task=_truncate(spawn_args.get("task", spawn_args.get("prompt", "")), 300),
                        child_session_key=child_key,
                        child_session_id=_extract_session_id_from_key(child_key),
                    )

                    # Enrich from subagent registry
                    reg = get_subagent_run(run_id)
                    if reg:
                        started = reg.get("startedAt", 0)
                        ended = reg.get("endedAt", 0)
                        if started and ended:
                            spawn.duration_ms = ended - started
                        outcome = reg.get("outcome", {})
                        spawn.outcome = outcome.get("status", "unknown") if isinstance(outcome, dict) else str(outcome)
                        if not spawn.label:
                            spawn.label = reg.get("label", "")

                    # Recursively parse child session
                    if recursive_subagents and child_key:
                        child_file = find_subagent_child_session(child_key)
                        if child_file:
                            child_analysis = parse_session(child_file, recursive_subagents=True)
                            spawn.child_turns = child_analysis.turns
                            spawn.cost_usd = child_analysis.total_cost
                            spawn.total_tokens = child_analysis.total_tokens

                    current_turn.subagent_spawns.append(spawn)

    # Finalize last turn
    if current_turn is not None:
        current_turn.raw_lines = turn_raw_lines
        _finalize_turn(current_turn, pending_tool_calls)
        turns.append(current_turn)

    analysis.turns = turns

    # Calculate totals
    for turn in turns:
        analysis.total_cost += turn.cost.get("total", 0)
        analysis.total_tokens += turn.usage.get("totalTokens", 0)

    if turns:
        first_ts = turns[0].timestamp
        last_turn = turns[-1]
        last_ts = last_turn.timestamp
        if first_ts and last_ts:
            # Use the last raw line timestamp for more accuracy
            for raw in reversed(last_turn.raw_lines):
                raw_ts = _ts_to_dt(raw.get("message", {}).get("timestamp") or raw.get("timestamp"))
                if raw_ts:
                    last_ts = raw_ts
                    break
            analysis.total_duration_ms = int((last_ts - first_ts).total_seconds() * 1000)

    # Detect session type from first user message
    if turns:
        first_source = turns[0].user_source
        if first_source == "cron":
            analysis.session_type = "cron"
        elif first_source == "heartbeat":
            analysis.session_type = "heartbeat"
        elif "subagent" in str(file_path):
            analysis.session_type = "subagent"
        else:
            analysis.session_type = "chat"

    return analysis


def _finalize_turn(turn: Turn, pending_tool_calls: dict):
    """Calculate turn duration from raw lines."""
    if not turn.raw_lines:
        return
    timestamps = []
    for raw in turn.raw_lines:
        ts = raw.get("message", {}).get("timestamp") or raw.get("timestamp")
        dt = _ts_to_dt(ts)
        if dt:
            timestamps.append(dt)
    if turn.timestamp:
        timestamps.append(turn.timestamp)
    if len(timestamps) >= 2:
        turn.duration_ms = int((max(timestamps) - min(timestamps)).total_seconds() * 1000)


# --- Session discovery ---

def list_sessions(agent_id: Optional[str] = None, last_n: int = 20,
                  session_type: Optional[str] = None) -> list:
    """List sessions across agents. Returns list of dicts with basic info."""
    results = []

    agents = []
    if agent_id and agent_id != "all":
        agent_dir = AGENTS_DIR / agent_id
        if agent_dir.exists():
            agents = [agent_dir]
    else:
        if AGENTS_DIR.exists():
            agents = [d for d in AGENTS_DIR.iterdir() if d.is_dir()]

    for agent_dir in agents:
        aid = agent_dir.name
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            continue
        for f in sessions_dir.glob("*.jsonl"):
            stat = f.stat()
            # Quick scan: read first few lines for metadata
            meta = _quick_scan_session(f, aid)
            if session_type and meta.get("type") != session_type:
                continue
            meta["file_path"] = str(f)
            meta["file_size"] = stat.st_size
            meta["modified"] = datetime.fromtimestamp(stat.st_mtime, tz=KST)
            results.append(meta)

    results.sort(key=lambda r: r.get("modified", datetime.min.replace(tzinfo=KST)), reverse=True)
    return results[:last_n]


def _quick_scan_session(file_path: Path, agent_id: str) -> dict:
    """Quick scan first/last lines for basic metadata without full parse."""
    meta = {
        "session_id": file_path.stem.split("-topic-")[0],
        "agent_id": agent_id,
        "type": "chat",
        "model": "",
        "turns": 0,
        "cost": 0.0,
        "tokens": 0,
    }

    try:
        with open(file_path) as f:
            first_lines = []
            user_count = 0
            total_cost = 0.0
            total_tokens = 0
            model = ""
            session_type = "chat"

            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entry = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                etype = entry.get("type")

                if etype == "session":
                    meta["started_at"] = _ts_to_dt(entry.get("timestamp"))

                elif etype == "model_change":
                    model = entry.get("modelId", "")

                elif etype == "message":
                    msg = entry.get("message", {})
                    role = msg.get("role", "")
                    if role == "user":
                        user_count += 1
                        if user_count == 1:
                            content = msg.get("content", [])
                            user_text = ""
                            if isinstance(content, list):
                                for c in content:
                                    if isinstance(c, dict) and c.get("type") == "text":
                                        user_text += c.get("text", "")
                            src = _detect_source(user_text)
                            if src == "cron":
                                session_type = "cron"
                            elif src == "heartbeat":
                                session_type = "heartbeat"
                    elif role == "assistant":
                        if msg.get("model"):
                            model = msg["model"]
                        usage = msg.get("usage", {})
                        total_tokens += usage.get("totalTokens", 0)
                        cost = usage.get("cost", {})
                        total_cost += cost.get("total", 0)

            if "subagent" in str(file_path):
                session_type = "subagent"

            meta["type"] = session_type
            meta["model"] = model
            meta["turns"] = user_count
            meta["cost"] = total_cost
            meta["tokens"] = total_tokens

    except (IOError, OSError):
        pass

    return meta


def get_raw_turn_lines(file_path: str | Path, turn_index: int) -> list:
    """Get the raw JSONL entries for a specific turn (for log viewing)."""
    analysis = parse_session(file_path, recursive_subagents=False)
    if turn_index < 0 or turn_index >= len(analysis.turns):
        return []
    return analysis.turns[turn_index].raw_lines
