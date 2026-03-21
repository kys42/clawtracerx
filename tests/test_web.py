"""
Tests for clawtracerx.web — Flask API endpoints.
"""
from __future__ import annotations

import json
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
             patch("clawtracerx.gateway.list_agents", side_effect=Exception("no gw")):
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
