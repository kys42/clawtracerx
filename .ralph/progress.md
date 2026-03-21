# Ralph Progress Log

> 각 루프 실행 후 작업 내용과 배운 점을 기록합니다.

## Loop 1 — US-001: 테스트 커버리지 대폭 확대

**작업 내용:**
- `conftest.py`에 7개 새 fixture 추가: `cron_dir`, `sessions_json`, `empty_session_path`, `session_with_compaction`, `session_with_thinking`, `session_with_malformed`, `_write_session` 헬퍼
- `test_session_parser.py`에 14개 테스트 추가: `load_cron_runs` (5), `load_session_metadata` (3), `get_raw_turn_lines` (2), parse_session 엣지 케이스 (4: empty, malformed, compaction, thinking)
- `test_web.py`에 15개 테스트 추가: 페이지 렌더링 (5), `/api/crons` (3), `/api/schedule` (2), `/api/health` (1), `/api/raw_turn` (3), `/api/cost` period (2)
- `test_cli.py`에 10개 테스트 추가: `cmd_sessions` (4), `cmd_cost` (2), `cmd_crons` (3) — capsys로 stdout 검증

**결과:** 69 → 108 테스트 (+39), ruff + pytest 모두 통과

**배운 점:**
- `/api/schedule` 응답 키가 `jobs`가 아니라 `cron_jobs`임 — API를 먼저 확인해야 함
- `conftest.py`의 `mock_openclaw_dir`에 `CRON_JOBS_FILE`, `CRON_RUNS_DIR`도 monkeypatch해야 cron 테스트가 동작
- E741 lint: 변수명 `l` 사용 불가 (ambiguous) — `entry`, `item` 등으로 대체

## Loop 2 — US-002: 디자인/UX 일괄 개선

**작업 내용:**
- **WCAG AA 대비 수정**: `--text-3` 색상 `#454954` → `#5c6170` (약 4.5:1 대비비로 상향)
- **호버 상태 강화**: `.data-table` hover를 `@media(hover:hover)` 래핑하여 터치 디바이스에서 ghost hover 방지, hover 강도 `0.04` → `0.06` 상향
- **에러 배너 시스템**: `app.js`에 `showErrorBanner(message, retryFn)` 함수 추가, `fetchJSONSafe` 실패 시 자동 표시 + Retry 버튼 + Dismiss. `role="alert"` 접근성 포함
- **에러 배너 CSS**: `.error-banner` 스타일 — 빨간 left border, error-muted 배경, slideInUp 애니메이션
- **모바일 햄버거 메뉴**: `base.html`에 `.hamburger` 버튼 + `.sidebar-overlay` 추가, 768px 이하에서 사이드바 slide-in/out 전환. 데스크톱에서는 숨김
- **접근성(aria-label)**: 모든 아이콘 전용 버튼에 aria-label 추가 — update dismiss, modal copy/toggle/close, copy path, raw view. 텍스트 모달에 `role="dialog" aria-modal="true"` 추가
- **Expand All / Collapse All**: `detail.html` 헤더에 2개 버튼 추가, turn-body + workflow-body + subagent-body 일괄 토글
- **모바일 반응형 보강**: 세션 카드 칩 wrap + 축소, filter-bar gap 축소, header-actions wrap, 일일 차트 높이 축소, cost breakdown 테이블 수평 스크롤

**결과:** ruff 통과, Python 파일 미변경으로 기존 108 테스트 영향 없음

**배운 점:**
- 모바일에서 사이드바를 60px 고정으로 축소하면 아이콘만 보여 사용성이 낮음 — 완전 숨기고 햄버거로 슬라이드 인하는 게 더 나음
- `@media(hover:hover)` 래핑으로 터치 디바이스의 "sticky hover" 문제를 예방할 수 있음
- `--text-3`을 올리면 disabled 상태와 일반 텍스트의 구분이 약해질 수 있으므로, disabled는 opacity로 처리하는 게 더 안전

## Loop 7 — US-024: 모바일 완전 대응 — 전 페이지 터치 UX + 반응형 레이아웃

