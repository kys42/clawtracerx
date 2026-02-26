# Repository Guidelines

## Project Structure & Module Organization
- `clawtracerx/`: main Python package.
- `clawtracerx/cli.py`: CLI-facing commands (`sessions`, `analyze`, `web`, `cost`, etc.).
- `clawtracerx/session_parser.py`: JSONL/session parsing and core analysis logic.
- `clawtracerx/web.py`, `templates/`, `static/`: Flask web dashboard and UI assets.
- `tests/`: pytest suite (`test_*.py`) plus fixtures in `tests/fixtures/`.
- `npm/`: npm wrapper package that installs/releases the `ctrace` binary.

## Build, Test, and Development Commands
- `pip install -e ".[dev]"`: install editable package with dev dependencies.
- `pytest -v --tb=short`: run test suite.
- `ruff check clawtracerx/ tests/`: run lint checks used in CI.
- `ctrace sessions --last 20`: quick CLI smoke check against local OpenClaw data.
- `ctrace web --port 8901`: run local dashboard.
- `cd npm && npm pack`: verify npm package contents before publish.

## Coding Style & Naming Conventions
- Python 3.9+ target, 4-space indentation, UTF-8 source.
- Ruff is the style gate (`E`, `F`, `W`, `I`) with `line-length = 120`.
- Use `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants.
- Keep CLI output helpers pure and small; put parsing/aggregation logic in parser modules.

## Testing Guidelines
- Framework: `pytest` (configured via `pyproject.toml`).
- Name files as `tests/test_<module>.py`; name tests as `test_<behavior>()`.
- Add regression tests for parsing edge cases and CLI formatting changes.
- For fixture-driven tests, place sample session data under `tests/fixtures/`.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history: `feat: ...`, `fix: ...`, `docs: ...`.
- Keep commits focused; separate parser logic, UI, and docs changes when possible.
- PRs should include:
  - concise problem/solution summary,
  - linked issue (if applicable),
  - test/lint evidence (`pytest`, `ruff`),
  - screenshots or GIFs for `templates/` or `static/` UI changes.

## Security & Configuration Tips
- This tool reads from `~/.openclaw/*`; avoid committing local session data or logs.
- Treat tokens/cost/session transcripts as sensitive operational data.
