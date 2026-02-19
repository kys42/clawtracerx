# OpenClaw Agent 내부 구조 완전 가이드

> ocmon 개발 과정에서 실제 데이터 탐색을 통해 확인한 OpenClaw 에이전트 플랫폼의 내부 동작, 데이터 구조, 이벤트 흐름에 대한 상세 문서.
> 작성일: 2026-02-20

---

## 1. 디렉터리 구조

```
~/.openclaw/
├── openclaw.json              # 메인 설정 (에이전트 defaults, 채널, 모델, 스킬, 게이트웨이 등)
├── exec-approvals.json        # 실행 승인 설정 (보안 모드, 소켓 경로)
├── .env                       # 환경변수 (DISCORD_BOT_TOKEN 등)
├── update-check.json          # 마지막 업데이트 체크 시각
│
├── agents/                    # 에이전트별 데이터
│   ├── main/
│   │   ├── agent/
│   │   │   ├── auth.json          # 에이전트 인증 설정
│   │   │   ├── auth-profiles.json # OAuth/API 키 프로필 (토큰, 만료, 사용 통계)
│   │   │   └── models.json        # 에이전트별 모델 오버라이드
│   │   └── sessions/
│   │       ├── {uuid}.jsonl                     # 활성 세션 파일
│   │       ├── {uuid}-topic-{id}.jsonl          # 텔레그램 토픽 세션
│   │       └── {uuid}.jsonl.deleted.{ISO-ts}    # soft-delete된 서브에이전트 세션
│   ├── aki/
│   ├── ddokddoki/
│   └── guardian/
│
├── cron/
│   ├── jobs.json              # 크론 잡 정의 (스케줄, 페이로드, 배달 설정, 상태)
│   └── runs/
│       └── {jobId}.jsonl      # 잡별 실행 이력 (started/finished 이벤트)
│
├── subagents/
│   └── runs.json              # 서브에이전트 실행 레지스트리 (version 2)
│
├── memory/
│   ├── main.sqlite            # 에이전트별 기억 DB (main: 118MB, aki: 56MB)
│   ├── aki.sqlite
│   ├── ddokddoki.sqlite
│   └── guardian.sqlite
│
├── shared-workspace/
│   ├── GLOBAL_RULES.md        # 전역 운영 규칙
│   ├── WHERE_TO_PUT_THINGS.md # 파일 배치 가이드
│   ├── memory/                # 공유 기억 저장소
│   └── templates/             # 공유 템플릿
│
├── credentials/               # 인증 정보 (discord-pairing.json 등)
├── delivery-queue/            # 메시지 배달 큐 (failed/ 하위 디렉터리)
├── logs/
│   ├── gateway.log            # 게이트웨이 활동 로그
│   ├── gateway.err.log        # 게이트웨이 에러 로그
│   ├── commands.log           # 명령어 로그
│   └── config-audit.jsonl     # 설정 변경 감사 로그
├── audit/                     # 감사 데이터 (guardian 하위)
├── browser/                   # 브라우저 프로필 데이터
├── bin/                       # 셸 자동완성 스크립트
├── workspace/                 # main 에이전트 작업 공간
├── workspace-aki/             # aki 에이전트 작업 공간
├── workspace-ddokddoki/       # ddokddoki 에이전트 작업 공간
├── workspace-guardian/         # guardian 에이전트 작업 공간
└── worktrees/                 # Git worktree 관리
```

---

## 2. 세션 JSONL 파일 포맷

세션 파일은 **줄 단위 JSON (JSONL)** 형식. 각 줄은 하나의 이벤트.

### 2.1 공통 필드

모든 이벤트에 존재하는 필드:
```json
{
  "type": "이벤트_타입",
  "id": "8자리_hex",        // e.g. "3fd81255" - 이벤트 고유 ID
  "parentId": "8자리_hex",  // 이전 이벤트 ID (첫 이벤트는 null)
  "timestamp": "ISO_8601"   // e.g. "2026-02-16T13:38:38.652Z"
}
```

### 2.2 이벤트 타입별 구조

#### `session` — 세션 초기화
```json
{
  "type": "session",
  "version": 3,
  "id": "uuid-전체형",        // 세션 초기화 이벤트만 전체 UUID 사용
  "timestamp": "2026-02-15T15:00:00.377Z",
  "cwd": "/Users/kys/.openclaw/workspace"
}
```

