# Stuck at 1069 Done / No New Completions – Root Cause

## What we saw (diagnose_stuck playbook)

- **DB:** 20 queued, **1 processing**, 1069 done, **0 failed**
- **Processing recording:** `e002b2e3-6c8f-4bb7-87ea-1ac0e6334e29` — **Call recording 5454_210513_095857.m4a**
- **Worker logs:** Started this task at 16:43; file duration **01:03:00** (63 minutes of audio); step “Transcribing audio…” then “Processing audio with duration 01:03:00.882”. No ERROR/FAIL/Exception. Heartbeat is updating (`updated_at` stays recent).
- **Redis queue:** 93 messages (many `enqueue_pending_recordings` every 2 min; worker is busy so they stay pending).
- **Beat:** Sending `enqueue_pending_recordings` every 2 min as expected.

## Root cause

**Tasks are not failing.** The pipeline is blocked by **one long-running task**:

1. **Single worker, concurrency 1** → only one Celery task runs at a time.
2. The only task running is **transcribing a 63-minute file** on CPU. That can take **hours** (often 2–4× realtime or more).
3. Until that task finishes, the worker does not start the next one, so **done** stays at 1069.
4. `enqueue_pending_recordings` is also in the same queue; while the worker is busy with this long `process_recording`, it never runs, so the 20 QUEUED rows are not turned into new `process_recording` tasks. When the long task finally completes, the worker will run the pending enqueuer tasks and then the next `process_recording`s.

So: **1069 is “stuck” only because the single worker is still working on one 63‑minute file.** No DB/Celery bug; it’s throughput limited by one very long job.

## What you can do

1. **Wait**  
   Let the current task finish. After that, the worker will process the next tasks (including enqueuer and then more recordings).

2. **Limit task length (optional)**  
   Set `TASK_TIMEOUT_SECONDS` in `.env` (e.g. 7200 = 2 hours). Tasks that run longer will be marked failed/queued (depending on retry logic), so one endless job doesn’t block the queue forever. See `docs/windows-access-and-debugging.md` and `app/worker/tasks.py`.

3. **Skip or cap very long files**  
   You could add logic to skip or fail-fast for files over N minutes (e.g. 60) so 63‑minute files don’t tie up the single worker. Not implemented today.

4. **More workers (if you have CPU/memory)**  
   Run a second worker container (or increase `worker_concurrency` in config) so one long task doesn’t block all progress. Two workers = one can run the long file while the other runs shorter jobs and `enqueue_pending_recordings`.

## Re-run diagnosis

```bash
cd ansible && ansible-playbook diagnose_stuck.yaml
```

Check: **PROCESSING RECORDINGS** (one row = the long file), **FAILED RECORDINGS** (0 = no failures), **Worker logs** (no ERROR/Exception), **API QUEUE STATUS** (queued: 20, processing: 1).
