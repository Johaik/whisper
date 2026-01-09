# Makefile Reference

The Makefile provides convenient shortcuts for common operations. Run `make` or `make help` to see all available commands.

## Command Overview

```
Whisper Service Management
==========================

Local Development (Mac):
  make dev        - Start local development environment
  make stop       - Stop local development environment
  make logs       - View local container logs

Build & Push:
  make login      - Login to GitHub Container Registry
  make build      - Build amd64 images locally
  make push       - Push images (build only if not exists)
  make push-build - Force rebuild and push all images

Remote Deployment (Windows):
  make deploy     - Deploy to Windows (pull + run)
  make status     - Check Windows container status

Utilities:
  make clean      - Remove local containers and images
```

## Detailed Command Reference

### Local Development

#### `make dev`

Starts the local development environment using Docker Compose with the override file for local builds.

```bash
# What it does:
docker compose up -d
```

**Services started:**
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`
- API on `localhost:8000`
- Worker (Celery)
- Watcher (folder monitor)

#### `make stop`

Stops the local development environment.

```bash
# What it does:
docker compose down
```

#### `make logs`

Shows container logs in follow mode.

```bash
# What it does:
docker compose logs --tail=100 -f
```

**Tip:** Press `Ctrl+C` to exit.

---

### Build & Push

#### `make login`

Authenticates with GitHub Container Registry using the token stored in `ansible/.ghcr_token`.

```bash
# Prerequisite:
echo "your_github_token" > ansible/.ghcr_token

# What it does:
cat ansible/.ghcr_token | docker login ghcr.io -u username --password-stdin
```

**Required token scopes:**
- `read:packages`
- `write:packages`

#### `make build`

Builds Docker images for `linux/amd64` architecture (required for Windows deployment).

```bash
# What it does:
docker buildx build --platform linux/amd64 -t ghcr.io/user/whisper-api:latest ...
docker buildx build --platform linux/amd64 -t ghcr.io/user/whisper-worker:latest ...
docker buildx build --platform linux/amd64 -t ghcr.io/user/whisper-watcher:latest ...
```

**Images built:**
| Image | Size | Description |
|-------|------|-------------|
| `whisper-api` | ~800MB | FastAPI server (no ML deps) |
| `whisper-worker` | ~2.5GB | Celery worker with Whisper |
| `whisper-watcher` | ~800MB | Folder watcher (no ML deps) |

#### `make push`

Pushes images to GitHub Container Registry. Only builds if images don't exist locally.

```bash
# Behavior:
# 1. Check if image exists locally
# 2. If exists → push directly (fast)
# 3. If not → build then push
```

**Use case:** Quick push after `make build`.

#### `make push-build`

Forces a full rebuild and push of all images, regardless of whether they exist locally.

```bash
# What it does:
docker buildx build --platform linux/amd64 ... --push
```

**Use case:** After code changes when you want fresh images.

---

### Remote Deployment

#### `make deploy`

Deploys the application to the Windows machine defined in `ansible/inventory.ini`.

```bash
# What it does:
ansible-playbook ansible/deploy.yaml
```

**Steps performed:**
1. Creates directories on Windows
2. Configures Docker registry credentials
3. Copies docker-compose files
4. Secures ports (binds to localhost)
5. Pulls latest images from GHCR
6. Starts all containers
7. Shows deployment status

#### `make status`

Checks the status of containers running on Windows.

```bash
# What it does:
ansible windows -m win_powershell -a 'docker ps'
```

**Example output:**
```
NAMES              STATUS          PORTS
whisper-api        Up 5 minutes    127.0.0.1:8000->8000/tcp
whisper-worker     Up 5 minutes
whisper-watcher    Up 5 minutes
whisper-postgres   Up 5 minutes    127.0.0.1:5432->5432/tcp
whisper-redis      Up 5 minutes    127.0.0.1:6379->6379/tcp
```

---

### Utilities

#### `make clean`

Removes local containers and images.

```bash
# What it does:
docker compose down --remove-orphans
docker rmi whisper-api:local whisper-worker:local whisper-watcher:local
```

---

## Environment Variables

The Makefile uses these environment variables (set automatically for macOS compatibility):

| Variable | Value | Purpose |
|----------|-------|---------|
| `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` | `YES` | Fixes Ansible multiprocessing on macOS |

## Token File

The GitHub token is stored in `ansible/.ghcr_token` (git-ignored):

```bash
# Create token file
echo "ghp_xxxxxxxxxxxx" > ansible/.ghcr_token

# File is checked before push/deploy commands
# Commands will fail with helpful message if token is missing
```

## Workflow Examples

### Daily Development

```bash
# Morning: Start dev environment
make dev

# Work on code...

# View logs when needed
make logs

# Evening: Stop
make stop
```

### Deploying Changes

```bash
# After code changes
make push        # Build if needed, push to GHCR
make deploy      # Deploy to Windows
make status      # Verify deployment
```

### Fresh Deployment

```bash
# Complete rebuild
make clean       # Remove old local images
make build       # Build fresh images
make push        # Push to GHCR
make deploy      # Deploy to Windows
```

### Troubleshooting

```bash
# Check Windows status
make status

# Force rebuild everything
make push-build
make deploy
```