#### `model_change` — 모델 전환
```json
{
  "type": "model_change",
  "id": "5fcfd33d",
  "provider": "openai-codex",      // google, openai-codex, moonshot 등
  "modelId": "gpt-5.2"             // gemini-3-flash-preview, kimi-k2.5 등
}
```

#### `thinking_level_change` — 사고 수준 변경
```json
{
  "type": "thinking_level_change",
  "thinkingLevel": "low"           // "low" | "high"
}
```

#### `message` — 메시지 (핵심 이벤트)

**User 메시지:**
```json
{
  "type": "message",
  "id": "dfd1effa",
  "message": {
    "role": "user",
    "content": [
      {"type": "text", "text": "메시지 본문"}
    ],
    "timestamp": 1771167600380     // ms epoch
  }
}
```

**Assistant 메시지:**
```json
{
  "type": "message",
  "id": "abc12345",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "text", "text": "응답 본문", "textSignature": "..."},
      {"type": "thinking", "thinking": "사고 내용", "thinkingSignature": "..."},
      {"type": "toolCall", "id": "tc_uuid", "name": "tool_name", "arguments": {...}}
    ],
    "timestamp": 1771167601500,
    "model": "gpt-5.2",
    "provider": "openai-codex",
    "api": "openai-codex-responses",
    "stopReason": "stop",          // "stop" | "tool_use" | "length" | "content_filter"
    "usage": {
      "input": 15746,
      "output": 13,
      "cacheRead": 0,
      "cacheWrite": 0,
      "totalTokens": 15759,
      "cost": {
        "input": 0.007873,
        "output": 0.000039,
        "cacheRead": 0,
        "cacheWrite": 0,
        "total": 0.007912
      }
    }
  }
}
```

**toolResult 메시지:**
```json
{
  "type": "message",
  "id": "def67890",
  "message": {
    "role": "toolResult",
    "toolCallId": "tc_uuid",
    "toolName": "exec",
    "isError": false,
    "content": [
      {"type": "text", "text": "실행 결과"}
    ],
    "details": {
      "durationMs": 1234,
      "status": "ok",              // "ok" | "error"
      "error": null,
      "childSessionKey": "...",    // sessions_spawn 전용
      "runId": "..."               // sessions_spawn 전용
    }
  }
}
```

#### `compaction` — 컨텍스트 압축
```json
{
  "type": "compaction",
  "id": "e51f5939",
  "timestamp": "2026-02-11T09:57:26.379Z",
  "summary": "## Goal\n- 압축된 컨텍스트 요약...",
  "firstKeptEntryId": "c40df7d5",  // 이 ID 이전의 모든 entry는 context에서 제거
  "tokensBefore": 89824,            // 압축 전 토큰 수
  "details": {
    "readFiles": [],
    "modifiedFiles": []
  },
  "fromHook": false
}
```

#### `custom` — 커스텀 이벤트
```json
{
  "type": "custom",
  "customType": "model-snapshot",
  "data": {
    "timestamp": 1771167600377,
    "provider": "openai-codex",
    "modelApi": "openai-codex-responses",
    "modelId": "gpt-5.2"
  }
}
```

### 2.3 이벤트 빈도 (실제 대규모 세션 기준)

| 이벤트 타입 | 빈도 | 비고 |
|------------|------|------|
| `message` | ~93% | user + assistant + toolResult |
| `custom` | ~4% | model-snapshot 등 |
| `session` | ~1% | 세션 시작 |
| `thinking_level_change` | ~1% | LLM thinking 수준 변경 |
| `model_change` | ~0.8% | 모델/provider 전환 |
| `compaction` | ~0.3% | 컨텍스트 윈도우 압축 |

---

## 3. 메시지 content 블록 타입

Assistant 메시지의 `content` 배열에 들어가는 블록 타입:

### 3.1 `text` — 텍스트 응답
```json
{"type": "text", "text": "응답 내용", "textSignature": "서명(옵션)"}
```
- **주의**: 빈 텍스트 블록 `{"type":"text","text":""}` 이 삽입될 수 있음 → 파싱 시 필터링 필요

### 3.2 `thinking` — 사고 과정
```json
{"type": "thinking", "thinking": "사고 내용 텍스트", "thinkingSignature": "..."}
```
- **Google 모델** (Gemini): thinking이 **평문**으로 들어옴 (약 61%)
- **OpenAI 모델**: thinking이 Fernet 암호화되어 들어옴 → signature만 존재, thinking 필드 비어있음
- **signature 판별**: `thinkingSignature`가 존재하면서 `thinking`이 비어있으면 → 암호화됨

