#!/usr/bin/env python3
"""
One-off script to remove duplicate tasks from the Celery Redis queue.

- process_recording: keep one per recording_id (oldest).
- enqueue_pending_recordings: keep one.
- Other tasks: keep all.

Run from repo root or from inside a container that can reach Redis:
  python scripts/purge_celery_duplicates.py
  REDIS_URL=redis://localhost:6379/0 python scripts/purge_celery_duplicates.py

Or inside Docker (from host):
  docker exec whisper-worker python /app/scripts/purge_celery_duplicates.py
"""

import base64
import json
import os
import re
import sys


def get_redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://redis:6379/0")


def parse_message(raw: bytes) -> tuple[str | None, str | None]:
    """Parse a Celery message; return (task_name, recording_id or None)."""
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, None
    headers = obj.get("headers") or {}
    task = headers.get("task")
    if task == "process_recording":
        # Get recording_id from argsrepr e.g. "('e002b2e3-6c8f-4bb7-87ea-1ac0e6334e29',)"
        argsrepr = headers.get("argsrepr") or ""
        match = re.search(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", argsrepr)
        return task, match.group(1) if match else None
    if task == "enqueue_pending_recordings":
        return task, "__single__"
    return task, None


def main() -> int:
    try:
        import redis
    except ImportError:
        print("Need redis package: pip install redis", file=sys.stderr)
        return 1

    redis_url = get_redis_url()
    queue_name = "celery"

    print(f"Connecting to {redis_url} ...")
    try:
        r = redis.from_url(redis_url, decode_responses=False)
        r.ping()
    except Exception as e:
        print(f"Redis connection failed: {e}", file=sys.stderr)
        return 1

    raw_list = r.lrange(queue_name, 0, -1)
    total = len(raw_list)
    print(f"Queue '{queue_name}' has {total} messages")

    if total == 0:
        print("Nothing to do.")
        return 0

    # Celery: LPUSH (add left), BRPOP (take right). So list is [newest, ..., oldest].
    # We iterate from right to left (oldest first); keep first occurrence per key.
    seen_process_recording: set[str] = set()
    seen_cleanup = False
    kept: list[bytes] = []

    for i in range(len(raw_list) - 1, -1, -1):
        raw = raw_list[i]
        task, key = parse_message(raw)
        if task == "process_recording" and key:
            if key in seen_process_recording:
                continue
            seen_process_recording.add(key)
        elif task == "enqueue_pending_recordings":
            if seen_cleanup:
                continue
            seen_cleanup = True
        kept.append(raw)

    # Rebuild queue: we have kept = [oldest_kept, ..., newest_kept]. BRPOP takes from right.
    # So we need rightmost = oldest_kept. RPUSH in order kept -> list [oldest_kept, ..., newest_kept]
    # with oldest at index 0 (left) and newest at -1 (right). BRPOP takes from right = newest first. Wrong.
    # So we must push in reverse: for m in reversed(kept): rpush(m). Then list is [newest_kept, ..., oldest_kept],
    # rightmost = oldest_kept, BRPOP gets oldest_kept first. Correct.
    removed = total - len(kept)
    if removed == 0:
        print("No duplicates found.")
        return 0

    print(f"Keeping {len(kept)} messages, removing {removed} duplicates")
    r.delete(queue_name)
    for m in reversed(kept):
        r.rpush(queue_name, m)
    print("Queue updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
