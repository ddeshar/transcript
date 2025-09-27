#!/usr/bin/env bash
# One-shot installer for Transcript app from a public GitHub repo
# Deploys to /var/www/transcript instead of /srv/transcript
# Usage (run as root):
#   sudo REPO_SLUG="ddeshar/transcript" BRANCH="main" bash deploy/install_public_github_varwww.sh
#
# Optional envs:
#   PROJECT_ROOT (/var/www/transcript)

set -euo pipefail

if [[ $(id -u) -ne 0 ]]; then
  echo "Please run as root (sudo)" >&2
  exit 1
fi

REPO_SLUG=${REPO_SLUG:-ddeshar/transcript}
BRANCH=${BRANCH:-main}
PROJECT_ROOT=${PROJECT_ROOT:-/var/www/transcript}
USER_NAME=${SUDO_USER:-ubuntu}

# If the specified USER_NAME doesn't exist (e.g., script run directly as root), fall back to root
if ! id -u "$USER_NAME" >/dev/null 2>&1; then
  USER_NAME=root
fi

# Helper for running commands as the target user (no-op if root)
if [[ "$USER_NAME" == "root" ]]; then
  RUN_AS=""
else
  RUN_AS="sudo -u $USER_NAME"
fi

echo "[1/6] Installing base dependencies (git, curl, gnupg)..."
apt-get update -y && apt-get install -y ca-certificates curl gnupg lsb-release git

echo "[2/6] Installing Docker Engine + Compose..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list >/dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker && systemctl start docker
if [[ "$USER_NAME" != "root" ]]; then
  usermod -aG docker "$USER_NAME" || true
fi

echo "[3/6] Creating /var/www directory structure..."
mkdir -p /var/www
chown -R "$USER_NAME":"$USER_NAME" /var/www

echo "[4/6] Cloning or updating public repository..."
# Determine expected remote URL
EXPECTED_REMOTE="https://github.com/${REPO_SLUG}.git"

# If target exists
if [[ -d "$PROJECT_ROOT" ]]; then
  if [[ -d "$PROJECT_ROOT/.git" ]]; then
    # It's a git repo; verify remote
    EXISTING_REMOTE=$($RUN_AS git -C "$PROJECT_ROOT" remote get-url origin 2>/dev/null || echo "")
    if [[ "$EXISTING_REMOTE" != "$EXPECTED_REMOTE" || -z "$EXISTING_REMOTE" ]]; then
      echo "Existing repo remote ('$EXISTING_REMOTE') doesn't match expected ('$EXPECTED_REMOTE'). Replacing..."
      rm -rf "$PROJECT_ROOT"
      echo "Cloning $EXPECTED_REMOTE (branch: $BRANCH)"
      $RUN_AS git clone --branch "$BRANCH" --depth 1 "$EXPECTED_REMOTE" "$PROJECT_ROOT"
    else
      echo "Repo exists with expected remote, updating..."
      $RUN_AS git -C "$PROJECT_ROOT" fetch --all --prune
      $RUN_AS git -C "$PROJECT_ROOT" checkout "$BRANCH"
      $RUN_AS git -C "$PROJECT_ROOT" pull --ff-only
    fi
  else
    # Directory exists but isn't a git repo; remove and clone afresh
    echo "Removing existing non-git directory at $PROJECT_ROOT"
    rm -rf "$PROJECT_ROOT"
    echo "Cloning $EXPECTED_REMOTE (branch: $BRANCH)"
    $RUN_AS git clone --branch "$BRANCH" --depth 1 "$EXPECTED_REMOTE" "$PROJECT_ROOT"
  fi
else
  # Target doesn't exist; clone fresh
  echo "Cloning $EXPECTED_REMOTE (branch: $BRANCH)"
  $RUN_AS git clone --branch "$BRANCH" --depth 1 "$EXPECTED_REMOTE" "$PROJECT_ROOT"
fi

# Ensure required directories exist after clone
mkdir -p "$PROJECT_ROOT"/{media/audio,logs,subtitles,models}
chown -R "$USER_NAME":"$USER_NAME" "$PROJECT_ROOT"

echo "[5/6] Skipping firewall configuration (per request)."

echo "[6/6] Ensuring env file..."
if [[ ! -f "$PROJECT_ROOT/deploy/.env" && -f "$PROJECT_ROOT/deploy/.env.example" ]]; then
  cp "$PROJECT_ROOT/deploy/.env.example" "$PROJECT_ROOT/deploy/.env"
  echo "Created default .env at $PROJECT_ROOT/deploy/.env — edit credentials as needed."
fi

echo "Building and starting the stack..."
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