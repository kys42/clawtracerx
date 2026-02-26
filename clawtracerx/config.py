"""ClawTracerX configuration — load, save, apply path overrides."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".openclaw" / "tools" / "ocmon" / "config.json"

_defaults = {
    "openclaw_dir": "",  # empty = use default (~/.openclaw)
}


def load() -> dict:
    """Load config from disk, return merged with defaults."""
    cfg = dict(_defaults)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save(cfg: dict):
    """Save config to disk."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def apply_paths(openclaw_dir: str = ""):
    """Override module-level path constants in session_parser and gateway."""
    if not openclaw_dir:
        return  # use defaults, no change

    from clawtracerx import session_parser as sp
    from clawtracerx import gateway as gw

    base = Path(openclaw_dir)
    sp.OPENCLAW_DIR = base
    sp.AGENTS_DIR = base / "agents"
    sp.SUBAGENTS_FILE = base / "subagents" / "runs.json"
    sp.CRON_JOBS_FILE = base / "cron" / "jobs.json"
    sp.CRON_RUNS_DIR = base / "cron" / "runs"
    gw.OPENCLAW_CONFIG = base / "openclaw.json"
    gw.DEVICE_IDENTITY_FILE = base / "identity" / "device.json"
