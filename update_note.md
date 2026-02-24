## [2026-02-24] - Lab 페이지 UX 전면 개선 (9개 변경사항)

### 작업 내용
- Lab 페이지 레이아웃을 수직 스택에서 2단 레이아웃으로 재구성
- Toast 알림 시스템 도입 (모든 alert() 교체)
- 즉시 메시지 피드백 (pending card), 경과 시간 타이머
- Settings localStorage 저장/복원, 새 세션 생성 버튼
- Textarea 자동 높이 + Cmd+Enter/Ctrl+Enter 지원
- 미저장 컨텍스트 파일 경고 + 최신 턴 자동 펼침
- 기존 버그 수정 (URL 파라미터, missing CSS)

### 주요 변경사항

| 파일 | 변경 내용 |
|------|----------|
| `static/style.css` | +248줄 — Toast 시스템, 2단 레이아웃 (`.lab-topbar`, `.lab-columns`, `.lab-sidebar`), fixed bottom input (`.lab-input-sticky`), pending card 스타일, elapsed timer, `.lab-status.connecting/.watching` 추가, `@media (max-width: 1024px)` 반응형 |
| `templates/lab.html` | 전면 재구성 — HTML: topbar(헤더+셀렉터+버튼 한 줄), columns(타임라인 좌 + 사이드바 우), sticky input(fixed bottom). JS: `showToast()`, `startElapsedTimer()`/`stopElapsedTimer()`, `insertPendingMessage()`/`removePendingMessage()`, `autoResizeTextarea()`, `handleInputKeydown()`, `saveSettingsToStorage()`/`loadSettingsFromStorage()`, `startNewSession()`, `markContextUnsaved()`, `autoExpandLatestTurn()` |

### 9개 변경사항 상세

1. **버그 수정**: `loadGatewaySessions()` URL `?`/`&` 분기 처리, `.lab-status.connecting/.watching` CSS
2. **Toast 알림**: slide-in/out 애니메이션, 4타입(success/error/info/warning), 3초 자동 제거
3. **2단 레이아웃**: `grid-template-columns: 1fr 340px`, 사이드바 sticky, 1024px 이하 1단 폴백
4. **즉시 피드백**: 파란 pending card + spinner, SSE init/update/done에서 자동 제거
5. **경과 타이머**: 전송→완료 시간 카운트, done/error 시 정지 + 5초 후 숨김
6. **Settings 저장**: localStorage에 model/thinking/deliver/timeout/extraPrompt/lastAgent 자동 저장
7. **New Session**: `+ New` 버튼 → 새 세션 키 + 타임라인 초기화 + toast
8. **Textarea 개선**: scrollHeight 기반 자동 높이(max 200px), OS 감지 키보드 힌트
9. **미저장 경고**: `unsavedContextFiles` Set 추적, beforeunload 경고, 최신 턴 auto-expand

### 중요 결정사항
- **수정 파일 최소화**: `turns.js`, `app.js`, `base.html`, `web.py` 미수정 — 기존 API/유틸 그대로 활용
- **`#turns-container` ID 유지**: `renderTurns()` 호환성 보장
- **Fixed bottom input**: `position: fixed` + `backdrop-filter: blur(16px)` — 항상 하단 고정, 배경 블러
- **Manual key input 토글**: Timeline 헤더의 "Key..." 버튼으로 숨김/표시 (공간 절약)

### 검증
- `restart.sh` 실행 → http://localhost:8901/lab 정상 로드
- 전체 검증 에이전트로 19개 기존 함수 + 14개 신규 함수 + 23개 DOM ID 매칭 확인

### 다음 단계
- [ ] 1440px+ 2단 레이아웃 실사용 테스트
- [ ] 메시지 전송 → pending card → SSE 실제 동작 확인
- [ ] 모바일 768px 이하 반응형 확인

---

## [2026-02-21] - 서브에이전트 UI 개선, delivery_mirror 자식 세션 로딩, 워크플로우 그루핑 명세화

### 작업 내용
- `SESSION_ANALYSIS_SPEC.md` 신규 생성 — 세션 로그 분류·분석·그루핑 전체 명세
- delivery_mirror 스폰 자식 세션 로딩 수정 (`_try_load_missing_children`)
- 서브에이전트 블록 UX 개선: 에이전트 이름 배지 + 클릭 시 즉시 전체 펼침
- 워크플로우 그루핑 구현 (section 3 in spec), 비연속 그룹 처리 (gap turns)

### 주요 변경사항

| 파일 | 변경 내용 |
|------|----------|
| `SESSION_ANALYSIS_SPEC.md` | 신규 — user_source 타입, delivery_mirror 상세, workflow 그루핑 알고리즘, 자식 세션 로딩 문제/해결 전체 명세 |
| `parser.py` | `_try_load_missing_children()` 추가, `_assign_workflow_groups()` 추가, Turn dataclass에 `workflow_group_id` 추가 |
| `static/turns.js` | `extractAgentId()` 헬퍼 추가, `renderSubagent()` 에이전트 배지 표시 + child turns 즉시 펼침, `renderChildTurn()` body 기본 오픈 |
| `static/style.css` | `.badge-agent-named`, `.badge-agent-sub` 추가, workflow group 스타일, delivery_mirror muted 스타일 |
| `web.py` | `_serialize_turn()`에 `workflow_group_id` 추가 |
| `OPENCLAW_AGENT_GUIDE.md` | SESSION_ANALYSIS_SPEC 링크, delivery_mirror vs cron_announce 섹션 추가 |

