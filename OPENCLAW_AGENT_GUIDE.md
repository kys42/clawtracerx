# OpenClaw Agent 내부 구조 완전 가이드

> ocmon 개발 과정에서 실제 데이터 탐색을 통해 확인한 OpenClaw 에이전트 플랫폼의 내부 동작, 데이터 구조, 이벤트 흐름에 대한 상세 문서.
> 작성일: 2026-02-20 (sessions.json 메타데이터, 부트스트랩 체인, 디버그 인터페이스 추가)

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
│   │       ├── sessions.json                     # ★ 세션 메타데이터 (SystemPromptReport, 토큰 카운터)
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

### 4.2 핵심 UUID 구분 ⚠️

서브에이전트에는 **3가지 다른 UUID**가 관여하며, **모두 다른 값**:

| UUID | 출처 | 용도 |
|------|------|------|
| `childSessionKey`의 UUID | `toolResult.details.childSessionKey` | 게이트웨이 라우팅용 — **파일명 아님** |
| `runId` | `toolResult.details.runId` | `subagents/runs.json`의 키 |
| **실제 sessionId** | announce 메시지에서만 얻을 수 있음 | **JSONL 파일명 UUID** — 이것으로 파일을 찾아야 함 |

```
childSessionKey: agent:aki:subagent:2858690d-...  ← 라우팅 키 UUID (파일명 아님)
실제 파일:        83aead09-....jsonl.deleted.*       ← 다른 UUID!
```

**파일 찾는 방법**: announce 메시지에서 실제 sessionId를 추출해야 함.

### 4.3 announce 메시지 포맷 (2종)

**구버전** (2026-02 중순 이전): Stats 안에 sessionKey, sessionId, transcript 포함
```
[Mon 2026-02-16 19:16 GMT+9] A subagent task "ys-pr10-dev-review-050" just completed successfully.

Findings:
(서브에이전트 응답 요약)

Stats: runtime 7s • tokens 37.9k (in 37.9k / out 722) • sessionKey agent:aki:subagent:UUID-A • sessionId UUID-C • transcript /path/UUID-C.jsonl

Summarize this naturally for the user...
```
→ `sessionId UUID-C` 부분에서 실제 파일 UUID를 직접 얻을 수 있음

**신버전** (2026-02 중순 이후): sessionId가 prefix에, Stats는 runtime+tokens만
```
[Fri 2026-02-20 19:20 GMT+9] [System Message] [sessionId: UUID-C] A subagent task "ys-scraps-detail-body-render-172" just completed successfully.

Result:
(서브에이전트 응답 요약)

Stats: runtime 4m52s • tokens 69.4k (in 63.4k / out 6.0k)

A completed subagent task is ready for user delivery...
```
→ `[sessionId: UUID-C]` prefix에서 실제 파일 UUID를 얻음

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

### 4.4 서브에이전트 컨텍스트 제한

> 소스: `src/agents/workspace.ts` — `filterBootstrapFilesForSession()`

서브에이전트는 부모와 다른 **제한된 부트스트랩 컨텍스트**를 받음:

| 세션 타입 | 주입 파일 | 비고 |
|-----------|----------|------|
| 메인/크론 세션 | AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md, HEARTBEAT.md, BOOTSTRAP.md, MEMORY.md | 최대 8개 파일 |
| 서브에이전트 | **AGENTS.md, TOOLS.md만** | 나머지 6개 파일 제외 |

```typescript
// workspace.ts에서 서브에이전트 세션 판별
if (sessionKey.includes(":subagent:")) {
    // AGENTS.md와 TOOLS.md만 필터링하여 반환
}
```

- 서브에이전트는 SOUL.md(인격), MEMORY.md(기억), HEARTBEAT.md 등을 받지 못함
- `sessions.json`의 `injectedWorkspaceFiles`에서 세션별로 실제 주입된 파일 확인 가능
- 이 정보로 세션 타입(메인 vs 서브에이전트)을 역추론할 수 있음

### 4.5 soft-delete 패턴

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

> 소스: `src/agents/pi-embedded-runner/compact.ts`