### 3.3 `toolCall` — 도구 호출
```json
{"type": "toolCall", "id": "tc_unique_id", "name": "tool_name", "arguments": {...}}
```

**주요 도구 목록:**
| 도구명 | 설명 | 주요 인자 |
|--------|------|----------|
| `read` | 파일 읽기 | `file_path` |
| `write` | 파일 쓰기 | `file_path`, `content` |
| `edit` | 파일 편집 | `file_path`, `old_text`, `new_text` |
| `exec` | 명령 실행 | `command`, `timeout` |
| `glob` | 파일 검색 | `pattern`, `path` |
| `grep` | 내용 검색 | `pattern`, `path`, `type` |
| `sessions_spawn` | 서브에이전트 생성 | `label`, `task`/`prompt`, `model` |
| `sessions_send` | 세션에 메시지 전송 | `sessionKey`, `message` |
| `fetch` | HTTP 요청 | `url`, `method` |
| `message` | 채널 메시지 전송 | `to`, `text` |
| `broadcast` | 브로드캐스트 | `channels`, `text` |
| `session_status` | 세션 상태 조회 | |
| `sessions_history` | 세션 이력 조회 | `sessionKey`, `limit` |

---

## 4. 서브에이전트 lifecycle

### 4.1 전체 흐름

```
1. 부모 세션 → toolCall(sessions_spawn) 발생
   arguments: {label: "task-label", task: "지시 내용", model: "모델명"}

2. toolResult 반환
   details: {childSessionKey: "agent:name:subagent:UUID-A", runId: "UUID-B"}

3. 자식 세션 JSONL 생성
   경로: ~/.openclaw/agents/{agentId}/sessions/{UUID-C}.jsonl
   (주의: UUID-C ≠ UUID-A, UUID-C ≠ UUID-B — 모두 다른 UUID)

4. 서브에이전트 실행 (독립 컨텍스트)

5. 실행 완료 → announce 메시지가 부모 세션에 user 메시지로 전달
   포맷: [Day YYYY-MM-DD HH:MM TZ] A subagent task "label" just completed...
   Stats: runtime Xm Ys • tokens XK (in XK / out XK) • sessionKey agent:name:subagent:UUID-A • sessionId UUID-C • transcript /path/to/UUID-C.jsonl

6. 자식 세션 JSONL soft-delete
   UUID-C.jsonl → UUID-C.jsonl.deleted.{ISO-timestamp}

7. subagents/runs.json에 실행 기록 업데이트
```

### 4.2 핵심 UUID 구분

서브에이전트에는 **3가지 다른 UUID**가 관여:

| UUID | 출처 | 용도 |
|------|------|------|
| `childSessionKey`의 UUID | toolResult.details.childSessionKey에서 추출 | 세션 파일명 매칭에 사용 (파일명 = 이 UUID.jsonl) |
| `runId` | toolResult.details.runId | subagents/runs.json의 키 |
| `sessionId` | announce 메시지의 Stats에 포함 | 실행 세션의 내부 ID (파일명과 다를 수 있음!) |

**중요**: `sessionKey`의 UUID가 파일명에 사용됨. `sessionId`는 다른 값이므로 매칭에 사용하면 안 됨!

### 4.3 announce 메시지 포맷

**일반:**
```
[Mon 2026-02-16 19:16 GMT+9] A subagent task "ys-pr10-dev-review-050" just completed successfully.

Findings:
(서브에이전트 응답 요약)

Stats: runtime 7s • tokens 37.9k (in 37.9k / out 722) • sessionKey agent:aki:subagent:4b2e01b3-9f2e-4d29-92ab-7d45615ed9d7 • sessionId f8cdd613-46e9-43ad-b2a4-a3f5460d05c7 • transcript /Users/kys/.openclaw/agents/aki/sessions/f8cdd613-46e9-43ad-b2a4-a3f5460d05c7.jsonl

Summarize this naturally for the user...
```

**대기 큐 (agent busy 중 쌓인 announces):**
```
[Mon 2026-02-16 19:41 GMT+9] [Queued announce messages while agent was busy]

---
Queued #1
A subagent task "label-1" just completed successfully.
...Stats: ...

---
Queued #2
A subagent task "label-2" just completed...
...Stats: ...
```

### 4.4 soft-delete 패턴

```
원본: f8cdd613-46e9-43ad-b2a4-a3f5460d05c7.jsonl
삭제: f8cdd613-46e9-43ad-b2a4-a3f5460d05c7.jsonl.deleted.2026-02-16T11-15-43.777Z
```