### 중요 결정사항

- **delivery_mirror 스폰 폴백**: `childSessionKey` UUID는 라우팅 UUID (파일 UUID와 다름). announce 없는 경우 타임스탬프 + label/task 키워드로 4시간 윈도우 탐색
- **레이블 영어 + 세션 내용 한국어** 케이스: `spawn.label`로 실패 시 `spawn.task.split()[:15]`로 2차 시도
- **자식 턴 즉시 펼침**: 클릭 횟수 줄이기 위해 subagent body 열리면 child turns/tool calls 모두 바로 보임. tc-result (결과 텍스트)만 클릭 필요
- **에이전트 구분**: `child_session_key`에서 agentId 추출 → `main` 이면 "서브세션" 배지, 명명 에이전트면 `🤖 {agentId}` 배지
- **워크플로우 비연속 그룹**: bounds(first~last) 범위 내 wf=None 갭 turn은 블록 밖 뒤에 렌더

### 문제 해결

- **문제**: opacity:0 + fadeSlide 미정의 애니메이션 → 워크플로우 블록 전부 검게 보임
  - **해결**: animation 제거, opacity:0 제거
- **문제**: 갭 turn(wf=None)이 워크플로우 블록 안에 포함됨
  - **해결**: bounds 범위 loop에서 gid 일치/불일치로 분리, gap turns를 블록 뒤에 렌더
- **문제**: delivery_mirror 완료 서브에이전트 child_turns 빈 배열
  - **해결**: `_try_load_missing_children()` — label → task text 순서로 파일 탐색

### 다음 단계
- [ ] sessions.html 변경사항 검토/커밋
- [ ] Lab 페이지에서도 서브에이전트 즉시 펼침 동작 확인

---

## [2026-02-21] - 버그 수정: 폴링 무한루프, Context 패널, 서브에이전트 세션 매칭

### 작업 내용
- Lab 폴링 무한루프 수정 (응답 완료 감지 + 속도 전환)
- Context Injection 패널에 Skills/Tools 크기 바 차트 추가
- PROJECT vs SYSTEM 개념 명확화 (Tools/Skills는 SYSTEM에 포함됨)
- 서브에이전트 child session 로딩 전면 수정 (announce 포맷 2종 지원)
- Open Session 링크 올바른 session ID 사용하도록 수정

### 주요 변경사항

| 파일 | 변경 내용 |
|------|----------|
| `templates/lab.html` | 폴링 2단계 속도 (fast 2s / slow 8s), 완료 시 slow 전환, 무한루프 방지 |
| `web.py` | poll 응답에 `done` 필드 추가 (마지막 turn stopReason=stop 감지), `_serialize_spawn`에서 `announce_stats.session_id`로 real sessionId 사용 |
| `templates/detail.html` | Skills/Tools 섹션을 chip → bar chart로 변경 (blockChars, summaryChars+schemaChars) |
| `static/style.css` | `.ctx-file-fill.skill`, `.tool-summary`, `.tool-schema` 색상 추가, `.ctx-file-bar`에 flex 추가 |
| `parser.py` | 서브에이전트 announce 파싱 전면 재작성 (아래 상세) |

### 서브에이전트 세션 매칭 수정 (parser.py)

**문제**: `child_session_id`(라우팅 키 UUID) ≠ 실제 JSONL 파일명 UUID → child_turns 항상 빈 배열, Open Session 404

**근본 원인 분석**:
- OpenClaw `sessions_spawn` 결과: `childSessionKey: agent:aki:subagent:2858690d-...` (라우팅용 UUID)
- 실제 JSONL 파일: `83aead09-....jsonl.deleted.*` (런타임에 새로 생성된 UUID)
- 두 UUID는 다른 값. 실제 UUID는 announce 메시지에서만 얻을 수 있음
- 기존 코드는 announce 처리 전에 파일을 찾으려 해서 항상 실패

**두 가지 announce 포맷**:
1. **신버전** (`91ed4a28` 같은 최근 세션): `[sessionId: UUID]` prefix + `Stats: runtime • tokens` (inline 필드 없음)
2. **구버전** (`0ab7efc0` 같은 이전 세션): `Stats: runtime • tokens • sessionKey ... • sessionId UUID • transcript PATH` (inline 필드 있음)

**수정 내역**:
- `_ANNOUNCE_RE`: Stats+tokens만 매칭 (sessionKey/transcript 옵셔널)
- `_ANNOUNCE_SESSION_ID_RE`: `[sessionId: UUID]` 추출 (신버전 prefix)
- `_ANNOUNCE_INLINE_SID_RE`: `• sessionId UUID` 추출 (구버전 Stats inline)
- `_ANNOUNCE_INLINE_TRANSCRIPT_RE`: `• transcript PATH` 추출 (구버전)
- `_parse_announce_match(m, full_text)`: 두 포맷 모두 session_id 추출
- `chunk` 범위를 `m.end()` → 다음 `\n\n`까지 확장 (inline 필드가 match 밖에 있었음)
- `_find_child_session_by_id(session_id, agent_id)`: 실제 UUID로 파일 탐색
- `_find_child_session_by_label(...)`: label + timestamp 기반 폴백 (announce에 sessionId 없는 경우)
- `_enrich_spawns_from_announces`: 구버전 포맷(Stats 없음) 별도 처리 분기
- `spawns_by_label`: dict → `defaultdict(list)` + pop(0) (같은 label 중복 spawn 순서 매칭)
- child session 로딩을 announce 처리 후로 이동 (announce가 실제 UUID를 제공하므로)

