# 📞 Whisper Call Transcription Pipeline

A production-ready call recording transcription system that automatically processes audio files, transcribes Hebrew speech, identifies speakers, and provides rich analytics—all accessible via a REST API.

<p align="center">
  <img src="https://img.shields.io/badge/Hebrew-Optimized-blue?style=flat-square" alt="Hebrew Optimized"/>
  <img src="https://img.shields.io/badge/Powered%20by-ivrit--ai-orange?style=flat-square" alt="Powered by ivrit-ai"/>
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Celery-37814A?style=flat-square&logo=celery&logoColor=white" alt="Celery"/>
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"/>
</p>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎙️ **Hebrew Transcription** | Uses [ivrit-ai](https://huggingface.co/ivrit-ai) models fine-tuned on 295+ hours of Hebrew speech |
| 👥 **Speaker Diarization** | Identifies who spoke when using [pyannote.audio](https://github.com/pyannote/pyannote-audio) |
| 📊 **Call Analytics** | Computes talk time, silence ratio, speaker turns, and more |
| 📁 **Auto-Discovery** | Watches a folder and automatically processes new recordings |
| 📇 **Caller ID** | Looks up caller names from Google Contacts via phone number |
| 🔄 **Async Processing** | Background workers handle transcription without blocking |
| 🌐 **REST API** | Full-featured API for ingestion, querying, and reprocessing |

---

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Folder        │     │   FastAPI       │     │   PostgreSQL    │
│   Watcher       │────▶│   API           │────▶│   Database      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   Redis         │◀────│   Celery        │
│   Queue         │     │   Worker        │
└─────────────────┘     └─────────────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │ Whisper   │  │ Pyannote  │  │ Google    │
        │ Transcibe │  │ Diarize   │  │ Contacts  │
        └───────────┘  └───────────┘  └───────────┘
```

### Components

- **Folder Watcher** — Polls a directory for new audio files, queues them for processing
- **FastAPI API** — REST endpoints for ingestion, recording list, details, and health checks
- **Celery Worker** — Processes recordings asynchronously (transcription, diarization, analytics)
- **PostgreSQL** — Stores recordings, transcripts, and enrichment data
- **Redis** — Message broker for Celery task queue

---

## 📋 Processing Pipeline

When a new recording is detected, it goes through these steps:

```
1. 📂 DISCOVERED    → File found in watch folder
2. 📝 PARSE         → Extract phone number & timestamp from filename
3. 🔍 METADATA      → Extract audio properties (duration, codec, sample rate)
4. 🎤 TRANSCRIBE    → Convert speech to text using Whisper
5. 👥 DIARIZE       → Identify different speakers (optional)
6. 📊 ANALYTICS     → Compute talk time, silence, speaker turns
7. 📇 CONTACTS      → Look up caller name from Google Contacts (optional)
8. ✅ DONE          → Store results in database
```

### Filename Parsing

The system automatically parses call recording filenames to extract metadata:

```
Call recording +15551234567_200605_114902.m4a
              └─────┬─────┘└──┬──┘└──┬───┘
                Phone     Date    Time
              Number    YYMMDD  HHMMSS
```

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- HuggingFace token (for speaker diarization)
- Google API credentials (optional, for caller name lookup)

### 1. Clone and Configure

```bash
# Clone the repository
git clone <your-repo-url>
cd whisper

# Create environment file
cat > .env << EOF
API_TOKEN=your-secure-api-token
HUGGINGFACE_TOKEN=hf_your_huggingface_token
DIARIZATION_ENABLED=true
EOF
```

### 2. Start the Services

```bash
# Start all services
docker-compose up -d

# Run database migrations
docker-compose run --rm migrate

# Check service health
curl http://localhost:8000/api/v1/health
```

### 3. Add Recordings

Place your call recordings in the `Calls/` folder. The watcher will automatically detect and process them.

```bash
# Or trigger manual ingestion via API
curl -X POST "http://localhost:8000/api/v1/ingest" \
  -H "Authorization: Bearer your-secure-api-token" \
  -H "Content-Type: application/json"
```

---

## 🔌 API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Service health check |
| `POST` | `/api/v1/ingest` | Scan folder and queue recordings |
| `GET` | `/api/v1/recordings` | List all recordings (paginated) |
| `GET` | `/api/v1/recordings/{id}` | Get recording details with transcript |
| `POST` | `/api/v1/recordings/{id}/reprocess` | Requeue a recording for processing |

### Authentication

All endpoints (except `/health`) require a Bearer token:

```bash
curl -H "Authorization: Bearer your-api-token" http://localhost:8000/api/v1/recordings
```

### Example: Get Recording Details

```bash
curl -H "Authorization: Bearer your-api-token" \
  "http://localhost:8000/api/v1/recordings/550e8400-e29b-41d4-a716-446655440000"
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "file_name": "Call recording +972521234567_230115_103045.m4a",
  "status": "done",
  "duration_sec": 185.5,
  "phone_number": "+972521234567",
  "caller_name": "John Doe",
  "call_datetime": "2023-01-15T10:30:45",
  "transcript": {
    "text": "שלום, מה שלומך? בסדר גמור, תודה...",
    "language": "he",
    "language_probability": 0.98,
    "segments": [
      {"start": 0.0, "end": 2.5, "text": "שלום, מה שלומך?", "speaker": "SPEAKER_00"},
      {"start": 2.8, "end": 5.1, "text": "בסדר גמור, תודה", "speaker": "SPEAKER_01"}
    ]
  },
  "enrichment": {
    "speaker_count": 2,
    "total_speech_time": 165.2,
    "total_silence_time": 20.3,
    "talk_time_ratio": 0.89,
    "speaker_turns": 24
  }
}
```

### Interactive API Docs

Visit **http://localhost:8000/docs** for Swagger UI documentation.

---

## ⚙️ Configuration

Configure via environment variables or `.env` file:

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `API_TOKEN` | `dev-token-change-me` | API authentication token |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `CALLS_DIR` | `/data/calls` | Directory to watch for recordings |

### Transcription Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_NAME` | `ivrit-ai/whisper-large-v3-turbo-ct2` | Whisper model to use |
| `DEVICE` | `cpu` | Device (`cpu` or `cuda`) |
| `COMPUTE_TYPE` | `int8` | Precision (`int8`, `float16`, `float32`) |
| `BEAM_SIZE` | `5` | Beam search size (higher = more accurate) |
| `VAD_FILTER` | `true` | Voice Activity Detection filtering |

### Diarization Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DIARIZATION_ENABLED` | `true` | Enable speaker diarization |
| `HUGGINGFACE_TOKEN` | — | Required for pyannote.audio models |

### Google Contacts (Optional)

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 client secret |
| `GOOGLE_REFRESH_TOKEN` | OAuth 2.0 refresh token |

### Watcher Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `WATCHER_POLL_INTERVAL` | `30` | Seconds between folder scans |
| `WATCHER_STABLE_SECONDS` | `10` | File must be stable for this long before processing |

---

## 🧪 Development

### Local Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start infrastructure
docker-compose up -d postgres redis

# Run migrations
alembic upgrade head

# Start API server
uvicorn app.main:app --reload

# Start worker (in another terminal)
celery -A app.worker.celery_app worker --loglevel=info

# Start watcher (in another terminal)
python -m app.watcher.folder_watcher
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test categories
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only
```

### Project Structure

```
whisper/
├── app/
│   ├── api/                 # FastAPI routes and schemas
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── db/                  # Database models and sessions
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/      # Alembic migrations
│   ├── processors/          # Audio processing modules
│   │   ├── transcribe.py    # Whisper transcription
│   │   ├── diarize.py       # Speaker diarization
│   │   ├── analytics.py     # Call analytics
│   │   ├── metadata.py      # Audio metadata extraction
│   │   └── filename_parser.py
│   ├── services/            # External integrations
│   │   └── google_contacts.py
│   ├── watcher/             # Folder monitoring
│   │   └── folder_watcher.py
│   ├── worker/              # Celery tasks
│   │   ├── celery_app.py
│   │   └── tasks.py
│   ├── auth.py
│   ├── config.py
│   └── main.py
├── tests/                   # Test suite
├── Calls/                   # Default recordings folder
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 🔧 Standalone Transcription

For quick one-off transcription without the full pipeline:

```bash
# Activate the virtual environment
source venv/bin/activate

# Using ivrit-ai model (recommended for Hebrew)
python transcribe_hebrew.py audio.mp3 --ivrit

# With timestamps
python transcribe_hebrew.py audio.mp3 --ivrit --timestamps

# Save to file
python transcribe_hebrew.py audio.mp3 --ivrit --output result.txt

# Higher accuracy (slower)
python transcribe_hebrew.py audio.mp3 --ivrit --beam-size 10
```

---

## 📊 Model Comparison

### Hebrew-Optimized Models (Recommended)

| Model | Speed | Accuracy | Notes |
|-------|-------|----------|-------|
| `ivrit-ai/whisper-large-v3-turbo-ct2` | ⚡ Fast | ★★★★★ | Default, fine-tuned on 295+ hrs Hebrew |
| `ivrit-ai/whisper-large-v3-ct2` | 🐢 Slow | ★★★★★ | Maximum accuracy |

### Standard Whisper Models

| Model | VRAM | Speed | Hebrew Accuracy |
|-------|------|-------|-----------------|
| `tiny` | ~1GB | ⚡⚡⚡ | ★☆☆☆☆ |
| `base` | ~1GB | ⚡⚡⚡ | ★★☆☆☆ |
| `small` | ~2GB | ⚡⚡ | ★★★☆☆ |
| `medium` | ~5GB | ⚡ | ★★★★☆ |
| `large-v3` | ~10GB | 🐢 | ★★★★☆ |

---

## 🙏 Credits

- [OpenAI Whisper](https://github.com/openai/whisper) — Base speech recognition
- [ivrit.ai](https://huggingface.co/ivrit-ai) — Hebrew fine-tuned models
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — CTranslate2 inference
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) — Speaker diarization

---

---

## 📚 Documentation

Detailed documentation is available in the [`docs/`](docs/) folder:

| Document | Description |
|----------|-------------|
| [Deployment Guide](docs/deployment.md) | Deploy from Mac to Windows |
| [Makefile Reference](docs/makefile.md) | All available make commands |
| [Architecture](docs/architecture.md) | System components and data flow |
| [Configuration](docs/configuration.md) | Environment variables reference |
| [Security](docs/security.md) | Security considerations |
| [Google Drive Integration](docs/google-drive.md) | Process files from Google Drive |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
