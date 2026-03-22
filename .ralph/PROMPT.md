# Ralph Loop Prompt

## 프로젝트
- 이름: ClawTracerX
- 스택: Python 3.9+ (Flask API 백엔드) + Next.js 15 (프론트엔드)
- 경로: ~/.openclaw/tools/ocmon/
- 프론트엔드: frontend/ (Next.js App Router + TypeScript + Tailwind + shadcn/ui)
- 백엔드 API: Flask (:8901) — clawtracerx/web.py의 /api/* 엔드포인트

## 매 루프에서 수행할 작업
1. `.ralph/prd.json`을 읽고 `passes: false`인 최고 우선순위 스토리를 선택
2. 해당 스토리를 완전히 구현 (placeholder 금지)
3. 구현 전 기존 코드를 충분히 검색 — "없다고 가정"하지 마라
4. 빌드 & 검증:
   ```bash
   # 백엔드 (Python 변경 시)
   ruff check clawtracerx/ tests/
   pytest -v --tb=short
   # 프론트엔드 (frontend/ 변경 시)
   cd frontend && npm run build
   ```
5. 통과하면:
   - prd.json에서 해당 스토리의 `passes`를 `true`로 업데이트
   - git add & commit (스토리 ID + 제목 포함)
   - `.ralph/progress.md`에 이번 루프 작업 내용과 배운 점 추가
   - **후속 태스크 추가**: 방금 완료한 작업에서 추가 개선이 필요하거나, 디테일하게 못 다룬 부분, 엣지 케이스, 관련 영역의 일관성 문제 등이 보이면 prd.json에 후속 스토리를 즉시 추가한다
6. 실패하면:
   - 에러를 분석하고 수정 시도
   - 수정 후 다시 빌드 & 테스트
7. **모든 스토리가 완료되어도 멈추지 마라** — 아래 "자율 확장" 절차로 이어간다

## 자율 확장 (모든 스토리 완료 시)
모든 `passes: false` 스토리가 없으면:
1. 코드베이스를 전체 탐색 (Python, TypeScript, React, CSS)
2. 버그, UX 개선점, 누락 기능, 테스트 갭, 성능 문제, TODO/FIXME를 찾는다
3. 발견한 항목을 새 스토리(다음 번호)로 `.ralph/prd.json`에 추가
4. 추가한 스토리 중 최고 우선순위를 즉시 구현 시작
5. 반복

## 프로젝트 구조
```
clawtracerx/                  ← Flask 백엔드 (수정하지 마라 — API만 사용)
├── web.py                    32개 /api/* JSON 엔드포인트
├── session_parser.py         핵심 파서
├── templates/                Jinja2 (레거시 — 건들지 마라)
└── static/                   JS/CSS (레거시 — 건들지 마라, 참조만)

frontend/                     ← Next.js 프론트엔드 (여기에서 작업)
├── src/app/                  App Router 페이지
├── src/components/           React 컴포넌트
├── src/lib/                  유틸 (api, format, hooks)
├── src/types/                TypeScript 타입
└── next.config.ts            API 프록시 (→ localhost:8901)
```

## Next.js 개발 규칙
- **기존 clawtracerx/ 코드는 절대 수정하지 마라** — API 소비자로서만 사용
- 기존 Flask 템플릿(templates/, static/)은 기능 참조용으로만 읽어라
- 각 페이지 구현 시 해당 Flask 템플릿의 JS 로직을 꼼꼼히 읽고 빠짐없이 옮겨라
- Tailwind + shadcn/ui 컴포넌트 사용, 프로덕션 레벨 디자인
- 다크/라이트 모드 양쪽 지원 (next-themes)
- 모바일 반응형 필수 (375px~)
- TypeScript strict 모드
- SWR로 데이터 페칭

## 규칙
- 한 루프에 한 스토리만 처리
- DO NOT IMPLEMENT PLACEHOLDER — FULL IMPLEMENTATIONS ONLY
- 코드가 이미 존재하는지 충분히 검색하라
- 빌드가 깨지면 다음 스토리로 넘어가지 마라
- **절대 멈추지 마라** — 스토리가 없으면 새로 만들어서 계속 개선하라
