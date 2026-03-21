"""
Tests for clawtracerx.config — load, save, apply_paths.
"""
from __future__ import annotations

import json

from clawtracerx import config


class TestConfigLoad:
    def test_load_default_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "nonexistent.json")
        cfg = config.load()
        assert cfg == {"openclaw_dir": ""}

    def test_load_custom_value(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({"openclaw_dir": "/custom/path"}))
        monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
        cfg = config.load()
        assert cfg["openclaw_dir"] == "/custom/path"

    def test_load_corrupted_json_returns_defaults(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text("NOT VALID JSON {{{")
        monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
        cfg = config.load()
        assert cfg == {"openclaw_dir": ""}


class TestConfigSave:
    def test_save_roundtrip(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "subdir" / "config.json"
        monkeypatch.setattr(config, "CONFIG_FILE", cfg_file)
        config.save({"openclaw_dir": "/my/path"})
        assert cfg_file.exists()
        loaded = json.loads(cfg_file.read_text())
        assert loaded["openclaw_dir"] == "/my/path"


class TestApplyPaths:
    def test_apply_empty_does_nothing(self, monkeypatch):
        import clawtracerx.session_parser as sp
        original = sp.OPENCLAW_DIR
        config.apply_paths("")
        assert sp.OPENCLAW_DIR == original

    def test_apply_custom_path(self, tmp_path, monkeypatch):
        import clawtracerx.gateway as gw
        import clawtracerx.session_parser as sp
        config.apply_paths(str(tmp_path))
        assert sp.OPENCLAW_DIR == tmp_path
        assert sp.AGENTS_DIR == tmp_path / "agents"
        assert gw.OPENCLAW_CONFIG == tmp_path / "openclaw.json"
