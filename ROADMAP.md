# 🗺️ Whisper Project Roadmap

This document tracks the current state of the Whisper Transcription Pipeline and outlines planned features and improvements. This is a living document intended to guide both human developers and AI agents (like Jules).

## 🟢 Current Status (February 20, 2026)

- **Core Pipeline:** Functional (Discovery -> Metadata -> Transcription -> Diarization -> Analytics -> Storage).
- **API:** FastAPI endpoints for most operations are implemented and tested.
- **Worker:** Celery-based async processing is stable.
- **Diarization:** Integrated with `pyannote.audio`.
- **Database:** PostgreSQL schema with migrations (up to `005_add_processing_step`).
- **Deployment:** Ansible-based deployment for Windows and local Docker-based development.
- **Testing:** Unit and integration tests cover most core components.

## 🟡 In Progress / Recently Added

- **Observability (Step Tracking):** Migration `005` added columns for `processing_step`. Implementation in worker tasks and beat is underway (see `docs/plans/segment_tracking_beat_observability.plan.md`).
- **Heartbeat & Stuck Detection:** Refined beat tasks to monitor "stuck" processing more effectively.

## 🔴 Planned / Upcoming Tasks

### 1. Observability Enhancements (Jules-friendly)
- [ ] Fully implement `processing_step` updates in `app/worker/tasks.py`.
- [ ] Add estimated % progress to transcription logs based on audio duration.
- [ ] Expose `processing_step` in API responses (`RecordingListItem`, `RecordingDetail`).
- [ ] Implement per-step Prometheus metrics for better Grafana dashboards.

### 2. Feature Improvements
- [ ] **Multi-language support:** Better detection and handling for non-Hebrew calls.
- [ ] **Advanced Analytics:** Keyword spotting, sentiment analysis (using lightweight LLMs).
- [ ] **UI Refresh:** Improve the Grafana dashboard or build a simple React-based frontend for transcript viewing.
- [ ] **Contact Sync:** Optimize Google Contacts lookup (caching, batching).

### 3. Developer Experience (DX)
- [ ] **Jules Integration:** Ensure the repo is "Jules-ready" (completed via `ROADMAP.md`, `AGENTS.md` update, and health checks).
- [ ] **CI/CD Pipeline:** Set up GitHub Actions for automated testing on PRs.
- [ ] **Better Mocking:** Improve integration tests by using better mocks for Whisper/Pyannote to avoid needing heavy ML models for every test run.

---

## 🛠️ Instructions for Agents

If you are an AI agent working on this repo:
1.  **Read `AGENTS.md`** for general guidelines.
2.  **Run `python scripts/agent_health_check.py`** to verify your environment.
3.  **Check `docs/plans/`** for detailed implementation guides of specific features.
4.  **Add tests** for every new feature or bug fix. Use `pytest` for all verifications.
