# ClawTracerX Session Log Classification & Analysis Spec

> 이 문서는 OpenClaw 세션 JSONL 로그를 파싱하고 분류·그루핑하는 ClawTracerX의 분석 로직 명세.
> 구현 위치: `parser.py` (Turn 구조화), `web.py` (직렬화), `static/turns.js` (렌더링)

---

## 1. Turn 소스 타입 (`user_source`)

Turn은 하나의 user 메시지로 시작하는 에이전트 응답 단위. `user_source`는 그 메시지가 어디서 왔는지를 분류한다.

| `user_source` | 판별 조건 | 의미 |
|--------------|-----------|------|
| `chat` | 기본값 (기타) | 직접 대화 (텔레그램/디스코드/Lab 포함) |
| `cron` | `[cron:{jobId}...]` 접두사 | 크론 잡 트리거 메시지 |
| `heartbeat` | `[heartbeat...]` / `Read HEARTBEAT.md` | 하트비트 자동 실행 |
| `subagent_announce` | `A subagent task` 포함 | 서브에이전트 완료 알림 (에이전트가 처리) |
| `cron_announce` | `A cron job` 포함 | 크론 isolated agent 완료 알림 (에이전트가 처리) |
| `system` | `[System Message]` 기타 | 기타 시스템 메시지 |
| `discord` | `[message_id: N]` + discord 키워드 | 디스코드 채널 메시지 |
| `telegram` | `[message_id: N]` + telegram 키워드 | 텔레그램 메시지 |
| `delivery_mirror` | `model: "delivery-mirror"` assistant 메시지로 시작 | 채널 발송 결과 미러링 (user 없음) |
| `proactive` | `parentRole=assistant` + 비-delivery-mirror + 비-error-chain | 에이전트 선제 발화 (현재 실측 0건) |

---

## 2. 특수 Turn 타입 상세

### 2.1 delivery_mirror Turn

**정체**: cron isolated agent가 텔레그램/디스코드 등 외부 채널로 메시지를 발송할 때,
그 내용을 세션 JSONL에도 기록하는 **사본 로그**.

**식별**: assistant 메시지의 `model` 필드가 `"delivery-mirror"`

```jsonl
{"type":"message","message":{"role":"assistant","model":"delivery-mirror","content":[...],"usage":{"input":0,"output":0}}}
```

- usage/cost 전부 0 (실제 추론 없음)
- `transcript.ts:appendAssistantMessageToSessionTranscript()` 에서 생성
- outbound 채널 발송 완료 콜백에서 호출됨

**파서 처리**: `parentId → 이전 assistant`인 assistant 메시지 발견 시 새 turn으로 분리.
`user_source = "delivery_mirror"`, `user_text = ""`

**duration 주의**: delivery_mirror를 이전 turn에 포함하면 타임스탬프 max-min 계산으로
duration이 수십 분으로 부풀려짐. 반드시 별도 turn으로 분리해야 함.

### 2.2 delivery_mirror vs cron_announce 차이

같은 cron 작업에서 두 가지가 **동시에** 생길 수 있다. 목적이 다르기 때문.

```
cron isolated agent 실행 완료
    │
    ├─ 결과를 텔레그램/디스코드로 발송
    │   └─ 발송 완료 → delivery_mirror turn 기록 (항상, 채널 발송 설정 시)
    │
    └─ delivery.mode = "announce" 설정 시
        └─ main session에 user 메시지 주입 → cron_announce turn → 에이전트가 처리
```

| | delivery_mirror | cron_announce |
|--|----------------|--------------|
| **역할** | "이 메시지가 채널로 나갔어요" 로그 | "에이전트야, 결과 처리해봐" 지시 |
| **실제 추론** | ❌ (usage = 0) | ✅ (에이전트가 응답) |
| **소스 코드** | `transcript.ts` | `isolated-agent/run.ts → runSubagentAnnounceFlow()` |

---

## 3. 워크플로우 그루핑 (Workflow Grouping)

### 3.1 개념

오토파일럿 연쇄 흐름을 하나의 **작업 단위**로 묶는 것.

```
cron 트리거 (spawn A)
  └→ A 완료 announce (spawn B)
      └→ B 완료 announce (spawn C)
          └→ C 완료 announce
```

각 단계가 별도 turn으로 기록되지만, 사실상 하나의 작업 흐름.
`workflow_group_id`로 묶어서 UI에서 단일 블록으로 표시.

### 3.2 알고리즘 (`_assign_workflow_groups()`)

**핵심 원리**: spawn의 `child_session_id` ↔ announce의 `[sessionId: UUID]` 매칭

