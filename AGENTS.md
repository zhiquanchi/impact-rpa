# Repository Guidelines

## Project Structure

- `main.py`: Primary CLI entry point (browser automation + menus).
- `vision_rpa.py`: Optional “vision RPA” handler (LLM + screenshots) used by the date-picker helpers.
- `config/`: Runtime configuration and templates:
  - `config/settings.json` (timeouts, proposal count, vision config)
  - `config/template.txt`, `config/templates.json`
- `logs/`: Runtime logs and (when enabled) screenshots.
- Test scripts live at repo root (e.g., `test_date_picker_interactive.py`) and in `scripts/`.

## Build, Test, and Development Commands

- Create an environment (Python 3.11+):
  - `uv sync` (if you use `uv`; lockfile: `uv.lock`)
  - or `python -m venv .venv` then `pip install drissionpage loguru plyer pydantic pyperclip questionary rich`
  - vision extras (optional): `pip install openai pyautogui pillow`
- Run the app: `python main.py`
- Impact 平台相关测试脚本（需要 Chrome/Edge 已打开并登录 Impact）：
  - `uv run python scripts/test_impact_cross_month_date.py`（跨月日期验证脚本）
  - `uv run python test_next_month_date.py`（在 Send Proposal 弹窗内测试设置下个月日期）
- Desktop notification smoke test: `python scripts/test_notification.py`

## Coding Style & Naming Conventions

- Python: 4-space indentation, follow PEP 8, prefer type hints on public methods and data objects.
- Logging: use `loguru.logger` instead of `print` for runtime output (Rich is used for terminal UI).
- Files: runnable scripts follow `test_*.py`; keep helpers in modules (e.g., `notification_service.py`).

## Testing Guidelines

- Tests in this repo are executable scripts (not a pytest harness). Keep them idempotent and safe to run.
- When adding a new scenario, update `TEST_DATE_PICKER.md` if it changes setup, coverage, or user steps.

## Commit & Pull Request Guidelines

- Commit messages follow a Conventional Commits style, often with scopes: `feat(date-picker): ...`, `fix: ...`, `chore(logging): ...`.
- PRs: include a short problem statement, repro/verification steps, and (if UI/automation behavior changes) a brief screen recording or screenshots plus the relevant `config/settings.json` knobs used.

## Security & Configuration

- Do not commit secrets in `config/settings.json`. Prefer environment variables for vision: `VL_API_KEY`, `VL_BASE_URL`.
- If enabling screenshots on error, verify `logs/` does not contain sensitive customer data before sharing.
