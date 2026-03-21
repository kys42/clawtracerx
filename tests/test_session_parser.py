"""
Tests for clawtracerx.session_parser — pure functions and I/O.
"""
from __future__ import annotations

import json
from collections import OrderedDict
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

    def test_invalid_string_returns_zero(self):
        assert sp._parse_token_str("not_a_number") == 0

    def test_empty_suffix_returns_zero(self):
        assert sp._parse_token_str("k") == 0

    def test_empty_string_returns_zero(self):
        assert sp._parse_token_str("") == 0


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

    def test_empty_session(self, empty_session_path):
        analysis = sp.parse_session(empty_session_path, recursive_subagents=False)
        assert analysis.turns == []
        assert analysis.total_cost == 0.0
        assert analysis.total_tokens == 0

    def test_malformed_lines_skipped(self, session_with_malformed):
        analysis = sp.parse_session(session_with_malformed, recursive_subagents=False)
        assert len(analysis.turns) == 1
        assert "Hi" in analysis.turns[0].user_text

    def test_compaction_parsed(self, session_with_compaction):
        analysis = sp.parse_session(session_with_compaction, recursive_subagents=False)
        assert analysis.compactions == 1
        assert len(analysis.compaction_events) == 1
        evt = analysis.compaction_events[0]
        assert evt.tokens_before == 10000
        assert evt.tokens_after == 2000
        assert "Summarized" in evt.summary

    def test_thinking_extracted(self, session_with_thinking):
        analysis = sp.parse_session(session_with_thinking, recursive_subagents=False)
        assert len(analysis.turns) == 1
        turn = analysis.turns[0]
        assert turn.thinking_text is not None
        assert "quantum physics" in turn.thinking_text


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


# ---------------------------------------------------------------------------
# Tier 3: I/O functions — cron, metadata, raw turn lines
# ---------------------------------------------------------------------------

class TestLoadCronRuns:
    def test_returns_runs(self, cron_dir, mock_openclaw_dir):
        runs = sp.load_cron_runs()
        assert len(runs) == 2
        # sorted by ts desc — error (ts=20000) first
        assert runs[0].status == "error"
        assert runs[1].status == "ok"

    def test_filter_by_job_id(self, cron_dir, mock_openclaw_dir):
        runs = sp.load_cron_runs(job_id="job-abc")
        assert len(runs) == 2
        runs_none = sp.load_cron_runs(job_id="nonexistent-job")
        assert runs_none == []

    def test_last_n_limit(self, cron_dir, mock_openclaw_dir):
        runs = sp.load_cron_runs(last_n=1)
        assert len(runs) == 1

    def test_empty_cron_dir(self, mock_openclaw_dir):
        runs = sp.load_cron_runs()
        assert runs == []

    def test_run_fields(self, cron_dir, mock_openclaw_dir):
        runs = sp.load_cron_runs()
        ok_run = [r for r in runs if r.status == "ok"][0]
        assert ok_run.job_id == "job-abc"
        assert ok_run.job_name == "Daily Cleanup"
        assert ok_run.summary == "Cleaned 5 items"
        assert ok_run.session_id == "cron-sess-001"
        assert ok_run.agent_id == "test-agent"
        assert ok_run.duration_ms == 10000


class TestLoadSessionMetadata:
    def test_returns_metadata(self, sessions_json, mock_openclaw_dir):
        meta = sp.load_session_metadata("test-agent", "aabbccdd")
        assert meta is not None
        assert meta["sessionId"] == "aabbccdd-0000-0000-0000-000000000001"
        assert meta["contextTokens"] == 5000

    def test_returns_none_for_missing_agent(self, sessions_json, mock_openclaw_dir):
        meta = sp.load_session_metadata("nonexistent-agent", "aabbccdd")
        assert meta is None

    def test_returns_none_for_missing_session(self, sessions_json, mock_openclaw_dir):
        meta = sp.load_session_metadata("test-agent", "zzzzzzzz")
        assert meta is None


