# ocmon — OpenClaw Agent Monitor

OpenClaw 멀티 에이전트 시스템의 내부 실행을 분석하는 모니터링 도구.

에이전트가 메시지를 받고 응답하기까지 내부에서 무슨 일이 벌어지는지 — 어떤 툴을 호출했고, 서브에이전트를 생성했고, 토큰을 얼마나 썼고, 얼마나 걸렸는지 — 한눈에 보여줍니다.

## Features

- **세션 분석**: Turn 단위로 구조화된 세션 상세 분석 (user → assistant → tool results)
- **서브에이전트 추적**: parent → child 세션을 재귀적으로 파싱하여 전체 실행 트리 구성
- **토큰/비용 추적**: 메시지 단위 토큰 사용량 및 USD 비용 집계 (에이전트별, 모델별, 일별)
- **Thinking 추출**: Google/Gemini 모델의 thinking 평문 표시, OpenAI 암호화 감지
- **크론 모니터링**: 크론 잡 실행 이력, 성공/실패 추적
- **인터랙티브 그래프**: Canvas 기반 실행 트리 시각화 (드래그, 줌, Tree/Force 레이아웃)
- **Raw 로그**: 특정 Turn의 JSONL 원문을 JSON pretty-print로 확인

## Requirements

- Python 3.9+
- Flask (`pip3 install flask`)
- OpenClaw (`~/.openclaw/` 디렉토리 구조 필요)

## Installation

```bash
# 1. 도구 디렉토리에 복사 (또는 git clone)
mkdir -p ~/.openclaw/tools/ocmon
cp -r . ~/.openclaw/tools/ocmon/

# 2. Flask 설치 (없는 경우)
pip3 install flask

# 3. alias 등록 (~/.zshrc 또는 ~/.bashrc)
echo 'alias ocmon="python3 $HOME/.openclaw/tools/ocmon/ocmon.py"' >> ~/.zshrc
source ~/.zshrc
```

## Usage

### CLI

```bash
# 세션 목록
ocmon sessions                          # 전체 (최근 20개)
ocmon sessions --agent aki --last 50    # aki 에이전트만, 50개
ocmon sessions --type cron              # 크론 세션만

# 세션 상세 분석 (핵심 기능)
ocmon analyze <session-id>              # UUID 앞부분만으로도 검색 가능
ocmon analyze a6604d70                  # 예시
ocmon analyze aki:92de0796              # agent:id 형식
ocmon analyze ~/.openclaw/agents/aki/sessions/xxxx.jsonl  # 전체 경로

# 특정 Turn의 JSONL 원문 보기
ocmon raw <session-id> --turn 0

# 크론 실행 이력
ocmon crons                             # 전체 (최근 20개)
ocmon crons --last 50 --job <job-id>    # 특정 잡 필터

# 서브에이전트 실행 이력
ocmon subagents                         # 전체
ocmon subagents --parent a6604d70       # 특정 parent 세션의 서브에이전트만

# 비용 요약
ocmon cost                              # 오늘
ocmon cost --period week                # 이번 주
ocmon cost --period month --agent aki   # 이번 달, aki만

# 웹 대시보드 시작
ocmon web                               # http://localhost:8901
ocmon web --port 9000                   # 커스텀 포트
```

### `ocmon analyze` 출력 예시

```
═══════════════════════════════════════════════════════
Session: a6604d70-deb (main)
Started: 2026-02-20 00:00:00 | Model: gemini-3-flash-preview | Provider: google
Type: cron | CWD: /Users/kys/.openclaw/workspace
═══════════════════════════════════════════════════════

── Turn 0 ────────────────────────────────────────────
  📩 User (cron)
     "[cron:01257c8d Nightly Daily Review & Self-Update]..."

  🤖 Assistant                          ⏱ 4m 28s  💰 $0.305
     Tokens: in=568.3K, out=3.3K, cache=224.9K, total=571.6K

     ├─ 🔧 session_status
     ├─ 💻 exec(python3 scripts/log_chunker_clean.py)    2.3s
     ├─ 🔀 subagent → nightly-map-2026-02-19-batch-0
     │     task: "너는 daily review mapper다..."
     │     ok | 14.7s | $0.042 | 12K tokens
     │     ├─ 📁 read(batch_0_chunks.md)                  201ms
     │     ├─ 💻 exec(gh pr diff 92)                     2340ms
     │     ├─ ✏️  edit(PR-92-review.md)                     45ms
     │     └─ ✅ Done (3 turns)
     ├─ 🔀 subagent → nightly-map-2026-02-19-batch-1
     │     ok | 5.0s
     └─ 💬 "DONE: 2026-02-19 batches=4..."

═══════════════════════════════════════════════════════
Summary
  Turns: 4 | Duration: 4m 28s | Cost: $0.330
  Tokens: in=568K out=3.3K cache=225K total=618K
  Tools: exec×13, write×3, sessions_spawn×3, session_status×2
  Subagents: 3 (success: 2, error: 1)
```

