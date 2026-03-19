# Track Plan: Analytics Microservice Implementation

This plan outlines the phased implementation of the Analytics microservice based on the `data_analytics_strategy.md`. All work follows the project's TDD-first workflow.

## Phase 1: Foundation & Data Models (Alembic) [checkpoint: 551b60b]
Goal: Update the PostgreSQL schema to support advanced analytics and vector embeddings.

- [x] Task: Initialize Alembic for the `analytics/` service. 1472a18
    - [ ] Write configuration to `alembic.ini`.
    - [ ] Create base environment in `app/db/migrations/`.
- [x] Task: Create migration for `Enrichment.fingerprint_json`. 17c7ec8
    - [ ] Write test for schema migration.
    - [ ] Implement SQLAlchemy model update.
    - [ ] Run migration on Supabase.
- [x] Task: Enable PGVector and add `Transcript.embedding`. 19d7b4d
    - [ ] Write test for vector operations.
    - [ ] Implement model update for `Transcript`.
    - [ ] Run migration on Supabase.
- [ ] Task: Conductor - User Manual Verification 'Foundation & Data Models' (Protocol in workflow.md)

## Phase 2: Core Analytics Commands (Precalculations) [checkpoint: 3dc17d7]
Goal: Implement the "Metric Cache" and fingerprint generation logic.

- [x] Task: Implement `GenerateFingerprintCommand`. abbd5ef
    - [ ] Write TDD tests for WPM, turn velocity, and overlap calculation.
    - [ ] Implement logic in `analytics/app/commands/fingerprint.py`.
- [x] Task: Implement Materialized View Refresh Command. 6731173
    - [ ] Write test for `caller_intelligence_mv` refresh.
    - [ ] Implement command in `analytics/app/commands/refresh_mv.py`.
- [x] Task: Implement `GenerateEmbeddingCommand`. 6b47570
    - [ ] Write test for embedding generation using a mock model.
    - [ ] Implement command in `analytics/app/commands/embedding.py`.
- [ ] Task: Conductor - User Manual Verification 'Core Analytics Commands' (Protocol in workflow.md)

## Phase 3: Analytics Queries & Business Intelligence [checkpoint: bb202fe]
Goal: Expose high-fidelity signals via read-optimized queries.

- [x] Task: Implement `CallerIntelligenceQuery`. 0bead2b
    - [ ] Write TDD tests for person-based aggregations.
    - [ ] Implement logic in `analytics/app/queries/caller_intel.py`.
- [x] Task: Implement `GetSystemBottlenecksQuery`. 12f1b4e
    - [ ] Write test for model performance and hardware cost analysis.
    - [ ] Implement logic in `analytics/app/queries/bottlenecks.py`.
- [x] Task: Implement Semantic Similarity Search. 6f550d0
    - [ ] Write test for vector cosine similarity search.
    - [ ] Implement query in `analytics/app/queries/similarity.py`.
- [ ] Task: Conductor - User Manual Verification 'Analytics Queries' (Protocol in workflow.md)

## Phase 4: API & Integration [checkpoint: 3aa8274]
Goal: Expose analytics via FastAPI and hook into the worker pipeline.

- [x] Task: Implement FastAPI Routes in `analytics/app/api/`. 7f8d0c3
    - [ ] Write integration tests for all endpoints.
    - [ ] Implement routes and Pydantic schemas.
- [x] Task: Integration - Worker Pipeline Trigger. b96a31b
    - [ ] Write test for triggering analytics precalculation after transcription.
    - [ ] Implement task hook in `app/worker/tasks.py`.
- [ ] Task: Conductor - User Manual Verification 'API & Integration' (Protocol in workflow.md)
