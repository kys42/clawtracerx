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
