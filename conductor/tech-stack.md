# Technology Stack: Whisper Call Transcription Pipeline

## 🐍 Language & Runtime
- **Python 3.10+:** The core application language for API, workers, and watcher.
- **Docker & Docker Compose:** Containerization for all microservices (API, Worker, Beat, Watcher, Redis, Postgres).

## 🚀 Backend Frameworks
- **FastAPI:** High-performance REST API for ingestion, querying, and monitoring.
- **Celery:** Distributed task queue for asynchronous audio processing.
- **Redis:** Message broker for Celery and state management.
- **Celery Beat:** Scheduler for periodic tasks (e.g., polling the database for queued items).

## 🗄️ Database & Storage
- **PostgreSQL + PGVector:** Relational database with vector similarity search capabilities for semantic intelligence.
- **CQRS Architecture:** Separate microservice logic for analytics precalculations (Commands) and read-optimized views (Queries/Materialized Views).
- **SQLAlchemy:** ORM (Object Relational Mapper) for database interactions.
- **Alembic:** Database migration tool for versioning the PostgreSQL schema.

## 🎤 Speech & ML Core
- **faster-whisper:** Optimized Whisper inference using CTranslate2.
- **ivrit-ai models:** Fine-tuned Hebrew-specific Whisper models (`large-v3-turbo-ct2`).
- **pyannote.audio:** Advanced speaker diarization and talk-time analytics.

## 🛠️ Dev & Ops
- **Ansible:** Playbooks for orchestrating deployments and managing local development environments.
- **Prometheus & Grafana:** Monitoring and observability stack for performance tracking.
- **Flower:** Real-time monitoring for the Celery task queue.

## 🔌 Integrations
- **Google Contacts API:** For looking up caller names via phone numbers.
- **HuggingFace:** Sourcing ML models and authentication for diarization.
