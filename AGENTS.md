# Repository Guidelines

## Project Structure & Module Organization
- `app/` contains the FastAPI service, Celery worker, folder watcher, and processing pipeline. Key areas include `app/api/`, `app/db/`, `app/processors/`, `app/services/`, and `app/worker/`.
- `tests/` holds unit and integration tests (see markers in `pytest.ini`).
- `Calls/` is the default watch folder for incoming recordings; `outputs/` stores generated artifacts.
- `docs/` contains deeper operational and architectural docs; `ansible/` and `monitoring/` support deployment and metrics.

## Build, Test, and Development Commands
- **Ansible (macOS):** When running playbooks against Windows, set `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` or use `ansible/run-playbook.sh` to avoid fork-safety errors with pywinrm.
- `docker-compose up -d` starts API, worker, watcher, and infrastructure locally.
- `docker-compose run --rm migrate` runs Alembic migrations.
- `uvicorn app.main:app --reload` runs the API without Docker.
- `celery -A app.worker.celery_app worker --loglevel=info` starts the worker.
- `python -m app.watcher.folder_watcher` starts the watcher.
- `make dev` / `make stop` orchestrate local Docker via `ansible/` for the standard setup.

### Working with a virtual environment (venv)
- Create and use a venv for local runs and tests: `make venv` then `source .venv/bin/activate` (or on Windows: `.venv\\Scripts\\activate`).
- With venv activated: `pip install -r requirements.txt`, then `pytest`, `uvicorn app.main:app --reload`, etc.
- Or run without activating: `make test` (uses `.venv/bin/python` and `.venv/bin/pytest` if venv exists).

## Coding Style & Naming Conventions
- Python code follows standard PEP 8 conventions: 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes.
- Keep modules focused by feature (`processors`, `services`, `watcher`, `worker`).
- Lint/type tools are listed in `requirements*.txt` (`ruff`, `mypy`) even if not wired to CI; use them when touching core logic.

## Testing Guidelines
- Pytest is configured in `pytest.ini` with markers: `unit`, `integration`, `db`, `slow`.
- Run all tests: `pytest`. Run unit-only: `pytest tests/unit/`. Run integration: `pytest tests/integration/`.
- Test files follow `test_*.py` naming; prefer focused, deterministic unit tests for processor logic.

## Commit & Pull Request Guidelines
- Recent history uses short, imperative subjects (e.g., “Add …”, “Fix …”, “Update …”); keep the first line under ~72 chars.
- PRs should include: summary, test results (commands + outcomes), and any relevant configuration changes.
- If you change API behavior or data models, update `docs/` and migration notes as needed.

## Configuration & Secrets
- Local configuration lives in `.env`; never commit secrets or tokens.
- `credentials.json` is required for Google Contacts integration; keep it out of Git history and document any setup steps in `docs/`.

## Working with Jules (Google Jules Cloud)
Jules is an asynchronous agent that can handle larger tasks. If you are Jules:
1.  **Check the Roadmap:** Look at `ROADMAP.md` for prioritized tasks.
2.  **Environment Check:** Run `python scripts/agent_health_check.py` to verify your environment.
3.  **Use Makefile:** Prefer `make venv` and `make test` for environment and verification.
4.  **Async Nature:** Remember that you may be running tasks over long periods; ensure logs are informative (step tracking, estimated progress).
5.  **Documentation:** Keep `docs/plans/` updated with your progress if working on a long-running feature.
