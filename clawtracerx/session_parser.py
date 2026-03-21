"""
ClawTracerX parser — OpenClaw session JSONL parser.

Parses session transcripts into structured Turn objects
with tool calls, subagent spawns, token usage, and cost tracking.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

KST = timezone(timedelta(hours=9))
OPENCLAW_DIR = Path.home() / ".openclaw"
AGENTS_DIR = OPENCLAW_DIR / "agents"
SUBAGENTS_FILE = OPENCLAW_DIR / "subagents" / "runs.json"
CRON_JOBS_FILE = OPENCLAW_DIR / "cron" / "jobs.json"
CRON_RUNS_DIR = OPENCLAW_DIR / "cron" / "runs"


@dataclass
class InjectedFile:
    name: str                    # "AGENTS.md", "SOUL.md", etc.
    path: str                    # absolute path
    missing: bool = False
    raw_chars: int = 0
    injected_chars: int = 0
    truncated: bool = False


@dataclass
class SkillEntry:
    name: str
    block_chars: int = 0


@dataclass
class ToolEntry:
    name: str
    summary_chars: int = 0
    schema_chars: int = 0


@dataclass
class SessionContext:
    """Session initialization context metadata (from sessions.json)."""
    injected_files: list = field(default_factory=list)   # List[InjectedFile]
    system_prompt_chars: int = 0
    project_context_chars: int = 0
    non_project_context_chars: int = 0
    skills: list = field(default_factory=list)            # List[SkillEntry]
    tools: list = field(default_factory=list)             # List[ToolEntry]
    bootstrap_max_chars: int = 0
    workspace_dir: str = ""
    sandbox_mode: str = ""


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
    round_idx: int = 0   # which assistant message round within the turn


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
    announce_stats: Optional[dict] = None  # parsed from announce message


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
    thinking_blocks: list = field(default_factory=list)  # per-round thinking, list[Optional[str]]
    model: str = ""
    provider: str = ""
    api: str = ""
    usage: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)
    stop_reason: str = ""
    duration_ms: int = 0
    timestamp: Optional[datetime] = None
    raw_lines: list = field(default_factory=list)
    in_context: bool = True  # whether this turn is still in context window
    thinking_level: str = ""      # thinking level at the time of this turn
    cache_hit_rate: float = 0.0   # cacheRead / (input + cacheRead)
    workflow_group_id: Optional[int] = None  # set if this turn is part of a multi-turn workflow chain
    channel_meta: Optional[dict] = None
    # {platform, sender, sender_id, channel, ts_str, message_id, actual_text, reply_context}
    delivery_texts: list = field(default_factory=list)  # merged from delivery-mirror events


@dataclass
class CompactionEvent:
    first_kept_entry_id: str = ""
    tokens_before: int = 0
    tokens_after: int = 0          # tokens after compaction
    summary: str = ""              # compaction summary text
    from_hook: bool = False        # whether triggered by hook
    timestamp: Optional[datetime] = None


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
    compaction_events: list = field(default_factory=list)  # list of CompactionEvent
    file_path: str = ""
    channel: str = ""                          # telegram, discord, whatsapp, slack, etc.
    context: Optional[SessionContext] = None   # from sessions.json
    thinking_level: str = ""                   # current thinking level
    context_tokens: int = 0                    # from sessions.json
    # session-level token counters from sessions.json
    session_input_tokens: int = 0
    session_output_tokens: int = 0
    session_total_tokens: int = 0
    session_compaction_count: int = 0
    memory_flush_at: Optional[datetime] = None


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


_BRACKET_CHANNEL_MAP = {
    "telegram": "telegram",
    "whatsapp": "whatsapp",
    "discord": "discord",
    "slack": "slack",
    "signal": "signal",
    "imessage": "imessage",
    "irc": "irc",
    "googlechat": "googlechat",
}


def _detect_source(user_text: str) -> str:
    """Detect user message source from text prefix.

    Returns one of:
      chat, cron, heartbeat, system, subagent_announce, cron_announce,
      discord, telegram, whatsapp, slack, signal, imessage, irc, googlechat

    OpenClaw message formats:
      - "[cron:...]" → cron trigger
      - "[System Message] A subagent..." → subagent announce
      - "[System Message] A cron job..." → cron announce
      - "[System Message]..." → generic system
      - "[Day YYYY-MM-DD ...] A subagent task..." → subagent announce (timestamped)
      - "[Day YYYY-MM-DD ...] A cron job..." → cron announce (timestamped)
      - "[Day YYYY-MM-DD ...] [Queued announce...] ... A subagent task" → queued announce
      - "[heartbeat..." → heartbeat trigger
      - "Read HEARTBEAT.md" / contains "heartbeat" → heartbeat
      - "[message_id: ...]" → channel message (discord/telegram/whatsapp/etc.)
    """
    if not user_text:
        return "chat"
    if user_text.startswith("[cron:"):
        return "cron"
    if user_text.startswith("[System Message]"):
        lower = user_text.lower()
        if "a subagent task" in lower or "subagent" in lower:
            return "subagent_announce"
        if "a cron job" in lower or "cron" in lower:
            return "cron_announce"
        return "system"
    if user_text.startswith("[heartbeat"):
        return "heartbeat"
    # Timestamped announce: [Day YYYY-MM-DD HH:MM TZ] A subagent/cron...
    if re.match(r"\[(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{4}-\d{2}-\d{2}", user_text):
        lower = user_text.lower()
        if "a subagent task" in lower:
            return "subagent_announce"
        if "a cron job" in lower:
            return "cron_announce"
        return "system"
    # Discord JSON format (no [message_id:] bracket marker)
    if "Conversation info (untrusted metadata):" in user_text:
        return "discord"
    # Channel messages with message_id marker — detect platform from bracket header
    if "[message_id:" in user_text:
        m = re.match(r'(?:System:\s*)?\[(\w+)', user_text.strip())
        if m:
            ch = m.group(1).lower()
            if ch in _BRACKET_CHANNEL_MAP:
                return ch
        return "telegram"  # legacy fallback for bracket format
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

import threading as _threading

_subagent_cache = None
_subagent_lock = _threading.Lock()

def load_subagent_runs() -> dict:
    global _subagent_cache
    with _subagent_lock:
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
    """Find the JSONL file for a child session key.

    OpenClaw soft-deletes subagent session files by renaming them to
    {uuid}.jsonl.deleted.{timestamp}, so we search for both .jsonl
    and .jsonl.deleted.* patterns.
    """
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
            if not f.name.startswith(session_id):
                continue
            # Match {uuid}.jsonl or {uuid}.jsonl.deleted.{ts}
            if f.suffix == ".jsonl" or ".jsonl.deleted." in f.name:
                return f
    return None


# --- Subagent announce parsing ---

# Matches Stats section (runtime + tokens). Optional trailing fields vary by version.
_ANNOUNCE_RE = re.compile(
    r"Stats:\s*runtime\s+([\d\w .]+?)\s*"
    r"[•·]\s*tokens\s+([\d.]+[KMkm]?)\s*\(in\s+([\d.]+[KMkm]?).*?out\s+([\d.]+[KMkm]?)\)",
    re.DOTALL,
)

# Old format: sessionId inline in Stats line  (• sessionId UUID)
_ANNOUNCE_INLINE_SID_RE = re.compile(r'[•·]\s*sessionId\s+([0-9a-f-]{36})')

# Old format: transcript path inline in Stats
_ANNOUNCE_INLINE_TRANSCRIPT_RE = re.compile(r'[•·]\s*transcript\s+(\S+\.jsonl\S*)')

# New format: sessionId in message prefix [sessionId: UUID]
_ANNOUNCE_SESSION_ID_RE = re.compile(r'\[sessionId:\s*([0-9a-f-]{36})\]')

# Extracts task label: A subagent task "LABEL" just completed
_ANNOUNCE_LABEL_RE = re.compile(r'A subagent task "([^"]+)"')


def _parse_token_str(s: str) -> int:
    s = s.strip().lower()
    if s.endswith("m"):
        return int(float(s[:-1]) * 1_000_000)
    if s.endswith("k"):
        return int(float(s[:-1]) * 1_000)
    return int(float(s))


def _parse_runtime_str(s: str) -> int:
    """Parse runtime like '1m25s' or '45s' to milliseconds."""
    s = s.strip()
    total_ms = 0
    m_match = re.search(r"(\d+)m", s)
    s_match = re.search(r"([\d.]+)s", s)
    if m_match:
        total_ms += int(m_match.group(1)) * 60_000
    if s_match:
        total_ms += int(float(s_match.group(1)) * 1000)
    return total_ms or 0


def _parse_announce_match(m, full_text: str = "") -> Optional[dict]:
    """Parse a regex match from _ANNOUNCE_RE into a stats dict.

    Supports two announce formats:
    - New: [sessionId: UUID] prefix + Stats: runtime • tokens (no inline sessionId)
    - Old: Stats: runtime • tokens • sessionKey ... • sessionId UUID • transcript PATH
    """
    try:
        result = {
            "runtime_ms": _parse_runtime_str(m.group(1)),
            "total_tokens": _parse_token_str(m.group(2)),
            "input_tokens": _parse_token_str(m.group(3)),
            "output_tokens": _parse_token_str(m.group(4)),
        }
        if full_text:
            # Label from "A subagent task "LABEL""
            label_m = _ANNOUNCE_LABEL_RE.search(full_text)
            if label_m:
                result["label"] = label_m.group(1)

            # Session ID: new format = [sessionId: UUID] prefix
            sid_m = _ANNOUNCE_SESSION_ID_RE.search(full_text)
            if sid_m:
                result["session_id"] = sid_m.group(1)
            else:
                # Old format: • sessionId UUID inline in Stats
                inline_sid_m = _ANNOUNCE_INLINE_SID_RE.search(full_text)
                if inline_sid_m:
                    result["session_id"] = inline_sid_m.group(1)

            # Transcript path (old format only)
            transcript_m = _ANNOUNCE_INLINE_TRANSCRIPT_RE.search(full_text)
            if transcript_m:
                result["transcript"] = transcript_m.group(1)

        return result
    except (ValueError, IndexError):
        return None


def _resolve_child_from_transcript(spawn, transcript: str):
    """Try to resolve child session turns from transcript path."""
    if not transcript:
        return
    tp = Path(transcript)
    # Check if the exact path exists
    if tp.exists():
        child_analysis = parse_session(tp, recursive_subagents=True)
        spawn.child_turns = child_analysis.turns
        if not spawn.cost_usd and child_analysis.total_cost:
            spawn.cost_usd = child_analysis.total_cost
        return
    # Try .deleted.* variant
    parent = tp.parent
    stem = tp.name  # e.g. "uuid.jsonl"
    if parent.exists():
        for f in parent.iterdir():
            if f.name.startswith(stem) and ".deleted." in f.name:
                child_analysis = parse_session(f, recursive_subagents=True)
                spawn.child_turns = child_analysis.turns
                if not spawn.cost_usd and child_analysis.total_cost:
                    spawn.cost_usd = child_analysis.total_cost
                return


# --- Channel message parsing ---

_DISCORD_CONV_RE = re.compile(
    r'Conversation info \(untrusted metadata\):\n```json\n([\s\S]*?)\n```')
_DISCORD_SENDER_RE = re.compile(
    r'Sender \(untrusted metadata\):\n```json\n([\s\S]*?)\n```')
_TG_PREFIX_RE = re.compile(
    r'\[Telegram\s+[^\]]+?\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+\S+)\]\s+'
    r'(.+?)\s+\(\d+\):\s*([\s\S]*)')
# General bracket prefix for all channel platforms (Telegram, WhatsApp, Slack, etc.)
_BRACKET_PREFIX_RE = re.compile(
    r'\[\w+[^\]]*?(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+\S+)\]\s+'
    r'(.+?)\s+\(\d+\):\s*([\s\S]*)',
    re.DOTALL)
_REPLY_BLOCK_RE = re.compile(
    r'\s*\[Replying to remote-agent id:\d+\]([\s\S]*?)\[/Replying\]\s*')


def _parse_channel_message(user_text: str, source: str) -> Optional[dict]:
    """Extract platform metadata and actual message text from channel messages."""
    if source == "discord":
        conv_m = _DISCORD_CONV_RE.search(user_text)
        if not conv_m:
            return None
        try:
            conv = json.loads(conv_m.group(1))
        except json.JSONDecodeError:
            conv = {}
        sender_info = {}
        sender_m = _DISCORD_SENDER_RE.search(user_text)
        if sender_m:
            try:
                sender_info = json.loads(sender_m.group(1))
            except json.JSONDecodeError:
                pass
        # 마지막 ```\n 블록 이후가 실제 메시지
        last_end = user_text.rfind('\n```\n')
        actual_text = user_text[last_end + 5:].strip() if last_end >= 0 else user_text
        # Detect real platform from JSON fields
        if conv.get("group_channel"):
            platform = "discord"
        elif conv.get("group_space"):
            label = conv.get("conversation_label", "").lower()
            platform = "googlechat" if ("google" in label or "space" in label) else "slack"
        elif conv.get("group_subject") or conv.get("is_forum"):
            platform = "telegram"
        else:
            label = conv.get("conversation_label", "")
            if re.search(r'id:-\d+', label):
                platform = "telegram"
            else:
                sender = conv.get("sender", "")
                if re.match(r'^\+\d{8,15}$', sender):
                    platform = "whatsapp"
                else:
                    platform = "discord"  # fallback

        return {
            "platform": platform,
            "sender": sender_info.get("label") or sender_info.get("name") or "",
            "sender_id": conv.get("sender", ""),
            "channel": (conv.get("group_channel") or conv.get("group_subject") or
                        conv.get("conversation_label", "")),
            "ts_str": "",
            "message_id": str(conv.get("message_id", "")),
            "actual_text": actual_text,
            "reply_context": "",
        }

    # Bracket format: telegram and any other _BRACKET_CHANNEL_MAP channel
    if source in _BRACKET_CHANNEL_MAP:
        msg_id_m = re.search(r'\[message_id:\s*([^\]]+)\]', user_text)
        message_id = msg_id_m.group(1).strip() if msg_id_m else ""
        clean = re.sub(r'\n?\[message_id:[^\]]+\]', '', user_text).strip()
        # System: prefix removal
        clean = re.sub(r'^System:\s*\[[^\]]+\][^\n]*\n+', '', clean).strip()

        # Determine actual platform from bracket header
        first_m = re.match(r'\[(\w+)', clean)
        if first_m:
            ch = first_m.group(1).lower()
            actual_platform = _BRACKET_CHANNEL_MAP.get(ch, source)
        else:
            actual_platform = source

        m = _BRACKET_PREFIX_RE.match(clean)
        if not m:
            return None
        ts_str, sender, actual_text = m.group(1), m.group(2), m.group(3).strip()
        reply_context = ""
        reply_m = _REPLY_BLOCK_RE.search(actual_text)
        if reply_m:
            reply_context = reply_m.group(1).strip()
            actual_text = _REPLY_BLOCK_RE.sub(' ', actual_text).strip()
        return {
            "platform": actual_platform,
            "sender": sender,
            "sender_id": "",
            "channel": "",
            "ts_str": ts_str,
            "message_id": message_id,
            "actual_text": actual_text,
            "reply_context": reply_context,
        }
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
                    duration_ms=d.get("durationMs", 0),
                ))
    results.sort(key=lambda r: r.ts, reverse=True)
    return results[:last_n]


def load_heartbeat_configs() -> list:
    """Load heartbeat configs from openclaw.json agents list."""
    config_path = OPENCLAW_DIR / "openclaw.json"
    if not config_path.exists():
        return []
    with open(config_path) as f:
        data = json.load(f)
    results = []
    for agent in data.get("agents", {}).get("list", []):
        hb = agent.get("heartbeat")
        if hb:
            results.append({
                "agent_id": agent.get("id", ""),
                "every": hb.get("every", ""),
                "target": hb.get("target", ""),
                "active_hours": hb.get("activeHours"),
                "model": hb.get("model", ""),
            })
    return results


# --- Session metadata ---

SESSIONS_JSON = "sessions.json"  # located in agents/{id}/sessions/


def load_session_metadata(agent_id: str, session_id: str) -> Optional[dict]:
    """Load metadata for a specific session from sessions.json."""
    sessions_file = AGENTS_DIR / agent_id / "sessions" / SESSIONS_JSON
    if not sessions_file.exists():
        return None
    with open(sessions_file) as f:
        data = json.load(f)
    # Find the entry whose sessionId starts with session_id
    for key, entry in data.items():
        if entry.get("sessionId", "").startswith(session_id):
            return entry
    return None


def _parse_session_context(report: dict) -> SessionContext:
    """Convert a systemPromptReport dict to a SessionContext dataclass."""
    ctx = SessionContext()
    ctx.workspace_dir = report.get("workspaceDir", "")
    ctx.bootstrap_max_chars = report.get("bootstrapMaxChars", 0)

    sp = report.get("systemPrompt", {})
    ctx.system_prompt_chars = sp.get("chars", 0)
    ctx.project_context_chars = sp.get("projectContextChars", 0)
    ctx.non_project_context_chars = sp.get("nonProjectContextChars", 0)

    sandbox = report.get("sandbox", {})
    ctx.sandbox_mode = sandbox.get("mode", "")

    for f in report.get("injectedWorkspaceFiles", []):
        ctx.injected_files.append(InjectedFile(
            name=f.get("name", ""),
            path=f.get("path", ""),
            missing=f.get("missing", False),
            raw_chars=f.get("rawChars", 0),
            injected_chars=f.get("injectedChars", 0),
            truncated=f.get("truncated", False),
        ))

    for s in report.get("skills", {}).get("entries", []):
        ctx.skills.append(SkillEntry(name=s.get("name", ""), block_chars=s.get("blockChars", 0)))

    for t in report.get("tools", {}).get("entries", []):
        ctx.tools.append(ToolEntry(
            name=t.get("name", ""),
            summary_chars=t.get("summaryChars", 0),
            schema_chars=t.get("schemaChars", 0),
        ))

    return ctx


# --- Session parsing ---

_parse_cache: dict = {}  # {path_str: (mtime, SessionAnalysis)}
_PARSE_CACHE_MAX = 50


def parse_session(file_path: str | Path, recursive_subagents: bool = True) -> SessionAnalysis:
    """Parse a session JSONL file into a SessionAnalysis."""
    file_path = Path(file_path)

    # mtime-based cache check
    path_key = str(file_path)
    try:
        current_mtime = file_path.stat().st_mtime
    except OSError:
        current_mtime = None

    if current_mtime is not None and path_key in _parse_cache:
        cached_mtime, cached_result = _parse_cache[path_key]
        if cached_mtime == current_mtime:
            return cached_result
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

    # Extract session_id from filename (handles both .jsonl and .jsonl.deleted.*)
    fname = file_path.name.split(".jsonl")[0]  # strip .jsonl and anything after
    session_id = fname.split("-topic-")[0]

    analysis = SessionAnalysis(
        session_id=session_id,
        agent_id=agent_id,
        file_path=str(file_path),
    )

    # First pass: extract metadata
    current_model = ""
    current_provider = ""
    current_api = ""
    current_thinking_level = ""

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
            analysis.compaction_events.append(CompactionEvent(
                first_kept_entry_id=entry.get("firstKeptEntryId", ""),
                tokens_before=entry.get("tokensBefore", 0),
                tokens_after=entry.get("tokensAfter", 0),
                summary=entry.get("summary", ""),
                from_hook=entry.get("fromHook", False),
                timestamp=_ts_to_dt(entry.get("timestamp")),
            ))
        elif etype == "thinking_level_change":
            current_thinking_level = entry.get("thinkingLevel", "")

    analysis.model = current_model
    analysis.provider = current_provider
    analysis.thinking_level = current_thinking_level

    # Build id → message info map for parent-chain lookups
    id_to_msg_info = {}  # id -> {"role": str, "stop_reason": str, "model": str}
    for entry in lines:
        eid = entry.get("id")
        if eid and entry.get("type") == "message":
            msg = entry["message"]
            id_to_msg_info[eid] = {
                "role": msg.get("role", ""),
                "stop_reason": msg.get("stopReason", ""),
                "model": msg.get("model", ""),
            }

    # Second pass: build turns
    # A turn starts with a user message (or a proactive/delivery assistant message)
    # and includes all assistant messages + tool results until the next boundary.
    turns = []
    current_turn = None
    pending_tool_calls = {}  # id -> ToolCall
    turn_raw_lines = []
    current_thinking_level = ""
    _turn_round_idx = 0  # assistant message round counter within current turn

    for entry in lines:
        etype = entry.get("type")

        if etype == "model_change":
            current_model = entry.get("modelId", "")
            current_provider = entry.get("provider", "")
            current_api = ""

        if etype == "thinking_level_change":
            current_thinking_level = entry.get("thinkingLevel", "")

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
                thinking_level=current_thinking_level,
            )
            # 채널 메시지 파싱 (discord / telegram / whatsapp / slack / etc.)
            if source in _BRACKET_CHANNEL_MAP or source == "discord":
                current_turn.channel_meta = _parse_channel_message(user_text, source)
                # Correct user_source to match actual detected platform
                if current_turn.channel_meta:
                    current_turn.user_source = current_turn.channel_meta.get("platform", source)
                    # Set session-level channel from first channel message
                    if not analysis.channel:
                        analysis.channel = current_turn.channel_meta.get("platform", source)
            pending_tool_calls = {}
            turn_raw_lines = [entry]
            _turn_round_idx = 0

        elif role == "assistant":
            model_name = msg.get("model", "")
            parent_id = entry.get("parentId")
            parent_info = id_to_msg_info.get(parent_id, {})
            parent_role = parent_info.get("role", "")
            parent_stop = parent_info.get("stop_reason", "")
            current_stop = msg.get("stopReason", "")

            is_delivery_mirror = (model_name == "delivery-mirror")
            # Proactive: parent is an assistant that completed normally (not an error retry)
            is_proactive = (
                parent_role == "assistant"
                and not is_delivery_mirror
                and current_stop != "error"
                and parent_stop != "error"
            )

            if is_delivery_mirror:
                # Merge delivery-mirror into current turn as metadata (not a new turn)
                if current_turn is not None:
                    dm_text = ""
                    for block in msg.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            dm_text += block.get("text", "")
                    if dm_text.strip():
                        current_turn.delivery_texts.append(dm_text.strip())
                    turn_raw_lines.append(entry)
                continue
            elif is_proactive:
                # Close current turn and start a new one
                if current_turn is not None:
                    current_turn.raw_lines = turn_raw_lines
                    _finalize_turn(current_turn, pending_tool_calls)
                    turns.append(current_turn)
                current_turn = Turn(
                    index=len(turns),
                    user_text="",
                    user_source="proactive",
                    timestamp=ts,
                    model=current_model,
                    provider=current_provider,
                    api=current_api,
                    thinking_level=current_thinking_level,
                )
                pending_tool_calls = {}
                turn_raw_lines = []
                _turn_round_idx = 0
            elif current_turn is None:
                # Assistant message without prior user - create implicit turn
                current_turn = Turn(
                    index=len(turns),
                    user_text="[implicit]",
                    user_source="system",
                    timestamp=ts,
                    model=current_model,
                    provider=current_provider,
                    api=current_api,
                    thinking_level=current_thinking_level,
                )
                pending_tool_calls = {}
                turn_raw_lines = []
                _turn_round_idx = 0

            turn_raw_lines.append(entry)
            content = msg.get("content", [])
            _round_thinking_parts: list = []  # thinking in this assistant round

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
                        text = c.get("text", "").strip()
                        if text:  # skip empty/whitespace-only text blocks
                            current_turn.assistant_texts.append(c.get("text", ""))

                    elif ctype == "thinking":
                        thinking_text = c.get("thinking", "")
                        if thinking_text:
                            _round_thinking_parts.append(thinking_text)
                            # maintain backward-compat thinking_text (merged)
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
                            round_idx=_turn_round_idx,
                        )
                        pending_tool_calls[tc.id] = tc
                        current_turn.tool_calls.append(tc)

            # Record per-round thinking in thinking_blocks
            round_thinking = "\n".join(_round_thinking_parts) or None
            while len(current_turn.thinking_blocks) <= _turn_round_idx:
                current_turn.thinking_blocks.append(None)
            current_turn.thinking_blocks[_turn_round_idx] = round_thinking
            _turn_round_idx += 1

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

    # Enrich subagent spawns from announce messages (uses real sessionId from announce prefix)
    _enrich_spawns_from_announces(turns, agent_id=agent_id)

    # Last-resort: load child sessions for spawns still missing child_turns
    # (handles delivery_mirror case where routing UUID ≠ file UUID, no announce turn)
    if recursive_subagents:
        _try_load_missing_children(turns, agent_id=agent_id)

    # Group consecutive turns that form a continuous workflow chain
    _assign_workflow_groups(turns)

    # Compute in_context based on compaction events
    if analysis.compaction_events:
        _compute_context_status(turns, lines, analysis.compaction_events)

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

    # Detect session type from first user message (skip proactive turns)
    if turns:
        first_real_turn = next(
            (t for t in turns if t.user_source != "proactive"),
            turns[0] if turns else None,
        )
        first_source = first_real_turn.user_source if first_real_turn else "chat"
        if first_source == "cron":
            analysis.session_type = "cron"
        elif first_source == "heartbeat":
            analysis.session_type = "heartbeat"
        elif "subagent" in str(file_path):
            analysis.session_type = "subagent"
        else:
            analysis.session_type = "chat"

    # Enrich from sessions.json metadata
    meta = load_session_metadata(agent_id, session_id)
    if meta:
        report = meta.get("systemPromptReport")
        if report:
            analysis.context = _parse_session_context(report)
        analysis.context_tokens = meta.get("contextTokens", 0)
        analysis.session_input_tokens = meta.get("inputTokens", 0)
        analysis.session_output_tokens = meta.get("outputTokens", 0)
        analysis.session_total_tokens = meta.get("totalTokens", 0)
        analysis.session_compaction_count = meta.get("compactionCount", 0)
        analysis.memory_flush_at = _ts_to_dt(meta.get("memoryFlushAt"))

    # Store in cache (LRU eviction)
    if current_mtime is not None:
        _parse_cache[path_key] = (current_mtime, analysis)
        if len(_parse_cache) > _PARSE_CACHE_MAX:
            # Evict oldest entry
            oldest_key = next(iter(_parse_cache))
            del _parse_cache[oldest_key]

    return analysis


def _compute_context_status(turns: list, lines: list, compaction_events: list):
    """Mark turns as out-of-context based on the last compaction event.

    Each entry has an 'id' field. The compaction's firstKeptEntryId tells us
    the first entry still in context. All entries (and thus turns) whose
    entry IDs come before firstKeptEntryId in the file order are out of context.
    """
    if not compaction_events:
        return

    # Use the last compaction event (most recent context boundary)
    last_compaction = compaction_events[-1]
    first_kept_id = last_compaction.first_kept_entry_id
    if not first_kept_id:
        return

    # Build ordered list of entry IDs from the raw lines
    entry_id_order = []
    for entry in lines:
        eid = entry.get("id", "")
        if eid:
            entry_id_order.append(eid)

    # Find the position of firstKeptEntryId
    try:
        kept_pos = entry_id_order.index(first_kept_id)
    except ValueError:
        return  # can't find it, don't modify anything

    # Set of entry IDs that are before the kept boundary
    evicted_ids = set(entry_id_order[:kept_pos])

    # For each turn, check if ALL its raw_lines entry IDs are evicted
    for turn in turns:
        if not turn.raw_lines:
            continue
        turn_ids = {e.get("id", "") for e in turn.raw_lines if e.get("id")}
        if turn_ids and turn_ids.issubset(evicted_ids):
            turn.in_context = False


def _finalize_turn(turn: Turn, pending_tool_calls: dict):
    """Calculate turn duration and cache hit rate from raw lines."""
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

    # Calculate cache hit rate
    cache_read = turn.usage.get("cacheRead", 0)
    input_tokens = turn.usage.get("input", 0)
    if cache_read + input_tokens > 0:
        turn.cache_hit_rate = cache_read / (cache_read + input_tokens)


def _find_child_session_by_id(session_id: str, agent_id: str) -> Optional[Path]:
    """Find a child session JSONL file by its real session UUID."""
    if not session_id:
        return None
    # Search in the same agent first, then all agents
    search_dirs = []
    agent_dir = AGENTS_DIR / agent_id
    if agent_dir.exists():
        search_dirs.append(agent_dir / "sessions")
    for d in AGENTS_DIR.iterdir():
        if d.is_dir() and d.name != agent_id:
            search_dirs.append(d / "sessions")

    for sessions_dir in search_dirs:
        if not sessions_dir.exists():
            continue
        for f in sessions_dir.iterdir():
            if f.name.startswith(session_id):
                if f.suffix == ".jsonl" or ".jsonl.deleted." in f.name:
                    return f
    return None


def _find_child_session_by_label(label: str, spawn_label: str, agent_id: str,
                                  announce_ts: datetime,
                                  window_after_secs: int = 60) -> Optional[Path]:
    """Fallback: find child session by scanning files near announce timestamp.

    Used for old announce format that lacks [sessionId:] and Stats: sections.
    Searches JSONL files modified within 30 minutes before the announce, and
    checks if the first user message contains the spawn label.

    window_after_secs: how many seconds after announce_ts to include in the window.
    Use a larger value (e.g. 7200) when searching for sessions that completed
    after the spawn time (delivery_mirror case, no announce).
    """
    target_ts = announce_ts.timestamp()
    window_start = target_ts - 1800  # 30 min before announce

    # Derive keywords from label (e.g. "ys-dev-trailing-slash-redirects-167-worker")
    keywords = [w for w in label.replace("-", " ").split() if len(w) > 3]

    search_dirs = []
    agent_dir = AGENTS_DIR / agent_id
    if agent_dir.exists():
        search_dirs.append(agent_dir / "sessions")
    for d in AGENTS_DIR.iterdir():
        if d.is_dir() and d.name != agent_id:
            search_dirs.append(d / "sessions")

    candidates = []
    for sessions_dir in search_dirs:
        if not sessions_dir.exists():
            continue
        for f in sessions_dir.iterdir():
            if not (f.suffix == ".jsonl" or ".jsonl.deleted." in f.name):
                continue
            try:
                mtime = f.stat().st_mtime
                if not (window_start <= mtime <= target_ts + window_after_secs):
                    continue
                candidates.append((mtime, f))
            except OSError:
                continue

    # Check first user message of each candidate for label keywords
    for _, f in sorted(candidates):
        try:
            for line in f.read_text(errors="replace").splitlines()[:10]:
                obj = json.loads(line)
                if obj.get("type") == "message":
                    msg = obj.get("message", {})
                    if msg.get("role") == "user":
                        text = (msg.get("content") or [{}])[0].get("text", "")
                        # Match if majority of keywords found in first user msg
                        hits = sum(1 for kw in keywords if kw in text)
                        if hits >= max(2, len(keywords) * 0.5):
                            return f
                        break
        except Exception:
            continue
    return None


def _try_load_missing_children(turns: list, agent_id: str) -> None:
    """Last-resort: load child sessions for spawns that have no child_turns yet.

    This handles the delivery_mirror case where the subagent result bypasses the
    announce mechanism (no subagent_announce turn). The routing UUID in childSessionKey
    does not match the real file UUID, so find_subagent_child_session() fails.
    We fall back to label/task keyword matching near the parent turn's timestamp.
    """
    for turn in turns:
        if not turn.timestamp:
            continue
        for spawn in turn.subagent_spawns:
            if spawn.child_turns:
                continue  # already loaded
            turn_end_ts = turn.timestamp + timedelta(milliseconds=turn.duration_ms or 0)
            kw_window = 14400  # 4 hours — subagent may run long

            # Try 1: search by label
            child_file = None
            if spawn.label:
                child_file = _find_child_session_by_label(
                    spawn.label, spawn.label, agent_id, turn_end_ts,
                    window_after_secs=kw_window,
                )
            # Try 2: search by task text (useful when label is English but task is Korean)
            if not child_file and spawn.task:
                task_text = " ".join(spawn.task.split()[:15])
                child_file = _find_child_session_by_label(
                    task_text, spawn.label, agent_id, turn_end_ts,
                    window_after_secs=kw_window,
                )
            if not child_file:
                continue
            if not child_file:
                continue
            try:
                child_analysis = parse_session(child_file, recursive_subagents=False)
                spawn.child_turns = child_analysis.turns
                if not spawn.cost_usd:
                    spawn.cost_usd = child_analysis.total_cost
                if not spawn.total_tokens:
                    spawn.total_tokens = child_analysis.total_tokens
                # Update child_session_id to the real UUID (stem of the found file)
                real_sid = child_file.name.split(".jsonl")[0]
                if real_sid and real_sid != spawn.child_session_id:
                    spawn.child_session_id = real_sid
            except Exception:
                pass


def _assign_workflow_groups(turns: list) -> None:
    """Group consecutive turns that form a continuous workflow chain.

    A workflow group starts when a turn spawns a subagent. Subsequent
    subagent_announce turns whose [sessionId:] matches a pending spawn's
    real child_session_id are chained into the same group.

    Sets turn.workflow_group_id (int) for each turn in a multi-turn chain.
    Single-turn spawns are NOT grouped (workflow_group_id stays None).
    """
    group_id = 0
    # child_session_id → workflow_group_id for spawns awaiting their announce
    pending: dict = {}

    for turn in turns:
        matched_group = None

        # Announce turn: check if it continues a pending workflow
        if turn.user_source in ("subagent_announce", "cron_announce"):
            m = _ANNOUNCE_SESSION_ID_RE.search(turn.user_text)
            if m:
                sid = m.group(1)
                if sid in pending:
                    matched_group = pending.pop(sid)

        # Turn with spawns but not yet matched: start a new group
        if matched_group is None and turn.subagent_spawns:
            group_id += 1
            matched_group = group_id

        if matched_group is not None:
            turn.workflow_group_id = matched_group
            # Register this turn's spawns so future announce turns can chain in
            for spawn in turn.subagent_spawns:
                real_sid = (
                    (spawn.announce_stats or {}).get("session_id")
                    or spawn.child_session_id
                )
                if real_sid:
                    pending[real_sid] = matched_group

    # Clear workflow_group_id from turns that ended up alone in their group
    # (spawned but no announce ever came — no need to show a workflow block)
    from collections import Counter
    counts = Counter(t.workflow_group_id for t in turns if t.workflow_group_id is not None)
    for turn in turns:
        if turn.workflow_group_id is not None and counts[turn.workflow_group_id] < 2:
            turn.workflow_group_id = None


def _enrich_spawns_from_announces(turns: list, agent_id: str = ""):
    """Match subagent announce messages to their spawns and load child turns.

    Current announce format:
      [sessionId: UUID] A subagent task "LABEL" just completed ...
      Stats: runtime Xm Ys • tokens X.Xk (in X.Xk / out X.Xk)

    The real child sessionId is in the [sessionId: ...] prefix (different from the
    childSessionKey UUID used for routing). We match by label, then load child turns
    using the real session UUID.
    """
    # Build lookup: label -> [SubagentSpawn, ...] (ordered, pop first match)
    from collections import defaultdict
    spawns_by_label: dict = defaultdict(list)
    for turn in turns:
        for spawn in turn.subagent_spawns:
            if spawn.label:
                spawns_by_label[spawn.label].append(spawn)

    if not spawns_by_label:
        return

    for turn in turns:
        if turn.user_source != "subagent_announce":
            continue
        text = turn.user_text

        # --- New format: has Stats: section ---
        for m in _ANNOUNCE_RE.finditer(text):
            match_start = m.start()
            chunk_start = text.rfind("---", 0, match_start)
            # Extend chunk past match end to capture inline • sessionId / transcript fields
            chunk_end = text.find("\n\n", m.end())
            if chunk_end < 0:
                chunk_end = len(text)
            chunk = text[chunk_start if chunk_start >= 0 else 0: chunk_end]

            stats = _parse_announce_match(m, chunk if chunk else text)
            if not stats:
                continue

            label = stats.get("label", "")
            candidates = spawns_by_label.get(label)
            if not candidates:
                continue
            spawn = candidates.pop(0)

            spawn.announce_stats = stats
            if not spawn.duration_ms and stats.get("runtime_ms"):
                spawn.duration_ms = stats["runtime_ms"]
            if not spawn.total_tokens and stats.get("total_tokens"):
                spawn.total_tokens = stats["total_tokens"]

            if not spawn.child_turns:
                real_sid = stats.get("session_id", "")
                child_file = _find_child_session_by_id(real_sid, agent_id)
                if child_file:
                    child_analysis = parse_session(child_file, recursive_subagents=True)
                    spawn.child_turns = child_analysis.turns
                    if not spawn.cost_usd and child_analysis.total_cost:
                        spawn.cost_usd = child_analysis.total_cost

        # --- Old format: no Stats section, just label in text ---
        if not _ANNOUNCE_RE.search(text):
            label_m = _ANNOUNCE_LABEL_RE.search(text)
            sid_m = _ANNOUNCE_SESSION_ID_RE.search(text)
            if label_m:
                label = label_m.group(1)
                candidates = spawns_by_label.get(label)
                if candidates:
                    spawn = candidates.pop(0)
                    stats = {"label": label}
                    if sid_m:
                        stats["session_id"] = sid_m.group(1)
                    if not spawn.announce_stats:
                        spawn.announce_stats = stats

                    if not spawn.child_turns:
                        real_sid = stats.get("session_id", "")
                        child_file = _find_child_session_by_id(real_sid, agent_id)
                        # Fallback: search by timestamp + label in first user message
                        if not child_file and turn.timestamp:
                            child_file = _find_child_session_by_label(
                                label, spawn.label, agent_id, turn.timestamp
                            )
                        if child_file:
                            child_analysis = parse_session(child_file, recursive_subagents=True)
                            spawn.child_turns = child_analysis.turns
                            # Store real session ID for Open Session link
                            if not spawn.announce_stats.get("session_id"):
                                sid = child_file.name.split(".jsonl")[0]
                                spawn.announce_stats["session_id"] = sid
                            if not spawn.cost_usd and child_analysis.total_cost:
                                spawn.cost_usd = child_analysis.total_cost


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
            user_count = 0
            total_cost = 0.0
            total_tokens = 0
            model = ""
            session_type = "chat"

            last_preview = ""
            last_preview_role = "user"
            tool_call_count = 0
            subagent_count = 0
            error_count = 0
            current_turn_user_ts = None
            current_turn_last_ts = None
            turn_durations = []
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
                    ts = _ts_to_dt(msg.get("timestamp") or entry.get("timestamp"))
                    if role == "user":
                        user_count += 1
                        if current_turn_user_ts and current_turn_last_ts:
                            dur = (current_turn_last_ts - current_turn_user_ts).total_seconds()
                            if dur > 0:
                                turn_durations.append(dur)
                        current_turn_user_ts = ts
                        current_turn_last_ts = None
                        content = msg.get("content", [])
                        user_text = ""
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    user_text += c.get("text", "")
                        last_preview = user_text
                        last_preview_role = "user"
                        # 채널 메시지: raw metadata 대신 실제 메시지 텍스트로 대체
                        _src = _detect_source(user_text)
                        if _src in _BRACKET_CHANNEL_MAP or _src == "discord":
                            _cm = _parse_channel_message(user_text, _src)
                            if _cm and _cm.get("actual_text"):
                                last_preview = _cm["actual_text"]
                        if user_count == 1:
                            src = _detect_source(user_text)
                            if src == "cron":
                                session_type = "cron"
                            elif src == "heartbeat":
                                session_type = "heartbeat"
                            elif src in _BRACKET_CHANNEL_MAP or src == "discord":
                                # 채널 메시지: session_type은 "chat" 유지, channel 필드에 기록
                                _cm = _parse_channel_message(user_text, src)
                                if _cm:
                                    meta["channel"] = _cm.get("platform", src)
                    elif role in ("assistant", "toolResult"):
                        # delivery-mirror는 실제 LLM 응답이 아니라 채널 미러링
                        # → 포함시키면 세션 전체 기간이 turn 시간으로 측정됨
                        if ts and msg.get("model") != "delivery-mirror":
                            current_turn_last_ts = ts
                    if role == "assistant":
                        if msg.get("model") != "delivery-mirror":
                            content = msg.get("content", [])
                            if isinstance(content, list):
                                for c in content:
                                    if isinstance(c, dict) and c.get("type") == "text":
                                        text = c.get("text", "").strip()
                                        if text:
                                            last_preview = text
                                            last_preview_role = "assistant"
                                            break
                        if msg.get("model"):
                            model = msg["model"]
                        usage = msg.get("usage", {})
                        total_tokens += usage.get("totalTokens", 0)
                        cost = usage.get("cost", {})
                        total_cost += cost.get("total", 0)
                        content = msg.get("content", [])
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "toolCall":
                                    tool_call_count += 1
                                    if c.get("name") == "sessions_spawn":
                                        subagent_count += 1
                    elif role == "toolResult":
                        details = msg.get("details", {})
                        if (msg.get("isError") or
                                details.get("error") or
                                details.get("status") == "error"):
                            error_count += 1

            if current_turn_user_ts and current_turn_last_ts:
                dur = (current_turn_last_ts - current_turn_user_ts).total_seconds()
                if dur > 0:
                    turn_durations.append(dur)

            if "subagent" in str(file_path):
                session_type = "subagent"

            meta["type"] = session_type
            meta["model"] = model
            meta["turns"] = user_count
            meta["cost"] = total_cost
            meta["tokens"] = total_tokens
            meta["last_message"] = last_preview[:200] if last_preview else ""
            meta["last_message_role"] = last_preview_role
            meta["tool_calls"] = tool_call_count
            meta["subagents"] = subagent_count
            meta["errors"] = error_count
            meta["avg_turn_time"] = round(sum(turn_durations) / len(turn_durations), 1) if turn_durations else None

    except (IOError, OSError):
        pass

    return meta


def get_raw_turn_lines(file_path: str | Path, turn_index: int) -> list:
    """Get the raw JSONL entries for a specific turn (for log viewing)."""
    analysis = parse_session(file_path, recursive_subagents=False)
    if turn_index < 0 or turn_index >= len(analysis.turns):
        return []
    return analysis.turns[turn_index].raw_lines