에이전트의 컨텍스트 윈도우가 가득 차면 `compaction` 이벤트가 발생:
1. `tokensBefore`: 압축 전 컨텍스트 토큰 수 (보통 250K~300K)
2. `tokensAfter`: 압축 후 컨텍스트 토큰 수
3. `firstKeptEntryId`: 압축 후 남겨진 첫 번째 entry의 ID
4. `summary`: 압축된 내용의 마크다운 텍스트 요약 (## Goal, ## Key Decisions 등)
5. `fromHook`: hook에 의한 강제 compaction 여부 (boolean)
6. `details.readFiles`, `details.modifiedFiles`: 압축 시점의 파일 목록
7. 이 ID 이전의 모든 entry는 LLM 컨텍스트에서 제거됨

### 5.2 컨텍스트 경계 계산

```python
# entry ID 순서에서 firstKeptEntryId의 위치 찾기
entry_ids = [entry["id"] for entry in all_entries if entry.get("id")]
kept_pos = entry_ids.index(compaction.first_kept_entry_id)

# kept_pos 이전의 모든 entry가 포함된 turn → out of context
evicted_ids = set(entry_ids[:kept_pos])
```

### 5.3 Pre-Compaction 메모리 플러시

> 소스: `src/auto-reply/reply/memory-flush.ts`

Compaction 직전에 자동으로 **메모리 플러시**가 실행됨:

1. 현재 컨텍스트에서 중요 정보를 추출
2. `memory/YYYY-MM-DD.md` 파일로 저장
3. `sessions.json`의 `memoryFlushAt` 타임스탬프 갱신
4. 이후 compaction 실행

이 메커니즘으로 compaction으로 사라지는 컨텍스트 정보가 기억 시스템에 보존됨.

### 5.4 실측 데이터

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

### 10.3 캐시 히트율

Assistant 메시지의 `usage`에서 캐시 효율 계산:

```python
cache_hit_rate = cacheRead / (cacheRead + input)
# 예: cacheRead=224K, input=568K → cache_hit = 28.3%
```

- 캐시 히트율이 높을수록 비용 절감 (캐시 읽기가 신규 입력보다 저렴)
- 장기 세션에서 컨텍스트가 안정화되면 캐시 히트율 상승
- Compaction 직후에는 캐시 히트율 급락 (새 요약으로 컨텍스트 변경)

### 10.4 세션 레벨 토큰 카운터 (sessions.json)

`sessions.json`에는 세션 전체의 누적 토큰 카운터가 있음:

| 필드 | 설명 |
|------|------|
| `contextTokens` | 세션 초기 컨텍스트 토큰 수 |
| `inputTokens` | 세션 전체 누적 입력 토큰 |
| `outputTokens` | 세션 전체 누적 출력 토큰 |
| `totalTokens` | 세션 전체 누적 총 토큰 |
| `compactionCount` | 세션 내 compaction 발생 횟수 |
| `memoryFlushAt` | 마지막 메모리 플러시 시각 (ISO 8601) |

이 값들은 JSONL의 턴별 usage 합산값과 대략 일치하나, sessions.json 값이 런타임 누적이므로 더 정확함.

### 10.5 실측 데이터

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

## 16. sessions.json 메타데이터

> **핵심 발견**: JSONL에는 초기 컨텍스트 정보가 기록되지 않으나, `sessions.json`에 `SystemPromptReport`가 이미 저장되어 있음.

### 16.1 파일 위치 및 구조

```
~/.openclaw/agents/{agentId}/sessions/sessions.json
```

플랫 JSON 객체. 키는 세션 키, 값은 세션 메타데이터:

```json
{
  "agent:main:main": {
    "sessionId": "5e57f3cb-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "contextTokens": 272000,
    "inputTokens": 1584000,
    "outputTokens": 42000,
    "totalTokens": 1626000,
    "compactionCount": 2,
    "memoryFlushAt": "2026-02-20T09:15:00.000Z",
    "systemPromptReport": { ... }
  },
  "agent:main:telegram:group:-1003886593826:topic:1": { ... },
  "agent:aki:cron:jobId:run:sessionId": { ... }
}
```

### 16.2 SystemPromptReport 구조

> 소스: `src/agents/system-prompt-report.ts` — `buildSystemPromptReport()`

세션 실행 시 `SystemPromptReport`가 생성되어 sessions.json에 저장됨:

```json
{
  "systemPromptReport": {
    "workspaceDir": "/Users/kys/.openclaw/workspace",
    "bootstrapMaxChars": 20000,
    "systemPrompt": {
      "chars": 32700,
      "projectContextChars": 15400,
      "nonProjectContextChars": 17300
    },
    "sandbox": {
      "mode": "lenient"
    },
    "injectedWorkspaceFiles": [
      {
        "name": "AGENTS.md",
        "path": "/Users/kys/.openclaw/workspace/AGENTS.md",
        "missing": false,
        "rawChars": 8300,
        "injectedChars": 8300,
        "truncated": false
      },
      {
        "name": "SOUL.md",
        "path": "/Users/kys/.openclaw/workspace/SOUL.md",
        "missing": false,
        "rawChars": 2100,
        "injectedChars": 2100,
        "truncated": false
      }
    ],
    "skills": {
      "entries": [
        {"name": "browser-manager", "blockChars": 351},
        {"name": "agent-ops-manager", "blockChars": 2105},
        {"name": "coding-guide", "blockChars": 4716}
      ]
    },
    "tools": {
      "entries": [
        {"name": "read", "summaryChars": 298, "schemaChars": 392},
        {"name": "write", "summaryChars": 245, "schemaChars": 301},
        {"name": "exec", "summaryChars": 412, "schemaChars": 567}
      ]
    }
  }
}
```

### 16.3 injectedWorkspaceFiles 필드 상세

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string | 파일명 (AGENTS.md, SOUL.md 등) |
| `path` | string | 절대 경로 |
| `missing` | boolean | 파일이 존재하지 않음 (true면 주입 안 됨) |
| `rawChars` | number | 원본 파일 크기 (chars) |
| `injectedChars` | number | 실제 주입된 크기 (truncation 적용 후) |
| `truncated` | boolean | bootstrapMaxChars 제한에 의해 잘렸는지 |

### 16.4 세션 타입별 가용 여부

| 세션 타입 | systemPromptReport | 비고 |
|-----------|-------------------|------|
| 메인 DM (main) | ✅ 있음 | 전체 8개 파일 |
| 텔레그램 토픽 | ✅ 있음 | |
| 크론 (isolated) | ⚠️ 일부 없음 | isolated 크론은 없을 수 있음 |
| 서브에이전트 | ✅ 있음 | AGENTS.md + TOOLS.md만 |

### 16.5 활용 예시

```python
from parser import load_session_metadata, _parse_session_context

# sessions.json에서 특정 세션 메타 로드
meta = load_session_metadata("main", "5e57f3cb")
report = meta.get("systemPromptReport")

# 주입된 파일 목록
for f in report["injectedWorkspaceFiles"]:
    status = "MISSING" if f["missing"] else ("TRUNC" if f["truncated"] else "ok")
    print(f"{f['name']}: {f['injectedChars']} chars ({status})")

# 세션 레벨 토큰 카운터
print(f"context: {meta['contextTokens']}K, compactions: {meta['compactionCount']}")
```

---

## 17. 부트스트랩 파일 로딩 체인

> 소스코드 분석으로 확인한 세션 초기화 시 컨텍스트 주입 전체 경로.

### 17.1 실행 흐름

```
resolveBootstrapContextForRun()          # bootstrap-files.ts
  └─ loadWorkspaceBootstrapFiles()       # workspace.ts — 8개 파일 로드
       └─ filterBootstrapFilesForSession()  # 서브에이전트면 필터링
            └─ buildBootstrapContextFiles()    # chars 제한 적용 (truncation)
                 └─ buildAgentSystemPrompt()   # system-prompt.ts — "# Project Context" 섹션 조립
                      └─ buildSystemPromptReport()  # system-prompt-report.ts — 리포트 생성 → sessions.json에 저장
```

### 17.2 부트스트랩 파일 목록 (8개)

> 소스: `src/agents/workspace.ts` — `loadWorkspaceBootstrapFiles()`

| 순서 | 파일명 | 용도 | 서브에이전트 |
|------|--------|------|-------------|
| 1 | `AGENTS.md` | 에이전트 시스템 프롬프트 (핵심 지시) | ✅ |
| 2 | `SOUL.md` | 에이전트 인격/성격 정의 | ❌ |
| 3 | `TOOLS.md` | 도구 사용 가이드 및 커스텀 도구 정의 | ✅ |
| 4 | `IDENTITY.md` | 에이전트 정체성 정보 | ❌ |
| 5 | `USER.md` | 사용자 프로필/선호도 | ❌ |
| 6 | `HEARTBEAT.md` | 하트비트 주기 실행 지시 | ❌ |
| 7 | `BOOTSTRAP.md` | 세션 시작 시 일회성 지시 | ❌ |
| 8 | `MEMORY.md` | 에이전트 기억 요약 | ❌ |

### 17.3 시스템 프롬프트 조립 구조

> 소스: `src/agents/system-prompt.ts` — `buildAgentSystemPrompt()`

최종 시스템 프롬프트는 다음 순서로 조립됨:

```
[System Prompt]
  ├── 플랫폼 기본 지시 (hardcoded)
  ├── "# Project Context"
  │   ├── AGENTS.md 내용
  │   ├── SOUL.md 내용
  │   ├── TOOLS.md 내용
  │   ├── ... (나머지 부트스트랩 파일)
  │   └── (bootstrapMaxChars 제한으로 잘릴 수 있음)
  ├── 스킬 블록 (skills.entries[])
  └── 도구 스키마 (tools.entries[])
```

- `bootstrapMaxChars`: 프로젝트 컨텍스트 최대 크기 (기본값은 settings에 따라 다름)
- 파일이 이 제한을 초과하면 `truncated: true`로 표시

### 17.4 파일 탐색 경로

부트스트랩 파일은 다음 경로에서 탐색:

```
~/.openclaw/workspace-{agentId}/          # 에이전트별 작업 공간
~/.openclaw/workspace/                     # 공유 작업 공간 (fallback)
```

파일이 없으면 `missing: true`로 기록 (에러가 아닌 정상 동작).

---

## 18. 디버그 및 확장 인터페이스

### 18.1 API 페이로드 로깅

> 소스: `src/agents/anthropic-payload-log.ts`

LLM API로 전송되는 전체 페이로드를 로깅하는 디버그 모드:

```bash
# 환경변수 설정으로 활성화
OPENCLAW_ANTHROPIC_PAYLOAD_LOG=1 openclaw start
```

- 시스템 프롬프트, 전체 메시지 히스토리, 도구 스키마가 포함된 API 요청을 기록
- JSONL 트랜스크립트에 없는 **실제 API 호출 내용**을 볼 수 있음
- 디버그 전용 — 프로덕션에서는 비활성 (대용량 로그 생성)

### 18.2 커스텀 이벤트 확장

> 소스: `SessionManager.appendCustomEntry()`

JSONL 트랜스크립트에 커스텀 이벤트를 주입하는 API:

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

현재 확인된 `customType`:
- `model-snapshot`: 모델/provider 스냅샷 (런타임 모델 상태 기록)

이 API를 활용하면 ocmon에서 추적하고 싶은 추가 정보를 JSONL에 주입 가능 (OpenClaw 소스 수정 필요).

### 18.3 데이터 소스별 가용 정보 비교

| 정보 | JSONL | sessions.json | API 페이로드 |
|------|-------|---------------|-------------|
| 메시지 내용 (user/assistant) | ✅ | ❌ | ✅ |
| 도구 호출/결과 | ✅ | ❌ | ✅ |
| 토큰/비용 (per-message) | ✅ | ❌ (누적만) | ❌ |
| 시스템 프롬프트 내용 | ❌ | ❌ (크기만) | ✅ |
| 주입된 파일 목록 | ❌ | ✅ | ❌ |
| 주입된 파일 크기/상태 | ❌ | ✅ | ❌ |
| 스킬/도구 스키마 목록 | ❌ | ✅ | ✅ |
| 세션 레벨 토큰 카운터 | ❌ (턴별만) | ✅ | ❌ |
| Compaction 횟수/시각 | ✅ | ✅ (count만) | ❌ |
| Compaction 요약 텍스트 | ✅ | ❌ | ❌ |
| Thinking (사고 과정) | ✅ (모델별) | ❌ | ✅ |
| 메모리 플러시 시각 | ❌ | ✅ | ❌ |

---

## 19. 파싱 팁 및 주의사항

### 19.1 파싱 시 주의

1. **빈 text 블록**: `{"type":"text","text":""}` 필터링 필요
2. **deleted 파일**: 서브에이전트 세션은 `.jsonl.deleted.*`로 rename됨
3. **session_id 추출**: `.jsonl.deleted.*` 파일에서 stem 사용 시 `.jsonl` 기준으로 분리
4. **sessionKey vs sessionId**: 서브에이전트에서 이 둘은 다른 UUID — sessionKey의 UUID가 파일명
5. **timestamp 형식**: entry 레벨은 ISO 8601, message 레벨은 ms epoch
6. **announce 메시지**: `[System Message]` 또는 `[Day YYYY-MM-DD ...]` 두 가지 접두사
7. **queued announces**: agent busy 시 여러 announce가 하나의 user 메시지로 묶임
8. **sessions.json 키 매칭**: 세션 키는 `agent:{agentId}:{type}:{...}` 형식, sessionId 값으로도 매칭 가능
9. **systemPromptReport 부재**: 일부 세션(특히 isolated 크론)에는 report가 없음 → graceful fallback 필요
10. **thinking_level_change**: JSONL에서 추적하되, 모든 세션에 있지는 않음 (thinking 미지원 모델은 이벤트 없음)

### 19.2 Turn 구조화

```
Turn = user 메시지 시작 → 다음 user 메시지 직전까지의 모든 이벤트
  - user message (1개)
  - assistant messages (N개, 각각 usage 포함)
  - toolResult messages (N개, toolCall과 id로 매칭)
```

### 19.3 비용 계산

```python
total_cost = sum(turn.cost["total"] for turn in turns)
# 주의: 서브에이전트 비용은 부모 세션 비용에 포함되지 않음
# 서브에이전트 비용은 별도로 자식 세션을 파싱하여 합산해야 함
```

---

## 부록: ocmon 분석 도구

이 문서의 데이터 소스인 `ocmon` 도구:
- 경로: `~/.openclaw/tools/ocmon/`
- CLI: `ocmon sessions|analyze|raw|crons|subagents|cost|context`
- 웹: `ocmon web` → http://localhost:8901
- 파서: `parser.py` — 이 문서에 기술된 모든 구조를 파싱

### ocmon이 활용하는 데이터 소스

| 소스 | 경로 | 용도 |
|------|------|------|
| 세션 JSONL | `agents/{id}/sessions/*.jsonl` | 턴별 메시지, 도구, 토큰, 비용 |
| sessions.json | `agents/{id}/sessions/sessions.json` | 초기 컨텍스트, 세션 레벨 메타 |
| subagents/runs.json | `subagents/runs.json` | 서브에이전트 매핑 |
| 크론 실행 로그 | `cron/runs/*.jsonl` | 크론 이력 |
| 크론 잡 정의 | `cron/jobs.json` | 잡 메타데이터 |

### ocmon context 커맨드

```bash
ocmon context <session-id>
```

출력 예시:
```
Context Injection for session 5e57f3cb (main)
═══════════════════════════════════════════════════════
  System Prompt: 32.7KB (project: 15.4KB, other: 17.3KB)
  Bootstrap Max: 20,000 chars | Workspace: ~/.openclaw/workspace

  Injected Files:
    AGENTS.md         8,300 chars  ok
    SOUL.md           2,100 chars  ok
    TOOLS.md          3,500 chars  ok
    IDENTITY.md       1,200 chars  ok
    USER.md             800 chars  ok
    HEARTBEAT.md        MISSING
    BOOTSTRAP.md        MISSING
    MEMORY.md         1,200 chars  ok

  Skills (7.2KB):
    browser-manager         351 chars
    agent-ops-manager     2,105 chars
    coding-guide          4,716 chars

  Session Tokens: context=272K, compactions=2, memory_flush=2026-02-20 09:15
```