**작업 내용:**
- style.css 끝에 US-024 전용 모바일 반응형 섹션 추가 (~200줄)
- **모달 전체화면**: `.modal`, `.diff-modal-overlay` 모두 768px 이하에서 padding:0, border-radius:0, height:100%
- **터치 타겟 44px**: `.btn`, `.btn-icon`, `.btn-close`, `.nav-link`, `.type-chip`, `.agent-chip`, `.hamburger` 모두 최소 44px
- **iOS 줌 방지**: 모든 input/select/textarea에 `font-size: 16px` 적용 (768px 이하)
- **Lab input bar 수정**: `left: 0` (기존 `left: 60px` 오류 수정)
- **Detail 페이지**: turn-header wrap, turn-body 패딩 축소, tc-result 스크롤 제한, ctx-table 수평 스크롤
- **Cost 페이지**: summary 1컬럼, 차트 높이 축소, breakdown 테이블 min-width로 수평 스크롤 보장
- **Schedule 페이지**: cron card 패딩 축소, runs table 수평 스크롤
- **Home 페이지**: stat-card 2열 wrap, feature-grid 1컬럼, 값 폰트 축소
- **Sessions 페이지**: page-header 세로 스택, search full-width, session-card 세로 레이아웃
- **Settings 페이지**: header/section 패딩 축소
- **Graph 페이지**: canvas touch-action:none (터치 드래그 지원)

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- 기존 768px 미디어쿼리가 여러 곳에 분산되어 있어 한 곳에 모으는 것보다 섹션별로 추가하는 게 유지보수에 유리
- iOS Safari는 input font-size < 16px일 때 자동 줌하므로 반드시 16px 적용 필요
- `min-height: 44px`이 `height`보다 안전 — 내용이 길어질 때 깨지지 않음
- Lab input bar의 `left: var(--sidebar-w)` → 모바일에서는 sidebar가 숨겨지므로 반드시 `left: 0`으로 덮어씌워야 함

## Loop 8 — US-025: 모바일 기능 동작 분석 + 추가 개선 태스크 생성

**작업 내용:**
- 전체 코드베이스를 375px 뷰포트 관점에서 분석
- 4개의 새 스토리 생성 (US-026~US-029):
  - US-026: Lab session-select min-width 300px 오버플로 + detail 검색 min-width 수정
  - US-027: D3 SVG 터치 pan/zoom 미지원 + 노드 패널 모바일 스크롤
  - US-028: Schedule 24h 바 hover-only 툴팁 + ApexCharts responsive 미설정
  - US-029: 터치 피드백 없음 (:hover만 사용, :active 없음)

**배운 점:**
- EventSource(SSE)는 iOS Safari 15+에서 잘 동작함, 호환성 문제 없음
- D3 zoom은 SVG에서 touch-action CSS가 없으면 iOS Safari에서 기본 스크롤로 처리됨
- Alpine.js의 @mouseenter/@mouseleave는 터치 이벤트를 발생시키지 않음 — @touchstart 별도 처리 필요
- ApexCharts는 `responsive` 배열로 breakpoint별 config 덮어쓰기 가능

## Loop 9 — US-028: Schedule 24시간 바 터치 툴팁 + ApexCharts 모바일 responsive

**작업 내용:**
- **schedule.html**: `hb-hour-seg`에 `@touchstart.prevent` 이벤트 추가 — 터치 시 hoveredHour 토글 (같은 시간 재탭하면 닫기)
- **schedule.html**: `hb-hours-bar`에 `@touchstart.outside="hoveredHour = null"` 추가 — 바 외부 터치 시 툴팁 닫기
- **cost.html**: `renderApexBar`에 `responsive` 배열 추가 — 480px 이하에서 차트 높이 축소, dataLabels/axis 폰트 9px, barHeight 70%, borderRadius 3
- **cost.html**: `renderApexArea`에 `responsive` 배열 추가 — 480px 이하에서 차트 높이 200px, x축 라벨 9px + rotate -60°, markers 축소, legend bottom 배치

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- Alpine.js의 `@touchstart.outside` 디렉티브로 외부 터치 감지를 간결하게 처리할 수 있음 — document 레벨 리스너 직접 등록 불필요
- `@touchstart.prevent`를 사용하면 터치 시 mouseenter 이벤트 발생을 막아 hover/touch 충돌 방지
- ApexCharts의 `responsive`는 차트 인스턴스별로 설정해야 함 — APEX_BASE에 넣으면 모든 차트에 같은 breakpoint 적용되어 bar/area 차트가 다른 최적값 불가

