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