### 문제 해결

- **문제**: chunk = `text[0: m.end()]` — match 끝에서 잘려서 그 뒤 `• sessionId UUID`가 누락
- **해결**: `chunk_end = text.find("\n\n", m.end())` 로 확장

- **문제**: 같은 label의 spawn이 여러 개일 때 마지막 것만 매칭됨
- **해결**: `spawns_by_label[label] = list` → `pop(0)` (순서대로 소비)

- **문제**: 구버전 announce는 Stats 섹션 자체가 없는 케이스 — `_ANNOUNCE_RE` 매칭 실패
- **해결**: Stats 없는 경우 별도 분기 → label만으로 spawn 매칭 → timestamp fuzzy search

### 검증 결과
- `0ab7efc0` (구버전): `child_turns=3, open_sid=83aead09-...` ✅
- `91ed4a28` (신버전): `child_turns=1, open_sid=2684c0a4-...` ✅
- Open Session → 실제 파일 (`83aead09-...jsonl.deleted.*`) 정상 조회 ✅

### 다음 단계
- [ ] 서버 재시작 필요 (현재 변경사항 미반영)
- [ ] subagent_announce source 감지 개선 (구버전 announce는 `[System Message]` prefix 없음)

---

## [2026-02-20] - Lab 실험실 + OpenClaw 지식 문서화

### 작업 내용
- **Lab (실험실)** 기능 전체 구현 — 에이전트에 실시간 메시지 전송, 결과 관찰, 컨텍스트/설정 조정 가능
- 게이트웨이 WebSocket RPC 클라이언트 (`gateway.py`) 구현 (Ed25519 디바이스 인증 포함)
- 턴 렌더링 코드를 `turns.js`로 추출하여 detail.html과 lab.html에서 공유
- Lab 전용 API 엔드포인트 6개 추가 (`web.py`)
- 활동 로그 시스템 (`lab.log` 파일 + 인메모리 캐시)
- OpenClaw 내부 지식 세부 문서 2개 작성 (Claude Code memory)

### 주요 변경사항

| 파일 | 상태 | 변경 내용 |
|------|------|----------|
| `gateway.py` | **신규** | 게이트웨이 WS RPC 클라이언트 — Ed25519 device auth, `rpc_call()`, `send_agent_message()`, `list_gateway_sessions()`, `patch_session()`, `reset_session()`, `list_models()`, `list_agents()` |
| `static/turns.js` | **신규** | detail.html에서 추출한 공유 턴 렌더링 — `renderTurns()`, `renderTurn()`, `renderToolCall()`, `renderSubagent()`, `renderChildTurn()`, `renderTokenBar()`, toggle 함수들 |
| `templates/lab.html` | **신규** | Lab 페이지 — 세션 셀렉터(게이트웨이 세션 드롭다운), 설정 패널(모델/thinking/deliver), 컨텍스트 에디터, 메시지 입력(Ctrl+Enter), 실행 타임라인, 활동 로그 |
| `web.py` | 수정 | +205줄 — `/lab`, `/api/lab/sessions`, `/api/lab/send`, `/api/lab/poll/<id>`, `/api/lab/context`, `/api/lab/context/<name>`, `/api/lab/settings/<key>`, `/api/lab/activity` |
| `templates/detail.html` | 수정 | 인라인 JS 274줄 제거 → `<script src="/static/turns.js">` import로 교체 |
| `templates/base.html` | 수정 | 사이드바에 Lab 네비게이션 링크 + 비커 SVG 아이콘 추가 |
| `static/app.js` | 수정 | `postJSON()`, `putJSON()`, `patchJSON()` 헬퍼 추가 |
| `static/style.css` | 수정 | +241줄 — `.input-text`, `.input-textarea`, `.lab-session-bar`, `.lab-status`, `.lab-settings`, `.lab-context`, `.lab-input-bar` (sticky), `.lab-timeline` 등 |

### 문제 해결

- **문제 1: 게이트웨이 connect 실패** — `minProtocol`, `maxProtocol`, `client.id/platform/mode` 필수 파라미터 누락
- **해결**: OpenClaw 소스(`ui/src/ui/gateway.ts`, `protocol/client-info.ts`) 분석하여 정확한 스키마 파악

- **문제 2: RPC "missing scope" 에러** — 올바른 scopes 요청해도 모든 RPC 실패
- **해결**: `message-handler.ts:416`에서 device identity 없으면 scopes를 `[]`로 강제 클리어하는 로직 발견. `~/.openclaw/identity/device.json`의 Ed25519 키로 디바이스 인증 구현

- **문제 3: 기존 세션에 메시지 전송 시 새 세션 생성됨**
- **원인**: Session Key(`agent:aki:chat:59428ab7...`)와 Session ID(`9520bb0d...`)가 서로 다른 UUID
- **해결**: `/api/lab/sessions`에서 `gateway.list_gateway_sessions()` RPC로 실제 key↔id 매핑 획득

