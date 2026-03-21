# ClawTracerX 프론트엔드 현대화 제안서

> 작성일: 2026-03-09
> 상태: Phase 1 진행 중, Phase 2 향후 검토

## 1. 현재 상태 분석

### 정량 데이터

| 항목 | 수치 |
|------|------|
| HTML 템플릿 | 8개 (2,100줄) |
| JS 파일 | 3개 (1,492줄) — app.js 280, turns.js 481, i18n.js 731 |
| 인라인 JS (템플릿 내) | ~1,871줄 (lab.html 660줄이 최대) |
| CSS | 1개 (3,341줄), 44개 CSS 변수, 7개 @media |
| 백엔드 라우트 | 36개 (API 28 + 템플릿 8) |
| CDN 의존성 | 3개 (marked.js, ApexCharts, D3.js) |
| 빌드 도구 | 없음 (CDN only) |
| 배포 | PyInstaller 바이너리 + npm postinstall |

### 아키텍처 특성

```
Flask + Jinja2 → JSON API → Vanilla JS (innerHTML string concat) → DOM
```

- **렌더링**: 100% 문자열 연결 + innerHTML (가상 DOM 없음)
- **상태 관리**: 전역 변수 + localStorage (구조화 안 됨)
- **컴포넌트 재사용**: turns.js만 detail/lab 공유 (나머지 각 페이지 독립)
- **i18n**: 커스텀 `_t()` + `data-i18n` 속성 (344키, 한/영)
- **실시간**: SSE (lab) + 수동 Refresh (나머지)

---

## 2. Phase 1: HTMX + Alpine.js (실행 완료/진행 중)

### 선택 이유
1. 빌드 파이프라인 추가 없음 — CDN 2줄
2. PyInstaller 바이너리 호환 — 배포 프로세스 변경 없음
3. 점진적 적용 — 기존 코드와 공존
4. 1인 개발에 최적 — 학습 곡선 최소

### 추가 의존성
- htmx (~15KB gzip)
- Alpine.js (~15KB gzip)

---

## 3. Phase 2: Vue 3 + Vite (향후 검토)

### 전환 조건
- 세션 데이터 200개+ 넘어가 가상 스크롤 필요 시
- 팀 확장 계획 시
- TypeScript 타입 안전성 필요 시

### 아키텍처
```
Flask API (/api/*) — 기존 유지
     ↓
Vite build → dist/ (정적 HTML/CSS/JS)
     ↓
Flask static serving (dist/ 폴더)
     ↓
PyInstaller에 dist/ 포함
```

### 컴포넌트 구조
```
src/
  components/
    SessionCard.vue        ← sessions 목록 카드
    TurnCard.vue           ← 턴 렌더 (현재 turns.js 481줄 분해)
    ToolCallBlock.vue      ← 도구 호출 블록
    SubagentBlock.vue      ← 서브에이전트 (깊이 제한 prop)
    HeartbeatCard.vue      ← HB 카드
    CronCard.vue           ← Cron 카드
    HourBar.vue            ← 24h 시각화
    TextModal.vue          ← 텍스트 확장 모달
  pages/
    SessionsPage.vue
    DetailPage.vue
    LabPage.vue
    SchedulePage.vue
    CostPage.vue
  stores/
    sessions.ts            ← Pinia store
    turns.ts
  composables/
    useSSE.ts              ← SSE 훅
    usePolling.ts          ← 자동 갱신
    useI18n.ts             ← 기존 344키 마이그레이션
```

### 핵심 개선
- **가상 스크롤**: sessions 200개+ → DOM 15개만 유지
- **턴 상태 분리**: 펼침/접힘이 리렌더 시 유지
- **서브에이전트 깊이 제한**: `maxDepth` prop으로 DOM 폭발 방지
- **SSE 훅**: lab의 EventSource를 composable로 추상화
- **TypeScript**: 타입 안전 (API 응답 타입 정의)

### 예상 성능 개선

| 메트릭 | 현재 | Phase 2 후 |
|--------|------|-----------|
| sessions 렌더 (50개) | 160ms | 45ms |
| detail 로드 (50턴) | 800ms | 250ms |
| DOM 요소 | 5000+ | 300-500 (가상) |
| First Paint | 1.8s | 0.4s |

---

## 4. 비추천 선택지

### Next.js
- Python 백엔드 유지 필수 + PyInstaller 배포 → Node.js 런타임 불필요
- 바이너리에 Node.js 포함 시 200MB+ 증가
- 1인 프로젝트에 오버킬

### Svelte
- 커뮤니티/라이브러리 부족
- 팀 확장 시 채용 제한
- ApexCharts/D3 생태계와 호환 제한적

---

## 5. 프레임워크 비교표

| | HTMX+Alpine | Vue 3+Vite | React+Vite | Svelte | Next.js |
|---|---|---|---|---|---|
| 마이그레이션 시간 | 1-2주 | 3-4주 | 4-6주 | 3-4주 | 6-8주 |
| 빌드 파이프라인 | 불필요 | Vite | Vite | Vite | Next+Node |
| PyInstaller 호환 | 100% | 정적빌드 | 정적빌드 | 정적빌드 | 비호환 |
| 번들 추가량 | ~30KB | ~100KB | ~120KB | ~50KB | ~300KB |
| 1인 생산성 | 최고 | 높음 | 보통 | 높음 | 낮음 |
| 컴포넌트 재사용 | 제한적 | 강력 | 강력 | 강력 | 강력 |
| 가상 스크롤 | 불가 | 가능 | 가능 | 가능 | 가능 |
