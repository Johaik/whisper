# Deployment Guide

This guide explains how to deploy the Whisper transcription service from a Mac to a Windows machine running Docker Desktop.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        DEPLOYMENT FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Mac (Development)              Windows (Production)          │
│   ┌─────────────────┐           ┌─────────────────┐            │
│   │  Source Code    │           │  Docker Desktop │            │
│   │  Dockerfiles    │           │                 │            │
│   │  Ansible        │           │  ┌───────────┐  │            │
│   └────────┬────────┘           │  │ Containers│  │            │
│            │                    │  └───────────┘  │            │
│            ▼                    │                 │            │
│   ┌─────────────────┐           └────────▲────────┘            │
│   │  Build Images   │                    │                     │
│   │  (linux/amd64)  │                    │                     │
│   └────────┬────────┘                    │                     │
│            │                             │                     │
│            ▼                             │                     │
│   ┌─────────────────┐                    │                     │
│   │  Push to GHCR   │────────────────────┘                     │
│   │  (ghcr.io)      │      Pull & Deploy via Ansible           │
│   └─────────────────┘                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Mac (Controller)
- Docker Desktop
- Python 3.11+
- Ansible with Windows modules:
  ```bash
  pip install ansible pywinrm
  ansible-galaxy collection install ansible.windows
  ```

### Windows (Target)
- Docker Desktop with WSL2 backend
- WinRM enabled (for Ansible)
- Network access from Mac

## Initial Setup

### 1. Configure Windows for Ansible

Run in PowerShell (Admin) on Windows:

```powershell
# Enable WinRM
Enable-PSRemoting -Force
winrm quickconfig -q

# Allow unencrypted (for local network only)
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
winrm set winrm/config/service/auth '@{Basic="true"}'

# Open firewall
New-NetFirewallRule -DisplayName "WinRM HTTP" -Direction Inbound -LocalPort 5985 -Protocol TCP -Action Allow

# For local accounts
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -Name 'LocalAccountTokenFilterPolicy' -Value 1 -Type DWord
```

### 2. Configure Ansible Inventory

Edit `ansible/inventory.ini`:

```ini
[windows]
winhost ansible_host=192.168.1.9  # Your Windows IP

[windows:vars]
ansible_user=your_username
ansible_password=your_password
ansible_connection=winrm
ansible_winrm_transport=ntlm
ansible_port=5985
ansible_winrm_server_cert_validation=ignore
```

### 3. Setup GitHub Token

```bash
# Generate token at: https://github.com/settings/tokens
# Required scopes: read:packages, write:packages

echo "ghp_your_token_here" > ansible/.ghcr_token
```

### 4. Test Connection

```bash
cd ansible
ansible windows -m win_ping
```

## Deployment Commands

### Full Deployment (First Time)

```bash
# 1. Build images for amd64 architecture
make build

# 2. Push to GitHub Container Registry
make push

# 3. Deploy to Windows
make deploy
```

### Quick Update (Code Changes)

```bash
# Rebuild and push (skips if unchanged)
make push

# Redeploy
make deploy
```

### Force Rebuild

```bash
# Force rebuild all images
make push-build

# Then deploy
make deploy
```

## What Happens During Deployment

The `make deploy` command runs `ansible/deploy.yaml` which:

1. **Creates directories** on Windows:
   - `C:\app\` - Main application directory
   - `C:\app\Calls\` - Audio files input
   - `C:\app\outputs\` - Transcription results
   - `C:\app\postgres-data\` - Database persistence
   - `C:\app\redis-data\` - Redis persistence

2. **Configures Docker credentials** for GHCR access

3. **Copies configuration files**:
   - `docker-compose.yml`
   - `docker-compose.override.yml` (Windows-specific paths)
   - `batch-copy.ps1` (for Google Drive integration)
   - `.env` file

4. **Secures ports** by binding to localhost only

5. **Pulls and starts containers**:
   - PostgreSQL (database)
   - Redis (task queue)
   - API (FastAPI server)
   - Worker (Celery transcription worker)
   - Watcher (file monitor)

## Verifying Deployment

```bash
# Check container status
make status

# View logs (on Windows)
docker logs -f whisper-worker
```

## Security

All Docker ports are bound to `127.0.0.1` (localhost only):
- Port 5432 (PostgreSQL) - Not accessible from network
- Port 6379 (Redis) - Not accessible from network
- Port 8000 (API) - Not accessible from network

Only WinRM (5985) remains accessible for Ansible management.

To access the API on Windows, use:
```
http://localhost:8000/api/v1/health
```

## Troubleshooting

### WinRM Connection Failed

```bash
# Test from Mac
curl http://192.168.1.9:5985

# If timeout, check Windows firewall
```

### Docker Images Not Found

```bash
# Login to GHCR first
make login

# Then push
make push
```

### Port Already in Use

```bash
# On Windows, stop all containers and wait
docker compose down
# Wait 30 seconds for TIME_WAIT to clear
docker compose up -d
```

### Permission Denied

Ensure the Windows user has Docker Desktop access (member of `docker-users` group).
