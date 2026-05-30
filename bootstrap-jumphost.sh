#!/usr/bin/env bash
set -euo pipefail

# bootstrap-jumphost.sh
# Idempotent bootstrap for the autoprovision jump host.
# - Installs system dependencies (git, Python, Ansible, talosctl)
# - Creates Python virtualenv
# - Installs Python dependencies for the web UI
# - Prepares data directories
# - Initializes SQLite state DB (if app provides a command)
# - Starts the Python web UI service on port 3000

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
DATA_DIR="$REPO_ROOT/data"
LOG_DIR="$DATA_DIR/logs"
INV_DIR="$DATA_DIR/inventory"
GEN_ENV_DIR="$DATA_DIR/generated-env"
STATE_DB="$DATA_DIR/state.db"

info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Required command '$1' not found. Install it and retry."
  fi
}

install_packages() {
  info "Installing system packages (git, Python, Ansible, talosctl prerequisites)..."

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y \
      git curl ca-certificates \
      python3 python3-venv python3-pip \
      sshpass \
      jq \
      software-properties-common

    # Ansible on Ubuntu/Debian
    if ! command -v ansible >/dev/null 2>&1; then
      sudo apt-get install -y ansible
    fi
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y \
      git curl ca-certificates \
      python3 python3-venv python3-pip \
      sshpass jq ansible
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y \
      git curl ca-certificates \
      python3 python3-venv python3-pip \
      sshpass jq ansible
  else
    warn "Unknown package manager. Please ensure git, Python 3, pip, ansible, curl, jq, sshpass are installed manually."
  fi
}

install_talosctl() {
  if command -v talosctl >/dev/null 2>&1; then
    info "talosctl already installed. Skipping."
    return
  fi

  info "Installing talosctl..."
  # Install latest talosctl (Linux amd64) into /usr/local/bin
  TMP_BIN="/tmp/talosctl"
  curl -fsSL https://github.com/siderolabs/talos/releases/latest/download/talosctl-linux-amd64 -o "$TMP_BIN"
  chmod +x "$TMP_BIN"
  sudo mv "$TMP_BIN" /usr/local/bin/talosctl
}

create_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
  else
    info "Virtualenv already exists at $VENV_DIR."
  fi
}

install_python_deps() {
  info "Installing Python dependencies inside virtualenv..."
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"

  # Prefer requirements.txt if present
  if [ -f "$REPO_ROOT/requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r "$REPO_ROOT/requirements.txt"
  else
    # Minimal baseline: FastAPI, Uvicorn, ansible-runner, sqlite helpers
    pip install --upgrade pip
    pip install fastapi uvicorn[standard] ansible-runner
  fi
}

prepare_data_dirs() {
  info "Preparing data directories..."
  mkdir -p "$DATA_DIR" "$LOG_DIR" "$INV_DIR" "$GEN_ENV_DIR"
}

init_state_db() {
  # If your app has a migration/init command, call it here.
  # For now, just ensure the file exists.
  if [ ! -f "$STATE_DB" ]; then
    info "Initializing empty state DB at $STATE_DB..."
    : > "$STATE_DB"
  else
    info "State DB already exists at $STATE_DB."
  fi
}

start_web_ui() {
  info "Starting Python web UI on port 3000..."

  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"

  # If there is a dedicated app entrypoint script, prefer that.
  if [ -f "$REPO_ROOT/app/main.py" ]; then
    # Run via nohup so it survives the SSH session.
    nohup uvicorn app.main:app --host 0.0.0.0 --port 3000 \
      > "$LOG_DIR/web-ui.log" 2>&1 &
    info "Web UI started via uvicorn (app.main:app)."
  elif [ -f "$REPO_ROOT/app/server.py" ]; then
    nohup python "$REPO_ROOT/app/server.py" \
      > "$LOG_DIR/web-ui.log" 2>&1 &
    info "Web UI started via app/server.py."
  else
    warn "No known web UI entrypoint found (app/main.py or app/server.py). Please wire this to your actual app."
  fi
}

main() {
  info "Bootstrapping autoprovision jump host at $REPO_ROOT"

  install_packages
  install_talosctl
  create_venv
  install_python_deps
  prepare_data_dirs
  init_state_db
  start_web_ui

  IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}') || IP_ADDR="<jump-host-ip>"
  echo
  info "Bootstrap complete."
  echo "Open: http://$IP_ADDR:3000/"
}

main "$@"
