"""
Tests for clawtracerx.session_parser — pure functions and I/O.
"""
from __future__ import annotations

import json
from datetime import datetime

import clawtracerx.session_parser as sp

# ---------------------------------------------------------------------------
# Tier 1: Pure functions
# ---------------------------------------------------------------------------

class TestTsToDt:
    def test_ms_int(self):
        dt = sp._ts_to_dt(1_700_000_000_000)
        assert isinstance(dt, datetime)
        assert dt.year == 2023

    def test_iso_string(self):
        dt = sp._ts_to_dt("2024-01-15T12:00:00Z")
        assert isinstance(dt, datetime)
        assert dt.year == 2024

    def test_none_returns_none(self):
        assert sp._ts_to_dt(None) is None

    def test_invalid_string_returns_none(self):
        assert sp._ts_to_dt("not-a-date") is None

    def test_float_epoch(self):
        dt = sp._ts_to_dt(1_700_000_000_000.5)
        assert isinstance(dt, datetime)


class TestTruncate:
    def test_short_string_unchanged(self):
        assert sp._truncate("hello", 100) == "hello"

    def test_long_string_truncated(self):
        result = sp._truncate("x" * 300, 200)
        assert result.endswith("...")
        assert len(result) == 203  # 200 chars + "..."

    def test_empty_string(self):
        assert sp._truncate("", 100) == ""

    def test_exact_boundary(self):
        s = "a" * 200
        assert sp._truncate(s, 200) == s


class TestDetectSource:
    def test_cron_prefix(self):
        assert sp._detect_source("[cron:abc123 My Job]") == "cron"

    def test_heartbeat_prefix(self):
        assert sp._detect_source("[heartbeat:check]") == "heartbeat"

    def test_system_message_subagent(self):
        assert sp._detect_source("[System Message] A subagent task just completed") == "subagent_announce"

    def test_system_message_cron(self):
        assert sp._detect_source("[System Message] A cron job ran") == "cron_announce"

    def test_system_message_generic(self):
        assert sp._detect_source("[System Message] Something happened") == "system"

    def test_heartbeat_read(self):
        assert sp._detect_source("Read HEARTBEAT.md and check status") == "heartbeat"

    def test_chat_default(self):
        assert sp._detect_source("Hello how are you?") == "chat"

    def test_empty_is_chat(self):
        assert sp._detect_source("") == "chat"

    def test_timestamped_subagent_announce(self):
        txt = "[Mon 2026-02-23 10:00 KST] A subagent task \"worker\" completed"
        assert sp._detect_source(txt) == "subagent_announce"

    def test_timestamped_cron_announce(self):
        txt = "[Tue 2026-01-01 00:00 KST] A cron job finished"
        assert sp._detect_source(txt) == "cron_announce"


class TestExtractSessionIdFromKey:
    def test_valid_key(self):
        key = "agent:main:subagent:de0b2c55-1234-5678-abcd-ef0123456789"
        result = sp._extract_session_id_from_key(key)
        assert result == "de0b2c55-1234-5678-abcd-ef0123456789"

    def test_short_key_returns_none(self):
        assert sp._extract_session_id_from_key("agent:main") is None

    def test_empty_key_returns_none(self):
        assert sp._extract_session_id_from_key("") is None


class TestParseTokenStr:
    def test_plain_int(self):
        assert sp._parse_token_str("500") == 500

    def test_k_suffix(self):
        assert sp._parse_token_str("12.5K") == 12_500

    def test_m_suffix(self):
        assert sp._parse_token_str("1.5M") == 1_500_000

    def test_lowercase_k(self):
        assert sp._parse_token_str("3k") == 3_000


class TestParseRuntimeStr:
    def test_minutes_and_seconds(self):
        assert sp._parse_runtime_str("1m25s") == 85_000

    def test_seconds_only(self):
        assert sp._parse_runtime_str("45s") == 45_000

    def test_empty_string(self):
        assert sp._parse_runtime_str("") == 0


