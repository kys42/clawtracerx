# ClawTracerX

<p align="center">
  <img src="docs/assets/mascot-skeleton.png" width="96" alt="ClawTracerX skeleton mascot" />
</p>

**OpenClaw agent session monitor** — visualizes what happens inside AI agent runs: tool calls, subagents, token usage, cost, and timing.

---

## What is this?

ClawTracerX reads the JSONL transcripts that [OpenClaw](https://github.com/kys42/openclaw) writes locally and turns them into a web dashboard + CLI. No data leaves your machine.

- **Session timeline** — every turn: user message → assistant thinking → tool calls → subagent spawns, with per-message token counts and cost
- **Subagent tree** — recursively parses child sessions so you see the full execution tree
- **Cost dashboard** — per-agent, per-model, per-day breakdown with charts
- **Cron monitor** — job run history, success/failure tracking
- **Interactive graph** — Canvas-based execution tree (drag, zoom, Tree/Force layout)
- **Lab** *(coming soon)* — send messages to agents directly from the dashboard

---

## Screenshots

| Home (overview) | Sessions |
|---|---|
| ![Home](docs/screenshots/home.png) | ![Sessions](docs/screenshots/sessions.png) |

| Cost dashboard |
|---|
| ![Cost dashboard](docs/screenshots/cost.png) |

> Next to add (best for README): **Session detail** (tools + subagent tree), **Graph**, **Schedule/Cron**, **Settings**.

---

## Requirements

- [OpenClaw](https://github.com/kys42/openclaw) installed and configured (`~/.openclaw/`)
- **Python 3.9+** (pip install) **or** **Node.js 18+** (npm install, no Python needed)

---

## Installation

### npm — no Python required (recommended)

```bash
npm install -g clawtracerx
```

`postinstall` automatically downloads the pre-built binary for your platform.

| Platform | Supported |
|----------|-----------|
| macOS arm64 (Apple Silicon) | ✅ |
| macOS x64 (Intel) | ❌ (use pip) |
| Linux x64 | ✅ |
| Windows | ❌ (use pip) |

### pip

```bash
pip install "clawtracerx[web]"
```

### From source

```bash
git clone https://github.com/kys42/clawtracerx.git
cd clawtracerx
pip install -e ".[web]"
```

### Verify

```bash
ctrace --version
ctrace sessions
```

---

## Usage

### Web dashboard

```bash
ctrace web                  # http://localhost:8901
ctrace web --port 9000      # custom port
ctrace web --debug          # debug mode
```

| Page | URL | Description |
|------|-----|-------------|
| Sessions | `/` | All sessions with agent/type filters |
| Session Detail | `/session/<id>` | Turn-by-turn timeline, tool call results, token chart |
| Graph | `/session/<id>/graph` | Interactive execution tree |
| Cost | `/cost` | Token/cost breakdown by agent, model, day |
| Schedule | `/schedule` | Cron job and heartbeat status |

### CLI

```bash
# List sessions
ctrace sessions                          # recent 20
ctrace sessions --agent aki --last 50    # filter by agent
ctrace sessions --type cron              # cron sessions only

# Analyze a session (core feature)
ctrace analyze <session-id>              # UUID prefix works
ctrace analyze a6604d70
ctrace analyze aki:92de0796              # agent:id format
ctrace analyze ~/.openclaw/agents/aki/sessions/xxxx.jsonl

# View raw JSONL for a turn
ctrace raw <session-id> --turn 0

# Cost summary
ctrace cost                              # today
ctrace cost --period week
ctrace cost --period month --agent aki

# Cron history
ctrace crons
ctrace crons --last 50 --job <job-id>

# Subagent history
ctrace subagents
ctrace subagents --parent a6604d70
```

### Example: `ctrace analyze` output

```
═══════════════════════════════════════════════════════
Session: a6604d70-deb (main)
Started: 2026-02-20 00:00:00 | Model: gemini-3-flash-preview | Provider: google
Type: cron | CWD: ~/.openclaw/workspace
═══════════════════════════════════════════════════════

── Turn 0 ────────────────────────────────────────────
  📩 User (cron)
     "[cron:01257c8d Nightly Daily Review & Self-Update]..."

  🤖 Assistant                          ⏱ 4m 28s  💰 $0.305
     Tokens: in=568.3K, out=3.3K, cache=224.9K, total=571.6K

     ├─ 🔧 session_status
     ├─ 💻 exec(python3 scripts/log_chunker.py)          2.3s
     ├─ 🔀 subagent → nightly-map-batch-0
     │     task: "batch mapper..."
     │     ok | 14.7s | $0.042 | 12K tokens
     │     ├─ 📁 read(batch_0_chunks.md)                201ms
     │     ├─ 💻 exec(gh pr diff 92)                   2340ms
     │     └─ ✅ Done (3 turns)
     └─ 💬 "DONE: batches=4..."

═══════════════════════════════════════════════════════
Summary
  Turns: 4 | Duration: 4m 28s | Cost: $0.330
  Tokens: in=568K out=3.3K cache=225K total=618K
  Tools: exec×13, write×3, sessions_spawn×3
  Subagents: 3 (success: 2, error: 1)
```

---

## Data sources

ClawTracerX is **read-only** — it only reads files OpenClaw writes locally.

| Source | Path | Contents |
|--------|------|----------|
| Session transcripts | `~/.openclaw/agents/{id}/sessions/*.jsonl` | Messages, tool calls, tokens, cost, timing |
| Subagent registry | `~/.openclaw/subagents/runs.json` | parent↔child mapping, task, duration, outcome |
| Cron run logs | `~/.openclaw/cron/runs/*.jsonl` | jobId, status, duration, summary |
| Cron job definitions | `~/.openclaw/cron/jobs.json` | schedule, agent, model, delivery |

### What's tracked (and what isn't)

| Item | Available | Notes |
|------|-----------|-------|
| Per-message token/cost | ✅ | usage + cost on every assistant message |
| Per-tool-call tokens | ❌ | multiple tool calls share one assistant message |
| Per-tool-call timing | ✅ partial | `exec`, `read` etc. have `durationMs` |
| Subagent internals | ✅ | recursive child JSONL parsing |
| Google/Gemini thinking | ✅ | plain text in `thinking` field |
| OpenAI thinking | ❌ | Fernet-encrypted, not locally decryptable |
| Turn duration | ✅ | user timestamp → last assistant timestamp |
| Model change tracking | ✅ | `model_change` events, per-message model field |

---

## Architecture

```
clawtracerx/
├── __main__.py          CLI entrypoint (argparse)
├── session_parser.py    JSONL → SessionAnalysis (Turn / ToolCall / SubagentSpawn tree)
├── cli.py               CLI commands → ANSI terminal output
├── web.py               Flask server + REST API
├── gateway.py           OpenClaw WebSocket RPC client
├── templates/           Jinja2 (base, sessions, detail, graph, cost, schedule)
└── static/
    ├── app.js           Shared utilities (fetchJSON, fmtTokens, shortenPath…)
    ├── turns.js         Shared turn renderer
    └── style.css        Dark Pro design system

npm/                     npm wrapper (downloads pre-built binary via postinstall)
tests/                   pytest test suite
```

---

## License

MIT
