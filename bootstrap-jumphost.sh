#!/usr/bin/env bash
set -euo pipefail

# bootstrap-jumphost.sh
# Idempotent bootstrap for the autoprovision jump host (RKE2 + Istio model).
# - Installs system dependencies (git, Python, Ansible, jq, sshpass)
# - Installs Kubernetes CLIs for the in-cluster runbooks: kubectl, helm, istioctl
#   (best-effort — a slow/blocked download never blocks the web UI from starting)
# - Creates Python virtualenv and installs web UI dependencies
# - Prepares data directories and SQLite state DB
# - Starts the Python web UI service on port 3000
#
# Note: talosctl and the cilium CLI are NOT installed — the stack moved from
# Talos+Cilium to RKE2 (Canal CNI). RKE2 itself is installed on the cluster nodes
# by Ansible (ansible/rke2_cluster.yml), not from the jump host.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
DATA_DIR="$REPO_ROOT/data"
LOG_DIR="$DATA_DIR/logs"
INV_DIR="$DATA_DIR/inventory"
GEN_ENV_DIR="$DATA_DIR/generated-env"
STATE_DB="$DATA_DIR/state.db"

ISTIO_VERSION="1.30.0"
# curl flags so a stalled download fails fast instead of hanging the bootstrap.
CURL_OPTS=(--fail --location --connect-timeout 15 --max-time 300 --retry 2)

info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }

linux_arch() {
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) echo "amd64" ;;
  esac
}

install_packages() {
  info "Installing system packages (git, Python, Ansible, jq, sshpass)..."

  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y \
      git curl ca-certificates \
      python3 python3-venv python3-pip \
      sshpass jq software-properties-common
    if ! command -v ansible >/dev/null 2>&1; then
      sudo apt-get install -y ansible
    fi
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y git curl ca-certificates python3 python3-venv python3-pip sshpass jq ansible
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y git curl ca-certificates python3 python3-venv python3-pip sshpass jq ansible
  else
    warn "Unknown package manager. Ensure git, Python 3, pip, ansible, curl, jq, sshpass are installed."
  fi
}

# ── Kubernetes CLIs (best-effort; needed only for the in-cluster runbook phase) ──

install_kubectl() {
  if command -v kubectl >/dev/null 2>&1 && kubectl version --client >/dev/null 2>&1; then
    info "kubectl already installed. Skipping."; return 0
  fi
  info "Installing kubectl..."
  local arch ver
  arch="$(linux_arch)"
  ver="$(curl "${CURL_OPTS[@]}" -s https://dl.k8s.io/release/stable.txt 2>/dev/null || true)"
  if [ -z "$ver" ]; then warn "Could not resolve kubectl version (network?). Skipping kubectl."; return 0; fi
  if curl "${CURL_OPTS[@]}" -o /tmp/kubectl "https://dl.k8s.io/release/${ver}/bin/linux/${arch}/kubectl"; then
    chmod +x /tmp/kubectl && sudo mv /tmp/kubectl /usr/local/bin/kubectl
    info "kubectl ${ver} installed."
  else
    warn "kubectl download failed. Install it manually later; not required for the web UI."
  fi
}

install_helm() {
  if command -v helm >/dev/null 2>&1; then info "helm already installed. Skipping."; return 0; fi
  info "Installing helm..."
  if curl "${CURL_OPTS[@]}" -s https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 -o /tmp/get-helm-3; then
    bash /tmp/get-helm-3 || warn "helm install script failed. Install it manually later."
    rm -f /tmp/get-helm-3
  else
    warn "Could not fetch helm install script. Install it manually later; not required for the web UI."
  fi
}

install_istioctl() {
  if command -v istioctl >/dev/null 2>&1; then info "istioctl already installed. Skipping."; return 0; fi
  info "Installing istioctl ${ISTIO_VERSION}..."
  local arch tgz
  arch="$(linux_arch)"
  tgz="/tmp/istioctl-${ISTIO_VERSION}-linux-${arch}.tar.gz"
  if curl "${CURL_OPTS[@]}" -o "$tgz" \
      "https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/istioctl-${ISTIO_VERSION}-linux-${arch}.tar.gz"; then
    tar -xzf "$tgz" -C /tmp istioctl && chmod +x /tmp/istioctl && sudo mv /tmp/istioctl /usr/local/bin/istioctl
    rm -f "$tgz"
    info "istioctl ${ISTIO_VERSION} installed."
  else
    warn "istioctl download failed. Install it manually later; not required for the web UI."
  fi
}

