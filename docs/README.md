# Whisper Documentation

Complete documentation for the Whisper Call Transcription Pipeline.

## Table of Contents

| Document | Description |
|----------|-------------|
| [Deployment Guide](deployment.md) | How to deploy to Windows from Mac |
| [Makefile Reference](makefile.md) | All available make commands |
| [Architecture](architecture.md) | System architecture and components |
| [Configuration](configuration.md) | Environment variables and settings |
| [Security](security.md) | Security considerations and setup |
| [Google Drive Integration](google-drive.md) | Processing files from Google Drive |

## Quick Links

- **Local Development**: `make dev`
- **Deploy to Windows**: `make deploy`
- **Check Status**: `make status`
- **View Logs**: `make logs`

## Getting Started

1. **Setup GitHub Token** (one-time):
   ```bash
   # Get token from: https://github.com/settings/tokens
   # Required scopes: read:packages, write:packages
   echo "YOUR_TOKEN" > ansible/.ghcr_token
   ```

2. **Local Development**:
   ```bash
   make dev      # Start all services locally
   make logs     # View logs
   make stop     # Stop services
   ```

3. **Deploy to Windows**:
   ```bash
   make build    # Build Docker images
   make push     # Push to GitHub Container Registry
   make deploy   # Deploy to Windows machine
   ```

## Project Structure

```
whisper/
├── ansible/              # Ansible playbooks for deployment
│   ├── deploy.yaml       # Windows deployment playbook
│   ├── local.yaml        # Local development playbook
│   ├── inventory.ini     # Windows host configuration
│   └── group_vars/       # Shared variables
├── app/                  # Python application code
├── docs/                 # Documentation (you are here)
├── Dockerfile.*          # Docker build files
├── docker-compose.yml    # Container orchestration
├── Makefile              # Command shortcuts
└── requirements*.txt     # Python dependencies
```
