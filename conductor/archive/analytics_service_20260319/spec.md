# Track Specification: Analytics Microservice

## Overview
Implement a high-performance analytics microservice following the CQRS (Command Query Responsibility Segregation) pattern, based on the `data_analytics_strategy.md`. This service will provide deep behavioral insights, acoustic metrics, and semantic intelligence from transcribed Hebrew recordings.

## Goals
- **CQRS Architecture:** Separate write/precalculation logic (Commands) from read/aggregation logic (Queries).
- **Behavioral Innovation:** Implement "Conflict & Interruption" index, WPM analysis, and Silence Archetype detection.
- **Performance Optimization:** Use a "Layered Cache" approach with `fingerprint_json` columns and Materialized Views.
- **Semantic Intelligence:** Integrate PGVector for transcript embeddings and similarity search.

## Technical Requirements

### 1. CQRS Structure
- **Commands:** Logic in `analytics/app/commands/` for:
  - Generating "Call Fingerprints" (`fingerprint_json`).
  - Refreshing Materialized Views.
  - Generating Vector Embeddings.
- **Queries:** Read-only logic in `analytics/app/queries/` for:
  - Aggregated statistics.
  - Caller Intelligence reports.
  - Trend analysis.
- **API:** FastAPI routes in `analytics/app/api/` exposing these queries.

### 2. Data Models (Alembic)
- Update `Enrichment` table with `fingerprint_json` (JSONB).
- Add `Transcript.embedding` (Vector) using PGVector.
- Create Materialized Views:
  - `caller_intelligence_mv`
  - `system_bottleneck_mv`

### 3. Processing Pipeline (Worker Hook)
- Hook into the existing Celery worker pipeline (after Step 5: Finalization) to trigger analytics precalculation.

## Success Criteria
- [ ] Analytics service successfully reads from the Supabase DB.
- [ ] `fingerprint_json` populated for existing recordings.
- [ ] Materialized views created and refreshable via commands.
- [ ] REST API endpoints for analytics return accurate, low-latency data.
- [ ] Unit tests for all commands and queries with >80% coverage.
