# Unified Development & Testing Workflow

This document establishes the **mandatory** workflow for all agents (Gemini CLI, Jules, etc.) and human developers to ensure consistent, high-quality results.

## 1. Preparation Phase ("The Setup")

Before modifying any code:

1.  **Sync & Clean:**
    *   Ensure `git status` is clean.
    *   Pull the latest changes: `git pull origin main`.
2.  **Baseline Verification:**
    *   Run the full test suite to establish a passing baseline.
    *   Command: `make test`
    *   *Constraint:* If tests fail *before* you start, **STOP**. Report the failure or fix the baseline first.
3.  **Environment Check:**
    *   Verify the virtual environment is active and dependencies are up-to-date.
    *   Command: `make venv` (ensures venv exists)

## 2. Implementation Loop ("The Work")

For every feature or bug fix:

1.  **Reproduction / Specification (Test First):**
    *   **Bug Fix:** Create a reproduction script or a new test case that fails, demonstrating the bug.
    *   **New Feature:** Create a new test file (e.g., `tests/unit/test_new_feature.py`) defining the expected behavior.
    *   *Goal:* You must have a "Red" (failing) state that confirms the need for change.
2.  **Code Changes:**
    *   Implement the minimal changes required to pass the test.
    *   Adhere to Project Standards:
        *   **Type Hinting:** Mandatory for all new functions/methods.
        *   **Async/Await:** Use `async def` for I/O bound operations; `def` for CPU bound.
        *   **Error Handling:** Use `try/except` blocks with specific exception types; log errors using `structlog` (or project logger).
        *   **File Paths:** Use `pathlib.Path`, never string manipulation for paths.
        *   **Encoding:** Always specify `encoding='utf-8'` for file I/O.
3.  **Iterative Verification:**
    *   Run the *specific* test you created.
    *   Command: `pytest tests/unit/test_your_feature.py`
    *   Repeat until "Green" (passing).

## 3. Final Verification ("The Done Definition")

A task is **NOT DONE** until all of the following are true:

1.  **New Tests Pass:** The specific test case for the feature/fix passes.
2.  **No Regressions:** The *entire* test suite passes.
    *   Command: `make test`
    *   *Note:* If running locally without Postgres, ensure `SQLite` fallback tests pass.
3.  **Linting & Types:**
    *   Code formatting adheres to project style (e.g., `black` or `ruff` if configured).
    *   No new type errors (if `mypy` is used).
4.  **Documentation:**
    *   Update docstrings for modified functions.
    *   If a new environment variable or configuration is added, update `.env.example` and `docs/configuration.md`.
    *   If a new dependency is added, update `requirements.txt`.
5.  **Cleanup:**
    *   Remove any temporary reproduction scripts or debug print statements.

## 4. Jules/Agent Specifics

*   **Autonomy:** If a step fails (e.g., existing tests break), you are authorized to fix them *if and only if* the breakage is a direct result of your valid change (e.g., a signature update). Otherwise, investigate the regression.
*   **Reporting:** When marking a task as done, explicitly state:
    *   "New test created: `tests/...`"
    *   "Verification command run: `make test`"
    *   "Result: PASSED"

## 5. Troubleshooting Common Issues

*   **Database Connection Failed:**
    *   *Context:* The project supports a seamless fallback to SQLite for testing when Postgres is unavailable.
    *   *Action:* Ensure you are not hardcoding `asyncpg` checks; allow the `conftest.py` logic to handle the DB connection.
*   **Path/Encoding Errors:**
    *   *Context:* Hebrew filenames require strict UTF-8 handling.
    *   *Action:* Verify `os.environ["LANG"]` or explicit `encoding="utf-8"` in open().
