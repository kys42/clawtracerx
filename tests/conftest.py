"""
Shared fixtures for ClawTracerX tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def minimal_session_path(tmp_path):
    """Copy minimal_session.jsonl to a proper agents/ directory tree."""
    session_id = "aabbccdd-0000-0000-0000-000000000001"
    sessions_dir = tmp_path / "agents" / "test-agent" / "sessions"
    sessions_dir.mkdir(parents=True)
    target = sessions_dir / f"{session_id}.jsonl"
    target.write_text((FIXTURES_DIR / "minimal_session.jsonl").read_text())
    return target


@pytest.fixture()
def mock_openclaw_dir(tmp_path, monkeypatch, minimal_session_path):
    """Patch session_parser module-level path constants to use tmp_path."""
    import clawtracerx.session_parser as sp

    agents_dir = tmp_path / "agents"
    openclaw_dir = tmp_path
    subagents_file = tmp_path / "subagents" / "runs.json"

    monkeypatch.setattr(sp, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(sp, "OPENCLAW_DIR", openclaw_dir)
    monkeypatch.setattr(sp, "SUBAGENTS_FILE", subagents_file)
    monkeypatch.setattr(sp, "CRON_JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr(sp, "CRON_RUNS_DIR", tmp_path / "cron" / "runs")
    # Reset the in-memory subagent cache so patched path takes effect
    monkeypatch.setattr(sp, "_subagent_cache", None)
    return tmp_path


@pytest.fixture()
def flask_client(mock_openclaw_dir):
    """Return a Flask test client for the web app."""
    from clawtracerx.web import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Cron fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def cron_dir(mock_openclaw_dir):
    """Create cron jobs.json and a run log JSONL under tmp_path."""
    cron_base = mock_openclaw_dir / "cron"
    cron_base.mkdir(parents=True, exist_ok=True)
    runs_dir = cron_base / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    jobs = [
        {"id": "job-abc", "name": "Daily Cleanup", "label": "Daily Cleanup",
         "agentId": "test-agent", "enabled": True,
         "schedule": {"expr": "0 9 * * *", "tz": "Asia/Seoul"},
         "wakeMode": "new", "state": {"lastStatus": "ok"},
         "payload": {"message": "run cleanup"}},
    ]
    (cron_base / "jobs.json").write_text(json.dumps(jobs))

    run_lines = [
        json.dumps({"action": "started", "ts": 1740000000000}),
        json.dumps({
            "action": "finished", "ts": 1740000010000,
            "status": "ok", "summary": "Cleaned 5 items",
            "sessionId": "cron-sess-001", "sessionKey": "agent:test-agent:cron:abc",
            "durationMs": 10000,
        }),
        json.dumps({
            "action": "finished", "ts": 1740000020000,
            "status": "error", "error": "timeout after 60s",
            "sessionId": "cron-sess-002", "sessionKey": "agent:test-agent:cron:abc",
            "durationMs": 60000,
        }),
    ]
    (runs_dir / "job-abc.jsonl").write_text("\n".join(run_lines))

    return cron_base


# ---------------------------------------------------------------------------
# sessions.json fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def sessions_json(mock_openclaw_dir):
    """Create a sessions.json metadata file for test-agent."""
    sessions_dir = mock_openclaw_dir / "agents" / "test-agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "agent:test-agent:chat:aabbccdd-key": {
            "sessionId": "aabbccdd-0000-0000-0000-000000000001",
            "contextTokens": 5000,
            "inputTokens": 3000,
            "outputTokens": 2000,
            "totalTokens": 5000,
            "compactionCount": 1,
        }
    }
    (sessions_dir / "sessions.json").write_text(json.dumps(meta))
    return meta


# ---------------------------------------------------------------------------
# Session with special content
# ---------------------------------------------------------------------------

def _write_session(sessions_dir, session_id, extra_lines):
    """Helper to write a session JSONL with standard header + extra lines."""
    base = [
        {"type": "session", "timestamp": 1740000000000, "cwd": "/tmp"},
        {"type": "model_change", "modelId": "claude-test", "provider": "anthropic"},
    ]
    f = sessions_dir / f"{session_id}.jsonl"
    f.write_text("\n".join(json.dumps(entry) for entry in base + extra_lines))
    return f


@pytest.fixture()
def empty_session_path(tmp_path):
    """Session with header only (no messages)."""
    sessions_dir = tmp_path / "agents" / "empty-agent" / "sessions"
    sessions_dir.mkdir(parents=True)
    return _write_session(sessions_dir, "empty0000-0000-0000-0000-000000000001", [])


@pytest.fixture()
def session_with_compaction(tmp_path):
    """Session containing a compaction event."""
    sessions_dir = tmp_path / "agents" / "test-agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sid = "compact0-0000-0000-0000-000000000001"
    extra = [
        {"type": "message", "id": "u1", "message": {
            "role": "user", "timestamp": 1740000001000,
            "content": [{"type": "text", "text": "Hello"}],
        }},
        {"type": "compaction", "timestamp": 1740000003000,
         "firstKeptEntryId": "u1", "tokensBefore": 10000,
         "tokensAfter": 2000, "summary": "Summarized earlier context",
         "fromHook": False},
        {"type": "message", "id": "a1", "parentId": "u1", "message": {
            "role": "assistant", "timestamp": 1740000005000,
            "model": "claude-test", "provider": "anthropic", "stopReason": "stop",
            "content": [{"type": "text", "text": "Done."}],
            "usage": {"input": 50, "output": 10, "cacheRead": 0, "cacheWrite": 0,
                       "totalTokens": 60, "cost": {"total": 0.0001}},
        }},
    ]
    return _write_session(sessions_dir, sid, extra)


@pytest.fixture()
def session_with_thinking(tmp_path):
    """Session where assistant has thinking blocks."""
    sessions_dir = tmp_path / "agents" / "test-agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sid = "think000-0000-0000-0000-000000000001"
    extra = [
        {"type": "message", "id": "u1", "message": {
            "role": "user", "timestamp": 1740000001000,
            "content": [{"type": "text", "text": "Explain quantum physics"}],
        }},
        {"type": "message", "id": "a1", "parentId": "u1", "message": {
            "role": "assistant", "timestamp": 1740000005000,
            "model": "claude-test", "provider": "anthropic", "stopReason": "stop",
            "content": [
                {"type": "thinking", "thinking": "Let me think about quantum physics..."},
                {"type": "text", "text": "Quantum physics studies subatomic particles."},
            ],
            "usage": {"input": 80, "output": 30, "cacheRead": 0, "cacheWrite": 0,
                       "totalTokens": 110, "cost": {"total": 0.0003}},
        }},
    ]
    return _write_session(sessions_dir, sid, extra)


@pytest.fixture()
def session_with_malformed(tmp_path):
    """Session with malformed JSONL lines mixed in."""
    sessions_dir = tmp_path / "agents" / "test-agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sid = "malfor00-0000-0000-0000-000000000001"
    f = sessions_dir / f"{sid}.jsonl"
    lines = [
        json.dumps({"type": "session", "timestamp": 1740000000000, "cwd": "/tmp"}),
        "THIS IS NOT JSON {{{",
        "",
        json.dumps({"type": "model_change", "modelId": "claude-test", "provider": "anthropic"}),
        "{broken json",
        json.dumps({"type": "message", "id": "u1", "message": {
            "role": "user", "timestamp": 1740000001000,
            "content": [{"type": "text", "text": "Hi"}],
        }}),
        json.dumps({"type": "message", "id": "a1", "parentId": "u1", "message": {
            "role": "assistant", "timestamp": 1740000005000,
            "model": "claude-test", "provider": "anthropic", "stopReason": "stop",
            "content": [{"type": "text", "text": "Hello!"}],
            "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                       "totalTokens": 15, "cost": {"total": 0.00005}},
        }}),
    ]
    f.write_text("\n".join(lines))
    return f
