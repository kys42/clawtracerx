"""
ClawTracerX web — Flask web dashboard for OpenClaw agent monitoring.
"""
from __future__ import annotations

import glob as _glob
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, stream_with_context

from clawtracerx import gateway
from clawtracerx import session_parser as _sp
from clawtracerx.session_parser import (
    KST,
    _truncate,
    get_raw_turn_lines,
    list_sessions,
    load_cron_runs,
    load_heartbeat_configs,
    parse_session,
)


def _get_base_path() -> str:
    """Return package base path (handles PyInstaller frozen bundles)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


# --- OpenClaw source discovery ---

def _get_openclaw_src() -> Path | None:
    """pnpm wrapper 스크립트에서 openclaw 소스 경로를 파생."""
    wrapper = Path.home() / "Library/pnpm/openclaw"
    if not wrapper.exists():
        return None
    try:
        content = wrapper.read_text()
        m = re.search(r'"?\$basedir/([^"]+openclaw\.mjs)"?', content)
        if not m:
            return None
        rel = m.group(1)  # e.g. ../../sources/openclaw/openclaw.mjs
        src = (wrapper.parent / rel).resolve().parent
        return src if src.is_dir() else None
    except Exception:
        return None


_tool_desc_cache: dict | None = None
_tool_desc_lock = threading.Lock()


def _build_tool_desc_map() -> dict:
    """pi-coding-agent dist + openclaw src/agents/tools TS에서 tool description 추출."""
    global _tool_desc_cache
    if _tool_desc_cache is not None:
        return _tool_desc_cache
    with _tool_desc_lock:
        # Double-check after acquiring lock
        if _tool_desc_cache is not None:
            return _tool_desc_cache

        result: dict[str, str] = {}
        openclaw_src = _get_openclaw_src()

        # 1. pi-coding-agent dist/core/tools/*.js
        if openclaw_src:
            pattern = str(openclaw_src / "node_modules/.pnpm/@mariozechner+pi-coding-agent*/node_modules/@mariozechner/pi-coding-agent/dist/core/tools")
            matches = _glob.glob(pattern)
            if matches:
                pi_tools_dir = Path(matches[0])
                tool_name_map = {
                    "bash": "exec", "find": "glob", "ls": "ls",
                    "grep": "grep", "read": "read", "write": "write",
                    "edit": "edit",
                }
                for js_file in pi_tools_dir.glob("*.js"):
                    if js_file.suffix == ".map":
                        continue
                    stem = js_file.stem
                    content = js_file.read_text(errors="replace")
                    # 가장 긴 description 찾기 (파라미터 설명 제외)
                    descs = re.findall(r'description:\s*`([\s\S]+?)`', content)
                    descs += re.findall(r'description:\s*"((?:[^"\\]|\\.)*)"', content)
                    best = max(descs, key=len, default="")
                    if len(best) > 30:
                        tool_name = tool_name_map.get(stem, stem)
                        result[tool_name] = best.strip()

        # 2. openclaw src/agents/tools/*.ts
        if openclaw_src:
            ts_dir = openclaw_src / "src/agents/tools"
            if ts_dir.is_dir():
                for ts_file in ts_dir.glob("*.ts"):
                    if ".test." in ts_file.name or ".e2e." in ts_file.name:
                        continue
                    content = ts_file.read_text(errors="replace")
                    name_m = re.search(r'\bname:\s*["`]([a-z_][a-z0-9_]*)["`]', content)
                    descs = re.findall(r'description:\s*`([\s\S]+?)`', content)
                    descs += re.findall(r'description:\s*"((?:[^"\\]|\\.)*)"', content)
                    best = max(descs, key=len, default="")
                    if name_m and len(best) > 30:
                        result[name_m.group(1)] = best.strip()

        _tool_desc_cache = result
        return result


# --- Lab activity logger ---
_lab_log_file = Path(_get_base_path()).parent / "lab.log"
_lab_logger = logging.getLogger("ctrace.lab")
_lab_logger.setLevel(logging.INFO)
_lab_handler = logging.FileHandler(_lab_log_file, encoding="utf-8")
_lab_handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
_lab_logger.addHandler(_lab_handler)

# In-memory log for UI display (last 100 entries) — thread-safe deque
_lab_activity_log: deque = deque(maxlen=100)
_lab_log_lock = threading.Lock()

def _log_lab(action: str, **kwargs):
    entry = {"ts": datetime.now(KST).isoformat(), "action": action, **kwargs}
    _lab_logger.info(json.dumps(entry, ensure_ascii=False, default=str))
    with _lab_log_lock:
        _lab_activity_log.append(entry)


def create_app():
    _base = _get_base_path()
    app = Flask(__name__,
                template_folder=os.path.join(_base, "templates"),
                static_folder=os.path.join(_base, "static"))

    @app.context_processor
    def inject_globals():
        return {'home_dir': os.path.expanduser('~')}

    # --- Pages ---

    @app.route("/home")
    def home_page():
        return render_template("home.html", active="home")

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

    @app.route("/schedule")
    def schedule_page():
        return render_template("schedule.html")

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
                "last_message": s.get("last_message", ""),
                "last_message_role": s.get("last_message_role", "user"),
                "tool_calls": s.get("tool_calls", 0),
                "subagents": s.get("subagents", 0),
                "errors": s.get("errors", 0),
                "avg_turn_time": s.get("avg_turn_time"),
                "channel": s.get("channel", ""),
                "file_path": s.get("file_path", ""),
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
        """Return nodes + edges for interactive D3 graph visualization."""
        file_path = _resolve(session_id)
        if not file_path:
            abort(404, "Session not found")

        analysis = parse_session(file_path, recursive_subagents=True)
        nodes, edges = _build_graph(analysis)
        return jsonify({"nodes": nodes, "edges": edges})

    @app.route("/api/skill-content")
    def api_skill_content():
        name = request.args.get("name", "").strip()
        if not name or "/" in name or ".." in name:
            abort(400, "Invalid skill name")
        openclaw_src = _get_openclaw_src()
        search_dirs = [
            _sp.OPENCLAW_DIR / "workspace" / "skills" / name,
            _sp.OPENCLAW_DIR / "workspace" / name,
        ]
        if openclaw_src:
            search_dirs.append(openclaw_src / "skills" / name)
        for skill_dir in search_dirs:
            skill_file = skill_dir / "SKILL.md"
            # Resolve symlinks and verify path stays within allowed dirs
            try:
                resolved = skill_file.resolve(strict=True)
            except (OSError, ValueError):
                continue
            if resolved.exists():
                content = resolved.read_text(encoding="utf-8", errors="replace")
                label = "bundled" if openclaw_src and skill_dir.is_relative_to(openclaw_src) else "workspace"
                return jsonify({"content": content, "size": skill_file.stat().st_size,
                                "name": name, "path": str(skill_file), "label": label})
        abort(404, f"'{name}' SKILL.md not found")

    @app.route("/api/tool-content")
    def api_tool_content():
        name = request.args.get("name", "").strip()
        if not name:
            abort(400, "name required")
        tool_map = _build_tool_desc_map()
        desc = tool_map.get(name) or tool_map.get(name.replace("-", "_"))
        if not desc:
            abort(404, f"No description found for tool '{name}'")
        return jsonify({"name": name, "description": desc})

    @app.route("/api/file-content")
    def api_file_content():
        path_str = request.args.get("path", "").strip()
        if not path_str:
            abort(400, "path required")
        path = Path(path_str).resolve()
        try:
            path.relative_to(_sp.OPENCLAW_DIR.resolve())
        except ValueError:
            abort(403, "Access denied: path outside ~/.openclaw/")
        if not path.is_file():
            abort(404, "File not found")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return jsonify({"content": content, "size": path.stat().st_size, "name": path.name})
        except Exception as e:
            abort(500, str(e))

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
        by_agent_type = {}  # {agent_id: {type: cost}}
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
            by_agent_type.setdefault(aid, {})
            by_agent_type[aid][stype] = by_agent_type[aid].get(stype, 0) + cost
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
            "by_agent_type": {
                aid: {t: round(c, 6) for t, c in types.items()}
                for aid, types in sorted(by_agent_type.items(), key=lambda x: -sum(x[1].values()))
            },
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

    @app.route("/api/schedule")
    def api_schedule():
        # Cron jobs + recent runs
        jobs_raw = _sp.load_cron_jobs()
        jobs = []
        for jid, job in jobs_raw.items():
            state = job.get("state", {})
            schedule = job.get("schedule", {})
            runs_raw = _sp.load_cron_runs(job_id=jid, last_n=10)
            runs = [{"ts": r.ts, "status": r.status, "summary": r.summary,
                     "error": r.error, "session_id": r.session_id,
                     "duration_ms": r.duration_ms} for r in runs_raw]
            jobs.append({
                "id": jid, "name": job.get("name", jid[:8]),
                "agent_id": job.get("agentId", ""),
                "enabled": job.get("enabled", False),
                "schedule_expr": schedule.get("expr", ""),
                "schedule_tz": schedule.get("tz", ""),
                "wake_mode": job.get("wakeMode", ""),
                "last_status": state.get("lastStatus", ""),
                "last_run_at_ms": state.get("lastRunAtMs"),
                "last_duration_ms": state.get("lastDurationMs"),
                "next_run_at_ms": state.get("nextRunAtMs"),
                "consecutive_errors": state.get("consecutiveErrors", 0),
                "payload_message": job.get("payload", {}).get("message", ""),
                "runs": runs,
            })
        jobs.sort(key=lambda j: (not j["enabled"], j.get("next_run_at_ms") or float('inf')))

        enabled = sum(1 for j in jobs if j["enabled"])
        ok = sum(1 for j in jobs if j["enabled"] and j["last_status"] == "ok")
        err = sum(1 for j in jobs if j["enabled"] and j["last_status"] == "error")

        # Heartbeat configs + recent sessions
        hb_configs = load_heartbeat_configs()
        heartbeats = []
        for hb in hb_configs:
            sessions = list_sessions(agent_id=hb["agent_id"], last_n=5, session_type="heartbeat")
            recent = [{"session_id": s["session_id"],
                       "modified": s.get("modified", "").isoformat() if hasattr(s.get("modified", ""), "isoformat") else "",
                       "tokens": s.get("tokens", 0), "cost": round(s.get("cost", 0), 6),
                       "turns": s.get("turns", 0)} for s in sessions]
            heartbeats.append({**hb, "sessions": recent})

        return jsonify({
            "cron_jobs": jobs,
            "summary": {"total": len(jobs), "enabled": enabled, "ok": ok, "error": err},
            "heartbeats": heartbeats,
        })

    @app.route("/api/agents")
    def api_agents():
        agents = []
        if _sp.AGENTS_DIR.exists():
            for d in sorted(_sp.AGENTS_DIR.iterdir()):
                if d.is_dir():
                    sessions_dir = d / "sessions"
                    count = len(list(sessions_dir.glob("*.jsonl"))) if sessions_dir.exists() else 0
                    agents.append({"id": d.name, "sessions": count})
        return jsonify(agents)

    # --- Lab ---

    @app.route("/lab")
    def lab_page():
        return render_template("coming_soon.html", feature="Lab", active="lab")

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
        except Exception:
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
        if len(message) > 100_000:
            return jsonify({"error": "message too long (max 100KB)"}), 413
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

        # Check if agent is done (last assistant turn has stopReason "stop")
        turns = data.get("turns", [])
        done = False
        if turns:
            last = turns[-1]
            if last.get("role") == "assistant" and last.get("stop_reason") == "stop":
                done = True

        return jsonify({"changed": True, "data": data, "done": done})

    @app.route("/api/lab/stream/<session_id>")
    def api_lab_stream(session_id):
        """SSE stream for real-time session monitoring."""
        file_path = _resolve(session_id)
        if not file_path:
            return jsonify({"error": "session not found"}), 404

        def generate():
            last_size = 0
            last_turn_count = 0
            event_id = 0
            idle_count = 0

            # Initial full load
            try:
                analysis = parse_session(file_path, recursive_subagents=True)
                data = _serialize_analysis(analysis)
                last_size = file_path.stat().st_size
                last_turn_count = len(data.get("turns", []))
                event_id += 1
                yield f"id: {event_id}\nevent: init\ndata: {json.dumps(data)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                return

            # Change detection loop
            while True:
                time.sleep(0.5)

                try:
                    current_size = file_path.stat().st_size
                except OSError:
                    idle_count += 1
                    if idle_count >= 600:  # 5 min timeout
                        yield "event: timeout\ndata: {}\n\n"
                        return
                    if idle_count % 30 == 0:
                        yield ": heartbeat\n\n"
                    continue

                if current_size == last_size:
                    idle_count += 1
                    if idle_count % 30 == 0:
                        yield ": heartbeat\n\n"
                    continue

                # File changed
                idle_count = 0
                last_size = current_size

                try:
                    analysis = parse_session(file_path, recursive_subagents=True)
                    data = _serialize_analysis(analysis)
                    turns = data.get("turns", [])
                    new_count = len(turns)

                    if new_count > last_turn_count:
                        # Delta: new turns only
                        delta = {
                            "new_turns": turns[last_turn_count:],
                            "total_turns": new_count,
                            "compaction_events": data.get("compaction_events", []),
                        }
                        last_turn_count = new_count
                        event_id += 1
                        yield f"id: {event_id}\nevent: update\ndata: {json.dumps(delta)}\n\n"

                        # Check agent completion
                        last_turn = turns[-1]
                        if last_turn.get("stop_reason") == "stop":
                            yield "event: done\ndata: {}\n\n"
                            return

                    elif new_count == last_turn_count and turns:
                        # Same turn count but file changed — patch last turn
                        event_id += 1
                        yield f"id: {event_id}\nevent: patch\ndata: {json.dumps({'index': turns[-1]['index'], 'turn': turns[-1]})}\n\n"

                        if turns[-1].get("stop_reason") == "stop":
                            yield "event: done\ndata: {}\n\n"
                            return

                except Exception as e:
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return Response(
            stream_with_context(generate()),
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.route("/api/lab/context")
    def api_lab_context():
        workspace = _get_workspace_dir()
        files = []
        for name in WORKSPACE_FILES:
            fp = workspace / name
            if fp.exists():
                try:
                    content = fp.read_text(encoding="utf-8")
                    backup = fp.with_suffix(fp.suffix + ".lab-backup")
                    files.append({
                        "name": name,
                        "size": len(content),
                        "content": content,
                        "has_backup": backup.exists(),
                    })
                except Exception:
                    files.append({"name": name, "size": 0, "content": "", "error": "read failed"})
        return jsonify(files)

    @app.route("/api/lab/context/<filename>/diff")
    def api_lab_context_diff(filename):
        if filename not in WORKSPACE_FILES:
            return jsonify({"error": "not allowed"}), 400
        workspace = _get_workspace_dir()
        fp = workspace / filename
        backup = fp.with_suffix(fp.suffix + ".lab-backup")
        if not backup.exists():
            return jsonify({"diff": "", "has_backup": False})
        import difflib
        old_lines = backup.read_text(encoding="utf-8").splitlines(keepends=True)
        new_lines = fp.read_text(encoding="utf-8").splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"{filename} (original)",
            tofile=f"{filename} (current)",
            n=3,
        ))
        return jsonify({"diff": "".join(diff), "has_backup": True})

    @app.route("/api/lab/context/<filename>/reset", methods=["POST"])
    def api_lab_context_reset(filename):
        if filename not in WORKSPACE_FILES:
            return jsonify({"error": "not allowed"}), 400
        workspace = _get_workspace_dir()
        fp = workspace / filename
        backup = fp.with_suffix(fp.suffix + ".lab-backup")
        if not backup.exists():
            return jsonify({"error": "no backup"}), 404
        shutil.copy2(backup, fp)
        _log_lab("context_reset", file=filename)
        return jsonify({"ok": True})

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
        with _lab_log_lock:
            return jsonify(list(reversed(_lab_activity_log)))

    # --- Settings ---

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        from clawtracerx import config
        cfg = config.load()
        cfg["effective_openclaw_dir"] = str(_sp.OPENCLAW_DIR)
        cfg["effective_agents_dir"] = str(_sp.AGENTS_DIR)
        return jsonify(cfg)

    @app.route("/api/settings", methods=["POST"])
    def api_settings_save():
        from clawtracerx import config
        data = request.get_json(force=True)
        cfg = config.load()
        if "openclaw_dir" in data:
            new_dir = data["openclaw_dir"].strip()
            if new_dir and not Path(new_dir).is_dir():
                return jsonify({"ok": False, "error": f"Directory not found: {new_dir}"}), 400
            cfg["openclaw_dir"] = new_dir
        config.save(cfg)
        return jsonify({"ok": True, "restart_required": True})

    @app.route("/api/openclaw-config")
    def api_openclaw_config():
        config_path = gateway.OPENCLAW_CONFIG
        try:
            with open(config_path) as f:
                data = json.load(f)
            masked = _mask_sensitive(data)
            return jsonify({"ok": True, "path": str(config_path), "config": masked})
        except FileNotFoundError:
            return jsonify({"ok": False, "error": "not found", "path": str(config_path)})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e), "path": str(config_path)})

    @app.route("/api/session/<session_id>/tc/<tc_id>/full")
    def api_tc_full(session_id, tc_id):
        file_path = _resolve(session_id)
        if not file_path:
            abort(404, "Session not found")
        analysis = parse_session(file_path)
        for turn in analysis.turns:
            for tc in turn.tool_calls:
                if tc.id == tc_id:
                    return jsonify({
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "result_text": tc.result_text,
                        "result_size": tc.result_size,
                    })
        abort(404, "Tool call not found")

    @app.route("/api/session/<session_id>/turn/<int:idx>/user-text")
    def api_turn_user_text(session_id, idx):
        file_path = _resolve(session_id)
        if not file_path:
            abort(404, "Session not found")
        analysis = parse_session(file_path)
        for turn in analysis.turns:
            if turn.index == idx:
                return jsonify({"content": turn.user_text})
        abort(404, "Turn not found")

    # --- Health ---

    _health_cache = {"data": None, "ts": 0}

    @app.route("/api/health")
    def api_health():
        now = time.time()
        if _health_cache["data"] and (now - _health_cache["ts"]) < 30:
            return jsonify(_health_cache["data"])

        checks = {}

        # 1. Config file
        try:
            gateway.load_gateway_config()
            checks["config"] = {"ok": True, "path": str(gateway.OPENCLAW_CONFIG)}
        except FileNotFoundError:
            checks["config"] = {"ok": False, "error": "not found", "path": str(gateway.OPENCLAW_CONFIG)}
        except Exception as e:
            checks["config"] = {"ok": False, "error": str(e)}

        # 2. Device identity
        identity_path = gateway.DEVICE_IDENTITY_FILE
        if identity_path.exists():
            try:
                with open(identity_path) as f:
                    did = json.load(f).get("deviceId", "?")
                checks["device"] = {"ok": True, "device_id": did[:12]}
            except Exception as e:
                checks["device"] = {"ok": False, "error": str(e)}
        else:
            checks["device"] = {"ok": False, "error": "not found"}

        # 3. Agents directory
        agents_dir = _sp.AGENTS_DIR
        if agents_dir.exists():
            agent_count = sum(1 for d in agents_dir.iterdir() if d.is_dir())
            session_count = sum(
                len(list((d / "sessions").glob("*.jsonl")))
                for d in agents_dir.iterdir()
                if d.is_dir() and (d / "sessions").exists()
            )
            checks["agents"] = {"ok": True, "agents": agent_count, "sessions": session_count}
        else:
            checks["agents"] = {"ok": False, "error": "dir not found"}

        # 4. Gateway connection (lightweight RPC to test connectivity + auth)
        try:
            result = gateway.list_agents()
            checks["gateway"] = {"ok": True, "agents": len(result) if isinstance(result, list) else 0}
        except Exception as e:
            checks["gateway"] = {"ok": False, "error": str(e)[:100]}

        # 5. Workspace
        workspace = _get_workspace_dir()
        checks["workspace"] = {
            "ok": workspace.exists(),
            "path": str(workspace),
        }

        health = {
            "timestamp": datetime.now(KST).isoformat(),
            "openclaw_dir": str(_sp.OPENCLAW_DIR),
            "checks": checks,
        }
        _health_cache["data"] = health
        _health_cache["ts"] = now
        return jsonify(health)

    return app


# --- Lab helpers ---

WORKSPACE_FILES = [
    "AGENTS.md", "SOUL.md", "TOOLS.md", "IDENTITY.md",
    "USER.md", "HEARTBEAT.md", "BOOTSTRAP.md", "MEMORY.md",
    "TODO.md", "MIGRATION.md",
]


def _get_workspace_dir() -> Path:
    """Get workspace directory from openclaw.json config."""
    config_path = gateway.OPENCLAW_CONFIG
    try:
        with open(config_path) as f:
            full_cfg = json.load(f)
        workspace = full_cfg.get("agents", {}).get("defaults", {}).get("workspace", "")
        if workspace:
            return Path(workspace)
    except Exception:
        pass
    return _sp.OPENCLAW_DIR / "workspace"


def _backup_context_file(filepath: Path):
    """Create .lab-backup before first modification."""
    backup = filepath.with_suffix(filepath.suffix + ".lab-backup")
    if filepath.exists() and not backup.exists():
        try:
            shutil.copy2(filepath, backup)
        except OSError as e:
            logging.warning("Failed to create backup for %s: %s", filepath, e)


# --- Helpers ---

_SENSITIVE_KEYS = re.compile(r'key|secret|token|password', re.IGNORECASE)


def _mask_sensitive(obj):
    """Recursively mask sensitive values in config dicts."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "env" and isinstance(v, dict):
                out[k] = {ek: "***" for ek in v}
            elif _SENSITIVE_KEYS.search(k) and isinstance(v, str):
                out[k] = "***"
            else:
                out[k] = _mask_sensitive(v)
        return out
    if isinstance(obj, list):
        return [_mask_sensitive(x) for x in obj]
    return obj


