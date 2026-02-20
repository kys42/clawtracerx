## [2026-02-20] - sessions.json 파싱 추가 — 초기 컨텍스트 + 메타데이터 추적

### 작업 내용
- OpenClaw `sessions.json`의 `systemPromptReport`를 파싱하여 세션 초기 컨텍스트 추적 기능 추가
- JSONL에 있지만 미추출이던 `compaction.summary`, `thinking_level_change` 이벤트 파싱 추가
- 턴별 캐시 히트율 계산 추가
- 새 CLI 커맨드 `ocmon context <session-id>` 추가

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
| `ocmon.py` | +12줄 — `context` (alias `ctx`) 서브커맨드 추가 |
| `web.py` | +45줄 — API에 `context`, `compaction_events`, `context_tokens` 등 필드 추가. 턴별 `thinking_level`, `cache_hit_rate` 직렬화 |

### 중요 결정사항
- **sessions.json 파싱 방식 선택**: OpenClaw 소스 수정(커스텀 JSONL 이벤트 추가) vs sessions.json 읽기 vs API payload 로깅 3가지 옵션 중, OpenClaw 수정 없이 기존 데이터를 활용하는 sessions.json 파싱으로 결정
- **systemPromptReport는 모든 세션에 있지 않음**: 크론 세션 일부는 report 없음 → graceful fallback 처리
- **서브에이전트 컨텍스트 제한 추적 가능**: OpenClaw은 서브에이전트에 AGENTS.md + TOOLS.md만 허용 → 세션 타입으로 추론 가능

### 테스트 및 검증
- `python3 -c "from parser import ..."` — 전체 임포트 성공
- `load_session_metadata('main', '5e57f3cb')` — injectedFiles 8개, skills 18개, tools 24개 정상 파싱
- `ocmon analyze cc52d980` — `cache_hit=35%`, `cache_hit=42%` 턴별 표시 확인
- `ocmon context 5e57f3cb` — 전체 컨텍스트 상세 출력 정상 (System Prompt 32.7KB, 8 files, 18 skills, 24 tools)
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

## [2026-02-20] - ocmon (OpenClaw Agent Monitor) 전체 구현

### 작업 내용
- OpenClaw 에이전트 모니터링 도구 `ocmon` 신규 개발
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

- `ocmon.py`: CLI 엔트리포인트 (argparse, web 서브커맨드 포함)

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

- **CLI 테스트**: `ocmon sessions`, `analyze`, `raw`, `crons`, `subagents`, `cost` 모두 실제 데이터로 정상 동작
- **서브에이전트 추적**: Nightly Review 크론(a6604d70) → 3개 서브에이전트(batch-0, batch-1, batch-1-retry) 추적 확인
- **웹 API 테스트**: Flask test_client로 7개 API 엔드포인트 전체 200 응답 확인
- **비용 검증**: 주간 비용 $621.66, 511개 세션, 에이전트별/모델별 분류 정상
- **웹 서버**: http://localhost:8901 에서 정상 구동 확인

### 문제 해결

- **문제**: Python 3.9에서 `str | Path` union type 문법 에러 (`TypeError: unsupported operand type(s) for |`)
- **해결**: `from __future__ import annotations` 추가하여 PEP 604 문법 활성화

### 참고사항

- 웹 서버 포트: 8901 (clawmetry 8900과 충돌 방지)
- `~/.zshrc`에 `alias ocmon="python3 $HOME/.openclaw/tools/ocmon/ocmon.py"` 등록됨
- 배포 예정 프로젝트 — UI/UX 프로덕션 레벨로 구현 (다크 테마, 반응형, 인터랙티브 그래프)

### 다음 단계
- [ ] 사용자 UI 피드백 반영 (서브에이전트 그래프 시각화 개선 등)
- [ ] 실시간 갱신 (WebSocket 또는 polling)
- [ ] pip 패키지화 및 배포 준비
- [ ] 추가 필터/검색 기능 (날짜 범위, 키워드 검색)

---
