# Whisper Transcription Service - Makefile
# ==========================================

.PHONY: help dev stop build push push-build deploy logs status clean login

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
	cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook deploy.yaml

status:
	@echo "Checking Windows deployment status..."
	@cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook status.yaml

# ==========================================
# Utilities
# ==========================================

clean:
	@echo "Stopping and removing local containers..."
	docker compose down --remove-orphans
	@echo "Removing local images..."
	docker rmi -f whisper-api:local whisper-worker:local whisper-watcher:local 2>/dev/null || true
	@echo "Clean complete"
