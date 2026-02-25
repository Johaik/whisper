# Whisper Transcription Service - Makefile
# ==========================================

.PHONY: help dev stop build push push-build deploy logs status clean login monitor tunnel venv ensure-venv test test-unit test-integration

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

# Ansible Venv (for reliable networking on Mac)
ANSIBLE_VENV := ansible_venv
ANSIBLE_PLAYBOOK := $(ANSIBLE_VENV)/bin/ansible-playbook

# Token file path
TOKEN_FILE := ansible/.ghcr_token

# Default target
help:
	@echo "Whisper Service Management"
	@echo "=========================="
	@echo ""
	@echo "Local Development (Mac):"
	@echo "  make dev      - Start local development environment"
	@echo "  make stop     - Stop local development environment"
	@echo "  make logs     - View local container logs"
	@echo ""
	@echo "Venv (local Python):"
	@echo "  make venv     - Create .venv and install requirements"
	@echo "  make test     - Run pytest (uses .venv if present)"
	@echo "  make test-unit - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo ""
	@echo "Build & Push:"
	@echo "  make login      - Login to GitHub Container Registry"
	@echo "  make build      - Build amd64 images locally"
	@echo "  make push       - Push images (build only if not exists)"
	@echo "  make push-build - Force rebuild and push all images"
	@echo ""
	@echo "Remote Deployment (Windows):"
	@echo "  make deploy   - Deploy to Windows (pull + run)"
	@echo "  make status   - Check Windows container status"
	@echo ""
	@echo "Monitoring (Mac):"
	@echo "  make tunnel   - Start SSH tunnel to Windows"
	@echo "  make monitor  - Start Prometheus + Grafana stack"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean    - Remove local containers and images"
	@echo ""
	@echo "Setup:"
	@echo "  1. Get GitHub token: https://github.com/settings/tokens"
	@echo "  2. Add token to: $(TOKEN_FILE)"
	@echo "  3. Run: make login"

# ==========================================
# Local Development
# ==========================================

dev:
	@echo "Starting local development environment..."
	cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook local.yaml --tags dev

stop:
	@echo "Stopping local development environment..."
	cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook local.yaml --tags stop

logs:
	@echo "Showing local container logs..."
	docker compose logs --tail=100 -f

# ==========================================
# Build & Push
# ==========================================

login:
	@echo "Logging in to GitHub Container Registry..."
	@if [ ! -f "$(TOKEN_FILE)" ] || [ "$$(cat $(TOKEN_FILE) | tr -d '[:space:]')" = "YOUR_GITHUB_TOKEN_HERE" ]; then \
		echo "Error: Please add your GitHub token to $(TOKEN_FILE)"; \
		echo "Generate a token at: https://github.com/settings/tokens"; \
		echo "Required scopes: read:packages, write:packages"; \
		exit 1; \
	fi
	@cat $(TOKEN_FILE) | tr -d '[:space:]' | docker login ghcr.io -u johaik --password-stdin

build:
	@echo "Building amd64 images locally..."
	cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook local.yaml --tags build

push:
	@if [ ! -f "$(TOKEN_FILE)" ] || [ "$$(cat $(TOKEN_FILE) | tr -d '[:space:]')" = "YOUR_GITHUB_TOKEN_HERE" ]; then \
		echo "Error: Please add your GitHub token to $(TOKEN_FILE)"; \
		exit 1; \
	fi
	@echo "Pushing images to ghcr.io (building only if needed)..."
	cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook local.yaml --tags push

push-build:
	@if [ ! -f "$(TOKEN_FILE)" ] || [ "$$(cat $(TOKEN_FILE) | tr -d '[:space:]')" = "YOUR_GITHUB_TOKEN_HERE" ]; then \
		echo "Error: Please add your GitHub token to $(TOKEN_FILE)"; \
		exit 1; \
	fi
	@echo "Force rebuilding and pushing all images to ghcr.io..."
	cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook local.yaml --tags push-build

# ==========================================
# Remote Deployment
# ==========================================

deploy:
	@if [ ! -f "$(TOKEN_FILE)" ] || [ "$$(cat $(TOKEN_FILE) | tr -d '[:space:]')" = "YOUR_GITHUB_TOKEN_HERE" ]; then \
		echo "Error: Please add your GitHub token to $(TOKEN_FILE)"; \
		exit 1; \
	fi
	@echo "Deploying to Windows..."
	cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ../$(ANSIBLE_PLAYBOOK) deploy.yaml

status:
	@echo "Checking Windows deployment status..."
	@cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ../$(ANSIBLE_PLAYBOOK) status.yaml

# ==========================================
# Monitoring
# ==========================================

tunnel:
	@echo "Starting SSH tunnel to Windows..."
	@echo "This will forward monitoring ports from Windows to localhost"
	@echo ""
	@cd monitoring && ./tunnel.sh johaik@192.168.1.9

monitor:
	@echo "Starting monitoring stack (Prometheus + Grafana)..."
	@cd monitoring && docker compose up -d
	@echo ""
	@echo "Monitoring started:"
	@echo "  Grafana:    http://localhost:3000 (admin/admin)"
	@echo "  Prometheus: http://localhost:9090"
	@echo "  Flower:     http://localhost:5555 (via tunnel)"
	@echo ""
	@echo "Note: Make sure the tunnel is running (make tunnel)"

monitor-stop:
	@echo "Stopping monitoring stack..."
	@cd monitoring && docker compose down

# ==========================================
# Venv and tests (use existing .venv if present)
# ==========================================

venv:
	@echo "Creating virtual environment at $(VENV)..."
	python3 -m venv $(VENV)
	@echo "Installing requirements..."
	$(PIP) install -q -r requirements.txt
	@echo "Done. Activate with: source $(VENV)/bin/activate"

# Use existing .venv; create only if missing
ensure-venv:
	@test -d $(VENV) || $(MAKE) venv

test: ensure-venv
	$(PYTEST) -v

test-unit: ensure-venv
	$(PYTEST) tests/unit/ -v

test-integration: ensure-venv
	$(PYTEST) tests/integration/ -v

# ==========================================
# Utilities
# ==========================================

clean:
	@echo "Stopping and removing local containers..."
	docker compose down --remove-orphans
	@echo "Removing local images..."
	docker rmi -f whisper-api:local whisper-worker:local whisper-watcher:local 2>/dev/null || true
	@echo "Clean complete"
