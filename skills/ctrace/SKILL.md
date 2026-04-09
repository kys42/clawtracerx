---
name: ctrace
description: ClawTracerX API를 조회하여 에이전트 세션, 코스트, 에러, 툴 사용량 등을 확인합니다
disable-model-invocation: false
argument-hint: 오늘 세션 | 최근 에러 | 코스트 | 세션 상세 <id-prefix>
allowed-tools: Bash(curl *), Read, WebFetch
---

# ClawTracerX API Query Skill

OpenClaw 에이전트 모니터링 도구 ClawTracerX의 REST API를 조회하여 세션, 코스트, 에러 등 정보를 확인합니다.

## 서버 확인 (항상 먼저 실행)

```bash
curl -sf http://localhost:8901/api/health | head -c 200
```

**서버가 안 떠있으면** 사용자에게 아래를 안내:
```
ClawTracerX 서버가 꺼져있습니다. 아래 명령어로 실행해주세요:
  ctrace web --port 8901
  # 또는: ctrace web --debug --port 8901

설치가 안 되어있다면:
  npm install -g clawtracerx    # npm
  pip install clawtracerx[web]  # pip
  # repo: https://github.com/kys42/clawtracerx
```

---

## API 엔드포인트 레퍼런스

Base URL: `http://localhost:8901`

### 1. 세션 목록

```bash
curl -s 'http://localhost:8901/api/sessions?last=50'
```

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `last` | 50 | 반환할 세션 수 |
| `agent` | all | 에이전트 ID 필터 |

**응답 핵심 필드:**
- `session_id` — 세션 UUID
- `agent_id` — 에이전트 ID
- `type` — chat / heartbeat
- `model` — 사용 모델
- `turns` — 턴 수
- `tokens` — 총 토큰
- `cost` — 비용 ($)
- `started_at` — 시작 시간 (ISO8601)
- `tool_calls` — 도구 호출 수
- `subagents` — 서브에이전트 수
- `errors` — 에러 수
- `last_message` — 마지막 메시지 요약

### 2. 세션 상세

```bash
curl -s 'http://localhost:8901/api/session/<SESSION_ID>'
```

세션의 전체 분석 결과. 턴 목록, 각 턴의 tool_calls, subagent_spawns, assistant_texts, errors 포함.

**응답 구조:**
- `turns[]` — 턴 배열
  - `user_text` — 사용자 입력
  - `assistant_texts[]` — 어시스턴트 응답
  - `tool_calls[]` — `{id, name, error, duration_ms}`
  - `subagent_spawns[]` — `{child_session_id, model, total_cost, total_tokens}`
  - `thinking_texts[]` — 사고 과정
  - `token_usage` — `{input, output, cache_read, cache_creation}`
- `model`, `total_tokens`, `total_cost`, `errors[]`

### 3. 코스트 분석

```bash
curl -s 'http://localhost:8901/api/cost?period=week'
```

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `period` | week | today / week / month / all |
| `agent` | all | 에이전트 ID 필터 |

**응답 핵심 필드:**
- `total_cost` — 총 비용
- `total_tokens` — 총 토큰
- `session_count` — 세션 수
- `by_agent` — 에이전트별 비용
- `by_model` — 모델별 비용
- `by_day` — 일별 비용
- `by_type` — 타입별 (chat/heartbeat) 비용

### 4. 스케줄 (크론/하트비트)

```bash
curl -s 'http://localhost:8901/api/schedule'
```

**응답 핵심 필드:**
- `cron_jobs[]` — `{id, name, enabled, last_status, consecutive_errors, runs[]}`
- `summary` — `{total, enabled, ok, error}`
- `heartbeats[]` — 에이전트별 하트비트 세션

### 5. 에이전트 목록

```bash
curl -s 'http://localhost:8901/api/agents'
```

**응답:** `[{id, sessions}]` — 에이전트 ID와 세션 수

### 6. 시스템 상태

