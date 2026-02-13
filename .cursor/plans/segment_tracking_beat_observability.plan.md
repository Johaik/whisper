---
name: ""
overview: ""
todos: []
isProject: false
---

# More informative segment tracking and beat-based hang/failure visibility

## Current state

- **Segment tracking:** Only `processing_segments_count` (integer). Worker logs "Transcription progress: N segments" every 5 segments (and 1). No indication of which pipeline step the job is in.
- **Stuck detection (beat):** `enqueue_pending_recordings` runs every 2 min, finds PROCESSING rows where `updated_at` is older than `stuck_processing_threshold_sec` (e.g. 15 min), and resets them to QUEUED or FAILED. It does **not** log which step or how many segments those recordings had.
- **Failures:** `error_message` is set to the exception string. We do **not** persist "failed at step X" or "last segment count".

## Goals

1. **More informative worker logs:** Step name in progress lines; duration/estimated % during transcribe; clear "failed at step X (N segments)" on errors.
2. **Step visibility in DB and API:** Persist current pipeline step (and optionally step start time).
3. **Beat logs and failure context:** Beat logs stuck recordings with file name, step, segment count, and last update age; when marking stuck as failed, set `error_message` to include step and segments. On task failure, include step (and segment count when in transcribe) in `error_message`.

---

## 1. Schema: add processing step (and optional step start time)

**File:** [app/db/models.py](app/db/models.py)

- Add nullable column `processing_step: Mapped[str | None]` (e.g. `"parse_metadata"`, `"extract_metadata"`, `"transcribe"`, `"diarization"`, `"analytics"`, `"store_results"`). Only set while `status == PROCESSING`; clear on success or failure.
- Add nullable `processing_step_started_at: Mapped[datetime | None]` so beat can log "in step X for Ym".

**New migration:** Add these columns to `recordings` (e.g. `add_processing_step_to_recordings.py`). Update [tests/db/test_migrations.py](tests/db/test_migrations.py) `expected_columns` for `recordings` to include `processing_step` and `processing_step_started_at`.

---

## 2. Worker: set step and enrich logs/errors

**File:** [app/worker/tasks.py](app/worker/tasks.py)

- **Set/clear step:** At the start of each major block (Step 0–5), set `recording.processing_step = "..."` and `recording.processing_step_started_at = datetime.utcnow()`; commit. In the `finally` that clears segment progress, also set `processing_step = None` and `processing_step_started_at = None`.
- **Progress callback (transcribe):** Enrich the log line with step name and, when `metadata.duration_sec` is available, elapsed time and **estimated %** (e.g. assume ~~2 segments per minute: `estimated_segments = max(1, int(metadata.duration_sec / 30))`, `pct = min(99, 100 * segments_count // estimated_segments)`). Log e.g. "Transcription progress: 30 segments (~~15% estimated, elapsed 2m)".
- **Step 2 start log:** Include duration when available, e.g. "Step 2: Transcribing audio... (duration 28m)".
- **On failure (all exception handlers):** When setting `recording.error_message`, include the current step (and, if in transcribe, segment count), e.g. "Timeout in step transcribe (45 segments): TimeLimitExceeded(1800)" or "Step diarization failed: ".

---

## 3. Beat: log stuck recordings with step/segments and set error_message

**File:** [app/worker/tasks.py](app/worker/tasks.py) — `enqueue_pending_recordings`

- When iterating over `stuck`, before changing status: log one line per stuck recording with `id`, `file_name`, `processing_step`, `processing_segments_count`, `updated_at`, `age_sec`.
- When marking as **failed** (max retries): set `error_message` to include step and segments and "last update Xm ago (cleanup)".
- When resetting to **queued**: keep current behavior (`error_message = None`).

---

## 4. API: expose processing_step and processing_step_started_at

**Files:** [app/api/schemas.py](app/api/schemas.py), [app/api/routes.py](app/api/routes.py)

- Add `processing_step: str | None = None` and `processing_step_started_at: datetime | None = None` to `RecordingListItem` and `RecordingDetail` (and `RecordingBase` if used). Responses will include them from the model.

---

## 5. Optional: Estimated progress and Prometheus metrics

