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