## Loop 10 — US-029: 모바일 터치 피드백 — :active 스타일 + hover 안전장치

**작업 내용:**
- **-webkit-tap-highlight-color: transparent**: 모든 인터랙티브 요소에 적용하여 iOS/Android 기본 파란색 하이라이트 제거
- **:active 규칙 추가**: 버튼(btn-primary, btn-outline, btn-icon, btn-close, hamburger, lang-btn), 카드(session-card, feature-card, summary-card, hb-card, cron-card), 칩(type-chip, agent-chip, stat-chip), 네비게이션(nav-link), 테이블 행(turn-header, workflow-header, tc-row, data-table clickable, modal-tool-btn)
- **터치 피드백 패턴**: 카드는 `scale(0.98)`, 칩은 `scale(0.95)`, 버튼은 `scale(0.97)` — 요소 크기에 비례한 미묘한 축소
- **@media(hover:none) 블록**: 터치 전용 기기에서 sticky hover 효과 비활성화 — session-card, feature-card, summary-card, hb-card, cron-card, type-chip, agent-chip, stat-chip, btn-primary, card, turn-card의 :hover에서 transform/box-shadow/border-color를 초기화

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- `@media(hover:none)`에서 hover 초기화 시 `initial`이 아닌 구체적 기본값을 써야 함 — `initial`은 CSS 속성의 명세 기본값이라 `var(--border)` 같은 테마값과 다를 수 있음
- transform 기반 피드백(`scale()`)이 background 변경보다 GPU 가속을 타서 60fps 유지에 유리
- `-webkit-tap-highlight-color: transparent`는 별도로 선언해야 함 — `all: unset` 같은 리셋에 포함되지 않음

## Loop 11 — US-030: Gateway RPC 키 오류 + Schedule 필드 불일치 수정

**작업 내용:**
- **gateway.py**: `patch_session()`과 `reset_session()`에서 `"sessionKey"` → `"key"` 변경. 게이트웨이 스키마가 `key` 필드를 기대하며 `additionalProperties: false`라 기존 호출이 모두 실패하고 있었음
- **web.py**: Schedule API에서 `"schedule_tz"` → `"timezone"` 변경하여 프론트엔드 `job.timezone` 참조와 일치
- **web.py**: `payload_message` 필드에 `text` 폴백 추가 — `systemEvent` 타입 크론은 `text` 필드를 사용하므로 `message`가 없을 때 `text`로 폴백

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- ANALYSIS_REPORT.md에 이미 5개 버그가 문서화되어 있었음 — 새 탐색 전 기존 분석 문서를 먼저 확인해야 함
- 게이트웨이 RPC는 `additionalProperties: false`이므로 잘못된 키를 보내면 서버에서 즉시 거부됨 — 에러 메시지에서 키 이름 힌트가 있었을 것

## Loop 12 — US-031: JSONL 파일 인코딩 에러 처리 강화

**작업 내용:**
- `_read_jsonl()`, `_quick_scan_session()`, `load_cron_runs()` JSONL 읽기 3곳에 `encoding="utf-8", errors="replace"` 추가
- non-UTF-8 바이트 포함 시 `UnicodeDecodeError` 대신 대체 문자(`\ufffd`)로 처리

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- Python 3.9의 `open()` 기본 인코딩은 시스템 로케일에 따라 다름 — macOS는 UTF-8이지만 명시적으로 지정하는 것이 안전
- `errors="replace"`는 데이터 무결성을 약간 희생하지만 파서 안정성을 크게 높임

## Loop 14 — US-033: 서브에이전트 감지를 sessions.json 기반으로 수정

