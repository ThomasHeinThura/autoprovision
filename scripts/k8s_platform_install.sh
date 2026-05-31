#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${TALOS_CLUSTER_NAME:-lab-cluster}"
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$BASE_DIR/data/k8s/$CLUSTER_NAME"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: $1"
    exit 1
  fi
}

require_cmd kubectl
require_cmd helm

if [ ! -f "$WORK_DIR/kubeconfig" ]; then
  echo "[ERROR] kubeconfig not found in $WORK_DIR. Run Create Talos Cluster first."
  exit 1
fi

export KUBECONFIG="$WORK_DIR/kubeconfig"

kubectl get nodes -o wide

helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
helm repo add envoy-gateway https://gateway.envoyproxy.io >/dev/null 2>&1 || true
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null 2>&1 || true
helm repo add sidero https://charts.siderolabs.com >/dev/null 2>&1 || true
helm repo update

kubectl create namespace cert-manager --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --set crds.enabled=true

kubectl create namespace envoy-gateway-system --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install envoy-gateway envoy-gateway/gateway-helm \
  --namespace envoy-gateway-system

kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argocd argo/argo-cd \
  --namespace argocd

kubectl create namespace headlamp --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install headlamp sidero/headlamp \
  --namespace headlamp

kubectl get pods -n cert-manager
kubectl get pods -n envoy-gateway-system
kubectl get pods -n argocd
kubectl get pods -n headlamp

echo "[INFO] Kubernetes platform install complete (cert-manager, Envoy Gateway, ArgoCD, Headlamp)."