class TestGetRawTurnLines:
    def test_returns_raw_lines(self, minimal_session_path):
        lines = sp.get_raw_turn_lines(minimal_session_path, 0)
        assert len(lines) > 0
        assert any(isinstance(item, dict) for item in lines)

    def test_invalid_index_returns_empty(self, minimal_session_path):
        assert sp.get_raw_turn_lines(minimal_session_path, 999) == []
        assert sp.get_raw_turn_lines(minimal_session_path, -1) == []


class TestParseCache:
    def test_cache_hit(self, minimal_session_path, monkeypatch):
        monkeypatch.setattr(sp, "_parse_cache", OrderedDict())
        monkeypatch.setattr(sp, "_subagent_cache", None)
        a1 = sp.parse_session(minimal_session_path)
        a2 = sp.parse_session(minimal_session_path)
        # Should return same object (cache hit)
        assert a1 is a2
        assert str(minimal_session_path) in sp._parse_cache

    def test_cache_invalidation_on_mtime_change(self, minimal_session_path, monkeypatch):
        import os
        monkeypatch.setattr(sp, "_parse_cache", OrderedDict())
        monkeypatch.setattr(sp, "_subagent_cache", None)
        a1 = sp.parse_session(minimal_session_path)
        # Touch file to change mtime
        os.utime(minimal_session_path, (0, 0))
        a2 = sp.parse_session(minimal_session_path)
        assert a1 is not a2  # Re-parsed

    def test_cache_lru_eviction(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sp, "_parse_cache", OrderedDict())
        monkeypatch.setattr(sp, "_PARSE_CACHE_MAX", 2)
        monkeypatch.setattr(sp, "_subagent_cache", None)

        # Create 3 minimal sessions
        sessions_dir = tmp_path / "agents" / "test" / "sessions"
        sessions_dir.mkdir(parents=True)
        for i in range(3):
            sid = f"cache{i:04d}0-0000-0000-0000-000000000001"
            f = sessions_dir / f"{sid}.jsonl"
            f.write_text(json.dumps({"type": "session", "timestamp": 1740000000000, "cwd": "/tmp"}) + "\n"
                         + json.dumps({"type": "model_change", "modelId": "claude-test", "provider": "anthropic"}))
            sp.parse_session(f)

        # Only 2 should remain in cache (LRU max = 2)
        assert len(sp._parse_cache) == 2


