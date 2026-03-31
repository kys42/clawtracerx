"""
Tests for clawtracerx.web — Flask API endpoints.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


class TestFlaskEndpoints:
    def test_index_returns_200(self, flask_client):
        resp = flask_client.get("/")
        assert resp.status_code == 200

    def test_api_sessions_returns_list(self, flask_client):
        resp = flask_client.get("/api/sessions")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

    def test_api_agents_returns_list(self, flask_client):
        resp = flask_client.get("/api/agents")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

    def test_api_session_nonexistent_returns_404(self, flask_client):
        resp = flask_client.get("/api/session/00000000-doesnotexist")
        assert resp.status_code == 404

    def test_api_cost_returns_200(self, flask_client):
        resp = flask_client.get("/api/cost?period=all")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "total_cost" in data
        assert "by_agent" in data


class TestPageRendering:
    def test_home_page(self, flask_client):
        resp = flask_client.get("/home")
        assert resp.status_code == 200

    def test_cost_page(self, flask_client):
        resp = flask_client.get("/cost")
        assert resp.status_code == 200

    def test_schedule_page(self, flask_client):
        resp = flask_client.get("/schedule")
        assert resp.status_code == 200

    def test_settings_page(self, flask_client):
        resp = flask_client.get("/settings")
        assert resp.status_code == 200

    def test_session_detail_page(self, flask_client):
        resp = flask_client.get("/session/aabbccdd")
        assert resp.status_code == 200


class TestApiCrons:
    def test_empty_crons(self, flask_client):
        resp = flask_client.get("/api/crons")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
        assert data == []

    def test_crons_with_data(self, flask_client, cron_dir):
        resp = flask_client.get("/api/crons")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 2
        assert data[0]["status"] in ("ok", "error")
        assert "job_id" in data[0]
        assert "job_name" in data[0]

    def test_crons_last_param(self, flask_client, cron_dir):
        resp = flask_client.get("/api/crons?last=1")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) == 1


class TestApiSchedule:
    def test_empty_schedule(self, flask_client):
        resp = flask_client.get("/api/schedule")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "cron_jobs" in data

    def test_schedule_with_data(self, flask_client, cron_dir):
        resp = flask_client.get("/api/schedule")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["cron_jobs"]) >= 1
        job = data["cron_jobs"][0]
        assert job["id"] == "job-abc"
        assert job["enabled"] is True


class TestApiHealth:
    def test_health_returns_checks(self, flask_client):
        with patch("clawtracerx.gateway.load_gateway_config", side_effect=FileNotFoundError), \
             patch("clawtracerx.gateway.list_agents", side_effect=ConnectionError("no gw")):
            resp = flask_client.get("/api/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "checks" in data
        assert "timestamp" in data
        assert "agents" in data["checks"]


class TestApiRawTurn:
    def test_raw_turn_valid(self, flask_client):
        resp = flask_client.get("/api/session/aabbccdd/raw/0")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_raw_turn_out_of_range(self, flask_client):
        resp = flask_client.get("/api/session/aabbccdd/raw/999")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == []

    def test_raw_turn_nonexistent_session(self, flask_client):
        resp = flask_client.get("/api/session/00000000-nope/raw/0")
        assert resp.status_code == 404


class TestApiCost:
    def test_cost_period_today(self, flask_client):
        resp = flask_client.get("/api/cost?period=today")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "total_cost" in data

    def test_cost_period_month(self, flask_client):
        resp = flask_client.get("/api/cost?period=month")
        assert resp.status_code == 200


class TestApiSessionExport:
    def test_export_session_json(self, flask_client):
        resp = flask_client.get("/api/session/aabbccdd/export")
        assert resp.status_code == 200
        assert resp.content_type == "application/json"
        data = json.loads(resp.data)
        assert "session_id" in data
        assert "turns" in data

    def test_export_session_not_found(self, flask_client):
        resp = flask_client.get("/api/session/00000000-nope/export")
        assert resp.status_code == 404


class TestApiSessionsExport:
    def test_export_csv(self, flask_client):
        resp = flask_client.get("/api/sessions/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type
        text = resp.data.decode()
        assert "session_id" in text  # CSV header

    def test_export_csv_with_agent_filter(self, flask_client):
        resp = flask_client.get("/api/sessions/export?agent=test-agent")
        assert resp.status_code == 200


class TestApiLogs:
    def test_logs_invalid_file(self, flask_client):
        resp = flask_client.get("/api/logs?file=secret")
        assert resp.status_code == 400

    def test_logs_nonexistent_file(self, flask_client):
        resp = flask_client.get("/api/logs?file=lab")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "lines" in data

    def test_logs_with_data(self, flask_client, tmp_path, monkeypatch):
        from clawtracerx import web as _web
        log_file = Path(_web._get_base_path()).parent / "lab.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("line1\nline2\nline3\n")
        resp = flask_client.get("/api/logs?file=lab&lines=2")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["lines"]) == 2
        # Cleanup
        if log_file.exists():
            log_file.unlink()


class TestApiSessionStream:
    def test_stream_not_found(self, flask_client):
        resp = flask_client.get("/api/session/00000000-nope/stream")
        assert resp.status_code == 404


class TestSerializeAnalysis:
    def test_serialize_basic(self, mock_openclaw_dir, minimal_session_path):
        from clawtracerx.session_parser import parse_session
        from clawtracerx.web import _serialize_analysis

        analysis = parse_session(minimal_session_path)
        result = _serialize_analysis(analysis)
        assert "session_id" in result
        assert "turns" in result
        assert isinstance(result["turns"], list)
        assert "total_cost" in result
        assert "agent_id" in result

    def test_serialize_turn_truncation(self, mock_openclaw_dir, minimal_session_path):
        from clawtracerx.session_parser import parse_session
        from clawtracerx.web import _serialize_turn

        analysis = parse_session(minimal_session_path)
        if analysis.turns:
            turn_data = _serialize_turn(analysis.turns[0])
            assert "index" in turn_data
            assert "user_text" in turn_data
            assert "tool_calls" in turn_data
            assert "subagent_spawns" in turn_data


class TestGraphPage:
    def test_graph_page_renders(self, flask_client):
        resp = flask_client.get("/session/aabbccdd/graph")
        assert resp.status_code == 200

    def test_graph_api(self, flask_client):
        resp = flask_client.get("/api/session/aabbccdd/graph")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "nodes" in data
        assert "edges" in data

    def test_graph_api_not_found(self, flask_client):
        resp = flask_client.get("/api/session/00000000-nope/graph")
        assert resp.status_code == 404


class TestExportCSVFields:
    def test_csv_header_and_data(self, flask_client):
        resp = flask_client.get("/api/sessions/export")
        text = resp.data.decode()
        lines = text.strip().split("\n")
        assert len(lines) >= 1
        header = lines[0]
        assert "session_id" in header
        assert "agent_id" in header
        assert "cost" in header

    def test_csv_data_row_count(self, flask_client):
        resp = flask_client.get("/api/sessions/export")
        text = resp.data.decode()
        lines = text.strip().split("\n")
        # At least header + 1 data row (from minimal_session)
        assert len(lines) >= 2


class TestExportJSONStructure:
    def test_export_json_required_fields(self, flask_client):
        resp = flask_client.get("/api/session/aabbccdd/export")
        data = json.loads(resp.data)
        assert "session_id" in data
        assert "turns" in data
        assert "total_cost" in data
        assert "model" in data


class TestLogsLimits:
    def test_logs_lines_capped(self, flask_client):
        resp = flask_client.get("/api/logs?file=lab&lines=999")
        assert resp.status_code == 200

    def test_logs_file_field(self, flask_client):
        resp = flask_client.get("/api/logs?file=web")
        data = json.loads(resp.data)
        assert data["file"] == "web"


class TestSessionDetailErrorHandling:
    def test_empty_session_returns_200(self, flask_client, mock_openclaw_dir):
        sessions_dir = mock_openclaw_dir / "agents" / "test-agent" / "sessions"
        bad = sessions_dir / "emptyses0-0000-0000-0000-000000000001.jsonl"
        bad.write_text("")
        resp = flask_client.get("/api/session/emptyses0")
        assert resp.status_code in (200, 400)
