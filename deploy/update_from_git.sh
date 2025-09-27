#!/usr/bin/env bash
set -euo pipefail

# Usage: sudo bash deploy/update_from_git.sh [branch]
# Default branch is 'main'. Pulls latest, rebuilds, and restarts the stack.

BRANCH=${1:-main}
PROJECT_ROOT=${PROJECT_ROOT:-/var/www/transcript}
COMPOSE_FILE=${COMPOSE_FILE:-$PROJECT_ROOT/deploy/docker-compose.prod.yml}

echo "[1/3] Pulling latest from Git ($BRANCH) ..."
cd "$PROJECT_ROOT"
sudo -u "${SUDO_USER:-$USER}" git fetch --all --prune
sudo -u "${SUDO_USER:-$USER}" git checkout "$BRANCH"
sudo -u "${SUDO_USER:-$USER}" git pull --ff-only

echo "[2/3] Rebuilding and restarting stack ..."
cd "$PROJECT_ROOT/deploy"
docker compose -f "$COMPOSE_FILE" up -d --build

echo "[3/3] Pruning old images (optional) ..."
docker image prune -f || true

echo "✅ Update complete. View logs with: docker compose -f $COMPOSE_FILE logs -f app"