- **문제 4: RPC 응답 파싱 실패** — `resp.get("result")` 사용
- **해결**: OpenClaw 프로토콜은 `payload` 필드 사용 (`result` 아님)

### 중요 결정사항
- **매 호출마다 새 WS 연결**: 커넥션 풀링보다 단순하고 안정적. Lab 사용 빈도 고려하면 충분
- **`deliver: false` 기본값**: Lab에서 보낸 실험 메시지가 텔레그램/디스코드로 배달되지 않도록 안전장치
- **컨텍스트 파일 백업**: `.lab-backup` 파일 생성 후 덮어쓰기 (최초 1회만)
- **2초 폴링**: SSE/WebSocket 대신 단순 폴링으로 구현 (향후 SSE 전환 가능)

### 문서화 (Claude Code memory)
- `openclaw-gateway-protocol.md` — WS RPC 프로토콜 v3, 프레임 타입, connect 파라미터, Ed25519 디바이스 인증, scope 시스템, RPC 메서드 전체
- `openclaw-internals.md` — 디렉토리 레이아웃, 에이전트 설정, 세션 키 형식, sessions.json 구조, JSONL 트랜스크립트 형식, 워크스페이스 파일, 채널 바인딩, 크론 작업
- `MEMORY.md` — 핵심 함정 3가지 + ClawTracerX 프로젝트 구조 요약 + 문서 링크

### 다음 단계
- [ ] SSE 스트리밍으로 폴링 대체 (실시간 업데이트)
- [ ] 세션 비교 기능 (같은 메시지를 다른 설정으로 보내고 side-by-side)
- [ ] Lab 전용 임시 워크스페이스 (실제 파일 대신 격리된 컨텍스트)
- [ ] 커넥션 풀링 (현재 매 호출마다 새 WS 연결)

---

## [2026-02-20] - 웹 대시보드 — context 패널 + compaction 개선 + turn stat chips

### 작업 내용
- update_note.md의 "다음 단계" 항목 3개 구현
- `detail.html` 세션 헤더에 Context Injection 패널 추가 (접이식)
- Compaction divider에 before→after 토큰 수, summary 텍스트 추가
- 턴 카드 stat chips에 `cache_hit_rate`, `thinking_level` 표시 추가
- VSCode tunnel 포트 감지 문제 수정 (`ctrace.py` 출력 포맷)

### 주요 변경사항

| 파일 | 변경 내용 |
|------|----------|
| `static/style.css` | Context 패널 CSS (usage bar, file bars, chips), compaction-info, stat-chip.cache/thinking |
| `templates/detail.html` | `fmtChars()`, `renderContextPanel()`, `renderHeader()` 확장, compaction divider 개선, turn stat chips 추가 |
| `ctrace.py` | VSCode tunnel 포트 감지용 출력 포맷 수정 (이모지/화살표 제거) |

### 구현 상세

**Context Injection 패널** (`<details>` 접이식, 세션 헤더 하단)
- System Prompt 사용량 바: Project context(accent) + System(cyan), 최대 대비 퍼센트 표시
- Injected Files: 파일명 + 상대 크기 바 차트 + 주입된 chars + truncated(✂) 표시
- Skills: 이름 chips
- Tools: 이름 chips
- `context_tokens` 메타 항목 추가 (sessions.json 데이터)
- `ctx.workspaceDir` 경로 표시 (`~` 대체)

**Compaction Divider 개선**
- `tokens_before → tokens_after` 표시 (얼마나 압축됐는지 한눈에)
- `[hook]` 배지 (hook-triggered compaction 구분)
- `<details>` Summary 텍스트 — 클릭하여 펼치기

**Turn stat chips (신규)**
- `cache_hit_rate > 0` → cyan `42% cache` chip
- `thinking_level` 존재 시 → magenta `💭 high` chip

**VSCode tunnel 포트 감지 수정**
- 문제: `🔍 ClawTracerX web dashboard → http://localhost:8901` — 이모지/화살표로 VSCode 포트 감지 실패
- 해결: URL을 별도 줄로 분리 → `http://localhost:8901\n` (VSCode 패턴 매칭 성공)

### helper 함수 추가
- `fmtChars(n)`: chars → `1.2K` 포맷 (파일 크기 표시용, fmtTokens와 별개)

### 중요 결정사항
- **`<details>` 네이티브 태그**: context 패널에 JS 토글 대신 `<details>/<summary>` 사용 — JS 없이 접기/펼치기, 상태 자동 유지
- **compaction summary 위치**: 중앙 `compaction-info` div 안에 배치 — 라인과 수평 배치하되 넓이 제한 없이 표시 가능
- **context data 조건부 렌더링**: `s.context`가 없는 세션(서브에이전트, 크론 일부)은 패널 자체를 렌더링 안 함

### 다음 단계
- [ ] `sessions.html`에 `context_tokens` 컬럼 추가 (API에서 list_sessions 레벨에서 불러오려면 별도 파싱 필요 — 현재 미지원)
- [ ] Context 패널 파일별 hover 시 full path 툴팁 확인
- [ ] compaction summary 길이 제한 검토 (현재 500자, 일부 세션은 더 긺)

