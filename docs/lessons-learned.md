# Lessons Learned: Shaping Features, Bugs, and Skills for Better Builds

Reflections from the segment-tracking, observability, and test-hang work—and how skills + framing improved efficiency.

---

## 1. How You Shaped Features and Bugs (What Worked)

### Ask for the outcome, not the implementation
- **Example:** “Check if segment tracking works and there are no hangs on Windows” → led to: DB check, migration run, stuck check, and a concrete “segment tracking works; no hangs” answer.
- **Lesson:** Describe the **goal** (e.g. “see progress in logs”, “know when/why jobs hang”). The agent can then choose schema, logs, beat, and tests.

### One sentence → full plan when you want it
- **Example:** “Segment tracking more informative + part of beat, understand when job hangs or why it fails” → turned into a **plan** (schema, worker, beat, API, docs, pytest) before any code.
- **Lesson:** When a change touches many layers, say “plan it” or “add optional X and pytest for all relevant” so you get a single, reviewable plan and tests in scope from the start.

### Deploy + environment in the question
- **Example:** “Check the **deployed** feature on **Windows**” made the agent use Ansible/WinRM and the real DB, not just local code.
- **Lesson:** Naming the environment (“Windows”, “deployed”, “in production”) pushes the agent toward the right tools (e.g. `.cursor/skills/windows-access-debug`) and real checks.

### “Build it” after the plan
- **Example:** Approving the plan with “build it” triggered implementation in a clear order: migration → worker → beat → API → docs → pytest.
- **Lesson:** Plan mode + “build it” keeps a single source of truth (the plan) and avoids rework from ad-hoc “do this file” requests.

---

## 2. How the Skill (windows-access-debug) Made Things Efficient

### What the skill did well
- **Single place for access:** Ansible one-liners, SSH tunnel, and “always set OBJC_…” are in one SKILL.md. The agent didn’t need to guess how to run commands on Windows.
- **Concrete commands:** Copy-paste commands for logs, DB queries, stuck check, worker restart. The agent used them as-is (e.g. `docker exec whisper-postgres psql ...`).
- **Correct context:** Description says “check worker logs, query the database on Windows, troubleshoot stuck/hanging recordings”—so when you asked about “deployed feature” and “hangs”, the agent **read the skill first** and then ran the right commands.

### How to reuse this pattern for other skills
1. **Name + description:** `name` and `description` should include the **trigger phrases** you’ll use (“Windows”, “debug”, “stuck”, “logs”, “deploy”).
2. **One doc, one concern:** One skill = one workflow (e.g. “access and debug Windows”). Don’t mix unrelated workflows in one skill.
3. **Copy-paste ready:** Use real commands (with your paths/ports) so the agent can run them without inventing syntax.
4. **Put it where the agent looks:** In Cursor, skills under `.cursor/skills/` (or your configured path) are suggested when the query matches; keep skill names and descriptions aligned with how you ask.

---

## 3. Patterns That Saved Time (and Avoided Pain)

### Observability up front
- **Segment tracking:** You asked for “see in logs” and “understand when/why it hangs or fails.” That led to: `processing_step`, beat **logging** stuck rows (file, step, segments, age), and **error_message** including step/segments. Debugging is now “read beat logs + one DB/API field.”
- **Lesson:** When adding a long-running or async flow, ask for “how will I monitor/debug it?” in the same breath. One round of “add observability” is cheaper than many “why did it hang?” sessions.

### Docs and code in one pass
- **Example:** `docs/monitoring.md` and `docs/failed-tasks-analysis.md` were updated in the same change set as the code (Flower timeout, beat logs, error_message format).
- **Lesson:** Include “update docs” in the plan (or in the same request) so runbooks and failure analysis stay in sync with behavior.

### Tests that match the plan
- **Example:** Plan said “pytest for all relevant”; implementation added schema, migrations, models, worker, beat, and API tests in one go.
- **Lesson:** “Add pytest for all relevant” (or “tests for this feature”) in the plan avoids “we forgot to test the beat task” and keeps coverage aligned with the feature.

### Fail fast in tests
- **Hang:** Integration tests hung when Postgres wasn’t running (connection block).
- **Fix:** `_test_db_reachable()` with a 2s socket check + `pytest.skip()` so DB-dependent tests **skip** instead of hanging. Optional: `heartbeat_interval_sec=0` in test settings so the worker doesn’t start a heartbeat thread and cause contention.
- **Lesson:** For tests that depend on external services (DB, Redis), add a cheap reachability check and skip when down. Document “run unit-only without DB” (e.g. `pytest tests/unit/`).

---

## 4. Checklist for Next Feature or Bug

Use this to shape the next ask so the agent can build better and more efficiently:

- [ ] **Outcome stated:** What should be true when we’re done? (e.g. “see segment progress in logs”, “know why a job was stuck”.)
- [ ] **Environment named:** Local, Windows, deployed, CI? (So the right skill and commands are used.)
- [ ] **Plan vs. implement:** Big change → ask for a **plan** first; then “build it” or “add optional X and tests.”
- [ ] **Observability:** How will we monitor or debug this? (logs, metrics, one or two DB/API fields.)
- [ ] **Docs:** Which runbook or doc should change? (e.g. monitoring, failed-tasks-analysis.)
- [ ] **Tests:** “Pytest for all relevant” or list layers (schemas, worker, beat, API).
- [ ] **Skills:** If this is a recurring workflow (e.g. “deploy to Windows”, “inspect Celery”), consider a small skill with trigger phrases and copy-paste commands.

---

## 5. One-Line Takeaway

**Shape the ask around the outcome and environment; put recurring workflows in a skill; include observability, docs, and tests in the same round.** That’s how we got segment tracking, beat observability, and a non-hanging test story without multiple back-and-forths.
