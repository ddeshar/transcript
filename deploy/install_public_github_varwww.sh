#!/usr/bin/env bash
# One-shot installer for Transcript app from a public GitHub repo
# Deploys to /var/www/transcript instead of /srv/transcript
# Usage (run as root):
#   sudo REPO_SLUG="ddeshar/transcript" BRANCH="main" bash deploy/install_public_github_varwww.sh
#
# Optional envs:
#   PROJECT_ROOT (/var/www/transcript), OPEN_PORTAINER (0/1), OPEN_PGADMIN (0/1)

set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "Please run as root (sudo)" >&2
  exit 1
fi

REPO_SLUG=${REPO_SLUG:-ddeshar/transcript}
BRANCH=${BRANCH:-main}
PROJECT_ROOT=${PROJECT_ROOT:-/var/www/transcript}
USER_NAME=${SUDO_USER:-ubuntu}

# Optional ports for tooling
OPEN_PORTAINER=${OPEN_PORTAINER:-1}
OPEN_PGADMIN=${OPEN_PGADMIN:-0}

echo "[1/7] Installing base dependencies (git, ufw, jq)..."
apt-get update -y && apt-get install -y ca-certificates curl gnupg lsb-release git ufw jq

echo "[2/7] Installing Docker Engine + Compose..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list >/dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker && systemctl start docker
usermod -aG docker "$USER_NAME" || true

echo "[3/7] Creating /var/www directory structure..."
mkdir -p /var/www
chown -R "$USER_NAME":"$USER_NAME" /var/www

echo "[4/7] Cloning public repository..."
if [[ ! -d "$PROJECT_ROOT/.git" ]]; then
  echo "Cloning https://github.com/${REPO_SLUG}.git (branch: $BRANCH)"
  # Remove any existing non-git directory at the target location
  if [[ -d "$PROJECT_ROOT" && ! -d "$PROJECT_ROOT/.git" ]]; then
    echo "Removing existing non-git directory at $PROJECT_ROOT"
    rm -rf "$PROJECT_ROOT"
  fi
  sudo -u "$USER_NAME" git clone --branch "$BRANCH" --depth 1 \
    "https://github.com/${REPO_SLUG}.git" "$PROJECT_ROOT"
else
  echo "Repo exists, pulling latest..."
  pushd "$PROJECT_ROOT" >/dev/null
  sudo -u "$USER_NAME" git fetch --all --prune
  sudo -u "$USER_NAME" git checkout "$BRANCH"
  sudo -u "$USER_NAME" git pull --ff-only
  popd >/dev/null
fi

# Ensure required directories exist after clone
mkdir -p "$PROJECT_ROOT"/{media/audio,logs,subtitles,models}
chown -R "$USER_NAME":"$USER_NAME" "$PROJECT_ROOT"

echo "[5/7] Firewall rules (UFW)..."
ufw allow OpenSSH
ufw allow 80/tcp     # App HTTP (standard port, no :8000 needed)
if [[ "$OPEN_PORTAINER" == "1" ]]; then
  ufw allow 9000/tcp # Portainer HTTP (optional)
  # ufw allow 9443/tcp # Portainer HTTPS (prefer if you configure certs)
fi
if [[ "$OPEN_PGADMIN" == "1" ]]; then
  ufw allow 5050/tcp # pgAdmin (optional)
fi
ufw --force enable

echo "[6/7] Ensuring env file..."
if [[ ! -f "$PROJECT_ROOT/deploy/.env" && -f "$PROJECT_ROOT/deploy/.env.example" ]]; then
  cp "$PROJECT_ROOT/deploy/.env.example" "$PROJECT_ROOT/deploy/.env"
  echo "Created default .env at $PROJECT_ROOT/deploy/.env — edit credentials as needed."
fi

echo "[7/7] Building and starting the stack..."
pushd "$PROJECT_ROOT/deploy" >/dev/null
docker compose -f docker-compose.prod.yml up -d --build
popd >/dev/null

echo "✅ Done. Visit the app at http://YOUR_SERVER_IP (port 80). For logs:"
echo "   docker compose -f $PROJECT_ROOT/deploy/docker-compose.prod.yml logs -f app"
echo ""
echo "Useful commands:"
echo "   cd $PROJECT_ROOT/deploy"
echo "   docker compose -f docker-compose.prod.yml ps"
echo "   docker compose -f docker-compose.prod.yml logs -f app"
echo "   docker compose -f docker-compose.prod.yml down"