---

## [2026-02-20] - sessions.json 파싱 추가 — 초기 컨텍스트 + 메타데이터 추적

### 작업 내용
- OpenClaw `sessions.json`의 `systemPromptReport`를 파싱하여 세션 초기 컨텍스트 추적 기능 추가
- JSONL에 있지만 미추출이던 `compaction.summary`, `thinking_level_change` 이벤트 파싱 추가
- 턴별 캐시 히트율 계산 추가
- 새 CLI 커맨드 `ctrace context <session-id>` 추가

### 배경 조사
- OpenClaw 소스코드(`~/openclaw/`) 분석으로 세션 초기화 시 컨텍스트 파일 로딩 경로 추적
  - `src/agents/bootstrap-files.ts` → `resolveBootstrapContextForRun()`
  - `src/agents/workspace.ts` → `loadWorkspaceBootstrapFiles()` (AGENTS.md, SOUL.md 등 8개 파일)
  - `src/agents/system-prompt.ts` → `buildAgentSystemPrompt()` (Project Context 섹션에 주입)
  - `src/agents/system-prompt-report.ts` → `buildSystemPromptReport()` (주입 결과 리포트 생성)
- 핵심 발견: `SystemPromptReport`가 `sessions.json`에 이미 저장됨 (JSONL에는 없음)
  - `injectedWorkspaceFiles[]`: name, path, missing, rawChars, injectedChars, truncated
  - `systemPrompt`: chars, projectContextChars, nonProjectContextChars
  - `skills.entries[]`, `tools.entries[]`

### 주요 변경사항

| 파일 | 변경 내용 |
|------|----------|
| `parser.py` | +141줄 — `InjectedFile`, `SkillEntry`, `ToolEntry`, `SessionContext` 데이터클래스 추가. `CompactionEvent`에 summary/tokens_after/from_hook 확장. `Turn`에 thinking_level/cache_hit_rate 추가. `load_session_metadata()`, `_parse_session_context()` 함수 추가. `parse_session()`에서 sessions.json 통합, thinking_level_change 추적, 캐시 히트율 계산 |
| `cli.py` | +100줄 — `_print_analysis()` 헤더에 System Prompt/Context Files/Skills 표시. 턴별 cache_hit 표시. compaction 요약 미리보기. `cmd_context()` 새 커맨드 |
| `ctrace.py` | +12줄 — `context` (alias `ctx`) 서브커맨드 추가 |
| `web.py` | +45줄 — API에 `context`, `compaction_events`, `context_tokens` 등 필드 추가. 턴별 `thinking_level`, `cache_hit_rate` 직렬화 |

### 중요 결정사항
- **sessions.json 파싱 방식 선택**: OpenClaw 소스 수정(커스텀 JSONL 이벤트 추가) vs sessions.json 읽기 vs API payload 로깅 3가지 옵션 중, OpenClaw 수정 없이 기존 데이터를 활용하는 sessions.json 파싱으로 결정
- **systemPromptReport는 모든 세션에 있지 않음**: 크론 세션 일부는 report 없음 → graceful fallback 처리
- **서브에이전트 컨텍스트 제한 추적 가능**: OpenClaw은 서브에이전트에 AGENTS.md + TOOLS.md만 허용 → 세션 타입으로 추론 가능

### 테스트 및 검증
- `python3 -c "from parser import ..."` — 전체 임포트 성공
- `load_session_metadata('main', '5e57f3cb')` — injectedFiles 8개, skills 18개, tools 24개 정상 파싱
- `ctrace analyze cc52d980` — `cache_hit=35%`, `cache_hit=42%` 턴별 표시 확인
- `ctrace context 5e57f3cb` — 전체 컨텍스트 상세 출력 정상 (System Prompt 32.7KB, 8 files, 18 skills, 24 tools)
- 웹 API: `/api/session/5e57f3cb` → context 필드 정상 반환 (Flask test_client 검증)

### 다음 단계
- [ ] `templates/detail.html`에 컨텍스트 주입 패널 UI 추가 (접이식, 파일 크기 바 차트)
- [ ] compaction 타임라인 UI (요약 텍스트 펼치기)
- [ ] sessions.json 기반 세션 목록에 context_tokens 컬럼 추가

---

## [2026-02-20] - 웹 대시보드 UI/UX 전면 리뉴얼

### 작업 내용
- 대시보드 전체를 "Dark Pro" 디자인 시스템으로 전면 리뉴얼
- 외부 차트 라이브러리 도입: ApexCharts (cost), D3.js (graph)
- CSS 변수 체계 전면 교체, Inter + JetBrains Mono 폰트 적용
- 총 6개 파일 수정 (+1162 / -737 lines)

### 주요 변경사항

| 파일 | 변경 내용 |
|------|----------|
| `static/style.css` | 전면 교체 — 새 디자인 시스템 (1082줄) |
| `templates/base.html` | Google Fonts CDN, SVG 아이콘, 그라디언트 로고 |
| `templates/sessions.html` | `data-type` 행 border, 고비용(`>$0.10`) amber 강조 |
| `templates/detail.html` | 타임라인 스파인 + 도트, 턴 카드 차별화, 토큰 바 14px, 도구 카테고리 색상 |
| `templates/cost.html` | ApexCharts 교체 (horizontal bar + area), hero 메트릭 카드 |
| `templates/graph.html` | Canvas → D3.js SVG 포스 그래프 전면 교체 |

