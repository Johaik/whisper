# Failed tasks analysis (Windows deployment)

## Summary

- **DB:** 4 recordings in `failed` status.
- **Flower “23 failed”:** That count is **task runs** (attempts), not unique recordings. Each retry is one failed task in Flower, so 4 recordings × several attempts can show as many failed tasks. The **source of truth** is `recordings.status = 'failed'` in the DB (4 rows).

---

## The 4 failed recordings

| Recording ID | File | Duration | retry_count | error_message | updated_at |
|-------------|------|----------|------------|----------------|------------|
| c85b90e2-... | Call recording 3014_190910_221233.m4a | **~61 min** | 3 | Max retries exceeded | 2026-02-04 22:18:32 |
| ab167b5a-... | Call recording +18134353769_200301_171119.m4a | **~68 min** | 3 | Max retries exceeded | 2026-02-04 22:18:32 |
| 4fc36bcc-... | Call recording 0586469010_200609_165234.m4a | **~60 min** | 3 | Max retries exceeded | 2026-02-04 22:18:32 |
| b52da034-... | Call recording 086230762_200923_143109.m4a | **~38 min** | 3 | Max retries exceeded | 2026-02-04 22:18:32 |

All four are **long** (38–68 min). Same `updated_at` suggests they were all marked failed in one go (e.g. by the periodic stuck cleanup after repeated timeouts).

---

## Root cause (fixable)

**Task timeout (30 min).**  
With `TASK_TIMEOUT_SECONDS=1800` (30 min), each run hits `TimeLimitExceeded(1800)` before finishing. The task resets the recording to `queued` and retries. After `task_max_retries` (3), the recording is marked `failed` with “Max retries exceeded”. So:

- **Fix:** Increase or remove the time limit so long files can finish.
  - In `C:\app\.env` (or your deploy env): set e.g. `TASK_TIMEOUT_SECONDS=7200` (2 h) or `14400` (4 h), or omit/`0` for no limit.
  - Restart the worker after changing.
- **Then:** Reset these 4 to retry:
  ```sql
  UPDATE recordings SET status = 'queued', error_message = NULL, retry_count = 0 WHERE status = 'failed' AND id IN (
    'c85b90e2-c37c-4267-944d-f4559a326e29',
    'ab167b5a-39b5-4608-bb90-c409c36b142b',
    '4fc36bcc-db3b-4c1c-b125-847075e7e86a',
    'b52da034-03ee-4563-a495-5564da9ce738'
  );
  ```
  Or reset all failed: `UPDATE recordings SET status = 'queued', error_message = NULL, retry_count = 0 WHERE status = 'failed';`

---

## What can be improved in code (done)

- **Preserve root cause in DB:** When marking a recording as failed after max retries, we now keep the last specific error (e.g. “Timeout exceeded: TimeLimitExceeded(1800)”) in `error_message` instead of only “Max retries exceeded”. That makes future analysis easier.

---

## What to treat as not relevant

1. **“23 failed” in Flower vs 4 in DB**  
   Flower counts every **task execution** (including retries). The DB counts **recordings**. So 23 failed tasks for 4 recordings is expected. No bug.

2. **Generic “Max retries exceeded”**  
   For these four, the underlying cause was timeout; the generic message was set by the max-retries path. With the code change above, new failures will store the real reason.

3. **Same timestamp for all four**  
   Expected if the periodic cleanup job marked them all in one run after they had been stuck/timeout for too long.

4. **Whether to retry or skip**  
   If you don’t need these four calls transcribed, you can leave them as `failed` or set `status = 'skipped'`. No code change required.