```python
pending: dict[str, int]  # child_session_id → workflow_group_id

for turn in turns:
    matched_group = None

    # announce turn: [sessionId: UUID] 접두사에서 UUID 추출 → pending 매칭
    if turn.user_source in ("subagent_announce", "cron_announce"):
        sid = extract_session_id(turn.user_text)  # [sessionId: UUID]
        if sid in pending:
            matched_group = pending.pop(sid)

    # 스폰이 있는 turn: 새 그룹 시작
    if matched_group is None and turn.subagent_spawns:
        group_id += 1
        matched_group = group_id

    if matched_group is not None:
        turn.workflow_group_id = matched_group
        # 이 turn의 spawns → 다음 announce에서 체인 연결
        for spawn in turn.subagent_spawns:
            real_sid = spawn.announce_stats.get("session_id") or spawn.child_session_id
            if real_sid:
                pending[real_sid] = matched_group

# 단일 turn만 있는 그룹은 해제 (의미 없는 그루핑 방지)
counts = Counter(t.workflow_group_id for t in turns if t.workflow_group_id)
for turn in turns:
    if counts[turn.workflow_group_id] < 2:
        turn.workflow_group_id = None
```

**전제 조건**: `_enrich_spawns_from_announces()` 이후에 실행해야 함.
이 함수가 announce 메시지에서 real `child_session_id`를 spawn에 역채워주기 때문.

### 3.3 비연속 그룹 (Non-Contiguous Groups)

같은 그룹의 turn들 사이에 `workflow_group_id=None`인 turn이 낄 수 있다.

```
Turn 8:  wf=3  [cron, spawns A]
Turn 9:  wf=3  [announce A, spawns B]
Turn 10: wf=None [cron, no spawns]  ← 갭: 같은 크론이 다시 트리거됐지만 할 일 없어서 스폰 안 함
Turn 11: wf=3  [announce B, spawns C]
Turn 12: wf=None [cron, no spawns]  ← 갭
Turn 13: wf=3  [announce C, spawns D]
Turn 14: wf=3  [announce D]
```

**갭 발생 이유**: 주기 크론이 반복 트리거되는 동안 워크플로우가 실행 중. 크론이 "이미 진행 중" 판단 후 아무것도 안 함.

**UI 처리 방법**: 워크플로우 bounds(first~last) 범위 내에서 `workflow_group_id == gid`인 turn만 블록에 포함. 갭 turn(wf=None)은 블록 **뒤에** 별도 렌더링.

```javascript
// bounds: {first: 8, last: 14}
const workflowTurns = range(8, 15).filter(j => turns[j].workflow_group_id === gid);
const gapTurns      = range(8, 15).filter(j => turns[j].workflow_group_id !== gid);

items.push({ type: 'workflow', turns: workflowTurns });
gapTurns.forEach(t => items.push({ type: 'turn', turn: t })); // 워크플로우 블록 뒤에 표시
```

### 3.4 워크플로우 집계 통계

UI 블록 헤더에 표시하는 집계:

| 항목 | 계산 방법 |
|------|-----------|
| **총 소요 시간** | `lastTurn.timestamp - firstTurn.timestamp + lastTurn.duration_ms` |
| **총 비용** | `sum(turn.cost.total)` for wf turns |
| **총 tool calls** | `sum(len(turn.tool_calls))` |
| **총 subagent 수** | `sum(len(turn.subagent_spawns))` |
| **총 tokens** | `sum(turn.usage.totalTokens)` |

duration은 개별 turn duration의 합이 아닌 **벽시계 시간(wall clock)** 기준.
중간에 서브에이전트가 비동기로 실행되는 시간이 포함되어야 실제 소요 시간이 됨.

---

## 4. Turn 체이닝 — parentId 분석

assistant 메시지의 `parentId`가 이전 assistant 메시지를 가리키는 경우 3가지:

| 케이스 | 조건 | 처리 |
|--------|------|------|
| **delivery_mirror** | `model == "delivery-mirror"` | 새 turn 시작 (`user_source="delivery_mirror"`) |
| **error retry** | `current_stop == "error"` 또는 `parent_stop == "error"` | 동일 turn 계속 (에러 후 재시도) |
| **proactive** | 위 두 가지 아님 | 이론상 새 turn (`user_source="proactive"`), 실측 0건 |

---

## 5. 세션 타입 판별

`session_type`은 첫 번째 **실질적인** turn의 `user_source`로 결정.

```python
first_real_turn = next(
    (t for t in turns if t.user_source not in ("proactive", "delivery_mirror")),
    turns[0],
)
```

| 첫 turn source | session_type |
|----------------|-------------|
| `cron` | `"cron"` |
| `heartbeat` | `"heartbeat"` |
| `subagent_announce` | `"subagent"` |
| `discord` / `telegram` / `chat` | `"chat"` |
| 기타 | `"chat"` |

---

## 6. 서브에이전트 자식 세션 로딩 — delivery_mirror 스폰 문제

### 6.1 문제: childSessionKey UUID ≠ 실제 파일 UUID

