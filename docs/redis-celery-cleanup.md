# Redis / Celery cleanup

How to clean Redis and the Celery queue so only relevant state remains. The **database is the source of truth** for what should be processed; the queue is repopulated every 2 minutes by `enqueue_pending_recordings`.

## What Redis holds

- **Broker (queue):** List `celery` — pending task messages. Only `enqueue_pending_recordings` enqueues `process_recording`; it runs every 2 minutes.
- **Result backend:** Task results (e.g. `celery-task-meta-<id>`). Used by Flower and for task status. **`result_expires` is set to 86400 (24 hours)** in `app/worker/celery_app.py`, so old results are removed automatically.

## When to clean

- After fixing config (e.g. removing duplicate enqueuers or wrong timeout): clear the queue so the next periodic run repopulates from DB.
- To drop stale or duplicate messages: purge the queue; DB-driven enqueue will re-add only what is `QUEUED` or recoverable `PROCESSING`.

## Safe cleanup: purge the Celery queue

This removes **all** pending tasks from the queue. No need to clear result keys manually — they expire in 24 hours.

**On Windows (from your Mac via Ansible):**

```bash
cd /path/to/whisper
# macOS: required to avoid "worker in dead state" with pywinrm
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible-playbook ansible/purge_celery_queue.yaml -i ansible/inventory.ini
```

Or use the wrapper (sets the env var for you):

```bash
cd /path/to/whisper/ansible
./run-playbook.sh purge_celery_queue.yaml -i inventory.ini
```

**Or run directly on the server:**

```powershell
cd C:\app
docker compose exec worker celery -A app.worker.celery_app purge -f
```

**Effect:** The queue is empty. Within 2 minutes, `enqueue_pending_recordings` (Celery Beat) will run and re-enqueue all `QUEUED` recordings and reset stuck `PROCESSING` ones, so the queue is repopulated from the DB. Do **not** purge if you want to keep the current pending tasks; use this when you want to “reset” the queue to match DB state.

## Optional: remove duplicate messages only

If the queue has many duplicate `process_recording` messages for the same recording (e.g. from an old config), use the one-off script to de-duplicate instead of a full purge:

```bash
docker compose exec worker python /app/scripts/purge_celery_duplicates.py
```

See `scripts/purge_celery_duplicates.py` and `ansible/purge_celery_duplicates.yaml`.

## Timeout vs heartbeat

Stuck detection does **not** rely on Redis or a task time limit. The worker updates `recordings.updated_at` (heartbeat) every 2 minutes; the periodic task marks a recording as stuck when it is `processing` and `updated_at` is older than 15 minutes. So:

- **No need to set `TASK_TIMEOUT_SECONDS`** for correctness; leave it unset so long files can complete.
- Result backend expiry (24 h) is only for keeping Redis small; it does not affect stuck detection.