### 디자인 시스템 변경사항

**컬러 팔레트**
- 서피스: `#09090b`(bg-0) ~ `#282d3e`(bg-4) 5단계
- 보더: `rgba()` 기반 분리 (border-subtle / default / emphasis)
- 시맨틱: success/warning/error/info + muted 변형
- 강조: `#6366f1` accent + muted(`rgba(99,102,241,0.15)`)

**타이포그래피**
- sans: Inter (400/500/600/700)
- mono: JetBrains Mono (400/500) — 코드, 숫자, 타임스탬프
- 기본 14px, `letter-spacing: -0.011em`, 안티앨리어싱

**레이아웃**
- 사이드바: 글래스모피즘 (`backdrop-filter: blur(20px)`)
- 로고: 인디고→퍼플 그라디언트 + SVG 아이콘
- 내비: active 시 왼쪽 3px accent bar (`::before`)

### Session Detail 개선

**타임라인 스파인**
- `#turns-container::before` — 2px 수직선 (accent-muted → transparent)
- `.turn-card::before` — 10px 도트, 타입별 glow 적용:
  - 에러: 빨강 + `box-shadow: 0 0 16px rgba(239,68,68,0.5)`
  - subagent spawn: accent + glow
  - 기본: bg-3 + border-default

**턴 카드 차별화**
- `has-errors`: 빨간 왼쪽 3px border + error-muted 그라디언트
- `high-cost` (>`$0.10`): amber 왼쪽 border
- `compacted`: opacity 0.45, bg-4 border
- `spawns-subagent`: accent 왼쪽 border + accent-muted 그라디언트

**스태거 애니메이션**
- 각 턴 카드 `animation-delay: idx * 40ms` → 순차 슬라이드인

**토큰 바**
- 높이: 6px → **14px**, `border-radius: 9999px`
- 각 세그먼트: 그라디언트 fill + shimmer 1회 애니메이션

**도구 카테고리 왼쪽 색상 bar**
- `data-category="file"` → cyan (Read/Write/Edit/Glob)
- `data-category="exec"` → amber (Bash/exec)
- `data-category="search"` → green (Grep/Fetch)

### Cost 대시보드 (ApexCharts)

- `renderBarChart()` → `renderApexBar()`: horizontal bar, 그라디언트 fill, 툴팁
- `renderDailyChart()` → `renderApexArea()`: area chart, 줌 가능, 마커, crosshair
- 공통 dark 테마: `background: transparent`, `foreColor: #b0b4c0`
- 요약 카드: hero card (2fr) + 일반 카드 (1fr × 2), hover lift `-2px`
- 차트 인스턴스 관리: `charts{}` 딕셔너리, `destroyChart()` 재생성 방식

### Graph 페이지 (D3.js)

- Canvas API → **D3.js v7 SVG** 완전 교체
- `d3.forceSimulation()` — 노드 타입별 charge 강도 조정
  - session: -900, turn: -380, tool: -100
- `d3.zoom()` — 줌/팬, `scaleExtent([0.05, 5])`
- `d3.drag()` — 드래그 후 노드 핀 고정
- SVG defs:
  - 도트 그리드 패턴 (24×24, opacity 0.07)
  - 방사형 그라디언트 (session/turn/tool/subagent)
  - glow filter (feGaussianBlur stdDeviation=4)
  - 화살표 마커 (일반 / spawn 색상 구분)
- 링크: 베지어 곡선, 노드 반지름 기준 시작/끝점 계산
- 클릭: circle에 glow filter, 패널 표시
- 더블클릭: child session으로 이동
- Tree/Force 토글: BFS 레이아웃 ↔ 포스 시뮬레이션

### 중요 결정사항

- **ApexCharts destroy+recreate 방식**: 필터 변경 시 `chart.updateOptions()`보다 카테고리 수가 바뀔 때 더 안정적
- **D3 노드 드래그 핀 고정**: `dragEnded`에서 `fx/fy`를 null로 해제하지 않음 → 의도적 핀
- **타임라인 스파인 padding-left: 36px**: 도트 중심(14px) + 여유 공간으로 계산
- **Turn 카드 클래스 우선순위**: has-errors > high-cost > spawns-subagent (에러가 최우선)

### 다음 단계
- [ ] 반응형 768px 이하 모바일 실제 테스트
- [ ] ApexCharts 툴팁 한국어 포맷 확인
- [ ] D3 그래프 노드 수가 많을 때(300+) 성능 확인
- [ ] 브라우저 캐시 문제 시 `?v=2` 쿼리스트링 버전 처리

---

## [2026-02-20] - 웹 대시보드 버그 수정 및 기능 개선 (5개 이슈)

### 작업 내용
- 웹 대시보드 테스트 중 발견된 5개 버그/기능 이슈 일괄 수정
- 실제 세션 데이터(aki 98dfebb5: 1030턴, 63 서브에이전트, 8 compaction)로 검증

### 수정 이슈 목록