`useSubagent` 도구 결과(toolResult)의 `childSessionKey`에는 **라우팅 UUID**가 담긴다.
실제 JSONL 파일명에 쓰이는 UUID와 **다른 값**이다.

```
childSessionKey: "agent:guardian:subagent:246aa4a4-..."   ← 라우팅 UUID
실제 파일: ~/.openclaw/agents/guardian/sessions/3bdbe281-....jsonl  ← 다른 UUID
```

`announce` turn이 있으면 `_enrich_spawns_from_announces()`가 `[sessionId: UUID]` 접두사에서
real UUID를 추출해 `spawn.child_session_id`를 보정한다.

### 6.2 delivery_mirror 스폰의 추가 문제

`delivery_mirror` turn으로 완료되는 서브에이전트는 **announce turn이 없다**.

```
서브에이전트 완료
  ├─ announce 없음  ← _enrich_spawns_from_announces()가 real UUID 못 찾음
  └─ delivery_mirror turn만 기록됨 (user 메시지 없음)
```

결과: `child_session_id`가 라우팅 UUID 그대로, `child_turns = []`.

### 6.3 해결: `_try_load_missing_children()` 폴백

announce 없이 `child_turns`가 비어 있는 spawn에 대해 타임스탬프 + 키워드 매칭으로 파일을 탐색.

```python
def _try_load_missing_children(turns, agent_id):
    for turn in turns:
        for spawn in turn.subagent_spawns:
            if spawn.child_turns:          # 이미 로딩됨 → 스킵
                continue

            turn_end_ts = turn.timestamp + timedelta(milliseconds=turn.duration_ms or 0)
            window = 14400  # 4시간 (서브에이전트 실행 여유 시간)

            # 시도 1: spawn.label 키워드로 파일 탐색
            child_file = _find_child_session_by_label(
                spawn.label, spawn.label, agent_id, turn_end_ts, window_after_secs=window)

            # 시도 2: spawn.task 텍스트 앞 15단어로 탐색 (레이블이 영어지만 세션 내용이 한국어인 경우)
            if not child_file and spawn.task:
                task_text = " ".join(spawn.task.split()[:15])
                child_file = _find_child_session_by_label(
                    task_text, spawn.label, agent_id, turn_end_ts, window_after_secs=window)

            if child_file:
                child_analysis = parse_session(child_file, recursive_subagents=False)
                spawn.child_turns = child_analysis.turns
                spawn.child_session_id = child_file.stem   # real UUID
```

**호출 순서** (`parse_session()` 내):
```
_enrich_spawns_from_announces()   # announce 기반 real UUID 보정 (1차)
_try_load_missing_children()      # 타임스탬프/키워드 폴백 (2차)
_assign_workflow_groups()         # 그루핑 (child_session_id 확정 후)
```

### 6.4 `_find_child_session_by_label()` 탐색 방식

```python
def _find_child_session_by_label(keyword, label, agent_id, ref_ts, window_after_secs=60):
    """ref_ts 기준으로 window_after_secs 이내 생성된 세션 중
       첫 user 메시지에 keyword가 포함된 파일 반환."""
```

- 기본 window는 60초 (announce 기반 탐색용)
- delivery_mirror 폴백은 4시간(14400초) 사용 (서브에이전트 실행 시간이 길 수 있음)
- 레이블이 영어인데 세션 user 메시지가 한국어인 경우 Try 2 (task text)로 커버

---

## 7. 알려진 엣지 케이스 및 함정

| 상황 | 증상 | 처리 |
|------|------|------|
| delivery_mirror가 이전 turn에 포함될 때 | `duration_ms`가 수십~수백 분으로 부풀려짐 | delivery_mirror를 별도 turn으로 분리 |
| 같은 워크플로우 중 크론 재트리거 (no spawns) | 갭 turn이 workflow bounds 내에 낌 | 갭 turn은 워크플로우 블록 밖에 따로 렌더 |
| announce chunk에 Stats 필드 없음 | `child_session_id` 미추출 | `_enrich_spawns_from_announces()`에서 fallback으로 파일 탐색 |
| 같은 레이블 서브에이전트 중복 spawn | announce 매칭 실패 | 순서대로 pop(0) 방식으로 매칭 |
| isolated cron 세션에 systemPromptReport 없음 | `context` 필드 None | graceful fallback 필요 |
| `childSessionKey` UUID ≠ 실제 파일명 UUID | 파일 찾기 실패 | announce의 `[sessionId: UUID]`만 신뢰 |
| delivery_mirror 스폰 (announce 없음) | `child_turns = []` 빈 상태 유지 | `_try_load_missing_children()` 타임스탬프+키워드 폴백 |
| 레이블 영어, 세션 내용 한국어 | label 키워드 탐색 실패 | task text 앞 15단어로 2차 탐색 |
