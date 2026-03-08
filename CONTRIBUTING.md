# Contributing to ClawTracerX

## Branching Model

```
feature/xxx  ──PR──→  dev  ──PR──→  main  ──tag v*──→  Release + npm
hotfix/xxx   ──PR──→  main (긴급 수정만)
```

| Branch | Role | Protection |
|--------|------|------------|
| `main` | Production. Release-ready only | PR only, CI required |
| `dev` | Integration branch | PR only, CI required |
| `feature/*` | New features | Free commits |
| `fix/*` | Bug fixes | Free commits |
| `hotfix/*` | Urgent production patches | Direct PR to main |

## Branch Naming

- `feature/short-description` — 새 기능
- `fix/short-description` — 버그 수정
- `hotfix/short-description` — 긴급 프로덕션 패치

## PR Rules

1. **기능 개발**: `feature/*` or `fix/*` → `dev` PR 생성
2. **통합 릴리스**: `dev` → `main` PR 생성
3. **긴급 수정**: `hotfix/*` → `main` 직접 PR (예외적 상황만)
4. 모든 PR은 CI (lint + test) 통과 필수

## Commit Convention

```
<type>: <subject>

[optional body]
```

| Type | Description |
|------|-------------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 기능 변경 없는 코드 개선 |
| `test` | 테스트 추가/수정 |
| `docs` | 문서 변경 |
| `chore` | 빌드, CI, 의존성 등 |

Examples:
```
feat: add session export to CSV
fix: handle empty JSONL files in parser
refactor: extract turn boundary logic
```

## Release Process

1. `dev` → `main` PR 생성 및 머지
2. `main`에서 태그 생성:
   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```
3. GitHub Actions가 자동으로:
   - macOS (arm64) + Linux (x64) 바이너리 빌드
   - GitHub Release 생성
   - npm 패키지 배포

## Local Development

```bash
# Install (dev mode)
pip install -e ".[dev]"

# Run web server
ctrace web --debug --port 8901

# Run tests
pytest -v

# Lint
ruff check clawtracerx/ tests/
```

## Branch Protection Setup (Admin)

GitHub Settings → Branches → Branch protection rules:

### `main`
- [x] Require a pull request before merging
- [x] Require status checks to pass (lint, test)
- [x] Do not allow bypassing the above settings

### `dev`
- [x] Require a pull request before merging
- [x] Require status checks to pass (lint, test)