#### 이슈 1 (CRITICAL): 서브에이전트 세션 파일 연결 안 됨
- **근본 원인**: OpenClaw이 서브에이전트 완료 후 세션 파일을 soft-delete → `{uuid}.jsonl.deleted.{timestamp}`로 rename. `find_subagent_child_session()`이 `.jsonl` 확장자만 검색
- **추가 발견**: 서브에이전트 announce 메시지에 풍부한 stats 포함 (runtime, tokens, sessionKey, sessionId, transcript 경로)
  - announce 포맷: `[Day YYYY-MM-DD HH:MM TZ] A subagent task "label" just completed...Stats: runtime Xm Ys • tokens XK (in XK / out XK) • sessionKey ... • sessionId ... • transcript ...`
  - queued 포맷: `[Day ...] [Queued announce messages...] --- Queued #N A subagent task...` (한 메시지에 여러 announce)
- **수정**:
  - `find_subagent_child_session()`: `.jsonl.deleted.*` 패턴도 검색
  - `_resolve()` (web.py): `.deleted.*` 패턴도 검색
  - announce 메시지 정규식 파싱 → `_ANNOUNCE_RE` (sessionKey로 spawn과 매칭)
  - transcript 경로에서 .deleted 파일도 resolve하여 child_turns 복원
  - 파일명에서 session_id 추출 시 `.jsonl.deleted.*` 처리
- **검증**: aki 세션 63개 spawn 중 52개 announce 매칭 성공

#### 이슈 2 (HIGH): 빈 Assistant 박스 표시
- **근본 원인**: `{"type":"text","text":""}` 빈 텍스트 블록이 `assistant_texts`에 추가됨
- **수정**: `parse_session()` line ~552: `strip()` 후 빈 문자열 필터링

#### 이슈 3 (NEW): Context Window 표시
- **데이터**: `compaction` 이벤트의 `firstKeptEntryId` — 이 entry ID 이전의 모든 entry는 context에서 제거됨
- **수정**:
  - `CompactionEvent` 데이터클래스 추가 (first_kept_entry_id, tokens_before, timestamp)
  - `SessionAnalysis.compaction_events` 리스트 추가
  - `Turn.in_context: bool` — 마지막 compaction의 firstKeptEntryId 기준 계산
  - `_compute_context_status()`: entry ID 순서로 evicted turn 판별
  - 웹 UI: compacted 턴 회색+반투명 처리, context 경계에 노란 divider 표시

#### 이슈 4 (MEDIUM): User vs System 메시지 구분
- **수정**: `_detect_source()` 대폭 보강
  - `[Mon 2026-02-16 ...]` 타임스탬프 접두사 패턴 인식
  - `A subagent task` → subagent_announce, `A cron job` → cron_announce
  - `[message_id:]` → discord/telegram 채널 구분
  - 소스별 색상 배지: chat(초록), cron/cron_announce(시안), heartbeat(마젠타), discord(파란), subagent_announce(회색), system(회색)
  - 신규 배지 CSS: `.badge-discord`, `.badge-telegram`, `.badge-cron_announce`, `.badge-compacted`

#### 이슈 5 (UX): 서브에이전트 인라인 펼치기
- **수정**:
  - 서브에이전트 블록: 헤더 클릭으로 접기/펼치기 (task + child turns)
  - `renderChildTurn()`: child turn별 tools/thinking/response 표시 + 접기/펼치기
  - 재귀 표시: 서브에이전트 안의 서브에이전트도 depth 기반 들여쓰기로 표시
  - announce_stats 폴백: child_turns 없을 때 announce의 runtime/tokens 표시
  - `.outcome-unknown` 스타일 추가 (회색 배지)

### 변경 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `parser.py` | `.deleted` 파일 검색, announce 파싱, 빈 text 필터, CompactionEvent, in_context, source 세분화 |
| `web.py` | `_resolve()` .deleted 지원, compaction_events/in_context/announce_stats 직렬화 |
| `templates/detail.html` | compacted turn 시각화, compaction divider, source 배지, 서브에이전트 inline expand, 재귀 child turn |
| `static/style.css` | compacted/divider 스타일, 신규 배지 색상(discord/telegram/cron_announce/compacted), subagent expand UI |

### 기술 발견사항 (OpenClaw 동작 분석)

- **서브에이전트 lifecycle**: sessions_spawn → child session JSONL 생성 → 완료 시 announce 메시지 → child JSONL soft-delete (`.jsonl.deleted.{ISO-timestamp}`)
- **sessionKey vs sessionId**: sessionKey(spawn 시 생성, format: `agent:name:subagent:UUID`)의 UUID와 sessionId(실행 시 생성)는 **서로 다른 UUID**. sessionKey의 UUID가 자식 세션 파일명에 사용됨
- **compaction**: entry별 8-char hex `id` 필드로 추적. `firstKeptEntryId` 이전 entry는 context window에서 제거
- **announce 메시지**: agent가 busy할 때 쌓여서 `[Queued announce messages while agent was busy]`로 일괄 전달됨

---

## [2026-02-20] - ClawTracerX (OpenClaw Agent Monitor) 전체 구현

### 작업 내용
- OpenClaw 에이전트 모니터링 도구 `ClawTracerX` 신규 개발
- JSONL 세션 트랜스크립트 파서, CLI 분석 도구, Flask 웹 대시보드 완성
- 실제 에이전트 세션 데이터(aki, main, guardian, ddokddoki)로 전체 기능 검증