**작업 내용:**
- **ANALYSIS_REPORT.md BUG-02 수정**: `"subagent" in str(file_path)` 체크가 실제로 작동하지 않는 문제
- `list_sessions()`: sessions.json을 에이전트별로 로드하여 세션 키에 `:subagent:` 패턴이나 `spawnedBy` 필드가 있으면 `"subagent"` 타입으로 오버라이드
- `_compute_totals()`: 새 `_is_subagent_session()` 함수 추가 — sessions.json의 `spawnedBy` 필드와 세션 키 패턴 기반 정확한 감지
- `_quick_scan_session()`: 깨진 `"subagent" in str(file_path)` 체크 제거 (list_sessions에서 오버라이드하므로 불필요)
- 추가로 `:hook:` 패턴도 감지하여 hook 타입 분류 지원

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- 서브에이전트 JSONL은 일반 세션과 같은 `agents/{id}/sessions/` 디렉토리에 일반 UUID 파일명으로 저장됨 — 경로에 "subagent" 문자열이 포함될 이유 없음
- sessions.json의 세션 키 형식: `agent:{agentId}:subagent:{uuid}` → `:subagent:` 패턴으로 정확한 감지 가능
- `load_session_metadata()`가 이미 `startswith` 매칭을 사용하므로 stem UUID의 prefix만으로도 매핑 가능

## Loop 13 — US-032: Lab 로그 파일 RotatingFileHandler로 디스크 성장 제한

**작업 내용:**
- `web.py`에 `import logging.handlers` 추가
- `FileHandler` → `RotatingFileHandler(maxBytes=5*1024*1024, backupCount=3)` 교체
- lab.log가 5MB 초과 시 자동 로테이션, 최대 3개 백업 유지 (lab.log.1, .2, .3)

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- `logging.handlers`는 `import logging`만으로는 사용 불가 — 별도 `import logging.handlers` 필요
- RotatingFileHandler는 스레드 안전함 — 기존 _lab_log_lock과 별도의 잠금 불필요

## Loop 14 — US-034: 브라우저 테스트 버그 수정 일괄 처리

**작업 내용:**
- `app.js` fetchJSON: 404 등 HTTP 에러 시 HTML 태그 strip 처리 → 깔끔한 에러 메시지만 표시
- `detail.html`: API 로드 실패 시 "Loading session..." 텍스트를 에러 메시지 + 돌아가기 링크로 교체
- `home.html`: Total Cost $0 버그 수정 — `costData.total.cost` → `costData.total_cost` 필드명 수정 + `period=all`로 전체 기간 집계
- `base.html`: Lab 네비게이션 disabled/soon 제거 → href="/lab" 활성 링크로 전환
- `base.html`: `<div id="toast-container">` 추가 — showToast 함수가 동작하도록

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- Home 페이지의 /api/cost 호출은 period 파라미터 없으면 기본 "week"로 필터링됨 — Total Cost엔 period=all 필수
- fetchJSON의 에러 텍스트가 HTML 페이지 전체를 포함할 수 있음 — 항상 태그 strip 필요

## Loop 15 — US-035: 검색/필터/드릴다운 기능 보완

**작업 내용:**
- 세션 검색 `data-search`에 `type`과 `channel` 추가 — "heartbeat" 검색이 이제 동작
- 검색 결과 카운트 표시 ("3 of 50 sessions") 추가
- Live 버튼, 비용 차트 드릴다운, URL 쿼리 파라미터 필터는 이미 구현되어 있어 변경 불필요

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- 기존 코드 검색이 중요 — PRD에 "구현 필요"로 적혀있어도 이미 구현된 경우가 많음
- 세션 카드의 data-search 속성에 모든 검색 가능 필드를 포함해야 텍스트 검색이 제대로 동작

## Loop 16 — US-036: 심화 기능 테스트 + 엣지케이스 탐색

**작업 내용:**
- 8개 점검 항목 코드 리뷰 완료, 6개 구체적 이슈 발견
- US-037: CSV Export BOM/개행/필드 누락
- US-038: 접근성 (세션 카드 키보드 nav + 모달 포커스 트랩)
- US-039: Lab SSE 재연결 로직 부재
- US-040: Settings web.log 미존재

