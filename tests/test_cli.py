"""
Tests for clawtracerx.cli — formatting helpers and CLI commands.
"""
from __future__ import annotations

from clawtracerx.cli import (
    _fmt_cost,
    _fmt_duration,
    _fmt_size,
    _fmt_tokens,
    _icon,
    cmd_context,
    cmd_cost,
    cmd_crons,
    cmd_raw,
    cmd_sessions,
    cmd_subagents,
)


class TestFmtDuration:
    def test_none(self):
        assert _fmt_duration(None) == ""

    def test_milliseconds(self):
        assert _fmt_duration(500) == "500ms"

    def test_seconds(self):
        result = _fmt_duration(5000)
        assert "s" in result
        assert "5.0" in result

    def test_minutes(self):
        result = _fmt_duration(90000)  # 1m 30s
        assert "1m" in result
        assert "30" in result

    def test_zero(self):
        assert _fmt_duration(0) == "0ms"

    def test_just_under_minute(self):
        result = _fmt_duration(59999)
        assert "s" in result
        assert "m" not in result


class TestFmtCost:
    def test_zero(self):
        assert _fmt_cost(0) == "$0"

    def test_negative(self):
        assert _fmt_cost(-1) == "$0"

    def test_very_small(self):
        result = _fmt_cost(0.0000001)
        assert result.startswith("$0.0000")

    def test_small(self):
        result = _fmt_cost(0.005)
        assert result.startswith("$0.0050")

    def test_normal(self):
        result = _fmt_cost(1.23456)
        assert result == "$1.235"


class TestFmtTokens:
    def test_small(self):
        assert _fmt_tokens(500) == "500"

    def test_thousands(self):
        assert "K" in _fmt_tokens(5000)

    def test_millions(self):
        assert "M" in _fmt_tokens(1_500_000)

    def test_zero(self):
        assert _fmt_tokens(0) == "0"


class TestFmtSize:
    def test_bytes(self):
        assert _fmt_size(500) == "500B"

    def test_kilobytes(self):
        assert "KB" in _fmt_size(2048)

    def test_megabytes(self):
        assert "MB" in _fmt_size(2 * 1024 * 1024)


class TestIcon:
    def test_known_tool(self):
        assert _icon("read") == "📁"

    def test_exec_tool(self):
        assert _icon("exec") == "💻"

    def test_spawn_tool(self):
        assert _icon("sessions_spawn") == "🔀"

    def test_unknown_returns_wrench(self):
        assert _icon("some_unknown_tool_xyz") == "🔧"


# ---------------------------------------------------------------------------
# CLI command output tests
# ---------------------------------------------------------------------------

class TestCmdSessions:
    def test_shows_sessions(self, capsys, mock_openclaw_dir):
        cmd_sessions()
        captured = capsys.readouterr()
        assert "test-agent" in captured.out
        assert "aabbccdd" in captured.out

    def test_no_sessions(self, capsys, tmp_path, monkeypatch):
        import clawtracerx.session_parser as sp
        monkeypatch.setattr(sp, "AGENTS_DIR", tmp_path / "nonexistent")
        cmd_sessions()
        captured = capsys.readouterr()
        assert "No sessions" in captured.out

    def test_filter_by_agent(self, capsys, mock_openclaw_dir):
        cmd_sessions(agent="test-agent")
        captured = capsys.readouterr()
        assert "test-agent" in captured.out

    def test_filter_nonexistent_agent(self, capsys, mock_openclaw_dir):
        cmd_sessions(agent="no-such-agent")
        captured = capsys.readouterr()
        assert "No sessions" in captured.out


class TestCmdCost:
    def test_cost_all(self, capsys, mock_openclaw_dir):
        cmd_cost(period="all")
        captured = capsys.readouterr()
        # Should show cost output (may be $0 or have data)
        assert "$" in captured.out or "No sessions" in captured.out

    def test_cost_today(self, capsys, mock_openclaw_dir):
        cmd_cost(period="today")
        captured = capsys.readouterr()
        # Should not crash — output may be empty if session is old
        assert captured.out is not None


class TestCmdCrons:
    def test_no_cron_runs(self, capsys, mock_openclaw_dir):
        cmd_crons()
        captured = capsys.readouterr()
        assert "No cron runs" in captured.out

    def test_cron_runs_with_data(self, capsys, cron_dir, mock_openclaw_dir):
        cmd_crons()
        captured = capsys.readouterr()
        assert "Daily Cleanup" in captured.out

    def test_cron_filter_by_job(self, capsys, cron_dir, mock_openclaw_dir):
        cmd_crons(job="job-abc")
        captured = capsys.readouterr()
        assert "Daily Cleanup" in captured.out


class TestCmdRaw:
    def test_raw_valid_turn(self, capsys, mock_openclaw_dir, minimal_session_path):
        cmd_raw(str(minimal_session_path), 0)
        captured = capsys.readouterr()
        assert "Raw JSONL" in captured.out

    def test_raw_nonexistent_session(self, capsys, mock_openclaw_dir, monkeypatch):
        import clawtracerx.cli as _cli
        monkeypatch.setattr(_cli, "AGENTS_DIR", mock_openclaw_dir / "agents")
        cmd_raw("00000000-nope", 0)
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_raw_out_of_range_turn(self, capsys, mock_openclaw_dir, minimal_session_path):
        cmd_raw(str(minimal_session_path), 999)
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()


class TestCmdSubagents:
    def test_no_subagents(self, capsys, mock_openclaw_dir):
        cmd_subagents()
        captured = capsys.readouterr()
        assert "No subagent" in captured.out


class TestCmdContext:
    def test_context_valid_session(self, capsys, mock_openclaw_dir, minimal_session_path):
        cmd_context(str(minimal_session_path))
        captured = capsys.readouterr()
        assert "Context" in captured.out or "context" in captured.out.lower()

    def test_context_nonexistent_session(self, capsys, mock_openclaw_dir, monkeypatch):
        import clawtracerx.cli as _cli
        monkeypatch.setattr(_cli, "AGENTS_DIR", mock_openclaw_dir / "agents")
        cmd_context("00000000-nope")
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()

    def test_context_with_sessions_json(self, capsys, sessions_json, mock_openclaw_dir, minimal_session_path):
        cmd_context(str(minimal_session_path))
        captured = capsys.readouterr()
        assert "Context" in captured.out or "aabbccdd" in captured.out