- 타임스탬프의 `:` → `-`로 치환 (파일명 호환)
- 파일 내용은 그대로 보존 (삭제가 아닌 rename)
- `cleanup` 필드가 `"delete"`이면 soft-delete, `"keep"`이면 유지

### 4.5 runs.json 구조

```json
{
  "version": 2,
  "runs": {
    "runId-uuid": {
      "runId": "uuid",
      "childSessionKey": "agent:name:subagent:uuid",
      "requesterSessionKey": "agent:name:main",
      "requesterOrigin": {
        "channel": "telegram",
        "to": "telegram:userId",
        "accountId": "default"
      },
      "task": "서브에이전트에 전달된 지시",
      "cleanup": "keep|delete",
      "expectsCompletionMessage": true,
      "model": "모델명",
      "runTimeoutSeconds": 0,
      "createdAt": 1771516932622,      // ms epoch
      "startedAt": 1771516945072,
      "endedAt": 1771516948966,
      "archiveAtMs": 1771520532622,
      "cleanupHandled": true,
      "cleanupCompletedAt": 1771516947801,
      "outcome": {
        "status": "ok|error",
        "message": "결과 메시지"
      }
    }
  }
}
```

---

## 5. Compaction (컨텍스트 윈도우 압축)

### 5.1 동작 원리

에이전트의 컨텍스트 윈도우가 가득 차면 `compaction` 이벤트가 발생:
1. `tokensBefore`: 압축 전 컨텍스트 토큰 수 (보통 250K~300K)
2. `firstKeptEntryId`: 압축 후 남겨진 첫 번째 entry의 ID
3. `summary`: 압축된 내용의 텍스트 요약
4. 이 ID 이전의 모든 entry는 LLM 컨텍스트에서 제거됨

### 5.2 컨텍스트 경계 계산

```python
# entry ID 순서에서 firstKeptEntryId의 위치 찾기
entry_ids = [entry["id"] for entry in all_entries if entry.get("id")]
kept_pos = entry_ids.index(compaction.first_kept_entry_id)

# kept_pos 이전의 모든 entry가 포함된 turn → out of context
evicted_ids = set(entry_ids[:kept_pos])
```

### 5.3 실측 데이터

aki 에이전트의 대규모 세션 (98dfebb5, 1030턴):
- 8회 compaction 발생
- 각 compaction 시 tokensBefore: 252K ~ 302K
- 780턴 compacted (context 밖), 250턴 in-context
- compaction 간격: 수 시간 (heartbeat 기반 장기 실행 세션)

---

## 6. 크론 시스템

### 6.1 잡 정의 (`cron/jobs.json`)

```json
{
  "id": "job-uuid",
  "agentId": "main",
  "name": "Daily Keep List Reminder",
  "enabled": true,
  "schedule": {
    "kind": "cron",         // "cron" | "at" | "every"
    "expr": "0 10 * * *",  // cron 표현식
    "tz": "Asia/Seoul",    // 타임존
    "everyMs": 300000,     // every 타입: 반복 간격 (ms)
    "anchorMs": 1771248206070,  // every 타입: 기준 시각
    "staggerMs": 300000    // every 타입: jitter
  },
  "sessionTarget": "isolated",  // "isolated" (새 세션) | "main" (기존 세션 재사용)
  "wakeMode": "now",            // "now" | "next-heartbeat"
  "payload": {
    "kind": "agentTurn",        // "agentTurn" | "systemEvent"
    "message": "[cron:jobId] 실행 지시...",
    "model": "google/gemini-3-flash-preview",
    "timeoutSeconds": 1800
  },
  "delivery": {
    "mode": "announce",         // "announce" | "none"
    "to": "telegram:-1003886593826:1",
    "channel": "telegram",
    "bestEffort": true
  },
  "state": {
    "nextRunAtMs": 1771549200000,
    "lastRunAtMs": 1771462800011,
    "lastStatus": "ok",
    "lastDurationMs": 31755,
    "consecutiveErrors": 0
  }
}
```

### 6.2 실행 로그 (`cron/runs/{jobId}.jsonl`)

```json
{"ts": 1771297518369, "jobId": "uuid", "action": "finished", "status": "ok",
 "summary": "실행 결과 요약", "sessionId": "session-uuid",
 "sessionKey": "agent:aki:cron:jobId:run:sessionId",
 "durationMs": 268962, "nextRunAtMs": 1771318800000}
```

### 6.3 현재 운용 중인 크론 잡 예시

