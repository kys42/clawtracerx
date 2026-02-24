# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClawTracerX은 OpenClaw 멀티 에이전트 시스템의 모니터링 도구. JSONL 세션 트랜스크립트를 파싱하여 CLI/웹 대시보드로 시각화하고, Lab에서 에이전트와 실시간 인터랙션 가능.

## Commands

```bash
# 패키지 설치 (개발 모드)
pip install -e ".[dev]"

# 웹 서버 (개발)
ctrace web --debug --port 8901

# 웹 서버 (백그라운드 운영)
./restart.sh

# CLI
ctrace sessions
ctrace analyze <session-id-prefix>
ctrace cost --period week

# 테스트
pytest -v

# 린트
ruff check clawtracerx/ tests/
```

## Architecture

```
ctrace.py (backward-compat shim → clawtracerx.__main__)
clawtracerx/
    __main__.py      엔트리포인트: argparse → CLI 또는 Flask
    session_parser.py  JSONL → SessionAnalysis (Turn/ToolCall/SubagentSpawn 트리)
    cli.py           parser 결과 → ANSI 컬러 터미널 출력
    web.py           parser 결과 → JSON API + Jinja2 HTML
    gateway.py       OpenClaw 게이트웨이 WebSocket RPC 클라이언트
    templates/       Jinja2 (base → sessions, detail, graph, cost, lab)
    static/
        app.js       공유 유틸 (fetchJSON, fmtTokens, escHtml 등)
        turns.js     공유 턴 렌더링 (detail.html + lab.html 양쪽에서 사용)
        style.css    Dark Pro 디자인 시스템

tests/               pytest 테스트 스위트
npm/                 npm 배포용 (바이너리 다운로드 방식)
```

### 데이터 흐름

```
~/.openclaw/agents/{id}/sessions/*.jsonl
        ↓
session_parser.parse_session(path, recursive_subagents=True)
        ↓
SessionAnalysis → list[Turn] → list[ToolCall] / list[SubagentSpawn]
        ↓
web._serialize_analysis() → JSON API → JS (app.js, turns.js) → HTML
```

### session_parser.py — 핵심 파서 (가장 복잡한 파일)

- `parse_session()` 이 모든 것의 시작점. JSONL 파일 → `SessionAnalysis` 반환
- Turn 경계: user 메시지를 만나면 이전 턴 마감, 새 턴 시작
- 서브에이전트: `sessions_spawn` 도구 호출 → announce 메시지에서 실제 sessionId 추출 → child JSONL 재귀 파싱
- `sessions.json` 메타데이터 (context injection, 토큰 카운터 등)도 병합
- Soft-deleted 파일 (`.jsonl.deleted.{timestamp}`) 처리 포함

### gateway.py — Lab의 게이트웨이 통신

- 매 RPC 호출마다 새 WS 연결 (connect challenge → Ed25519 device auth → RPC → close)
- Device identity: `~/.openclaw/identity/device.json` (Ed25519 키쌍)
- 인증 없으면 scopes가 `[]`로 클리어되어 모든 RPC 실패

### turns.js — 공유 턴 렌더링

detail.html과 lab.html 양쪽에서 import. app.js의 전역 함수들(fmtTokens, escHtml 등)에 의존.
`showRaw` 함수는 detail.html에만 정의 — turns.js에서 `typeof showRaw === 'function'`으로 조건 체크.

## 핵심 함정

### Session Key ≠ Session ID
```
Session Key:  agent:aki:chat:59428ab7-...    ← 게이트웨이 라우팅 키
Session ID:   9520bb0d-fed2-4b35-...          ← JSONL 파일명 UUID
```
둘은 다른 값. `sessions.json`에서 매핑됨. 키로 파일을 찾으면 404.

### 서브에이전트 UUID 3종
| UUID | 출처 | 파일명? |
|------|------|---------|
| childSessionKey 내 UUID | 게이트웨이 라우팅 | **아님** |
| runId | subagents/runs.json | **아님** |
| announce의 sessionId | announce 메시지 파싱 | **이것이 파일명** |

### RPC 응답 필드
게이트웨이 RPC 성공 응답의 데이터는 `result`가 아닌 **`payload`** 필드.

## 코딩 규칙

- **Python 3.9 호환 필수** (macOS 기본). `from __future__ import annotations` 사용하여 `str | Path` 문법 가능하게.
- `session_parser.py`의 dataclass 필드 추가 시 `web.py`의 `_serialize_*()` 함수도 같이 수정해야 API에 반영됨.
- 워크스페이스 파일 수정 시 `.lab-backup` 백업 생성 (web.py `WORKSPACE_FILES` 리스트 참조).
- CSS는 `var(--*)` 변수 체계 사용. 새 컴포넌트는 기존 변수 활용.

## OpenClaw 데이터 소스

모두 `~/.openclaw/` 하위, **읽기 전용** (Lab context 편집 제외):

| 소스 | 경로 |
|------|------|
| 세션 JSONL | `agents/{id}/sessions/*.jsonl` (`.deleted.*` 포함) |
| 세션 메타 | `agents/{id}/sessions/sessions.json` |
| 서브에이전트 | `subagents/runs.json` |
| 크론 로그 | `cron/runs/*.jsonl`, `cron/jobs.json` |
| 워크스페이스 | `workspace/` (AGENTS.md, SOUL.md 등) |
| 게이트웨이 설정 | `openclaw.json` → `gateway` 섹션 |
| 디바이스 키 | `identity/device.json` |

## 참조 문서

- `OPENCLAW_AGENT_GUIDE.md` — OpenClaw 내부 구조 상세 (JSONL 형식, 세션 키, 서브에이전트 lifecycle, 크론)
- `SESSION_ANALYSIS_SPEC.md` — Turn 소스 분류, delivery_mirror, workflow 그루핑 알고리즘
