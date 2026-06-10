# Production RKE2 / Kubernetes Setup Guide

## Scope

Production topology: **3 RKE2 control-plane (server) nodes + 5 RKE2 worker (agent) nodes**, with
the **default CNI (Canal)** and **Istio ambient** ingress (this replaced the original
Talos-based guide, removed in cleanup).

## App or manual?

Recommended: use the Python web UI to trigger `ansible/rke2_cluster.yml`, which installs RKE2
across all 8 nodes. Then follow this guide for the in-cluster add-ons (which are not automated).

The cluster install itself is **Ansible-automated**; the steps below show the equivalent manual
commands and the add-on runbook.

## Production differences from UAT

1. **3 servers** form an HA control plane (etcd quorum). Use a stable **registration address**
   (VIP or LB) so joining servers and agents use one endpoint.
2. Do not schedule workloads on servers.
3. Run Istio ingress gateway and other HA add-ons with ≥2 replicas.
4. WSO2 connects to the **MSSQL AG listener**, not a single node.

## Prerequisites

- 3 control-plane VMs + 5 worker VMs, freshly installed Ubuntu 22.04 (or RKE2-supported OS),
  reachable over SSH from the jump host.
- A registration address (VIP/LB DNS name) that resolves to the 3 control-plane servers, or at
  least the first server's IP if no VIP is available.
- Jump host with `kubectl`, `helm`, `istioctl`, Ansible.
- MSSQL AG and GitLab already (or concurrently) being installed.

## Environment variables (manual reference)

```bash
export CLUSTER_NAME="prod-cluster"
export RKE2_VERSION="v1.36.1+rke2r2"        # Kubernetes v1.36.1, Canal CNI (default)
export REGISTRATION_ADDRESS="rke2-prod.example.local"   # VIP / LB / first server IP
export SERVER1_IP="192.168.64.11"
export SERVER2_IP="192.168.64.12"
export SERVER3_IP="192.168.64.13"
export AGENT_IPS="192.168.64.21 192.168.64.22 192.168.64.23 192.168.64.24 192.168.64.25"
export RKE2_TOKEN="<shared-cluster-token>"
export WORK_DIR="$HOME/autoprovision/data/k8s/$CLUSTER_NAME"
mkdir -p "$WORK_DIR"
```

---

## Phase 1 — Install RKE2 (automated by Ansible)

The web UI / `ansible/rke2_cluster.yml` performs the following. Manual equivalent below.

### 1a. First server (bootstrap)

On `SERVER1`:

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml <<EOF
token: ${RKE2_TOKEN}
tls-san:
  - ${REGISTRATION_ADDRESS}
  - ${SERVER1_IP}
  - ${SERVER2_IP}
  - ${SERVER3_IP}
# Default CNI (Canal) is used — do NOT set cni: none
# Istio owns ingress — disable the RKE2-bundled ingress (Traefik is the v1.36 default).
disable:
  - rke2-ingress-nginx
  - rke2-traefik
EOF

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=server INSTALL_RKE2_VERSION=${RKE2_VERSION} sh -
systemctl enable --now rke2-server.service

# Wait for the node to be ready
/var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get nodes
```

Why: the first server initializes etcd and the control plane with the bundled Canal CNI and
kube-proxy. No separate CNI install is needed.

### 1b. Remaining servers (join)

On `SERVER2` and `SERVER3`:

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml <<EOF
server: https://${REGISTRATION_ADDRESS}:9345
token: ${RKE2_TOKEN}
tls-san:
  - ${REGISTRATION_ADDRESS}
EOF

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=server INSTALL_RKE2_VERSION=${RKE2_VERSION} sh -
systemctl enable --now rke2-server.service
```

Why: additional servers join the etcd quorum via the registration address on port `9345`.

### 1c. Agents (workers)

On each of the 5 agent nodes:

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/config.yaml <<EOF
server: https://${REGISTRATION_ADDRESS}:9345
token: ${RKE2_TOKEN}
EOF

curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=agent INSTALL_RKE2_VERSION=${RKE2_VERSION} sh -
systemctl enable --now rke2-agent.service
```

### 1d. Fetch kubeconfig to the jump host

```bash
scp ${SERVER1_IP}:/etc/rancher/rke2/rke2.yaml "$WORK_DIR/kubeconfig"
# Rewrite the API server address to the registration address
sed -i '' "s/127.0.0.1/${REGISTRATION_ADDRESS}/g" "$WORK_DIR/kubeconfig"   # macOS sed
export KUBECONFIG="$WORK_DIR/kubeconfig"
kubectl get nodes -o wide      # 3 servers + 5 agents, all Ready
```

`ansible/rke2_cluster.yml` does 1a–1d for you and writes the kubeconfig to `$WORK_DIR/kubeconfig`.

### Scaling — add control-plane / worker nodes later (1→5 CP, 2→100 workers)

The playbook is **idempotent**, so adding nodes is just re-running it with a longer IP list:

- In the web UI use the **"RKE2 add/scale nodes"** track for the env, put **all** node IPs (existing
  + new) in the Control Plane / Worker fields, and Run. Already-joined nodes are skipped (the
  install is guarded by `creates` and config/service tasks are no-ops); only the **new IPs** join.
- Manual equivalent: add the new node to `rke2_agents` (worker) or `rke2_servers` (control plane)
  and re-run, or just install RKE2 on the new node with the same join config:
  ```bash
  # new worker
  cat > /etc/rancher/rke2/config.yaml <<EOF
  server: https://${REGISTRATION_ADDRESS}:9345
  token: ${RKE2_TOKEN}
  EOF
  curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=agent INSTALL_RKE2_VERSION=${RKE2_VERSION} sh -
  systemctl enable --now rke2-agent
  ```
- **Use the registration address / VIP** so new control-plane and worker nodes join one stable
  endpoint. New control-plane nodes join the etcd quorum (keep the CP count **odd**: 1 → 3 → 5).
- Verify: `kubectl get nodes -o wide` shows the new nodes `Ready` (Canal handles their networking).

---

## Phase 2 — In-cluster add-ons (runbook)

Follow [rke2-addons-istio-argocd-headlamp.md](rke2-addons-istio-argocd-headlamp.md) with these
production choices:

1. **Istio 1.30 ambient** — `profile=ambient` (no sidecars, no ingressgateway) + the single
   shared Gateway API `Gateway` in `istio-system` (one MetalLB IP for all production hosts).
   For HA, scale istiod replicas ≥2 (ztunnel/istio-cni are DaemonSets already).
2. **cert-manager** — install (+ internal CA `ca-issuer`).
3. **ArgoCD** — `HTTPRoute` on the shared gateway, production DNS (`argocd.prod.example.com`).
4. **Headlamp** — `HTTPRoute` on the shared gateway (`headlamp.prod.example.com`).
5. **OpenTelemetry Collector** — export to the **production ELK** VM.
6. **WSO2 APIM/IS** — deploy with the team's repo
   [WSO2_APIM_KUBE_ISTIO](../WSO2_APIM_KUBE_ISTIO/README.md) (namespaces enrolled in **ambient**
   via `istio.io/dataplane-mode=ambient`, certs, `istio-system` TLS secret `wso2-ingress-cert`,
   then `kubectl apply -f` of control-plane / internal-gw / external-gw / wso2-is — or just run
   the web UI's WSO2 cards). Production replica topology
   (2 CP + 2 internal GW + 2 external GW).
   With the **HA AG (CLUSTER_TYPE=EXTERNAL)** point the WSO2 JDBC URL at the **Pacemaker
   listener/VIP**; with a read-scale AG (CLUSTER_TYPE=NONE, no listener) use the **AG primary
   node** (apply `mssql/*.sql` schemas on the primary). See
   [planning/wso2-rke2.md](../planning/wso2-rke2.md).

---

## Phase 3 — Final checks

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get svc -n istio-system shared-gateway-istio
kubectl get gateway,httproute -A
kubectl get applications -n argocd
kubectl get pods -n wso2-cp -n wso2-is
```

Confirm: 8 nodes Ready (Canal), the shared gateway has its MetalLB external IP, ArgoCD/Headlamp
reachable, WSO2 pods Running and connected to MSSQL (VIP or primary).

---

## Notes vs the old Talos guide

| Old (Talos) | New (RKE2) |
| ----------- | ---------- |
| `talosctl gen config` + `cni: none` patch | RKE2 `config.yaml` with default CNI (Canal) |
| `talosctl bootstrap` | First `rke2-server` bootstraps etcd |
| Cilium Helm install | None — Canal ships with RKE2 |
| Envoy Gateway + Gateway API CRDs | Istio **ambient** + Gateway API (`shared-gateway` + `HTTPRoute`) |
| `talosctl kubeconfig` | `scp` `/etc/rancher/rke2/rke2.yaml` (done by Ansible) |

ArgoCD and Headlamp install steps are unchanged from the Talos guide.
