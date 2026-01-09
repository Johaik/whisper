# System Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           WHISPER TRANSCRIPTION SYSTEM                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │   Google     │    │   Folder     │    │   FastAPI    │                   │
│  │   Drive      │───▶│   Watcher    │───▶│   API        │                   │
│  │   (Source)   │    │              │    │              │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│                              │                   │                           │
│                              │                   │                           │
│                              ▼                   ▼                           │
│                       ┌──────────────┐    ┌──────────────┐                   │
│                       │    Redis     │◀───│  PostgreSQL  │                   │
│                       │   (Queue)    │    │  (Database)  │                   │
│                       └──────────────┘    └──────────────┘                   │
│                              │                   ▲                           │
│                              │                   │                           │
│                              ▼                   │                           │
│                       ┌──────────────┐           │                           │
│                       │   Celery     │───────────┘                           │
│                       │   Worker     │                                       │
│                       └──────────────┘                                       │
│                              │                                               │
│              ┌───────────────┼───────────────┐                               │
│              ▼               ▼               ▼                               │
│       ┌───────────┐   ┌───────────┐   ┌───────────┐                         │
│       │  Whisper  │   │ Pyannote  │   │  Google   │                         │
│       │ Transcibe │   │ Diarize   │   │ Contacts  │                         │
│       └───────────┘   └───────────┘   └───────────┘                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Components

### Folder Watcher
**Image:** `whisper-watcher` (~800MB)

Monitors the `Calls/` directory for new audio files and queues them for processing.

- **Poll interval:** 30 seconds (configurable)
- **Stability check:** Waits 10 seconds for file to be completely written
- **Deduplication:** Uses file hash to avoid reprocessing

### FastAPI API
**Image:** `whisper-api` (~800MB)

REST API for managing recordings and viewing results.

- **Endpoints:** Health check, recordings list, recording details, reprocess
- **Authentication:** Bearer token
- **Documentation:** Swagger UI at `/docs`

### Celery Worker
**Image:** `whisper-worker` (~2.5GB)

Performs the actual transcription and processing work.

- **Concurrency:** 1 (processes one file at a time)
- **Model:** ivrit-ai/whisper-large-v3-turbo-ct2
- **Features:** Transcription, diarization, analytics

### PostgreSQL
**Image:** `postgres:16-alpine`

Stores all recording metadata, transcripts, and enrichment data.

- **Persistence:** `C:\app\postgres-data` on Windows
- **Port:** 5432 (localhost only)

### Redis
**Image:** `redis:7-alpine`

Message broker for Celery task queue.

- **Persistence:** `C:\app\redis-data` on Windows
- **Port:** 6379 (localhost only)

## Data Flow

```
1. Audio File Arrives
   └─▶ Watcher detects new file
       └─▶ Creates recording in database (status: queued)
           └─▶ Sends task to Redis queue

2. Worker Picks Up Task
   └─▶ Updates status to "processing"
       └─▶ Step 1: Parse filename (phone, datetime)
           └─▶ Step 2: Extract audio metadata
               └─▶ Step 3: Transcribe with Whisper
                   └─▶ Step 4: Diarize speakers (optional)
                       └─▶ Step 5: Calculate analytics
                           └─▶ Step 6: Lookup caller name (optional)
                               └─▶ Updates status to "done"

3. Results Available
   └─▶ Query via API: GET /api/v1/recordings/{id}
       └─▶ JSON response with transcript, speakers, analytics
```

## Processing Pipeline Detail

| Step | Component | Input | Output |
|------|-----------|-------|--------|
| 1 | Filename Parser | `Call recording +123_240115_103045.m4a` | Phone: +123, DateTime: 2024-01-15 10:30:45 |
| 2 | Metadata Extractor | Audio file | Duration, sample rate, codec |
| 3 | Whisper | Audio file | Text transcript with timestamps |
| 4 | Pyannote | Audio file | Speaker segments (who spoke when) |
| 5 | Analytics | Transcript + Diarization | Talk time, silence, turns |
| 6 | Google Contacts | Phone number | Caller name |

## File Structure on Windows

```
C:\app\
├── docker-compose.yml          # Main compose file
├── docker-compose.override.yml # Windows-specific volumes
├── .env                        # Environment variables
├── batch-copy.ps1              # Google Drive batch script
├── processed-files.txt         # Tracking for batch processing
├── Calls\                      # Input: Audio files go here
│   └── *.m4a, *.mp3, *.wav
├── outputs\                    # Output: Transcription results
│   └── *.json
├── postgres-data\              # PostgreSQL data (persistent)
└── redis-data\                 # Redis data (persistent)
```

## Network Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     DOCKER NETWORK                          │
├────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐              │
│   │   api   │────▶│  redis  │◀────│ worker  │              │
│   │  :8000  │     │  :6379  │     │         │              │
│   └────┬────┘     └─────────┘     └────┬────┘              │
│        │                               │                    │
│        │          ┌─────────┐          │                    │
│        └─────────▶│postgres │◀─────────┘                    │
│                   │  :5432  │                               │
│                   └─────────┘                               │
│                                                             │
│   ┌─────────┐                                               │
│   │ watcher │──────(queues tasks via redis)────────────────▶│
│   │         │                                               │
│   └─────────┘                                               │
│                                                             │
└────────────────────────────────────────────────────────────┘
                          │
                          │ All ports bound to 127.0.0.1
                          │ (not accessible from network)
                          ▼
              ┌───────────────────────┐
              │   Host Machine Only   │
              │   localhost:8000      │
              │   localhost:5432      │
              │   localhost:6379      │
              └───────────────────────┘
```

## Resource Requirements

### Minimum Requirements
- **CPU:** 4 cores
- **RAM:** 8 GB
- **Storage:** 20 GB (plus audio files)

### Recommended Requirements
- **CPU:** 8+ cores
- **RAM:** 16 GB
- **Storage:** 100 GB SSD

### Processing Time Estimates (CPU)

| Audio Length | Transcription Time | Notes |
|--------------|-------------------|-------|
| 1 minute | ~30 seconds | First file slower (model loading) |
| 5 minutes | ~2-3 minutes | |
| 30 minutes | ~15-20 minutes | |
| 1 hour | ~30-40 minutes | |

*Times vary based on CPU, audio complexity, and diarization settings.*
