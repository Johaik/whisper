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

## Phase 2: Core Analytics Commands (Precalculations)
Goal: Implement the "Metric Cache" and fingerprint generation logic.

- [ ] Task: Implement `GenerateFingerprintCommand`.
    - [ ] Write TDD tests for WPM, turn velocity, and overlap calculation.
    - [ ] Implement logic in `analytics/app/commands/fingerprint.py`.
- [ ] Task: Implement Materialized View Refresh Command.
    - [ ] Write test for `caller_intelligence_mv` refresh.
    - [ ] Implement command in `analytics/app/commands/refresh_mv.py`.
- [ ] Task: Implement `GenerateEmbeddingCommand`.
    - [ ] Write test for embedding generation using a mock model.
    - [ ] Implement command in `analytics/app/commands/embedding.py`.
- [ ] Task: Conductor - User Manual Verification 'Core Analytics Commands' (Protocol in workflow.md)

## Phase 3: Analytics Queries & Business Intelligence
Goal: Expose high-fidelity signals via read-optimized queries.

- [ ] Task: Implement `GetCallerIntelligenceQuery`.
    - [ ] Write TDD tests for person-based aggregations.
    - [ ] Implement logic in `analytics/app/queries/caller_intel.py`.
- [ ] Task: Implement `GetSystemBottlenecksQuery`.
    - [ ] Write test for model performance and hardware cost analysis.
    - [ ] Implement logic in `analytics/app/queries/bottlenecks.py`.
- [ ] Task: Implement Semantic Similarity Search.
    - [ ] Write test for vector cosine similarity search.
    - [ ] Implement query in `analytics/app/queries/similarity.py`.
- [ ] Task: Conductor - User Manual Verification 'Analytics Queries' (Protocol in workflow.md)

## Phase 4: API & Integration
Goal: Expose analytics via FastAPI and hook into the worker pipeline.

- [ ] Task: Implement FastAPI Routes in `analytics/app/api/`.
    - [ ] Write integration tests for all endpoints.
    - [ ] Implement routes and Pydantic schemas.
- [ ] Task: Integration - Worker Pipeline Trigger.
    - [ ] Write test for triggering analytics precalculation after transcription.
    - [ ] Implement task hook in `app/worker/tasks.py`.
- [ ] Task: Conductor - User Manual Verification 'API & Integration' (Protocol in workflow.md)