class TestParseSessionContext:
    def test_basic_context(self):
        report = {
            "workspaceDir": "/home/user/workspace",
            "bootstrapMaxChars": 50000,
            "systemPrompt": {"chars": 1000, "projectContextChars": 500, "nonProjectContextChars": 200},
            "sandbox": {"mode": "strict"},
            "injectedWorkspaceFiles": [],
            "skills": {"entries": [{"name": "my-skill", "blockChars": 300}]},
            "tools": {"entries": [{"name": "read", "summaryChars": 100, "schemaChars": 200}]},
        }
        ctx = sp._parse_session_context(report)
        assert ctx.workspace_dir == "/home/user/workspace"
        assert ctx.bootstrap_max_chars == 50000
        assert ctx.system_prompt_chars == 1000
        assert ctx.sandbox_mode == "strict"
        assert len(ctx.skills) == 1
        assert ctx.skills[0].name == "my-skill"
        assert len(ctx.tools) == 1
        assert ctx.tools[0].name == "read"

    def test_empty_report(self):
        ctx = sp._parse_session_context({})
        assert ctx.system_prompt_chars == 0
        assert ctx.injected_files == []


# ---------------------------------------------------------------------------
# Tier 2: I/O tests (use tmp_path via fixtures)
# ---------------------------------------------------------------------------

class TestParseSession:
    def test_minimal_session(self, minimal_session_path):
        analysis = sp.parse_session(minimal_session_path, recursive_subagents=False)
        assert analysis.session_id.startswith("aabbccdd")
        assert analysis.agent_id == "test-agent"
        assert analysis.model == "claude-test"
        assert len(analysis.turns) == 1
        turn = analysis.turns[0]
        assert "Hello" in turn.user_text
        assert turn.usage["totalTokens"] == 120
        assert abs(analysis.total_cost - 0.0004) < 1e-9

    def test_session_type_chat(self, minimal_session_path):
        analysis = sp.parse_session(minimal_session_path, recursive_subagents=False)
        assert analysis.session_type == "chat"

    def test_cron_session_type(self, tmp_path):
        sessions_dir = tmp_path / "agents" / "main" / "sessions"
        sessions_dir.mkdir(parents=True)
        sid = "cron0000-0000-0000-0000-000000000001"
        f = sessions_dir / f"{sid}.jsonl"
        lines = [
            {"type": "session", "timestamp": 1740000000000, "cwd": "/tmp"},
            {"type": "model_change", "modelId": "test-model", "provider": "test"},
            {"type": "message", "id": "u1", "message": {
                "role": "user", "timestamp": 1740000001000,
                "content": [{"type": "text", "text": "[cron:abc Task Name]"}],
            }},
            {"type": "message", "id": "a1", "parentId": "u1", "message": {
                "role": "assistant", "timestamp": 1740000005000,
                "model": "test-model", "provider": "test", "stopReason": "stop",
                "content": [{"type": "text", "text": "Done."}],
                "usage": {"input": 10, "output": 5, "cacheRead": 0, "cacheWrite": 0,
                           "totalTokens": 15, "cost": {"total": 0.0001}},
            }},
        ]
        f.write_text("\n".join(json.dumps(line) for line in lines))
        analysis = sp.parse_session(f, recursive_subagents=False)
        assert analysis.session_type == "cron"


class TestListSessions:
    def test_returns_sessions(self, mock_openclaw_dir, minimal_session_path):
        sessions = sp.list_sessions(last_n=10)
        assert len(sessions) >= 1
        s = sessions[0]
        assert "session_id" in s
        assert "agent_id" in s
        assert s["agent_id"] == "test-agent"

    def test_filter_by_agent(self, mock_openclaw_dir, minimal_session_path):
        sessions = sp.list_sessions(agent_id="test-agent", last_n=10)
        assert len(sessions) >= 1

    def test_empty_dir(self, tmp_path, monkeypatch):
        import clawtracerx.session_parser as sp2
        monkeypatch.setattr(sp2, "AGENTS_DIR", tmp_path / "nonexistent")
        sessions = sp2.list_sessions(last_n=10)
        assert sessions == []