- Daily Keep List Reminder
- Daily Memory-Based Insight (Morning)
- Daily Reddit Analysis
- Daily Notion Task Summary (Morning/Evening)
- Nightly Daily Review & Self-Update
- Aki Project Autopilot (TODO-driven)
- AgentOps: TODO archive/cleanup

---

## 7. 세션 키 포맷

세션 키는 에이전트, 세션 타입, 식별자를 `:` 로 연결한 문자열:

```
agent:{agentId}:{sessionType}:{identifier}
```

| 패턴 | 설명 | 예시 |
|------|------|------|
| `agent:main:main` | 메인 DM 세션 | |
| `agent:main:telegram:group:{groupId}:topic:{topicId}` | 텔레그램 그룹 토픽 | |
| `agent:main:discord:{guildId}:{channelId}` | 디스코드 채널 | |
| `agent:aki:cron:{jobId}:run:{sessionId}` | 크론 실행 세션 | |
| `agent:ddokddoki:subagent:{uuid}` | 서브에이전트 세션 | |

---

## 8. 채널 및 메시지 소스

### 8.1 user 메시지 소스 판별

| 패턴 | 소스 | 의미 |
|------|------|------|
| `[cron:{jobId}]...` | cron | 크론 잡 트리거 |
| `[heartbeat...]` / `Read HEARTBEAT.md` | heartbeat | 하트비트 자동 실행 |
| `[System Message] A subagent task...` | subagent_announce | 서브에이전트 완료 알림 |
| `[System Message] A cron job...` | cron_announce | 크론 잡 완료 알림 |
| `[System Message]...` | system | 기타 시스템 메시지 |
| `[Day YYYY-MM-DD ...] A subagent task...` | subagent_announce | 타임스탬프 형식 |
| `[Day YYYY-MM-DD ...] A cron job...` | cron_announce | 타임스탬프 형식 |
| `[Day YYYY-MM-DD ...] [Queued announce...]` | subagent_announce | 대기 큐 묶음 |
| `[message_id: N]` + discord 키워드 | discord | 디스코드 채널 메시지 |
| `[message_id: N]` + telegram 키워드 | telegram | 텔레그램 메시지 |
| 기타 | chat | 직접 대화 |

### 8.2 배달 대상 포맷

```
telegram:{userId}              # 텔레그램 DM
telegram:{groupId}:{topicId}   # 텔레그램 그룹 토픽
discord:{channelId}            # 디스코드 채널
channel:discord:{channelId}    # 디스코드 채널 (대체 형식)
```

---

## 9. 모델 및 Provider

### 9.1 확인된 모델 목록

| Provider | 모델 ID | 비고 |
|----------|---------|------|
| openai-codex | gpt-5.2 | 기본 모델 |
| openai-codex | gpt-5.3-codex | fallback |
| openai-codex | gpt-5.2-codex | fallback |
| google | gemini-3-flash-preview | fallback / 크론 기본 |
| google | gemini-2.5-flash | fallback |
| moonshot | kimi-k2.5 | 커스텀 provider |

### 9.2 Provider 인증 방식

| Provider | 인증 | API |
|----------|------|-----|
| openai-codex | OAuth (access/refresh 토큰) | openai-codex-responses |
| google | API Key | google-generative-ai |
| moonshot | API Key | openai-completions (호환) |

### 9.3 사용 통계 추적

`auth-profiles.json`의 `usageStats`에서 provider별:
- `lastUsed`: 마지막 사용 시각
- `errorCount`: 누적 에러 수
- `failureCounts`: 에러 유형별 카운트 (`rate_limit`, `timeout`)
- `cooldownUntil`: rate limit 시 쿨다운 만료 시각

---

## 10. 토큰/비용 추적

### 10.1 추적 단위

- **단위**: assistant 메시지 하나당 `usage` 객체
- **제한**: per-tool-call 단위 추적은 불가 (JSONL 구조 한계)
- **축적**: 하나의 Turn에 여러 assistant 메시지 → usage 합산

### 10.2 비용 필드

```json
{
  "usage": {
    "input": 15746,       // 입력 토큰
    "output": 13,         // 출력 토큰
    "cacheRead": 0,       // 캐시 읽기 토큰
    "cacheWrite": 0,      // 캐시 쓰기 토큰
    "totalTokens": 15759, // 전체 토큰
    "cost": {
      "input": 0.007873,     // USD
      "output": 0.000039,
      "cacheRead": 0,
      "cacheWrite": 0,
      "total": 0.007912      // 총 비용 USD
    }
  }
}
```