**Estimated progress (in worker logs):** Implemented in section 2 (progress callback uses `metadata.duration_sec` for estimated % and elapsed time in log lines).

**Prometheus metrics (optional):**

- **Where:** API already exposes `/metrics`; add gauges or info metrics there, or document that Flower/Celery metrics remain the primary task-level source.
- **Metrics to add (e.g. in [app/main.py](app/main.py) or a small metrics module used by the API):**
  - `whisper_processing_recordings_total` — count of recordings with `status=processing` (could be a gauge updated on each queue/status request or a periodic scrape of DB).
  - `whisper_processing_step_info{step="transcribe", recording_id="..."}` — or a single gauge `whisper_processing_segments_count` for the current in-progress recording (if only one worker). Simpler option: add labels to an existing or new gauge such as `whisper_recording_progress{step="transcribe", segments="45"}` for the single active job.
- **Implementation:** Query DB for PROCESSING recordings (or use a shared cache updated by the worker); expose one gauge per recording or a summary (e.g. `whisper_processing_count`, `whisper_processing_segment_count` for the first processing recording). Keep scope minimal: e.g. one gauge `whisper_processing_segments_count` (value = segment count of the first processing recording, or 0) and optionally `whisper_processing_step` as an info label or separate gauge so Grafana can show "current step" and "current segments".

---

## 6. Documentation

- **[docs/monitoring.md](docs/monitoring.md):** Update "Worker logs: segment progress" to mention step name, estimated %, and elapsed time; add "Beat logs: stuck detection" with example log line and `error_message` format. If Prometheus metrics are added, document the new gauges and example Grafana queries.
- **[docs/failed-tasks-analysis.md](docs/failed-tasks-analysis.md):** Note that `error_message` may include "Step X (N segments)" for timeouts and "Stuck in step X (N segments); last update Ym ago (cleanup)" for beat cleanup.

---

## 7. Pytest: tests for all relevant behavior

Add or extend tests so that segment/step tracking and beat behavior are covered.

### 7.1 Unit tests

**File:** [tests/unit/test_schemas.py](tests/unit/test_schemas.py)

- Add tests that `RecordingListItem` and `RecordingDetail` include `processing_step` and `processing_step_started_at` (nullable, optional in constructor, present in serialization).

**File:** [tests/unit/test_worker_config.py](tests/unit/test_worker_config.py) (if needed)

- No change required unless new config keys are added (e.g. for segment estimation heuristic). Optional: test that `stuck_processing_threshold_sec` / `heartbeat_interval_sec` are used (already covered indirectly by integration tests).

### 7.2 DB / migration tests

**File:** [tests/db/test_migrations.py](tests/db/test_migrations.py)

- In `test_recordings_table_has_correct_columns`, add `"processing_step"` and `"processing_step_started_at"` to `expected_columns` for the recordings table after the new migration.

**File:** [tests/db/test_models.py](tests/db/test_models.py)

- Add test that a `Recording` can have `processing_step` and `processing_step_started_at` set and persisted (e.g. create recording, set these fields, commit, reload, assert values).
- Optional: test that clearing them on success is consistent (covered by integration test below).

### 7.3 Integration tests: process_recording (worker)

**File:** [tests/integration/test_celery_tasks.py](tests/integration/test_celery_tasks.py)

- **processing_step and processing_step_started_at set during steps:** In a test that runs `process_recording` with mocks, either:
  - Assert that at some point during execution the recording had `processing_step` set (e.g. by querying in a side-effect or by inspecting DB after a partial run), or
  - Prefer: test that **after successful completion** `processing_step` and `processing_step_started_at` are **None** (cleared in finally), and that **during** transcribe the progress callback updates both segment count and step (mock transcribe to call progress_callback and then assert DB has processing_step="transcribe" and processing_segments_count set before the mock returns). This may require running the task in a thread and querying DB while it is in progress, or using a mock that captures the callback and then running the callback and checking DB.