```bash
curl -s 'http://localhost:8901/api/health'
```

**응답:** config, device, agents, gateway, workspace 각각의 ok/error 상태

---

## 질문 → API 매핑 가이드

사용자 질문을 받으면 아래 패턴에 따라 API를 호출하고 결과를 정리합니다.

### 세션 조회 계열

| 질문 | API 호출 | 응답 처리 |
|------|---------|----------|
| "오늘 세션 뭐있었어?" | `GET /api/sessions?last=100` | `started_at`이 오늘인 것만 필터. type, model, turns, cost 요약 |
| "최근 세션 보여줘" | `GET /api/sessions?last=10` | 그대로 요약 테이블로 |
| "방금 대화 뭐였어?" | `GET /api/sessions?last=1` | 첫번째 세션의 last_message + turns + cost |
| "heartbeat 세션 빼고 보여줘" | `GET /api/sessions?last=50` | `type != "heartbeat"` 필터 |

### 에러/실패 계열

| 질문 | API 호출 | 응답 처리 |
|------|---------|----------|
| "최근 실패한거 뭐야?" | `GET /api/sessions?last=50` | `errors > 0` 필터. session_id, errors 수, last_message |
| "에러 상세 보여줘" | `GET /api/session/<id>` | turns에서 tool_calls의 `error` 필드가 있는 것 추출 |
| "크론 에러 있어?" | `GET /api/schedule` | cron_jobs에서 `last_status == "error"` 필터 |

### 도구/서브에이전트 계열

| 질문 | API 호출 | 응답 처리 |
|------|---------|----------|
| "방금 대화 툴 몇개 썼어?" | sessions → 최근 1개 session_id → `GET /api/session/<id>` | 전체 tool_calls 수 + 이름별 카운트 |
| "어떤 도구 가장 많이 쓰나?" | sessions → 최근 N개 → 각각 session detail | tool_calls name별 집계 |
| "서브에이전트 몇번 썼어?" | `GET /api/sessions?last=50` | `subagents` 필드 합산 또는 특정 세션 상세 |

### 코스트 계열

| 질문 | API 호출 | 응답 처리 |
|------|---------|----------|
| "이번주 코스트 얼마야?" | `GET /api/cost?period=week` | total_cost, by_day 차트 데이터 |
| "오늘 얼마 썼어?" | `GET /api/cost?period=today` | total_cost, session_count, by_model |
| "이번달 비용?" | `GET /api/cost?period=month` | total_cost + by_agent 브레이크다운 |
| "모델별 비용 비교" | `GET /api/cost?period=week` | by_model 필드 |

### 시스템 계열

| 질문 | API 호출 | 응답 처리 |
|------|---------|----------|
| "시스템 상태 어때?" | `GET /api/health` | checks 각 항목의 ok/error 요약 |
| "에이전트 몇개야?" | `GET /api/agents` | 에이전트 목록 + 세션 수 |
| "게이트웨이 연결 돼있어?" | `GET /api/health` | checks.gateway 상태 |

---

## 응답 포맷 가이드

- 세션 목록은 **테이블 형식**으로 (session_id 앞 8자리, type, turns, cost, started_at)
- 코스트는 **총액 + 브레이크다운**으로
- 에러는 **세션ID + 에러 내용** 리스트로
- 큰 JSON 응답은 jq로 필터링: `curl -s ... | jq '.[] | {session_id, turns, cost, errors}'`
- session_id는 앞 8자리만 표시해도 충분 (API는 prefix match 지원)

## 주의사항

- 서버가 꺼져있으면 API 호출 실패. 반드시 health check 먼저
- 세션 상세 API는 큰 세션의 경우 응답이 클 수 있음. jq로 필요한 필드만 추출
- `started_at` 시간은 ISO8601 형식 (UTC 아닌 로컬 시간)
- heartbeat 세션은 자동 크론 세션이라 일반 대화가 아님. 필요시 필터링