### 10.3 실측 데이터

- aki 에이전트 주간 비용: 수백 달러 (대규모 자동화)
- 대형 세션 (1030턴): 수천만 토큰
- compaction 발생 시점: 약 250K~300K 토큰

---

## 11. Thinking (사고 과정) 데이터

### 11.1 모델별 동작

| 모델 | thinking 필드 | 판독 가능 |
|------|--------------|----------|
| Google (Gemini) | 평문 텍스트 | O (약 61%) |
| OpenAI (GPT) | 비어있음 (암호화) | X |

### 11.2 암호화 판별 로직

```python
if thinkingSignature and not thinking_text:
    # 암호화된 thinking
elif thinkingSignature and isinstance(thinkingSignature, dict):
    # 암호화된 thinking
elif thinkingSignature and "encrypted" in thinkingSignature.lower():
    # 명시적 암호화
else:
    # 평문 thinking
```

---

## 12. 감사 로그 (`logs/config-audit.jsonl`)

설정 파일 변경 시 자동 기록:

```json
{
  "ts": "2026-02-19T11:59:41.762Z",
  "source": "config-io",
  "event": "config.write",
  "configPath": "/Users/kys/.openclaw/openclaw.json",
  "pid": 97073,
  "argv": ["node", "openclaw.mjs", "doctor", "--generate-gateway-token"],
  "existsBefore": true,
  "previousHash": "f366f256...",
  "nextHash": "8e131b3a...",
  "changedPathCount": 5,
  "suspicious": [],
  "result": "rename"
}
```

---

## 13. 기억 시스템 (`memory/`)

- SQLite 데이터베이스 (에이전트당 1개)
- main: 118.5MB, aki: 55.8MB (장기 운용 에이전트)
- ddokddoki: 69KB, guardian: 102KB (소규모 에이전트)
- `memorySearch.extraPaths`로 공유 기억 경로 추가 가능

---

## 14. 게이트웨이

```json
{
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "loopback",
    "auth": {"mode": "token", "token": "..."},
    "tailscale": {"mode": "off"}
  }
}
```

- 로컬 HTTP 게이트웨이 (포트 18789)
- 토큰 인증
- Tailscale 통합 가능 (현재 off)

---

## 15. 스킬 시스템

### 15.1 번들 스킬

```
browser-manager, exa-web-search-free, keep, self-updater,
session-monitor, coding-agent, github, healthcheck, skill-creator
```

### 15.2 커스텀 스킬

- 로드 경로: `~/.openclaw/workspace/skills/`
- `skill-creator` 스킬로 새 스킬 생성 가능

---

## 16. 파싱 팁 및 주의사항

### 16.1 파싱 시 주의

1. **빈 text 블록**: `{"type":"text","text":""}` 필터링 필요
2. **deleted 파일**: 서브에이전트 세션은 `.jsonl.deleted.*`로 rename됨
3. **session_id 추출**: `.jsonl.deleted.*` 파일에서 stem 사용 시 `.jsonl` 기준으로 분리
4. **sessionKey vs sessionId**: 서브에이전트에서 이 둘은 다른 UUID — sessionKey의 UUID가 파일명
5. **timestamp 형식**: entry 레벨은 ISO 8601, message 레벨은 ms epoch
6. **announce 메시지**: `[System Message]` 또는 `[Day YYYY-MM-DD ...]` 두 가지 접두사
7. **queued announces**: agent busy 시 여러 announce가 하나의 user 메시지로 묶임

### 16.2 Turn 구조화

```
Turn = user 메시지 시작 → 다음 user 메시지 직전까지의 모든 이벤트
  - user message (1개)
  - assistant messages (N개, 각각 usage 포함)
  - toolResult messages (N개, toolCall과 id로 매칭)
```

### 16.3 비용 계산

```python
total_cost = sum(turn.cost["total"] for turn in turns)
# 주의: 서브에이전트 비용은 부모 세션 비용에 포함되지 않음
# 서브에이전트 비용은 별도로 자식 세션을 파싱하여 합산해야 함
```

---

## 부록: ocmon 분석 도구

이 문서의 데이터 소스인 `ocmon` 도구:
- 경로: `~/.openclaw/tools/ocmon/`
- CLI: `ocmon sessions|analyze|raw|crons|subagents|cost`
- 웹: `ocmon web` → http://localhost:8901
- 파서: `parser.py` — 이 문서에 기술된 모든 구조를 파싱