### 웹 대시보드

`ocmon web` 실행 후 http://localhost:8901 접속.

| 페이지 | 경로 | 설명 |
|--------|------|------|
| Sessions | `/` | 전체 세션 목록. 에이전트/타입 필터, 클릭하여 상세 |
| Session Detail | `/session/<id>` | Turn별 타임라인. 툴콜 결과 펼치기, 토큰 바 차트, Raw 모달 |
| Graph View | `/session/<id>/graph` | Canvas 인터랙티브 실행 그래프. 서브에이전트 트리 시각화 |
| Cost Dashboard | `/cost` | 에이전트별/타입별/모델별/일별 비용 차트 |

## Data Sources

ocmon은 OpenClaw가 로컬에 저장하는 파일들을 읽기만 합니다 (read-only).

| 소스 | 경로 | 내용 |
|------|------|------|
| 세션 트랜스크립트 | `~/.openclaw/agents/{id}/sessions/*.jsonl` | 메시지, 툴콜, 토큰, 비용, 타이밍 |
| 서브에이전트 레지스트리 | `~/.openclaw/subagents/runs.json` | parent↔child 매핑, task, duration, outcome |
| 크론 실행 로그 | `~/.openclaw/cron/runs/*.jsonl` | jobId, status, duration, summary |
| 크론 잡 정의 | `~/.openclaw/cron/jobs.json` | schedule, agent, model, delivery |

### 데이터 한계

| 항목 | 가능 여부 | 비고 |
|------|----------|------|
| 메시지 단위 토큰/비용 | ✅ | assistant 메시지마다 usage + cost |
| 개별 툴콜 단위 토큰 | ❌ | 하나의 assistant 메시지에 여러 toolCall이 포함되어 분리 불가 |
| 개별 툴콜 실행 시간 | ✅ (일부) | exec, read 등은 `details.durationMs` 있음 |
| 서브에이전트 내부 추적 | ✅ | childSessionKey로 자식 세션 JSONL 재귀 파싱 |
| Thinking (Google/Gemini) | ✅ | `thinking` 필드에 평문 저장 |
| Thinking (OpenAI) | ❌ | Fernet 암호화, 로컬 복호화 불가 |
| Turn 소요 시간 | ✅ | user timestamp → 마지막 assistant timestamp |
| 모델 변경 추적 | ✅ | model_change 이벤트, 메시지별 model 필드 |

## Architecture

```
~/.openclaw/tools/ocmon/
├── ocmon.py          # 엔트리포인트 (CLI + web 서브커맨드)
├── parser.py         # JSONL 파싱, Turn 구조화, 서브에이전트 매핑
├── cli.py            # CLI 명령어 (sessions, analyze, raw, crons, cost)
├── web.py            # Flask 웹 서버 + REST API
├── templates/
│   ├── base.html     # 레이아웃 (사이드바, 네비게이션)
│   ├── sessions.html # 세션 목록 페이지
│   ├── detail.html   # 세션 상세 (Turn 타임라인)
│   ├── graph.html    # 실행 그래프 (Canvas)
│   └── cost.html     # 비용 대시보드
└── static/
    ├── style.css     # 다크 테마 CSS
    └── app.js        # 공유 JS 유틸리티
```

### 핵심 데이터 모델

```
SessionAnalysis
├── session_id, agent_id, session_type
├── model, provider, started_at
├── total_cost, total_tokens, total_duration_ms
└── turns[]
    └── Turn
        ├── user_text, user_source (chat|cron|heartbeat)
        ├── assistant_texts[], thinking_text
        ├── model, provider, usage{}, cost{}
        ├── duration_ms, stop_reason
        ├── tool_calls[]
        │   └── ToolCall {name, arguments, result_text, duration_ms, is_error}
        ├── subagent_spawns[]
        │   └── SubagentSpawn {label, task, outcome, child_turns[], cost_usd}
        └── raw_lines[] (JSONL 원문)
```

## License

Internal tool for OpenClaw ecosystem.