# ── DISABLED: Talos + Cilium (replaced by RKE2 + Canal CNI) ─────────────────────
# Kept commented for reference only. The stack moved from Talos+Cilium to RKE2
# (default Canal CNI). RKE2 is installed on the cluster nodes by Ansible
# (ansible/rke2_cluster.yml), so the jump host no longer needs these CLIs.
# Re-enable by uncommenting the function and its call in main() if you revert.
#
# install_talosctl() {
#   if command -v talosctl >/dev/null 2>&1 && talosctl version >/dev/null 2>&1; then
#     info "talosctl already installed. Skipping."; return 0
#   fi
#   info "Installing talosctl..."
#   local arch; arch="$(linux_arch)"
#   if curl "${CURL_OPTS[@]}" -o /tmp/talosctl \
#       "https://github.com/siderolabs/talos/releases/latest/download/talosctl-linux-${arch}"; then
#     chmod +x /tmp/talosctl && sudo mv /tmp/talosctl /usr/local/bin/talosctl
#   else
#     warn "talosctl download failed."
#   fi
# }
#
# install_cilium_cli() {
#   if command -v cilium >/dev/null 2>&1; then info "cilium CLI already installed. Skipping."; return 0; fi
#   info "Installing cilium CLI..."
#   local ver arch; arch="$(linux_arch)"
#   ver="$(curl "${CURL_OPTS[@]}" -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt || true)"
#   [ -z "$ver" ] && { warn "Could not resolve cilium CLI version."; return 0; }
#   if curl "${CURL_OPTS[@]}" -o "/tmp/cilium.tar.gz" \
#       "https://github.com/cilium/cilium-cli/releases/download/${ver}/cilium-linux-${arch}.tar.gz"; then
#     sudo tar xzf "/tmp/cilium.tar.gz" -C /usr/local/bin && rm -f "/tmp/cilium.tar.gz"
#   else
#     warn "cilium CLI download failed."
#   fi
# }

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
  pip install --upgrade pip
  if [ -f "$REPO_ROOT/requirements.txt" ]; then
    pip install -r "$REPO_ROOT/requirements.txt"
  else
    pip install fastapi "uvicorn[standard]" ansible-runner
  fi
}

prepare_data_dirs() {
  info "Preparing data directories..."
  mkdir -p "$DATA_DIR" "$LOG_DIR" "$INV_DIR" "$GEN_ENV_DIR"
}

init_state_db() {
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

  # Stop any previous instance so re-runs are clean.
  pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true

  if [ -f "$REPO_ROOT/app/main.py" ]; then
    ( cd "$REPO_ROOT" && nohup uvicorn app.main:app --host 0.0.0.0 --port 3000 \
        > "$LOG_DIR/web-ui.log" 2>&1 & )
    sleep 2
    if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
      info "Web UI started via uvicorn (app.main:app)."
    else
      warn "Web UI did not stay up. Check $LOG_DIR/web-ui.log:"
      tail -n 20 "$LOG_DIR/web-ui.log" 2>/dev/null || true
    fi
  else
    warn "No web UI entrypoint found (app/main.py)."
  fi
}

main() {
  info "Bootstrapping autoprovision jump host at $REPO_ROOT"

  install_packages
  # DISABLED — Talos + Cilium replaced by RKE2 + Canal. Re-enable if you revert.
  # install_talosctl
  # install_cilium_cli
  # Kubernetes CLIs are best-effort and must never block the web UI from starting.
  install_kubectl
  install_helm
  install_istioctl
  create_venv
  install_python_deps
  prepare_data_dirs
  init_state_db
  start_web_ui

  IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}') || IP_ADDR="<jump-host-ip>"
  echo
  info "Bootstrap complete."
  echo "Open: http://${IP_ADDR:-<jump-host-ip>}:3000/"
}

main "$@"