def _resolve(session_id: str):
    """Resolve session ID to file path.

    Searches for both active .jsonl files and soft-deleted
    .jsonl.deleted.{timestamp} files.
    """
    for agent_dir in _sp.AGENTS_DIR.iterdir():
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
        "file_path": analysis.file_path,
        "channel": analysis.channel,
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
        "thinking_blocks": [b[:2000] if b else None for b in turn.thinking_blocks],
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
        "workflow_group_id": turn.workflow_group_id,
        "channel_meta": {
            **turn.channel_meta,
            "actual_text": _truncate(turn.channel_meta.get("actual_text", ""), 500),
        } if turn.channel_meta else None,
    }


def _serialize_tc(tc):
    args = {}
    truncated: dict = {}
    for k, v in tc.arguments.items():
        if isinstance(v, str) and len(v) > 300:
            args[k] = v[:300] + "..."
            truncated[k] = len(v)
        else:
            args[k] = v
    result = {
        "id": tc.id,
        "name": tc.name,
        "arguments": args,
        "result_text": tc.result_text[:500],
        "result_size": tc.result_size,
        "duration_ms": tc.duration_ms,
        "is_error": tc.is_error,
        "status": tc.status,
        "round_idx": tc.round_idx,
    }
    if truncated:
        result["arguments_truncated"] = truncated
    return result