### 주요 변경사항

- `parser.py`: 핵심 JSONL 파서
  - Turn 기반 세션 구조화 (user → assistant → toolResult 매핑)
  - 서브에이전트 재귀 파싱 (runs.json → 자식 세션 JSONL 추적)
  - 토큰/비용 집계 (assistant 메시지 단위 usage + cost)
  - thinking 평문 추출 (Google/Gemini) 및 암호화 감지 (OpenAI)
  - 크론 실행 로그, 서브에이전트 레지스트리 파싱

- `cli.py`: CLI 분석 도구
  - `sessions`: 에이전트/타입별 세션 목록 (컬러 출력)
  - `analyze`: 세션 상세 분석 (턴별 툴콜 체인, 서브에이전트 내부 추적)
  - `raw`: 특정 턴의 JSONL 원문 pretty-print
  - `crons`: 크론 실행 이력
  - `subagents`: 서브에이전트 실행 이력
  - `cost`: 에이전트/타입/모델별 비용 요약

- `ctrace.py`: CLI 엔트리포인트 (argparse, web 서브커맨드 포함)

- `web.py`: Flask 웹 서버
  - REST API: `/api/sessions`, `/api/session/<id>`, `/api/session/<id>/graph`, `/api/cost`, `/api/crons`
  - 서브에이전트 트리 → 그래프 데이터 변환 (nodes + edges)

- `templates/`: Jinja2 HTML 템플릿
  - `sessions.html`: 세션 목록 (필터, 정렬, 클릭하여 상세)
  - `detail.html`: 세션 상세 (턴 접기/펼치기, 툴콜 결과, 토큰 바, Raw 모달)
  - `graph.html`: Canvas 기반 인터랙티브 실행 그래프 (드래그/줌/Force/Tree 레이아웃)
  - `cost.html`: 비용 대시보드 (에이전트/타입/모델/일별 바 차트)

- `static/style.css`: 다크 테마 프로덕션 UI (사이드바, 카드, 테이블, 그래프)
- `static/app.js`: 공유 JS 유틸리티 (fmtTokens, fmtCost, fmtDuration 등)

### 중요 결정사항

- **Python 3.9 호환**: macOS 기본 Python 3.9.6 사용 → `from __future__ import annotations` 필수 (`str | Path` 문법 불가)
- **외부 라이브러리 최소화**: Flask만 의존 (이미 clawmetry 때 설치됨), 그래프는 Canvas API 직접 구현 (D3.js 등 불필요)
- **재귀 서브에이전트 파싱**: runs.json의 childSessionKey로 자식 세션 JSONL을 재귀 파싱하여 전체 실행 트리 구성
- **토큰 추적 범위**: per-assistant-message 단위만 가능 (per-tool-call 불가 — OpenClaw JSONL 구조 한계)
- **thinking 데이터**: Google 모델은 평문 61%, OpenAI는 Fernet 암호화 → 모델별 분기 처리

### 데이터 소스 검증 결과

| 소스 | 경로 | 검증 |
|------|------|------|
| 세션 JSONL | `~/.openclaw/agents/{id}/sessions/*.jsonl` | ✅ message, toolCall, toolResult, compaction 등 7개 이벤트 타입 확인 |
| 서브에이전트 | `~/.openclaw/subagents/runs.json` | ✅ version 2, childSessionKey → 자식 JSONL 재귀 파싱 확인 |
| 크론 로그 | `~/.openclaw/cron/runs/*.jsonl` | ✅ finished 이벤트의 status, summary, error 확인 |
| 크론 잡 정의 | `~/.openclaw/cron/jobs.json` | ✅ job ID → label 매핑 |

### 테스트 및 검증

- **CLI 테스트**: `ctrace sessions`, `analyze`, `raw`, `crons`, `subagents`, `cost` 모두 실제 데이터로 정상 동작
- **서브에이전트 추적**: Nightly Review 크론(a6604d70) → 3개 서브에이전트(batch-0, batch-1, batch-1-retry) 추적 확인
- **웹 API 테스트**: Flask test_client로 7개 API 엔드포인트 전체 200 응답 확인
- **비용 검증**: 주간 비용 $621.66, 511개 세션, 에이전트별/모델별 분류 정상
- **웹 서버**: http://localhost:8901 에서 정상 구동 확인

### 문제 해결

- **문제**: Python 3.9에서 `str | Path` union type 문법 에러 (`TypeError: unsupported operand type(s) for |`)
- **해결**: `from __future__ import annotations` 추가하여 PEP 604 문법 활성화

### 참고사항

- 웹 서버 포트: 8901 (clawmetry 8900과 충돌 방지)
- `~/.zshrc`에 `alias ctrace="python3 $HOME/.openclaw/tools/ocmon/ctrace.py"` 등록됨
- 배포 예정 프로젝트 — UI/UX 프로덕션 레벨로 구현 (다크 테마, 반응형, 인터랙티브 그래프)

### 다음 단계
- [ ] 사용자 UI 피드백 반영 (서브에이전트 그래프 시각화 개선 등)
- [ ] 실시간 갱신 (WebSocket 또는 polling)
- [ ] pip 패키지화 및 배포 준비
- [ ] 추가 필터/검색 기능 (날짜 범위, 키워드 검색)

---
