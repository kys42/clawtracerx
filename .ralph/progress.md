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