def _serialize_spawn(spawn):
    # Use real session ID from announce if available (key UUID != file UUID)
    real_sid = spawn.child_session_id
    if spawn.announce_stats and spawn.announce_stats.get("session_id"):
        real_sid = spawn.announce_stats["session_id"]
    return {
        "run_id": spawn.run_id,
        "label": spawn.label,
        "task": spawn.task[:500],
        "child_session_key": spawn.child_session_key,
        "child_session_id": real_sid,
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
        edges.append({"source": root_id, "target": turn_id, "type": "contains"})

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
            edges.append({"source": turn_id, "target": tc_id, "type": "calls"})

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
    edges.append({"source": parent_id, "target": spawn_id, "type": "spawns"})

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
            edges.append({"source": spawn_id, "target": tc_id, "type": "calls"})

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


def _build_turn_flow(turn):
    """Build sequential execution flow for a single turn."""
    steps = []
    spawn_idx = 0

    for tc in turn.tool_calls:
        if tc.name == "sessions_spawn":
            if spawn_idx < len(turn.subagent_spawns):
                spawn = turn.subagent_spawns[spawn_idx]
                spawn_idx += 1
                steps.append({
                    "type": "subagent",
                    "label": spawn.label or "subagent",
                    "task": _truncate(spawn.task, 120),
                    "status": spawn.outcome,
                    "cost": round(spawn.cost_usd, 4) if spawn.cost_usd else None,
                    "tokens": spawn.total_tokens,
                    "duration_ms": spawn.duration_ms,
                    "child_session_id": spawn.child_session_id,
                    "child_steps": _build_subagent_steps(spawn),
                })
        else:
            steps.append({
                "type": "tool",
                "id": tc.id,
                "name": tc.name,
                "summary": _tool_summary(tc),
                "duration_ms": tc.duration_ms,
                "status": "error" if tc.is_error else "ok",
            })

    return {
        "user_msg": _truncate(turn.user_text, 300),
        "user_source": turn.user_source,
        "assistant_msg": _truncate(turn.assistant_texts[-1] if turn.assistant_texts else "", 300),
        "cost": round(turn.cost.get("total", 0), 4),
        "tokens": turn.usage.get("totalTokens", 0),
        "duration_ms": turn.duration_ms,
        "model": turn.model,
        "steps": steps,
    }


def _build_subagent_steps(spawn):
    """Recursively build tool steps from a subagent spawn's child turns."""
    steps = []
    for child_turn in spawn.child_turns:
        sub_spawn_idx = 0
        for tc in child_turn.tool_calls:
            if tc.name == "sessions_spawn":
                if sub_spawn_idx < len(child_turn.subagent_spawns):
                    nested = child_turn.subagent_spawns[sub_spawn_idx]
                    sub_spawn_idx += 1
                    steps.append({
                        "type": "subagent",
                        "label": nested.label or "subagent",
                        "task": _truncate(nested.task, 80),
                        "status": nested.outcome,
                        "cost": round(nested.cost_usd, 4) if nested.cost_usd else None,
                        "duration_ms": nested.duration_ms,
                        "child_session_id": nested.child_session_id,
                        "child_steps": _build_subagent_steps(nested),
                    })
            else:
                steps.append({
                    "type": "tool",
                    "id": tc.id,
                    "name": tc.name,
                    "summary": _tool_summary(tc),
                    "duration_ms": tc.duration_ms,
                    "status": "error" if tc.is_error else "ok",
                })
    return steps
