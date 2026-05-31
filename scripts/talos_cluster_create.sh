#!/usr/bin/env bash
set -euo pipefail

# Required env vars (passed by app/main.py)
CLUSTER_NAME="${TALOS_CLUSTER_NAME:-lab-cluster}"
CONTROL_PLANE_IPS_RAW="${TALOS_CONTROL_PLANE_IPS:-}"
WORKER_IPS_RAW="${TALOS_WORKER_IPS:-}"
INSTALL_DISK="${TALOS_INSTALL_DISK:-sda}"

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$BASE_DIR/data/k8s/$CLUSTER_NAME"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: $1"
    exit 1
  fi
}

trim_csv() {
  echo "$1" | tr -d ' ' | sed 's/^,*//;s/,*$//'
}

split_csv_to_array() {
  local csv
  csv="$(trim_csv "$1")"
  if [ -z "$csv" ]; then
    return 0
  fi
  IFS=',' read -r -a SPLIT_RESULT <<< "$csv"
}

require_cmd talosctl
require_cmd kubectl
require_cmd helm
require_cmd cilium

CONTROL_PLANE_IPS_RAW="$(trim_csv "$CONTROL_PLANE_IPS_RAW")"
WORKER_IPS_RAW="$(trim_csv "$WORKER_IPS_RAW")"

if [ -z "$CONTROL_PLANE_IPS_RAW" ]; then
  echo "[ERROR] TALOS_CONTROL_PLANE_IPS is required (comma-separated IPs)."
  exit 1
fi

split_csv_to_array "$CONTROL_PLANE_IPS_RAW"
CONTROL_PLANE_IPS=("${SPLIT_RESULT[@]}")
if [ "${#CONTROL_PLANE_IPS[@]}" -eq 0 ]; then
  echo "[ERROR] No valid control-plane IPs found."
  exit 1
fi

split_csv_to_array "$WORKER_IPS_RAW"
WORKER_IPS=("${SPLIT_RESULT[@]-}")

FIRST_CP="${CONTROL_PLANE_IPS[0]}"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "[INFO] Cluster: $CLUSTER_NAME"
echo "[INFO] Control planes: $CONTROL_PLANE_IPS_RAW"
echo "[INFO] Workers: ${WORKER_IPS_RAW:-<none>}"
echo "[INFO] Install disk: /dev/$INSTALL_DISK"

cat > cluster-patch.yaml <<'YAML'
cluster:
  network:
    cni:
      name: none
  proxy:
    disabled: true
YAML

talosctl gen config "$CLUSTER_NAME" "https://$FIRST_CP:6443" \
  --force \
  --install-disk "/dev/$INSTALL_DISK" \
  --config-patch @cluster-patch.yaml

export TALOSCONFIG="$WORK_DIR/talosconfig"

# Apply control-plane configs.
for idx in "${!CONTROL_PLANE_IPS[@]}"; do
  ip="${CONTROL_PLANE_IPS[$idx]}"
  if [ "$idx" -eq 0 ]; then
    patch_file="controlplane-allow-scheduling-patch.yaml"
    cat > "$patch_file" <<'YAML'
cluster:
  allowSchedulingOnControlPlanes: true
YAML
    echo "[INFO] Applying control-plane config to $ip (with allowSchedulingOnControlPlanes)"
    talosctl apply-config --insecure --nodes "$ip" --file controlplane.yaml --config-patch @"$patch_file"
  else
    echo "[INFO] Applying control-plane config to $ip"
    talosctl apply-config --insecure --nodes "$ip" --file controlplane.yaml
  fi
done

# Apply worker configs if provided.
if [ "${#WORKER_IPS[@]}" -gt 0 ] && [ -n "${WORKER_IPS[0]:-}" ]; then
  for ip in "${WORKER_IPS[@]}"; do
    echo "[INFO] Applying worker config to $ip"
    talosctl apply-config --insecure --nodes "$ip" --file worker.yaml
  done
fi

echo "[INFO] Bootstrapping etcd on first control-plane node: $FIRST_CP"
talosctl bootstrap --nodes "$FIRST_CP" --talosconfig "$WORK_DIR/talosconfig"

echo "[INFO] Fetching kubeconfig"
talosctl kubeconfig "$WORK_DIR/kubeconfig" --nodes "$FIRST_CP" --talosconfig "$WORK_DIR/talosconfig"

export KUBECONFIG="$WORK_DIR/kubeconfig"

# Gateway API CRDs (safe to re-apply)
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gatewayclasses.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gateways.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_httproutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_referencegrants.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_grpcroutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/experimental/gateway.networking.k8s.io_tlsroutes.yaml

helm repo add cilium https://helm.cilium.io/ >/dev/null 2>&1 || true
helm repo update

if cilium status --wait --wait-duration 15s >/dev/null 2>&1; then
  echo "[INFO] Cilium is already installed. Skipping install."
else
  cilium install \
    --version 1.19.4 \
    --helm-set=ipam.mode=kubernetes \
    --helm-set=kubeProxyReplacement=true \
    --helm-set=securityContext.capabilities.ciliumAgent="{CHOWN,KILL,NET_ADMIN,NET_RAW,IPC_LOCK,SYS_ADMIN,SYS_RESOURCE,DAC_OVERRIDE,FOWNER,SETGID,SETUID}" \
    --helm-set=securityContext.capabilities.cleanCiliumState="{NET_ADMIN,SYS_ADMIN,SYS_RESOURCE}" \
    --helm-set=cgroup.autoMount.enabled=false \
    --helm-set=cgroup.hostRoot=/sys/fs/cgroup \
    --helm-set=l2announcements.enabled=true \
    --helm-set=externalIPs.enabled=true \
    --set gatewayAPI.enabled=true \
    --helm-set=devices=e+ \
    --helm-set=operator.replicas=1
fi

cilium status --wait
kubectl get nodes -o wide

echo "[INFO] Talos cluster creation complete."
echo "[INFO] talosconfig: $WORK_DIR/talosconfig"
echo "[INFO] kubeconfig:  $WORK_DIR/kubeconfig"