**결과:** 코드 수정 없이 PRD에 4개 새 스토리 추가

**배운 점:**
- web.log는 아무 곳에서도 생성하지 않아 Settings 로그 뷰어가 항상 빈 결과 표시
- CSV export에서 BOM 없으면 Excel이 UTF-8을 인식 못함 — Windows 사용자 고려 필수
- EventSource의 error 이벤트는 transient/permanent 구분이 어려움 — readyState 체크 필수

## Loop 17 — US-037: CSV Export UTF-8 BOM + 개행 이스케이프 + 필드 보강

**작업 내용:**
- 클라이언트/서버 양쪽 CSV export에 UTF-8 BOM(`\uFEFF`) 추가
- 클라이언트 exportCSV()에서 개행 문자를 공백으로 치환
- header에 file_size, tool_calls, errors, subagents, channel 필드 추가 (클라이언트+서버)
- fields 배열 기반 루프로 리팩터링하여 유지보수 용이하게

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- CSV의 python csv.writer는 개행을 자동 처리하지만, JS 클라이언트 측은 수동으로 치환 필요

## Loop 18 — US-038: 접근성 개선

**작업 내용:**
- 세션 카드에 tabindex="0", role="link", aria-label, Enter/Space keydown 핸들러 추가
- 텍스트 모달: 열 때 첫 번째 버튼에 focus(), Tab 키 트랩 (first↔last 순환), 닫을 때 이전 요소로 포커스 복원

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- div onclick 패턴은 키보드/스크린리더에서 완전히 무시됨 — tabindex+role+keydown 필수
- 모달 포커스 트랩은 querySelectorAll('button, [href], ...')로 focusable 요소 목록 수집 필요

## Loop 19 — US-039: Lab SSE 재연결 + 상태 표시 개선

**작업 내용:**
- Lab SSE: readyState CLOSED 시 exponential backoff 재연결 (1s, 2s, 4s, 8s, 16s), 최대 5회
- 최대 재시도 초과 시 showToast로 사용자 알림
- init 이벤트 수신 시 reconnectCount 리셋
- stopStream()에서 reconnect 타이머 정리
- detail.html Live SSE에도 동일 패턴 적용 (readyState 체크 + backoff + 타이머 정리)
- i18n에 `lab.connection_lost` 키 추가 (ko/en)

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- EventSource error 이벤트는 readyState로 구분: CONNECTING=transient(브라우저 자동 재연결), CLOSED=permanent(수동 재연결 필요)
- clearTimeout으로 pending reconnect 정리 안 하면 stopStream 후에도 자동 재연결 발생

## Loop 20 — US-040: Settings 로그 뷰어 web.log 초기화

**작업 내용:**
- web.py에 web.log RotatingFileHandler 추가 (5MB, 3백업)
- after_request 훅으로 HTTP 요청 로깅 (static/SSE 제외)
- /api/logs에서 파일 미존재 시 `missing: true` 필드 반환
- settings.html에서 missing 파일일 때 "아직 생성되지 않음" 메시지 표시

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- Flask after_request는 모든 응답에 대해 호출됨 — static 파일과 SSE 스트림은 제외해야 로그가 과도해지지 않음

## Loop 21 — 자율 확장: 코드 리뷰 → US-041~043 추가 + US-041 구현

**작업 내용:**
- 코드베이스 전체 탐색으로 16개 이슈 발견 (HIGH 3, MEDIUM 5, LOW 8)
- US-041 (XSS 수정), US-042 (LRU 캐시+재귀 깊이), US-043 (턴 페이지네이션) 스토리 추가
- US-041 즉시 구현: turns.js의 t.user_source 3곳 + data-source 1곳 escHtml() 래핑

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- JSONL 파서 출력이 HTML 렌더링에 쓰일 때는 모든 필드를 escHtml()로 이스케이프해야 함
- CSS 클래스명에도 사용자 입력이 들어가면 attribute injection 가능

## Loop 22 — US-042: parse_session LRU 캐시 + 재귀 깊이 제한

