# Ralph Loop Prompt

## 프로젝트
- 이름: ClawTracerX
- 스택: Python 3.9+ / Flask / Jinja2 / Vanilla JS / pytest
- 경로: ~/.openclaw/tools/ocmon/

## 매 루프에서 수행할 작업
1. `.ralph/prd.json`을 읽고 `passes: false`인 최고 우선순위 스토리를 선택
2. 해당 스토리를 완전히 구현 (placeholder 금지)
3. 구현 전 기존 코드를 충분히 검색 — "없다고 가정"하지 마라
4. 빌드 & 테스트 실행:
   ```bash
   ruff check clawtracerx/ tests/
   pytest -v --tb=short
   ```
5. 통과하면:
   - prd.json에서 해당 스토리의 `passes`를 `true`로 업데이트
   - git add & commit (스토리 ID + 제목 포함)
   - `.ralph/progress.md`에 이번 루프 작업 내용과 배운 점 추가
   - **후속 태스크 추가**: 방금 완료한 작업에서 추가 개선이 필요하거나, 디테일하게 못 다룬 부분, 엣지 케이스, 관련 영역의 일관성 문제 등이 보이면 prd.json에 후속 스토리를 즉시 추가한다 (다음 루프에서 처리)
6. 실패하면:
   - 에러를 분석하고 수정 시도
   - 수정 후 다시 빌드 & 테스트
7. **모든 스토리가 완료되어도 멈추지 마라** — 아래 "자율 확장" 절차로 이어간다

## 자율 확장 (모든 스토리 완료 시)
모든 `passes: false` 스토리가 없으면:
1. 코드베이스를 전체 탐색 (Python, HTML, JS, CSS)
2. 버그, UX 개선점, 누락 기능, 테스트 갭, 성능 문제, TODO/FIXME를 찾는다
3. 발견한 항목을 새 스토리(다음 번호)로 `.ralph/prd.json`에 추가
4. 추가한 스토리 중 최고 우선순위를 즉시 구현 시작
5. 반복

## 프로젝트 구조
```
clawtracerx/
├── __init__.py           __version__ = "0.1.0"
├── __main__.py           CLI 엔트리포인트 (argparse)
├── session_parser.py     JSONL → SessionAnalysis (핵심 파서, 1400+줄)
├── cli.py                CLI 커맨드 → ANSI 터미널 출력
├── web.py                Flask 서버 + REST API + Jinja2
├── gateway.py            OpenClaw WebSocket RPC 클라이언트
├── config.py             설정 관리
├── templates/            Jinja2 HTML (base, sessions, detail, cost, lab 등)
└── static/
    ├── app.js            공유 유틸 (fetchJSON, fmtTokens 등)
    ├── turns.js          턴 렌더링
    ├── i18n.js           다국어 지원
    └── style.css         Dark Pro 디자인 시스템 (CSS 변수 체계)
```

## 코딩 규칙
- **Python 3.9 호환 필수**: `from __future__ import annotations` 사용
- `session_parser.py` dataclass 변경 시 `web.py`의 `_serialize_*()` 함수도 수정
- CSS는 `var(--*)` 변수 체계 사용. 새 컴포넌트는 기존 변수 활용
- 웹 UI 변경 시 `ctrace web --debug --port 8901`로 직접 확인
- 테스트에서 `session_parser._subagent_cache`를 `None`으로 리셋 필수

## 규칙
- 한 루프에 한 스토리만 처리
- DO NOT IMPLEMENT PLACEHOLDER — FULL IMPLEMENTATIONS ONLY
- 코드가 이미 존재하는지 충분히 검색하라
- 테스트가 깨지면 다음 스토리로 넘어가지 마라
- ruff lint도 통과해야 한다
- **절대 멈추지 마라** — 스토리가 없으면 새로 만들어서 계속 개선하라
