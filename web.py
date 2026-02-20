"""
ocmon web — Flask web dashboard for OpenClaw agent monitoring.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, jsonify, request, abort

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser import (
    parse_session, list_sessions, load_cron_runs, load_subagent_runs,
    get_raw_turn_lines, KST, _ts_to_dt, _truncate, AGENTS_DIR,
    OPENCLAW_DIR,
)
import gateway

# --- Lab activity logger ---
_lab_log_file = Path(__file__).parent / "lab.log"
_lab_logger = logging.getLogger("ocmon.lab")
_lab_logger.setLevel(logging.INFO)
_lab_handler = logging.FileHandler(_lab_log_file, encoding="utf-8")
_lab_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_lab_logger.addHandler(_lab_handler)

# In-memory log for UI display (last 100 entries)
_lab_activity_log: list[dict] = []

def _log_lab(action: str, **kwargs):
    entry = {"ts": datetime.now(KST).isoformat(), "action": action, **kwargs}
    _lab_logger.info(json.dumps(entry, ensure_ascii=False, default=str))
    _lab_activity_log.append(entry)
    if len(_lab_activity_log) > 100:
        _lab_activity_log.pop(0)


def create_app():
    app = Flask(__name__,
                template_folder=os.path.join(os.path.dirname(__file__), "templates"),
                static_folder=os.path.join(os.path.dirname(__file__), "static"))

    # --- Pages ---

    @app.route("/")
    def index():
        return render_template("sessions.html")

    @app.route("/session/<session_id>")
    def session_detail(session_id):
        return render_template("detail.html", session_id=session_id)

    @app.route("/session/<session_id>/graph")
    def session_graph(session_id):
        return render_template("graph.html", session_id=session_id)

    @app.route("/cost")
    def cost_page():
        return render_template("cost.html")

    # --- API ---

    @app.route("/api/sessions")
    def api_sessions():
        agent = request.args.get("agent", "all")
        last_n = int(request.args.get("last", 50))
        session_type = request.args.get("type")

        sessions = list_sessions(
            agent_id=None if agent == "all" else agent,
            last_n=last_n,
            session_type=session_type,
        )

        result = []
        for s in sessions:
            result.append({
                "session_id": s["session_id"],
                "agent_id": s["agent_id"],
                "type": s.get("type", "chat"),
                "model": s.get("model", ""),
                "turns": s.get("turns", 0),
                "tokens": s.get("tokens", 0),
                "cost": round(s.get("cost", 0), 6),
                "file_size": s.get("file_size", 0),
                "modified": s.get("modified", "").isoformat() if hasattr(s.get("modified", ""), "isoformat") else "",
                "started_at": s.get("started_at", "").isoformat() if hasattr(s.get("started_at", ""), "isoformat") else "",
            })
        return jsonify(result)

    @app.route("/api/session/<session_id>")
    def api_session_detail(session_id):
        file_path = _resolve(session_id)
        if not file_path:
            abort(404, "Session not found")

        analysis = parse_session(file_path, recursive_subagents=True)
        return jsonify(_serialize_analysis(analysis))

    @app.route("/api/session/<session_id>/graph")
    def api_session_graph(session_id):
        """Return graph data for subagent tree visualization."""
        file_path = _resolve(session_id)
        if not file_path:
            abort(404, "Session not found")

        analysis = parse_session(file_path, recursive_subagents=True)
        nodes, edges = _build_graph(analysis)
        return jsonify({"nodes": nodes, "edges": edges})

    @app.route("/api/session/<session_id>/raw/<int:turn_index>")
    def api_raw_turn(session_id, turn_index):
        file_path = _resolve(session_id)
        if not file_path:
            abort(404, "Session not found")
        raw_lines = get_raw_turn_lines(file_path, turn_index)
        return jsonify(raw_lines)

    @app.route("/api/cost")
    def api_cost():
        period = request.args.get("period", "week")
        agent = request.args.get("agent", "all")

        sessions = list_sessions(
            agent_id=None if agent == "all" else agent,
            last_n=1000,
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

        filtered = [s for s in sessions
                     if s.get("modified", datetime.min.replace(tzinfo=KST)) >= cutoff]

        by_agent = {}
        by_type = {}
        by_model = {}
        by_day = {}
        total_cost = 0
        total_tokens = 0

        for s in filtered:
            aid = s["agent_id"]
            stype = s.get("type", "chat")
            model = s.get("model", "unknown")
            cost = s.get("cost", 0)
            tokens = s.get("tokens", 0)
            day = s.get("modified", now).strftime("%Y-%m-%d")

            by_agent[aid] = by_agent.get(aid, 0) + cost
            by_type[stype] = by_type.get(stype, 0) + cost
            by_model[model] = by_model.get(model, 0) + cost
            by_day[day] = by_day.get(day, 0) + cost
            total_cost += cost
            total_tokens += tokens

        return jsonify({
            "period": period,
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "session_count": len(filtered),
            "by_agent": {k: round(v, 6) for k, v in sorted(by_agent.items(), key=lambda x: -x[1])},
            "by_type": {k: round(v, 6) for k, v in sorted(by_type.items(), key=lambda x: -x[1])},
            "by_model": {k: round(v, 6) for k, v in sorted(by_model.items(), key=lambda x: -x[1])},
            "by_day": dict(sorted(by_day.items())),
        })

    @app.route("/api/crons")
    def api_crons():
        last_n = int(request.args.get("last", 50))
        runs = load_cron_runs(last_n=last_n)
        return jsonify([{
            "ts": r.ts,
            "job_id": r.job_id,
            "job_name": r.job_name,
            "status": r.status,
            "summary": r.summary,
            "error": r.error,
            "session_id": r.session_id,
            "agent_id": r.agent_id,
        } for r in runs])

    @app.route("/api/agents")
    def api_agents():
        agents = []
        if AGENTS_DIR.exists():
            for d in sorted(AGENTS_DIR.iterdir()):
                if d.is_dir():
                    sessions_dir = d / "sessions"
                    count = len(list(sessions_dir.glob("*.jsonl"))) if sessions_dir.exists() else 0
                    agents.append({"id": d.name, "sessions": count})
        return jsonify(agents)

    # --- Lab ---

    @app.route("/lab")
    def lab_page():
        return render_template("lab.html")

    @app.route("/api/lab/sessions")
    def api_lab_sessions():
        """Return gateway sessions (with real session keys) merged with local file info."""
        agent = request.args.get("agent")
        limit = int(request.args.get("last", 30))
        try:
            gw_sessions = gateway.list_gateway_sessions(
                agent_id=agent if agent and agent != "all" else None,
                limit=limit,
            )
        except Exception as e:
            # Fallback to local file listing if gateway unavailable
            gw_sessions = []

        result = []
        for s in (gw_sessions if isinstance(gw_sessions, list) else []):
            key = s.get("key", "")
            sid = s.get("sessionId", "")
            # Extract agent from key: agent:<agentId>:...
            parts = key.split(":")
            agent_id = parts[1] if len(parts) >= 2 and parts[0] == "agent" else ""
            result.append({
                "session_key": key,
                "session_id": sid,
                "agent_id": agent_id,
                "display_name": s.get("displayName", ""),
                "model": s.get("model", ""),
                "tokens": s.get("totalTokens", 0),
                "cost": round(s.get("costUsd", 0) or 0, 6),
                "updated_at": s.get("updatedAt", 0),
            })
        return jsonify(result)

    @app.route("/api/lab/send", methods=["POST"])
    def api_lab_send():
        data = request.get_json(force=True)
        message = data.get("message", "").strip()
        session_key = data.get("sessionKey", "").strip()
        if not message or not session_key:
            return jsonify({"error": "message and sessionKey required"}), 400
        agent_id = data.get("agentId", "main")
        model = data.get("model") or None
        _log_lab("send", sessionKey=session_key, agentId=agent_id,
                 message=message[:200], model=model,
                 deliver=data.get("deliver", False))
        try:
            result = gateway.send_agent_message(
                message=message,
                session_key=session_key,
                agent_id=agent_id,
                model=model,
                thinking=data.get("thinking") or None,
                deliver=data.get("deliver", False),
                extra_system_prompt=data.get("extraSystemPrompt") or None,
                timeout=int(data.get("timeout", 120)),
            )
            _log_lab("send_ok", sessionKey=session_key,
                     runId=result.get("runId", ""))
            return jsonify({"ok": True, "result": result}), 202
        except Exception as e:
            _log_lab("send_error", sessionKey=session_key, error=str(e))
            return jsonify({"ok": False, "error": str(e)}), 500

    # Track file sizes for change detection
    _poll_file_cache = {}  # session_id -> (file_path, file_size)

    @app.route("/api/lab/poll/<session_id>")
    def api_lab_poll(session_id):
        since_turns = int(request.args.get("since_turns", 0))
        file_path = _resolve(session_id)
        if not file_path:
            return jsonify({"changed": False, "error": "session not found"})

        # Check file size for change detection
        try:
            current_size = file_path.stat().st_size
        except OSError:
            return jsonify({"changed": False, "error": "file not accessible"})

        cache_key = str(file_path)
        prev_size = _poll_file_cache.get(cache_key, 0)
        _poll_file_cache[cache_key] = current_size

        if current_size == prev_size and since_turns > 0:
            return jsonify({"changed": False})

        # Parse and return full analysis
        analysis = parse_session(file_path, recursive_subagents=True)
        data = _serialize_analysis(analysis)

        if len(data.get("turns", [])) == since_turns and current_size == prev_size:
            return jsonify({"changed": False})

        return jsonify({"changed": True, "data": data})

    @app.route("/api/lab/context")
    def api_lab_context():
        workspace = _get_workspace_dir()
        files = []
        for name in WORKSPACE_FILES:
            fp = workspace / name
            if fp.exists():
                try:
                    content = fp.read_text(encoding="utf-8")
                    files.append({
                        "name": name,
                        "size": len(content),
                        "content": content,
                    })
                except Exception:
                    files.append({"name": name, "size": 0, "content": "", "error": "read failed"})
        return jsonify(files)

    @app.route("/api/lab/context/<filename>", methods=["PUT"])
    def api_lab_context_save(filename):
        if filename not in WORKSPACE_FILES:
            return jsonify({"error": f"Not an allowed file: {filename}"}), 400
        workspace = _get_workspace_dir()
        fp = workspace / filename
        data = request.get_json(force=True)
        content = data.get("content", "")
        # Create backup before overwriting
        _backup_context_file(fp)
        fp.write_text(content, encoding="utf-8")
        _log_lab("context_save", file=filename, size=len(content))
        return jsonify({"ok": True, "size": len(content)})

    @app.route("/api/lab/settings/<session_key>", methods=["PATCH"])
    def api_lab_settings(session_key):
        data = request.get_json(force=True)
        _log_lab("settings_patch", sessionKey=session_key, **data)
        try:
            result = gateway.patch_session(session_key, **data)
            return jsonify({"ok": True, "result": result})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/lab/activity")
    def api_lab_activity():
        """Return recent lab activity log entries."""
        return jsonify(list(reversed(_lab_activity_log)))

    return app


# --- Lab helpers ---

WORKSPACE_FILES = [
    "AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md",
    "USER.md", "HEARTBEAT.md", "BOOTSTRAP.md", "MEMORY.md",
    "TODO.md", "MIGRATION.md",
]


def _get_workspace_dir() -> Path:
    """Get workspace directory from openclaw.json config."""
    try:
        cfg = gateway.load_gateway_config()
    except Exception:
        pass
    # Read workspace from full config
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    try:
        with open(config_path) as f:
            full_cfg = json.load(f)
        workspace = full_cfg.get("agents", {}).get("defaults", {}).get("workspace", "")
        if workspace:
            return Path(workspace)
    except Exception:
        pass
    return OPENCLAW_DIR / "workspace"


def _backup_context_file(filepath: Path):
    """Create .lab-backup before first modification."""
    backup = filepath.with_suffix(filepath.suffix + ".lab-backup")
    if filepath.exists() and not backup.exists():
        shutil.copy2(filepath, backup)


# --- Helpers ---

def _resolve(session_id: str):
    """Resolve session ID to file path.

    Searches for both active .jsonl files and soft-deleted
    .jsonl.deleted.{timestamp} files.
    """
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.exists():
            continue
        # Try exact .jsonl first
        for f in sessions_dir.glob(f"{session_id}*.jsonl"):
            return f
        # Try .deleted.* variants
        for f in sessions_dir.iterdir():
            if f.name.startswith(session_id) and ".jsonl.deleted." in f.name:
                return f
    return None


def _serialize_analysis(analysis):
    """Serialize SessionAnalysis to JSON-safe dict."""
    result = {
        "session_id": analysis.session_id,
        "agent_id": analysis.agent_id,
        "session_type": analysis.session_type,
        "started_at": analysis.started_at.isoformat() if analysis.started_at else None,
        "cwd": analysis.cwd,
        "model": analysis.model,
        "provider": analysis.provider,
        "total_cost": round(analysis.total_cost, 6),
        "total_tokens": analysis.total_tokens,
        "total_duration_ms": analysis.total_duration_ms,
        "compactions": analysis.compactions,
        "compaction_events": [
            {
                "first_kept_entry_id": ce.first_kept_entry_id,
                "tokens_before": ce.tokens_before,
                "tokens_after": ce.tokens_after,
                "summary": _truncate(ce.summary, 500),
                "from_hook": ce.from_hook,
                "timestamp": ce.timestamp.isoformat() if ce.timestamp else None,
            }
            for ce in analysis.compaction_events
        ],
        "turns": [_serialize_turn(t) for t in analysis.turns],
        # session-level metadata from sessions.json
        "context_tokens": analysis.context_tokens,
        "session_input_tokens": analysis.session_input_tokens,
        "session_output_tokens": analysis.session_output_tokens,
        "session_total_tokens": analysis.session_total_tokens,
        "session_compaction_count": analysis.session_compaction_count,
        "memory_flush_at": analysis.memory_flush_at.isoformat() if analysis.memory_flush_at else None,
    }

    if analysis.context:
        result["context"] = {
            "systemPromptChars": analysis.context.system_prompt_chars,
            "projectContextChars": analysis.context.project_context_chars,
            "nonProjectContextChars": analysis.context.non_project_context_chars,
            "bootstrapMaxChars": analysis.context.bootstrap_max_chars,
            "workspaceDir": analysis.context.workspace_dir,
            "sandboxMode": analysis.context.sandbox_mode,
            "injectedFiles": [
                {
                    "name": f.name,
                    "path": f.path,
                    "rawChars": f.raw_chars,
                    "injectedChars": f.injected_chars,
                    "missing": f.missing,
                    "truncated": f.truncated,
                }
                for f in analysis.context.injected_files
            ],
            "skills": [
                {"name": s.name, "chars": s.block_chars}
                for s in analysis.context.skills
            ],
            "tools": [
                {"name": t.name, "summaryChars": t.summary_chars, "schemaChars": t.schema_chars}
                for t in analysis.context.tools
            ],
        }

    return result


def _serialize_turn(turn):
    return {
        "index": turn.index,
        "user_text": turn.user_text[:500],
        "user_source": turn.user_source,
        "assistant_texts": [t[:1000] for t in turn.assistant_texts],
        "tool_calls": [_serialize_tc(tc) for tc in turn.tool_calls],
        "subagent_spawns": [_serialize_spawn(s) for s in turn.subagent_spawns],
        "thinking_text": turn.thinking_text[:2000] if turn.thinking_text else None,
        "thinking_encrypted": turn.thinking_encrypted,
        "model": turn.model,
        "provider": turn.provider,
        "api": turn.api,
        "usage": turn.usage,
        "cost": turn.cost,
        "stop_reason": turn.stop_reason,
        "duration_ms": turn.duration_ms,
        "timestamp": turn.timestamp.isoformat() if turn.timestamp else None,
        "in_context": turn.in_context,
        "thinking_level": turn.thinking_level,
        "cache_hit_rate": round(turn.cache_hit_rate, 4),
    }


def _serialize_tc(tc):
    args = {}
    for k, v in tc.arguments.items():
        if isinstance(v, str) and len(v) > 300:
            args[k] = v[:300] + "..."
        else:
            args[k] = v
    return {
        "id": tc.id,
        "name": tc.name,
        "arguments": args,
        "result_text": tc.result_text[:500],
        "result_size": tc.result_size,
        "duration_ms": tc.duration_ms,
        "is_error": tc.is_error,
        "status": tc.status,
    }


def _serialize_spawn(spawn):
    return {
        "run_id": spawn.run_id,
        "label": spawn.label,
        "task": spawn.task[:500],
        "child_session_key": spawn.child_session_key,
        "child_session_id": spawn.child_session_id,
        "child_turns": [_serialize_turn(t) for t in spawn.child_turns],
        "duration_ms": spawn.duration_ms,
        "total_tokens": spawn.total_tokens,
        "cost_usd": round(spawn.cost_usd, 6) if spawn.cost_usd else None,
        "outcome": spawn.outcome,
        "announce_stats": spawn.announce_stats,
    }


def _build_graph(analysis):
    """Build nodes + edges for interactive graph visualization."""
    nodes = []
    edges = []

    # Root node = this session
    root_id = f"session:{analysis.session_id[:8]}"
    nodes.append({
        "id": root_id,
        "type": "session",
        "label": f"{analysis.agent_id}/{analysis.session_type}",
        "sublabel": analysis.session_id[:10],
        "model": analysis.model,
        "cost": round(analysis.total_cost, 4),
        "tokens": analysis.total_tokens,
        "duration_ms": analysis.total_duration_ms,
        "turns": len(analysis.turns),
        "status": "ok",
    })

    for turn in analysis.turns:
        turn_id = f"turn:{analysis.session_id[:8]}:{turn.index}"
        nodes.append({
            "id": turn_id,
            "type": "turn",
            "label": f"Turn {turn.index}",
            "sublabel": _truncate(turn.user_text.replace("\n", " "), 60),
            "model": turn.model,
            "cost": round(turn.cost.get("total", 0), 4),
            "tokens": turn.usage.get("totalTokens", 0),
            "duration_ms": turn.duration_ms,
            "tools": len(turn.tool_calls),
            "source": turn.user_source,
            "status": "error" if any(tc.is_error for tc in turn.tool_calls) else "ok",
        })
        edges.append({"from": root_id, "to": turn_id, "type": "contains"})

        # Tool call nodes
        for tc in turn.tool_calls:
            if tc.name == "sessions_spawn":
                continue  # handled by subagent nodes
            tc_id = f"tool:{tc.id[:16]}"
            nodes.append({
                "id": tc_id,
                "type": "tool",
                "label": tc.name,
                "sublabel": _tool_summary(tc),
                "duration_ms": tc.duration_ms,
                "result_size": tc.result_size,
                "status": "error" if tc.is_error else "ok",
            })
            edges.append({"from": turn_id, "to": tc_id, "type": "calls"})

        # Subagent nodes (with recursive children)
        for spawn in turn.subagent_spawns:
            _add_subagent_graph(nodes, edges, turn_id, spawn)

    return nodes, edges


def _add_subagent_graph(nodes, edges, parent_id, spawn):
    """Recursively add subagent nodes to graph."""
    spawn_id = f"subagent:{spawn.run_id[:12]}" if spawn.run_id else f"subagent:{spawn.child_session_id or 'unknown'}"

    nodes.append({
        "id": spawn_id,
        "type": "subagent",
        "label": spawn.label or "subagent",
        "sublabel": _truncate(spawn.task, 80),
        "cost": round(spawn.cost_usd, 4) if spawn.cost_usd else None,
        "tokens": spawn.total_tokens,
        "duration_ms": spawn.duration_ms,
        "turns": len(spawn.child_turns),
        "outcome": spawn.outcome,
        "status": spawn.outcome,
        "child_session_id": spawn.child_session_id,
    })
    edges.append({"from": parent_id, "to": spawn_id, "type": "spawns"})

    # Child turn tool nodes
    for child_turn in spawn.child_turns:
        for tc in child_turn.tool_calls:
            if tc.name == "sessions_spawn":
                continue
            tc_id = f"tool:{tc.id[:16]}"
            nodes.append({
                "id": tc_id,
                "type": "tool",
                "label": tc.name,
                "sublabel": _tool_summary(tc),
                "duration_ms": tc.duration_ms,
                "result_size": tc.result_size,
                "status": "error" if tc.is_error else "ok",
            })
            edges.append({"from": spawn_id, "to": tc_id, "type": "calls"})

        for nested_spawn in child_turn.subagent_spawns:
            _add_subagent_graph(nodes, edges, spawn_id, nested_spawn)


def _tool_summary(tc):
    """Short summary for tool call display."""
    if tc.name in ("read", "write", "edit"):
        fp = tc.arguments.get("file_path", "")
        return os.path.basename(fp) if fp else ""
    elif tc.name == "exec":
        cmd = tc.arguments.get("command", "")
        return _truncate(cmd, 50)
    elif tc.name in ("glob", "grep"):
        return tc.arguments.get("pattern", "")[:40]
    return ""