**작업 내용:**
- `_parse_cache`를 `OrderedDict`로 변경, 캐시 히트 시 `move_to_end()` 호출 → 진정한 LRU
- eviction을 `popitem(last=False)` 사용으로 개선
- `parse_session()`에 `_depth` 파라미터 추가, `_PARSE_MAX_DEPTH=10` 초과 시 `recursive_subagents=False`
- `_build_turns`, `_enrich_spawns_from_announces`, `_try_load_missing_children`, `_resolve_child_from_transcript` 모두 depth 전파
- 테스트의 `_parse_cache` mock을 `OrderedDict()`로 업데이트

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- `OrderedDict.move_to_end()` + `popitem(last=False)` 조합으로 간단한 LRU 캐시 구현 가능
- 재귀 깊이 제한은 모든 중간 함수에 depth를 전파해야 함 — 6개 함수 시그니처 수정 필요

## Loop 23 — US-043: 대형 세션 턴 페이지네이션 + markdown 에러 핸들링

**작업 내용:**
- turns.js: renderTurns()를 페이지네이션 방식으로 리팩터링 — 초기 50개만 렌더, 나머지는 "Load more" 버튼
- _turnsPageState로 아이템 목록/렌더 상태 관리, _renderTurnsBatch()로 50개씩 추가
- compaction divider 위치가 pagination 경계와 겹쳐도 정확히 삽입되도록 처리
- app.js: marked.parse() try/catch 추가, 실패 시 raw 텍스트로 자동 폴백
- style.css: .load-more-turns 버튼 스타일 (dashed border, hover 시 accent 색상)
- i18n: turns.load_more / turns.remaining 키 추가 (ko/en)

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- innerHTML 일괄 삽입 → insertAdjacentHTML + 점진적 추가로 전환하면 대형 DOM 성능 개선
- workflow group이 pagination 경계를 넘을 수 있으므로 아이템 단위(turn/workflow)로 카운트해야 함

## Loop 24 — US-047: API 요청 파라미터 유효성 검증

**작업 내용:**
- `_int_param()` 안전 헬퍼 추가 — int() 변환 실패 시 기본값 반환 (6곳 적용)
- POST 엔드포인트 4곳: `get_json(force=True)` → `get_json(silent=True)` + None 체크 → 400
- US-044, US-045 (QA 중복 스토리) passes: true로 마킹

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- Flask의 `get_json(force=True)`는 Content-Type 무시하고 파싱하지만 잘못된 JSON에서 예외 발생 — `silent=True`가 안전
- 쿼리 파라미터는 항상 문자열 — int() 직접 변환은 위험

## Loop 25 — US-048: Graph 뷰 도구 노드 ID 충돌 방지

**작업 내용:**
- `tool:{tc.id[:16]}` → `tool:{tc.id}` 전체 ID 사용 (2곳: _build_graph, _add_subagent_graph)

**결과:** ruff 통과, pytest 160 tests 전부 통과

## Loop 26 — US-049: 세션 검색 필터 변경 시 정리

**작업 내용:**
- sessions.html `reload()`: 검색 입력 초기화, search-count 텍스트 초기화, #no-match-msg DOM 제거

**결과:** ruff 통과, pytest 160 tests 전부 통과

## Loop 24 — US-047: API 요청 파라미터 유효성 검증

**작업 내용:**
- `_int_param()` 안전 헬퍼 함수 추가 — ValueError/TypeError 시 기본값 반환
- 6개 엔드포인트의 `int(request.args.get(...))` → `_int_param(...)` 교체
- 4개 POST 엔드포인트의 `get_json(force=True)` → `get_json(silent=True)` + None 체크 → 400 반환
- US-044~046 (이전 QA에서 이미 수정된 중복 스토리) passes:true 처리

**결과:** ruff 통과, pytest 160 tests 전부 통과

**배운 점:**
- `request.get_json(force=True)`는 Content-Type 무시하고 파싱하지만 잘못된 JSON에서 500 에러 발생
- `get_json(silent=True)`는 파싱 실패 시 None 반환 — 더 안전한 패턴
