#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${TALOS_CLUSTER_NAME:-lab-cluster}"
WORKER_IPS_RAW="${TALOS_WORKER_IPS:-}"

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$BASE_DIR/data/k8s/$CLUSTER_NAME"

trim_csv() {
  echo "$1" | tr -d ' ' | sed 's/^,*//;s/,*$//'
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: $1"
    exit 1
  fi
}

require_cmd talosctl
require_cmd kubectl

if [ ! -f "$WORK_DIR/talosconfig" ] || [ ! -f "$WORK_DIR/worker.yaml" ] || [ ! -f "$WORK_DIR/kubeconfig" ]; then
  echo "[ERROR] Cluster config not found in $WORK_DIR. Run Create Talos Cluster first."
  exit 1
fi

WORKER_IPS_RAW="$(trim_csv "$WORKER_IPS_RAW")"
if [ -z "$WORKER_IPS_RAW" ]; then
  echo "[ERROR] TALOS_WORKER_IPS is required for add-talos-workers action."
  exit 1
fi

IFS=',' read -r -a WORKER_IPS <<< "$WORKER_IPS_RAW"
export TALOSCONFIG="$WORK_DIR/talosconfig"
export KUBECONFIG="$WORK_DIR/kubeconfig"

for idx in "${!WORKER_IPS[@]}"; do
  ip="${WORKER_IPS[$idx]}"
  n="$((idx + 1))"
  patch_file="$WORK_DIR/worker-add-$n-patch.yaml"

  cat > "$patch_file" <<YAML
machine:
  network:
    hostname: ${CLUSTER_NAME}-worker-${n}
YAML

  echo "[INFO] Applying worker config to $ip"
  talosctl apply-config --insecure --nodes "$ip" --file "$WORK_DIR/worker.yaml" --config-patch @"$patch_file"
done

kubectl get nodes -o wide

echo "[INFO] Worker add flow completed."
