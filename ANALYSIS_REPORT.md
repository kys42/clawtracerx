# ClawTracerX vs OpenClaw Source — 교차 분석 리포트

> **분석일**: 2026-03-09
> **대상**: ClawTracerX (`~/.openclaw/tools/ocmon/`) vs OpenClaw (`~/openclaw/`)
> **방법**: 6개 분석 에이전트 팀이 기능별로 OpenClaw 소스 코드와 ClawTracerX 파서/API/프론트를 교차 비교

---

## 목차

1. [Critical Bugs (즉시 수정 필요)](#1-critical-bugs)
2. [Sessions List — 세션 분류 불일치](#2-sessions-list)
3. [Session Detail — 이벤트 파싱 갭](#3-session-detail)
4. [Channel/Messaging — 플랫폼 감지 누락](#4-channelmessaging)
5. [Schedule — 크론/하트비트 파싱 오류](#5-schedule)
6. [Gateway/Lab — RPC 프로토콜 불일치](#6-gatewaylab)
7. [Cost/Token — 비용 계산 갭](#7-costtoken)
8. [종합 우선순위 매트릭스](#8-priority-matrix)

---

## 1. Critical Bugs

즉시 수정해야 하는 실제 동작 오류들.

### BUG-01: `sessions.patch` RPC 파라미터 키 오류 (Gateway)

**파일**: `clawtracerx/gateway.py:251`

```python
params = {"sessionKey": session_key}  # ← WRONG
```

OpenClaw 게이트웨이 스키마(`src/gateway/protocol/schema/sessions.ts:51-83`)는 `key` 필드를 기대하며 `additionalProperties: false`이므로 **모든 patch 호출이 실패함**.

**수정**: `"sessionKey"` → `"key"`

### BUG-02: `sessions.reset` RPC 파라미터 키 오류 (Gateway)

**파일**: `clawtracerx/gateway.py:258`

동일한 문제. `"sessionKey"` → `"key"` 변경 필요.

### BUG-03: `send_agent_message()` model 파라미터 무시됨 (Gateway)

**파일**: `clawtracerx/gateway.py:232-233`

`agent` RPC 핸들러(`src/gateway/server-methods/agent.ts`)는 `request.model`을 **읽지 않음**. 모델은 오직 `sessions.patch`의 `modelOverride`로만 변경됨. Lab에서 모델 선택이 실제로는 아무 효과 없음.

### BUG-04: Schedule 타임존 필드명 불일치

**파일**: `web.py:393` vs `templates/schedule.html:205`

API: `"schedule_tz"` 반환 → 프론트: `job.timezone` 참조. **타임존이 절대 표시 안 됨**.

### BUG-05: systemEvent 크론 페이로드 텍스트 누락

**파일**: `web.py:400`

```python
"payload_message": job.get("payload", {}).get("message", "")
```

`systemEvent` 타입 페이로드는 `text` 필드 사용 (`message` 아님). → 빈 문자열 표시.

**수정**: `payload.get("message", "") or payload.get("text", "")`

---

## 2. Sessions List

### 2.1 세션 타입 분류 불일치 (HIGH)

OpenClaw의 실제 `SessionKind` (`src/agents/tools/sessions-helpers.ts:11`):
```typescript
type SessionKind = "main" | "group" | "cron" | "hook" | "node" | "other";
```

ClawTracerX는 JSONL 첫 메시지 텍스트 패턴으로 추론:
- `[cron:...]` → `"cron"`
- `[heartbeat...]` → `"heartbeat"`
- 경로에 `"subagent"` 포함 → `"subagent"`
- 그 외 → `"chat"`

| 누락 타입 | OpenClaw 의미 | ClawTracerX 분류 |
|-----------|-------------|-----------------|
| `hook` | 웹훅/Gmail 트리거 세션 | `"chat"` (오분류) |
| `node` | 원격 노드 세션 | `"chat"` (오분류) |
| `group` | 그룹/채널 채팅 | `"chat"` (오분류) |

**근본 원인**: `list_sessions()`가 `sessions.json`을 전혀 읽지 않음. 세션 키 패턴으로 분류해야 정확함.

### 2.2 서브에이전트 감지 취약 (HIGH)

```python
if "subagent" in str(file_path):  # session_parser.py:1619
```

서브에이전트 JSONL은 같은 `agents/{id}/sessions/` 디렉토리에 일반 UUID 파일명으로 저장됨. 경로에 `"subagent"` 문자열이 포함될 이유 없음. → 실제로 감지 안 됨.

**올바른 방법**: `sessions.json`의 세션 키 패턴 (`agent:X:subagent:UUID`) 또는 `spawnedBy` 필드 확인.

### 2.3 sessions.json 미활용 데이터 (MEDIUM)

`list_sessions()`가 매번 전체 JSONL을 스캔하지만, `sessions.json`에 이미 있는 데이터:

| 필드 | 용도 |
|------|------|
| `label` / `displayName` | 세션 이름 표시 |
| `chatType` | `dm` / `group` / `channel` 분류 |
| `channel` | 플랫폼 |
| `totalTokens` / `inputTokens` / `outputTokens` | 토큰 카운터 (JSONL 스캔 불필요) |
| `model` | 현재 모델 |
| `spawnedBy` | 서브에이전트 부모 세션 |
| `sendPolicy` | 메시지 수신 가능 여부 |
| `abortedLastRun` | 마지막 실행 중단 여부 |
| `updatedAt` | 정확한 업데이트 타임스탬프 |

**성능 영향**: sessions.json 활용 시 전체 JSONL 스캔을 건너뛸 수 있어 대규모 세션에서 속도 대폭 개선.

### 2.4 인코딩/안정성 이슈 (LOW)

- `_quick_scan_session()`이 `encoding="utf-8", errors="replace"` 없이 파일 열기 → 비UTF-8 바이트에서 크래시 가능
- `UnicodeDecodeError` 미캐치 (OSError만 캐치)
- 파일 rename 레이스 컨디션 (`FileNotFoundError` 미캐치)
- topic 파일 (`{uuid}-topic-{id}.jsonl`) 중복 표시 문제

---

## 3. Session Detail

### 3.1 누락 이벤트 타입 (MEDIUM)

| 이벤트 | ClawTracerX | 영향 |
|--------|:-----------:|------|
| `custom` → `openclaw:prompt-error` | 미처리 | 프롬프트 실패 턴이 응답 없이 표시됨 (이유 없음) |
| `custom` → `model-snapshot` | 미처리 | 실제 사용 모델 vs 설정 모델 차이 추적 불가 |

`parse_session()` 2nd pass (line 780)에서 `if etype != "message": continue`로 모든 custom 이벤트 스킵.

### 3.2 서브에이전트 에러 사유 누락 (MEDIUM)

```python
spawn.outcome = outcome.get("status", "unknown")  # session_parser.py:1029
```

`SubagentRunOutcome.error` 필드를 캡처하지 않음. 서브에이전트 실패 사유 표시 불가.

### 3.3 stopReason 시각적 구분 없음 (MEDIUM)

| stopReason | 빈도 (실데이터) | ClawTracerX 처리 |
|-----------|:---:|------|
| `"error"` | 109건 | 일반 턴과 동일 표시 |
| `"aborted"` | 2건 | 일반 턴과 동일 표시 |
| `"injected"` | 다수 | 실제 LLM 응답과 혼재 |

### 3.4 tokensAfter 데드 필드 (INFO)

`CompactionEvent.tokens_after`는 항상 0. OpenClaw이 실제로 이 필드를 쓰지 않음 (`tokensAfter` 키 자체가 JSONL에 없음).

---

## 4. Channel/Messaging

### 4.1 누락 플랫폼 10개 (HIGH)

`_BRACKET_CHANNEL_MAP`에 없는 실제 OpenClaw 플랫폼:

| 플랫폼 | 소스 | 브래킷 헤더 |
|--------|------|-----------|
| LINE | `src/line/` | `[LINE ...]` |
| Matrix | `extensions/matrix/` | `[Matrix ...]` |
| MS Teams | `extensions/msteams/` | `[Teams ...]` |
| Mattermost | `extensions/mattermost/` | `[Mattermost ...]` |
| BlueBubbles | `extensions/bluebubbles/` | `[BlueBubbles ...]` |
| Tlon | `extensions/tlon/` | `[Tlon ...]` |
| Twitch | `extensions/twitch/` | `[Twitch ...]` |
| Zalo | `extensions/zalo/` | `[Zalo ...]` |
| Zalo Personal | `extensions/zalouser/` | `[Zalo Personal ...]` |
| Nextcloud Talk | `extensions/nextcloud-talk/` | `[Nextcloud Talk ...]` |

참고: `"irc"` 는 맵에 있지만 **OpenClaw에 IRC 채널은 없음** (팬텀 엔트리).

### 4.2 멀티워드 채널명 감지 불가 (HIGH)

`[Google Chat ...]`, `[Zalo Personal ...]`, `[Nextcloud Talk ...]` — 첫 단어만 추출하는 정규식(`\[(\w+)`)으로는 올바른 채널명 매칭 불가.

### 4.3 Reply/Quote 패턴 불완전 (MEDIUM)

`_REPLY_BLOCK_RE`가 `[Replying to remote-agent id:\d+]`만 매칭. 실제 패턴:
- `[Replying to Alice id:7160]` — 매칭 안 됨
- `[Quoting Bob id:3291]..."quoted text"...[/Quoting]` — 지원 안 됨
- `[Forwarded from OriginUser at ISO_DATE]` — 지원 안 됨

### 4.4 `[from: SENDER]` 접미사 미처리 (MEDIUM)

OpenClaw이 그룹 메시지에 `\n[from: SenderLabel]` 접미사를 추가하는데, ClawTracerX가 이를 파싱하지 않아 `actual_text`에 포함됨.

### 4.5 Slack/Mattermost message_id 형식 차이 (LOW)

Slack: `[slack message id: TS channel: CH]` / Mattermost: `[mattermost message id: ...]` — `[message_id:]` 패턴과 다름.

### 4.6 JSON "Conversation info" 포맷은 레거시 (INFO)

현재 OpenClaw 소스에 이 포맷이 존재하지 않음. 모든 채널이 통합 브래킷 포맷 사용. 기존 JSONL 호환을 위해 유지하되, 주 감지 경로에서 제외 가능.

---

## 5. Schedule

### 5.1 `at`/`every` 스케줄 타입 빈 뱃지 (HIGH)

OpenClaw 스케줄 종류 3가지: `cron`, `at`, `every`. ClawTracerX는 `schedule.expr`만 표시하는데, `at`/`every` 타입에는 `expr` 필드가 없음 → 빈 뱃지.

- `at`: `{"kind":"at", "at":"2026-02-02T04:11:40.000Z"}` — expr 없음
- `every`: `{"kind":"every", "everyMs":1800000}` — expr 없음

### 5.2 `skipped` 상태 미처리 (MEDIUM)

OpenClaw `CronRunStatus`: `"ok"` | `"error"` | `"skipped"`. ClawTracerX 서머리에서 skipped 카운트 안 됨, 시각적으로도 구분 없음.

### 5.3 크론 런 텔레메트리 누락 (MEDIUM)

런 로그에 있지만 파싱하지 않는 필드:

| 필드 | 용도 |
|------|------|
| `runAtMs` | 예정 실행 시간 (지연 감지) |
| `model` / `provider` | 실제 사용 모델 |
| `usage` (토큰) | 크론별 토큰/비용 추적 |
| `nextRunAtMs` | 완료 시점 다음 스케줄 |

### 5.4 하트비트 defaults 미병합 (MEDIUM)

OpenClaw은 `agents.defaults.heartbeat`와 per-agent 설정을 머지함. ClawTracerX는 per-agent만 읽음 → defaults만 설정된 경우 하트비트 0개로 표시.

### 5.5 `activeHours` 포맷 불일치 (MEDIUM)

OpenClaw: `"start": "09:00"` (HH:MM 문자열) / ClawTracerX: 정수 시간으로 처리. 현재 설정에 activeHours가 없어 미발현이지만, 추가 시 렌더링 깨짐.

### 5.6 누락 크론 잡 필드들 (LOW)

| 필드 | 용도 |
|------|------|
| `description` | 잡 설명 |
| `sessionTarget` | `"main"` vs `"isolated"` 실행 모드 |
| `schedule.kind` | 스케줄 타입 구분 |
| `delivery` | 결과 전달 설정 (channel, webhook, none) |
| `deleteAfterRun` | 일회성 잡 표시 |
| `state.lastError` | 마지막 에러 메시지 |
| `state.runningAtMs` | 현재 실행 중 표시 |

---

## 6. Gateway/Lab

### 6.1 미구현 고가치 RPC 메서드 (MEDIUM-HIGH)

현재 7개 구현 / 게이트웨이 84+ 메서드 중:

| 메서드 | 가치 | 용도 |
|--------|------|------|
| `agent.wait` | **HIGH** | 폴링 대신 완료 대기 (정확한 타이밍) |
| `chat.send` | **HIGH** | 스트리밍 응답 + abort 지원 |
| `chat.abort` | **HIGH** | Lab에서 실행 중단 버튼 |
| `sessions.preview` | MEDIUM | JSONL 전체 파싱 없이 프리뷰 |
| `health` / `status` | MEDIUM | 게이트웨이 상태 대시보드 |
| `logs.tail` | MEDIUM | 실시간 로그 뷰어 |
| `usage.cost` | MEDIUM | 캐시된 비용 조회 (30초 캐시) |
| `channels.status` | MEDIUM | 채널 연결 상태 |
| `wake` | LOW | 수동 에이전트 깨우기 |
| `cron.*` | LOW | 크론 관리 (list, run, add, remove) |

### 6.2 Connection-per-call 아키텍처 (LOW-MEDIUM)

매 RPC마다 새 WS → challenge → Ed25519 인증 → RPC → close. 영구 연결로 전환 시:
- 오버헤드 대폭 감소
- 서버 푸시 이벤트 수신 가능 (`agent`, `chat`, `health`, `cron` 이벤트)
- Lab 실시간 스트리밍 가능

### 6.3 이벤트 구독 미활용 (MEDIUM)

게이트웨이 브로드캐스트 이벤트 (`agent`, `chat`, `presence`, `health`, `cron`, `shutdown` 등)를 전부 버림 (`# Skip events`). 영구 연결 + 이벤트 구독으로 JSONL 폴링 대체 가능.

---

## 7. Cost/Token

### 7.1 Fallback 비용 추정 없음 (MEDIUM)

`usage.cost` 누락 시 ClawTracerX는 $0 기록. OpenClaw은 `openclaw.json`의 모델 가격표로 추정 (`estimateUsageCost()`).

### 7.2 `missingCostEntries` 추적 없음 (LOW)

비용 데이터 누락 건수를 추적하지 않아, 대시보드 비용이 실제보다 낮을 수 있다는 경고 없음.

### 7.3 Gateway `usage.cost` RPC 미사용 (MEDIUM)

OpenClaw 게이트웨이에 30초 캐시 비용 API 있음. ClawTracerX는 매번 전체 JSONL 스캔 → 느림.

### 7.4 OAuth 세션 비용 표시 (LOW)

OpenClaw은 `authMode === "api-key"`인 경우만 비용 표시. ClawTracerX는 무차별 표시 → OAuth 세션에서 $0.00 또는 부정확한 값.

### 7.5 서브에이전트별 비용 미표시 (LOW)

`SubagentSpawn.cost_usd` 데이터는 있지만 비용 대시보드에 반영 안 됨.

---

## 8. Priority Matrix

### P0 — 즉시 수정 (실제 기능 오류)

| ID | 영역 | 설명 |
|----|------|------|
| BUG-01 | Gateway | `sessions.patch` 키 오류 → 항상 실패 |
| BUG-02 | Gateway | `sessions.reset` 키 오류 → 항상 실패 |
| BUG-04 | Schedule | 타임존 필드명 불일치 → 미표시 |
| BUG-05 | Schedule | systemEvent payload `text` 미읽기 |

### P1 — 높은 우선순위 (데이터 정확성)

| ID | 영역 | 설명 |
|----|------|------|
| 2.1 | Sessions | `hook`/`node`/`group` 세션 타입 오분류 |
| 2.2 | Sessions | 서브에이전트 감지 경로 기반 → 실패 |
| 4.1 | Channel | 10개 플랫폼 감지 누락 |
| 4.2 | Channel | 멀티워드 채널명 감지 불가 |
| 5.1 | Schedule | `at`/`every` 스케줄 빈 뱃지 |
| BUG-03 | Gateway | Lab 모델 선택 무효 |

### P2 — 중간 우선순위 (기능 개선)

| ID | 영역 | 설명 |
|----|------|------|
| 2.3 | Sessions | sessions.json 활용 (성능 + 데이터) |
| 3.1 | Detail | `openclaw:prompt-error` 이벤트 미처리 |
| 3.2 | Detail | 서브에이전트 에러 사유 누락 |
| 3.3 | Detail | stopReason 시각 구분 |
| 4.3 | Channel | Reply/Quote/Forward 패턴 불완전 |
| 5.2 | Schedule | `skipped` 상태 미처리 |
| 5.3 | Schedule | 크론 런 텔레메트리 누락 |
| 5.4 | Schedule | 하트비트 defaults 미병합 |
| 6.1 | Lab | `chat.abort` 구현 (중단 버튼) |
| 6.1 | Lab | `agent.wait` 구현 (폴링 대체) |
| 7.1 | Cost | Fallback 비용 추정 |
| 7.3 | Cost | Gateway `usage.cost` RPC 활용 |

### P3 — 낮은 우선순위 (향후 개선)

| ID | 영역 | 설명 |
|----|------|------|
| 2.4 | Sessions | 인코딩/레이스 컨디션 안정성 |
| 4.4 | Channel | `[from: SENDER]` 접미사 처리 |
| 4.5 | Channel | Slack/Mattermost message_id 형식 |
| 5.5 | Schedule | activeHours HH:MM 포맷 처리 |
| 5.6 | Schedule | 누락 크론 잡 메타데이터 |
| 6.2 | Lab | 영구 WS 연결 |
| 6.3 | Lab | 이벤트 구독 (실시간) |
| 7.2 | Cost | missingCostEntries 추적 |
| 7.4 | Cost | OAuth 세션 비용 필터링 |
| 7.5 | Cost | 서브에이전트별 비용 대시보드 |

---

## 핵심 인사이트 요약

1. **sessions.json 미활용이 가장 큰 구조적 문제**: 세션 타입 분류, 서브에이전트 감지, 토큰 카운터, 메타데이터 대부분이 sessions.json에 이미 있음. 현재는 전체 JSONL 스캔에 의존하여 느리고 부정확함.

2. **Gateway RPC 파라미터 오류 2건은 즉시 수정 필요**: `sessions.patch`/`sessions.reset`가 항상 실패하는 상태.

3. **채널 감지는 상당한 리팩터링 필요**: 10개 플랫폼 누락 + 멀티워드 채널명 + reply/quote 패턴. 통합 브래킷 포맷 파서를 OpenClaw의 `formatInboundEnvelope` 출력 형식에 맞게 재작성하는 것이 권장됨.

4. **Lab의 잠재력이 크게 미활용**: 84+ RPC 중 7개만 구현. `chat.abort`(중단), `agent.wait`(폴링 대체), `chat.send`(스트리밍)이 가장 가치 높은 추가 대상.

5. **스케줄 시스템은 `cron` 타입만 제대로 처리**: `at`/`every` 타입과 `skipped` 상태가 빠져있어 실제 운영 시 혼란 유발.