- **Error message includes step and segments on failure:** In existing tests that trigger metadata or transcribe failure (e.g. `test_process_recording_handles_metadata_error`), extend the assertion on `recording.error_message` to contain the expected step string (e.g. "extract_metadata" or "transcribe") and, for transcribe failure, segment count if applicable. Add a **new test** that forces a failure **during transcribe** (e.g. transcribe_audio raises) and assert `error_message` includes step and segment count.
- **Progress callback updates segment count and step:** Existing `test_process_recording_passes_progress_callback_to_transcribe` and `test_process_recording_clears_segment_progress_on_success` already cover callback and clearing. Extend or add:
  - Test that when progress_callback is invoked, the recording row has `processing_step="transcribe"` and `processing_segments_count` updated (e.g. call the captured progress_callback with 5, then query DB and assert recording.processing_segments_count == 5 and processing_step == "transcribe").
  - Test that after success both `processing_segments_count` and `processing_step` (and `processing_step_started_at`) are None.

### 7.4 Integration tests: enqueue_pending_recordings (beat)

**File:** [tests/integration/test_celery_tasks.py](tests/integration/test_celery_tasks.py) (or a dedicated test class)

- **Stuck detection logs and error_message:** Create a recording in PROCESSING with `updated_at` in the past (e.g. `cutoff - 1 second`), set `processing_step="transcribe"`, `processing_segments_count=45`, `retry_count` such that the next stuck run will mark it failed (e.g. `retry_count = task_max_retries - 1`). Run `enqueue_pending_recordings()`. Assert:
  - Recording status is FAILED (or QUEUED if retry_count is lower, depending on desired case).
  - If failed: `error_message` contains the step and segment count and "cleanup" or "Stuck".
- **Stuck logging:** Use `caplog` or a log capture to assert that a log line was emitted containing the recording's file_name (or id), step, and segment count when a recording is considered stuck. Optionally assert age_sec or "Stuck" in the message.
- **No-op when not stuck:** Recording in PROCESSING with `updated_at` recent; run beat; assert status remains PROCESSING and no FAILED/QUEUED change.
- **Enqueue QUEUED:** Already covered indirectly; optional: add one test that creates QUEUED recordings and runs beat and asserts they are enqueued (process_recording.delay called or status set to PROCESSING). Existing watcher/API tests may cover this; add here only if beat’s enqueue path is not yet tested.

### 7.5 Integration tests: API

**File:** [tests/integration/test_api_recordings.py](tests/integration/test_api_recordings.py)

- **List and detail include processing_step and processing_step_started_at:** Add test that creates a recording in PROCESSING with `processing_step="transcribe"` and `processing_step_started_at` set; GET list and GET detail; assert response JSON includes `processing_step` and `processing_step_started_at` with the expected values. Add test that for a DONE recording these fields are null/absent or null.
- Reuse or extend existing fixtures that set `processing_segments_count` to also set `processing_step` and `processing_step_started_at` where relevant.

### 7.6 Test summary table


| Area                            | File                                     | Tests to add/extend                                                               |
| ------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------- |
| Schemas                         | tests/unit/test_schemas.py               | processing_step, processing_step_started_at on list/detail                        |
| Migrations                      | tests/db/test_migrations.py              | expected_columns for recordings                                                   |
| Models                          | tests/db/test_models.py                  | Recording processing_step, processing_step_started_at persist                     |
| Worker process_recording        | tests/integration/test_celery_tasks.py   | step set/cleared; error_message has step/segments; progress updates step+segments |
| Beat enqueue_pending_recordings | tests/integration/test_celery_tasks.py   | stuck logging; stuck→failed error_message; no-op when not stuck                   |
| API                             | tests/integration/test_api_recordings.py | list/detail return processing_step, processing_step_started_at                    |


---

## Implementation order

1. Migration + model: add `processing_step` and `processing_step_started_at`; update test_recordings_table_has_correct_columns.
2. Worker: set/clear step and step_started_at; enrich progress and step-start logs (including estimated %); include step/segments in all failure error_message.
3. Beat: per-stuck logging; when marking stuck as failed, set error_message with step and segments.
4. API: add processing_step and processing_step_started_at to schemas and responses.
5. Optional: Prometheus gauges for processing count / step / segment count (and docs).
6. Docs: monitoring.md and failed-tasks-analysis.md.
7. Pytest: add all tests above (schemas, migrations, models, worker, beat, API) and run full suite.