class TestReadJsonl:
    def test_reads_valid_lines(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a": 1}\n{"b": 2}\n')
        lines = sp._read_jsonl(f)
        assert len(lines) == 2
        assert lines[0] == {"a": 1}

    def test_skips_empty_and_invalid(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"ok": true}\n\nNOT_JSON\n{"ok2": true}\n')
        lines = sp._read_jsonl(f)
        assert len(lines) == 2


class TestExtractMetadata:
    def test_extracts_session_info(self):
        lines = [
            {"type": "session", "timestamp": 1740000000000, "cwd": "/tmp"},
            {"type": "model_change", "modelId": "claude-test", "provider": "anthropic"},
        ]
        analysis = sp.SessionAnalysis(session_id="test", agent_id="test")
        model, provider, api, thinking = sp._extract_metadata(lines, analysis)
        assert model == "claude-test"
        assert provider == "anthropic"
        assert analysis.cwd == "/tmp"
        assert analysis.started_at is not None

    def test_counts_compactions(self):
        lines = [
            {"type": "compaction", "timestamp": 1740000000000,
             "firstKeptEntryId": "u1", "tokensBefore": 10000,
             "tokensAfter": 2000, "summary": "Summarized"},
        ]
        analysis = sp.SessionAnalysis(session_id="test", agent_id="test")
        sp._extract_metadata(lines, analysis)
        assert analysis.compactions == 1
        assert len(analysis.compaction_events) == 1


class TestBuildIdMap:
    def test_builds_map(self):
        lines = [
            {"type": "message", "id": "u1", "message": {"role": "user", "stopReason": ""}},
            {"type": "message", "id": "a1", "message": {"role": "assistant", "stopReason": "stop", "model": "claude"}},
            {"type": "model_change", "modelId": "claude"},  # non-message, should be ignored
        ]
        result = sp._build_id_map(lines)
        assert "u1" in result
        assert "a1" in result
        assert len(result) == 2
        assert result["a1"]["role"] == "assistant"


# ---------------------------------------------------------------------------
# _parse_announce_match
# ---------------------------------------------------------------------------

class TestParseAnnounceMatch:
    def test_basic_stats_extraction(self):
        text = 'Stats: runtime 1m25s • tokens 12.5K (in 8K / out 4.5K)'
        m = sp._ANNOUNCE_RE.search(text)
        assert m is not None
        result = sp._parse_announce_match(m)
        assert result["runtime_ms"] == 85_000
        assert result["total_tokens"] == 12_500
        assert result["input_tokens"] == 8_000
        assert result["output_tokens"] == 4_500

    def test_new_format_session_id(self):
        text = '[sessionId: 9520bb0d-fed2-4b35-abcd-1234567890ab] A subagent task "research" just completed.\nStats: runtime 45s • tokens 3K (in 2K / out 1K)'
        m = sp._ANNOUNCE_RE.search(text)
        assert m is not None
        result = sp._parse_announce_match(m, full_text=text)
        assert result["session_id"] == "9520bb0d-fed2-4b35-abcd-1234567890ab"
        assert result["label"] == "research"

    def test_label_extraction(self):
        text = 'A subagent task "code-review" just completed.\nStats: runtime 2m10s • tokens 50K (in 30K / out 20K)'
        m = sp._ANNOUNCE_RE.search(text)
        result = sp._parse_announce_match(m, full_text=text)
        assert result["label"] == "code-review"
        assert "session_id" not in result

    def test_invalid_groups_returns_none(self):
        """When regex match groups are invalid, should return None."""
        import re
        # Create a fake match with only 1 group (needs 4)
        fake_m = re.search(r"(.*)", "not-a-number")
        result = sp._parse_announce_match(fake_m)
        assert result is None


# ---------------------------------------------------------------------------
# load_subagent_runs edge cases
# ---------------------------------------------------------------------------

class TestLoadSubagentRuns:
    def test_missing_file_returns_empty(self, monkeypatch, tmp_path):
        sp._subagent_cache = None
        monkeypatch.setattr(sp, "SUBAGENTS_FILE", tmp_path / "nonexistent.json")
        result = sp.load_subagent_runs()
        assert result == {}
        sp._subagent_cache = None

    def test_corrupted_json_returns_empty(self, monkeypatch, tmp_path):
        sp._subagent_cache = None
        bad_file = tmp_path / "runs.json"
        bad_file.write_text("{invalid json")
        monkeypatch.setattr(sp, "SUBAGENTS_FILE", bad_file)
        result = sp.load_subagent_runs()
        assert result == {}
        sp._subagent_cache = None

    def test_valid_file_returns_runs(self, monkeypatch, tmp_path):
        sp._subagent_cache = None
        runs_file = tmp_path / "runs.json"
        runs_file.write_text(json.dumps({"runs": {"r1": {"status": "done"}}}))
        monkeypatch.setattr(sp, "SUBAGENTS_FILE", runs_file)
        result = sp.load_subagent_runs()
        assert "r1" in result
        assert result["r1"]["status"] == "done"
        sp._subagent_cache = None


# ---------------------------------------------------------------------------
# _find_child_session_file edge cases
# ---------------------------------------------------------------------------

class TestFindChildSessionFile:
    def test_nonexistent_agents_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sp, "AGENTS_DIR", tmp_path / "nonexistent")
        result = sp.find_subagent_child_session("agent:foo:chat:9520bb0d-fed2-4b35-abcd-1234567890ab")
        assert result is None

    def test_invalid_key_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sp, "AGENTS_DIR", tmp_path)
        result = sp.find_subagent_child_session("short")
        assert result is None
