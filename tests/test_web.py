"""
Tests for clawtracerx.web — Flask API endpoints.
"""
from __future__ import annotations

import json
import pytest


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
