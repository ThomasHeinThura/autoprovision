# UAT RKE2 / Kubernetes Setup Guide

## Scope

UAT topology: **1 RKE2 control-plane (server) node + 2 RKE2 worker (agent) nodes**, with the
**default CNI (Canal)** and **Istio ambient** ingress (this replaced the original Talos-based
guide, removed in cleanup).

> RKE2 ships Canal CNI and kube-proxy by default. No separate CNI install. The cluster install is
> Ansible-automated via `ansible/k8s/rke2_cluster.yml`; in-cluster add-ons follow the shared runbook.

## Prerequisites

- 1 control-plane VM + 2 worker VMs (Ubuntu 22.04 or RKE2-supported OS), reachable over SSH.
- Jump host with `kubectl`, `helm`, `istioctl`, Ansible.
- UAT MSSQL single instance and GitLab available (or installing in parallel).

## Environment variables (manual reference)

```bash
export CLUSTER_NAME="uat-cluster"
export RKE2_VERSION="v1.36.1+rke2r2"        # Kubernetes v1.36.1, Canal CNI (default)
export SERVER1_IP="192.168.65.11"           # also the registration address for UAT
export AGENT_IPS="192.168.65.21 192.168.65.22"
export RKE2_TOKEN="<shared-cluster-token>"
export WORK_DIR="$HOME/autoprovision/data/k8s/$CLUSTER_NAME"
mkdir -p "$WORK_DIR"
```

For a single-server UAT cluster, the registration address is simply the server IP.

---

## Phase 1 — Install RKE2 (automated by Ansible)

### 1a. Server (bootstrap)

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml <<EOF
token: ${RKE2_TOKEN}
tls-san:
  - ${SERVER1_IP}
# Default CNI (Canal) — do NOT set cni: none
# Istio owns ingress — disable the RKE2-bundled ingress (Traefik is the v1.36 default).
disable:
  - rke2-ingress-nginx
  - rke2-traefik
EOF

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=server INSTALL_RKE2_VERSION=${RKE2_VERSION} sh -
systemctl enable --now rke2-server.service
```

### 1b. Agents (2 workers)

On each agent:

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml <<EOF
server: https://${SERVER1_IP}:9345
token: ${RKE2_TOKEN}
EOF

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=agent INSTALL_RKE2_VERSION=${RKE2_VERSION} sh -
systemctl enable --now rke2-agent.service
```

### 1c. Fetch kubeconfig to the jump host

```bash
scp ${SERVER1_IP}:/etc/rancher/rke2/rke2.yaml "$WORK_DIR/kubeconfig"
sed -i '' "s/127.0.0.1/${SERVER1_IP}/g" "$WORK_DIR/kubeconfig"   # macOS sed
export KUBECONFIG="$WORK_DIR/kubeconfig"
kubectl get nodes -o wide      # 1 server + 2 agents, all Ready
```

`ansible/k8s/rke2_cluster.yml` performs 1a–1c for the UAT host groups.

---

## Phase 2 — In-cluster add-ons (runbook)

Follow [rke2-addons-istio-argocd-headlamp.md](rke2-addons-istio-argocd-headlamp.md) with UAT
choices:

1. **Istio 1.30 ambient** — `profile=ambient` (no sidecars, no ingressgateway) + the single
   shared Gateway API `Gateway` in `istio-system`. One MetalLB IP serves all UAT hosts.
2. **cert-manager** — install (+ internal CA `ca-issuer`).
3. **ArgoCD** — `HTTPRoute` on the shared gateway (`argocd.uat.example.com` or `argocd.uat.local`).
4. **Headlamp** — `HTTPRoute` on the shared gateway (`headlamp.uat.local`).
5. **OpenTelemetry Collector** — export to the **UAT ELK** VM.
6. **WSO2 APIM/IS** — deploy with the team's repo
   [WSO2_APIM_KUBE_ISTIO](../../WSO2_APIM_KUBE_ISTIO/README.md) (namespaces enrolled in **ambient**
   via `istio.io/dataplane-mode=ambient`, certs, `istio-system` TLS secret, then
   `kubectl apply -f` of the component folders — or just run the web UI's WSO2 cards). UAT
   replica topology (1 CP + 1 internal GW + 1 external GW); WSO2 JDBC URL points at the
   **UAT single MSSQL instance**. See [planning/wso2-rke2.md](../../docs/planning/wso2-rke2.md).

---

## Phase 3 — Final checks

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get svc -n istio-system shared-gateway-istio
kubectl get gateway,httproute -A
kubectl get applications -n argocd
```

UAT runs **in parallel** with production on execution day — see
[planning/parallel-installation.md](../../docs/planning/parallel-installation.md).
