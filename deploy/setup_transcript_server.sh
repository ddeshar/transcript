#!/usr/bin/env bash
set -euo pipefail

# Transcript server bootstrap for Ubuntu 22.04+
# - Installs Docker & Compose
# - Creates directory structure under /srv/transcript
# - Optionally clones/pulls the repo (set REPO_URL/REPO_BRANCH)
# - Copies env and brings up docker-compose.prod.yml

if [[ $(id -u) -ne 0 ]]; then
  echo "Please run as root (sudo)" >&2
  exit 1
fi

USER_NAME=${SUDO_USER:-ubuntu}
PROJECT_ROOT=${PROJECT_ROOT:-/var/www/transcript}

REPO_URL=${REPO_URL:-}
REPO_BRANCH=${REPO_BRANCH:-main}

echo "[1/8] Updating system..."
apt-get update -y && apt-get upgrade -y

echo "[2/8] Installing dependencies..."
apt-get install -y ca-certificates curl gnupg lsb-release ufw jq git

echo "[3/8] Installing Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker && systemctl start docker
usermod -aG docker "$USER_NAME" || true

echo "[4/8] Creating directories..."
mkdir -p /var/www
mkdir -p "$PROJECT_ROOT"/{media/audio,logs,subtitles,models,deploy}
chown -R "$USER_NAME":"$USER_NAME" /var/www
chown -R "$USER_NAME":"$USER_NAME" "$PROJECT_ROOT"

echo "[5/8] Fetching project from Git (optional) ..."
if [[ -n "$REPO_URL" ]]; then
  if [[ ! -d "$PROJECT_ROOT/.git" ]]; then
    echo "Cloning $REPO_URL (branch: $REPO_BRANCH) into $PROJECT_ROOT"
    # Ensure directory exists and is owned by the target user
    mkdir -p "$PROJECT_ROOT"
    chown -R "$USER_NAME":"$USER_NAME" "$PROJECT_ROOT"
    sudo -u "$USER_NAME" git clone --branch "$REPO_BRANCH" --depth 1 "$REPO_URL" "$PROJECT_ROOT"
  else
    echo "Repo already present. Pulling latest changes on branch $REPO_BRANCH ..."
    cd "$PROJECT_ROOT"
    sudo -u "$USER_NAME" git fetch --all --prune
    sudo -u "$USER_NAME" git checkout "$REPO_BRANCH"
    sudo -u "$USER_NAME" git pull --ff-only
  fi
else
  echo "REPO_URL not set; assuming project files are already present at $PROJECT_ROOT"
fi

echo "[6/8] Configuring firewall..."
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
# Comment out these lines in production if you don’t want them exposed
# ufw allow 5432/tcp  # Postgres
# ufw allow 6379/tcp  # Redis
# ufw allow 5050/tcp  # pgAdmin
ufw --force enable

echo "[7/8] Placing deployment files..."
# Expect caller to copy project to /srv/transcript; otherwise, you can rsync/scp separately
if [[ ! -f "$PROJECT_ROOT/deploy/docker-compose.prod.yml" ]]; then
  echo "Missing $PROJECT_ROOT/deploy/docker-compose.prod.yml. Please copy project files." >&2
  exit 2
fi

if [[ ! -f "$PROJECT_ROOT/deploy/.env" && -f "$PROJECT_ROOT/deploy/.env.example" ]]; then
  cp "$PROJECT_ROOT/deploy/.env.example" "$PROJECT_ROOT/deploy/.env"
  echo "Created default .env at $PROJECT_ROOT/deploy/.env — edit credentials before starting."
fi

echo "[8/8] Starting the stack..."
cd "$PROJECT_ROOT/deploy"
docker compose -f docker-compose.prod.yml up -d --pull always

echo "✅ Deployment started. Useful commands:"
echo "- docker compose -f $PROJECT_ROOT/deploy/docker-compose.prod.yml ps"
echo "- docker compose -f $PROJECT_ROOT/deploy/docker-compose.prod.yml logs -f app"
echo "- docker compose -f $PROJECT_ROOT/deploy/docker-compose.prod.yml down"
