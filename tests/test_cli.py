"""
Tests for clawtracerx.cli — formatting helpers.
"""
from __future__ import annotations

from clawtracerx.cli import _fmt_cost, _fmt_duration, _fmt_size, _fmt_tokens, _icon


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
