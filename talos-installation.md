# Talos OS Installation Guide
## Cilium CNI + Envoy Gateway + ArgoCD + Headlamp + Cilium L2 IP Announcements

> **Environment:** UTM VMs (ARM64), `vda` disk, 1 control plane + 2 workers  
> **Talos:** v1.13.3 | **Cilium:** v1.19.4 | **Kubernetes:** v1.32+

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Variables](#2-environment-variables)
3. [Phase 1 — Verify Nodes in Maintenance Mode](#3-phase-1--verify-nodes-in-maintenance-mode)
4. [Phase 2 — Generate Cluster Config](#4-phase-2--generate-cluster-config)
5. [Phase 3 — Apply Config to Nodes](#5-phase-3--apply-config-to-nodes)
6. [Phase 4 — Bootstrap etcd](#6-phase-4--bootstrap-etcd)
7. [Phase 5 — Get kubeconfig](#7-phase-5--get-kubeconfig)
8. [Phase 6 — Install Gateway API CRDs](#8-phase-6--install-gateway-api-crds)
9. [Phase 7 — Install Cilium](#9-phase-7--install-cilium)
10. [Phase 8 — Configure Cilium L2 IP Pool](#10-phase-8--configure-cilium-l2-ip-pool)
11. [Phase 9 — Install Envoy Gateway](#11-phase-9--install-envoy-gateway)
12. [Phase 10 — Install ArgoCD](#12-phase-10--install-argocd)
13. [Phase 11 — Install Headlamp](#13-phase-11--install-headlamp)
14. [Phase 12 — Expose Apps via Envoy HTTPRoute](#14-phase-12--expose-apps-via-envoy-httproute)
15. [Phase 13 — Final Health Check](#15-phase-13--final-health-check)
16. [Troubleshooting](#16-troubleshooting)
17. [Architecture Overview](#17-architecture-overview)

---

## 1. Prerequisites

```bash
# Verify all required tools are installed
talosctl version
kubectl version --client
helm version
cilium version
```

| Tool | Purpose |
|------|---------|
| `talosctl` | Talos node management |
| `kubectl` | Kubernetes CLI |
| `helm` | Chart package manager |
| `cilium` CLI | Cilium install and status |

---

## 2. Environment Variables

Set these once — all phases reference them:

```bash
export CLUSTER_NAME="lab-cluster"
export CONTROL_PLANE_IP="192.168.64.19"
export WORKER1_IP="192.168.64.20"
export WORKER2_IP="192.168.64.21"
export DISK_NAME="vda"
export WORK_DIR="$HOME/autoprovision/data/k8s/$CLUSTER_NAME"

# Cilium L2 IP pool — pick a free range on your LAN
export L2_IP_POOL_START="192.168.64.100"
export L2_IP_POOL_END="192.168.64.120"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"
```

---

## 3. Phase 1 — Verify Nodes in Maintenance Mode

Confirm all nodes are reachable via insecure API (maintenance mode only):

```bash
# Check disks on all nodes — confirm vda exists
talosctl get disks --insecure --nodes "$CONTROL_PLANE_IP"
talosctl get disks --insecure --nodes "$WORKER1_IP"
talosctl get disks --insecure --nodes "$WORKER2_IP"
```

Expected output for each node:
```
ID      SIZE    TRANSPORT
vda     69 GB   virtio
```

```bash
# Confirm Talos version responds without auth error
talosctl version --insecure --endpoints "$CONTROL_PLANE_IP" --nodes "$CONTROL_PLANE_IP"
talosctl version --insecure --endpoints "$WORKER1_IP" --nodes "$WORKER1_IP"
talosctl version --insecure --endpoints "$WORKER2_IP" --nodes "$WORKER2_IP"
```

> ✅ Expected: Returns `Tag: v1.13.x`  
> ❌ If `PermissionDenied`: node is NOT in maintenance mode — wipe it first (see [Troubleshooting](#16-troubleshooting))

---

## 4. Phase 2 — Generate Cluster Config

### Create patches

```bash
# Patch 1: Disable default CNI (Cilium will replace it) and kube-proxy
cat > "$WORK_DIR/cluster-patch.yaml" <<'EOF'
cluster:
  network:
    cni:
      name: none
  proxy:
    disabled: true
EOF

# Patch 2: Allow workloads on control plane (single CP setup)
cat > "$WORK_DIR/cp-schedule-patch.yaml" <<'EOF'
cluster:
  allowSchedulingOnControlPlanes: true
EOF
```

### Generate secrets and configs

```bash
# Generate persistent secrets — NEVER regenerate on a running cluster
talosctl gen secrets -o "$WORK_DIR/secrets.yaml"

# Generate cluster configs
talosctl gen config "$CLUSTER_NAME" "https://$CONTROL_PLANE_IP:6443" \
  --with-secrets "$WORK_DIR/secrets.yaml" \
  --install-disk "/dev/$DISK_NAME" \
  --config-patch @"$WORK_DIR/cluster-patch.yaml" \
  --force

# Verify files created
ls "$WORK_DIR"
# Expected: controlplane.yaml  worker.yaml  talosconfig  secrets.yaml
```

### Set talosconfig endpoints (critical — fixes "failed to determine endpoints")

```bash
export TALOSCONFIG="$WORK_DIR/talosconfig"

talosctl config endpoint "$CONTROL_PLANE_IP" --talosconfig "$WORK_DIR/talosconfig"
talosctl config node "$CONTROL_PLANE_IP" --talosconfig "$WORK_DIR/talosconfig"

# Verify endpoints are set
talosctl config info --talosconfig "$WORK_DIR/talosconfig"
# Should show: Endpoints: [192.168.64.19]
```

---

## 5. Phase 3 — Apply Config to Nodes

### Control plane (with scheduling patch)

```bash
talosctl apply-config --insecure \
  --nodes "$CONTROL_PLANE_IP" \
  --file "$WORK_DIR/controlplane.yaml" \
  --config-patch @"$WORK_DIR/cp-schedule-patch.yaml"
```

### Worker nodes

```bash
talosctl apply-config --insecure --nodes "$WORKER1_IP" --file "$WORK_DIR/worker.yaml"
talosctl apply-config --insecure --nodes "$WORKER2_IP" --file "$WORK_DIR/worker.yaml"
```

> ⏳ Watch the UTM console — wait until you see **"etcd is waiting to join"** on the control plane before proceeding to bootstrap.

---

## 6. Phase 4 — Bootstrap etcd

> ⚠️ Run `bootstrap` **EXACTLY ONCE**. Running it twice corrupts the cluster.

```bash
talosctl bootstrap \
  --talosconfig "$WORK_DIR/talosconfig" \
  --endpoints "$CONTROL_PLANE_IP" \
  --nodes "$CONTROL_PLANE_IP"
```

Watch cluster health (takes 2–5 minutes):

```bash
talosctl health \
  --talosconfig "$WORK_DIR/talosconfig" \
  --endpoints "$CONTROL_PLANE_IP" \
  --nodes "$CONTROL_PLANE_IP"
```

---

## 7. Phase 5 — Get kubeconfig

```bash
talosctl kubeconfig "$WORK_DIR/kubeconfig" \
  --talosconfig "$WORK_DIR/talosconfig" \
  --endpoints "$CONTROL_PLANE_IP" \
  --nodes "$CONTROL_PLANE_IP"

export KUBECONFIG="$WORK_DIR/kubeconfig"

# Nodes will show NotReady until Cilium is installed — that is expected
kubectl get nodes -o wide
```

---

## 8. Phase 6 — Install Gateway API CRDs

Install both standard and experimental CRDs — Envoy Gateway requires TLS/TCP route CRDs:

```bash
# Standard CRDs
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gatewayclasses.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gateways.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_httproutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_referencegrants.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_grpcroutes.yaml

# Experimental CRDs (required for Envoy TLS/TCP routes)
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/experimental/gateway.networking.k8s.io_tlsroutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/experimental/gateway.networking.k8s.io_tcproutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/experimental/gateway.networking.k8s.io_backendtlspolicies.yaml

# Verify
kubectl get crd | grep gateway
```

---

## 9. Phase 7 — Install Cilium

> **Important:** `gatewayAPI.enabled=false` here because Envoy Gateway manages the GatewayClass, not Cilium. Enabling both causes GatewayClass conflicts.

```bash
helm repo add cilium https://helm.cilium.io/
helm repo update

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
  --helm-set=gatewayAPI.enabled=false \
  --helm-set=devices=e+ \
  --helm-set=operator.replicas=1

# Wait for Cilium to be fully ready
cilium status --wait

# All nodes should now show Ready
kubectl get nodes -o wide
```

---

## 10. Phase 8 — Configure Cilium L2 IP Pool

Create the IP pool and announcement policy so `LoadBalancer` services get real LAN IPs via ARP:

```bash
# IP pool — adjust range to match your LAN
cat <<EOF | kubectl apply -f -
apiVersion: "cilium.io/v2alpha1"
kind: CiliumLoadBalancerIPPool
metadata:
  name: "l2-pool"
spec:
  blocks:
    - start: "${L2_IP_POOL_START}"
      stop: "${L2_IP_POOL_END}"
EOF

# L2 announcement policy
cat <<EOF | kubectl apply -f -
apiVersion: "cilium.io/v2alpha1"
kind: CiliumL2AnnouncementPolicy
metadata:
  name: "l2-policy"
spec:
  interfaces:
    - ^e.*          # matches eth0, ens3, enp0s1, enp1s0, etc.
  externalIPs: true
  loadBalancerIPs: true
EOF

# Verify pool and policy accepted
kubectl get ciliumloadbalancerippool
kubectl get ciliuml2announcementpolicy
```

---

## 11. Phase 9 — Install Envoy Gateway

```bash
kubectl delete namespace envoy-gateway-system --ignore-not-found
kubectl get crd | grep -E "gateway|envoy" | awk '{print $1}' | xargs kubectl delete crd --ignore-not-found

kubectl create namespace envoy-gateway-system

helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.8.0 -n envoy-gateway-system --create-namespace --set config.envoyGateway.extensionApis.enableBackend=true --set deployment.replicas=2

kubectl rollout status deployment/envoy-gateway -n envoy-gateway-system
kubectl get pods -n envoy-gateway-system
```

### Create GatewayClass

```bash
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: envoy
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
EOF
```

### Create Gateway (triggers Cilium to assign L2 IP)

```bash
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: main-gateway
  namespace: envoy-gateway-system
spec:
  gatewayClassName: envoy
  listeners:
    - name: http
      protocol: HTTP
      port: 80
    - name: https
      protocol: HTTPS
      port: 443
      tls:
        mode: Terminate
        certificateRefs:
          - name: tls-secret
EOF

# Check that Gateway got an external IP from L2 pool (e.g. 192.168.64.100)
kubectl get gateway -n envoy-gateway-system
kubectl get svc -n envoy-gateway-system
```

---

## 12. Phase 10 — Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

kubectl get pods -n argocd

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo

# Open: https://localhost:8080  (user: admin)
```

---

## 13. Phase 11 — Install Headlamp

```bash
# first add our custom repo to your local helm repositories
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/

# now you should be able to install headlamp via helm
helm install headlamp headlamp/headlamp --namespace kube-system

# Generate login token (paste this into Headlamp UI)
kubectl create token headlamp --namespace kube-system

```

---

## 14. Phase 12 — Expose Apps via Envoy HTTPRoute

Route external traffic through the Gateway's L2 IP to ArgoCD and Headlamp:

### ArgoCD HTTPRoute

```bash
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: argocd
  namespace: argocd
spec:
  parentRefs:
    - name: main-gateway
      namespace: envoy-gateway-system
  hostnames:
    - "argocd.lab.local"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: argocd-server
          port: 80
EOF
```

### Headlamp HTTPRoute

```bash
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: headlamp
  namespace: kube-system
spec:
  parentRefs:
    - name: main-gateway
      namespace: envoy-gateway-system
  hostnames:
    - "headlamp.lab.local"
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: headlamp
          port: 80
EOF
```

### Add to /etc/hosts (or local DNS)

```bash
# Replace 192.168.64.100 with the actual EXTERNAL-IP from your Gateway
echo "192.168.64.100  argocd.lab.local" | sudo tee -a /etc/hosts
echo "192.168.64.100  headlamp.lab.local" | sudo tee -a /etc/hosts
```

Now accessible at:
- **ArgoCD:** http://argocd.lab.local
- **Headlamp:** http://headlamp.lab.local

---

## 15. Phase 13 — Final Health Check

```bash
# Talos cluster members
talosctl --talosconfig "$WORK_DIR/talosconfig" \
  --endpoints "$CONTROL_PLANE_IP" \
  --nodes "$CONTROL_PLANE_IP","$WORKER1_IP","$WORKER2_IP" \
  get members

# Kubernetes nodes — all should be Ready
kubectl get nodes -o wide

# All pods across all namespaces
kubectl get pods -A

# Cilium health
cilium status

# L2 pool and policy
kubectl get ciliumloadbalancerippool
kubectl get ciliuml2announcementpolicy

# Gateway external IP
kubectl get gateway,svc -n envoy-gateway-system

# Component pods
kubectl get pods -n envoy-gateway-system
kubectl get pods -n argocd
kubectl get pods -n kubesystem | grep headlamp
```

# Env paths reminder
echo "TALOSCONFIG: $WORK_DIR/talosconfig"
echo "KUBECONFIG:  $WORK_DIR/kubeconfig"

Argo has some issues with self-signed certs, so you may need to run this in your terminal to access the ArgoCD UI without cert errors:
```
# See current config
kubectl -n argocd get configmap argocd-cmd-params-cm -o yaml

kubectl patch configmap argocd-cmd-params-cm -n argocd \
  --type merge \
  -p '{"data":{"server.insecure":"true"}}'

kubectl rollout restart deployment argocd-server -n argocd
kubectl get pods -n argocd
```

```

---

## 16. Troubleshooting

### Node not in maintenance mode (`PermissionDenied` on `--insecure`)

The node has a prior config applied. Boot it from the Talos ISO in UTM, then:

```bash
talosctl reset --insecure \
  --endpoints <NODE_IP> \
  --nodes <NODE_IP> \
  --graceful=false \
  --wipe-mode system-disk \
  --wait=false
```

### PKI mismatch (`x509: certificate signed by unknown authority`)

You regenerated secrets after the node was already configured. Options:
1. Reset nodes to maintenance (above) and rerun with new secrets
2. Restore the original `secrets.yaml` that was used to configure the node

### `talosctl bootstrap` fails with `failed to determine endpoints`

The talosconfig has empty endpoints. Fix:
```bash
talosctl config endpoint "$CONTROL_PLANE_IP" --talosconfig "$WORK_DIR/talosconfig"
talosctl config node "$CONTROL_PLANE_IP" --talosconfig "$WORK_DIR/talosconfig"
```

### Nodes stuck at `NotReady`

Expected until Cilium is installed. If still NotReady after Cilium:
```bash
cilium status
kubectl describe node <NODE_NAME>
kubectl logs -n kube-system -l k8s-app=cilium
```

### Gateway has no EXTERNAL-IP

Check Cilium L2 pool and policy are correctly applied:
```bash
kubectl get ciliumloadbalancerippool -o yaml
kubectl get ciliuml2announcementpolicy -o yaml
# Verify the interface regex matches your NIC name
ip link show
```

### `cannot use --wait and --insecure together`

Add `--wait=false` explicitly:
```bash
talosctl reset --insecure --nodes <IP> --endpoints <IP> --graceful=false --wipe-mode system-disk --wait=false
```

---

## 17. Architecture Overview

```
Your LAN (192.168.64.x)
         │
         │  ARP (Cilium L2AnnouncementPolicy)
         ▼
  LoadBalancer IP (e.g. 192.168.64.100)  ◄─── CiliumLoadBalancerIPPool
         │
         ▼
  Envoy Gateway Pod (GatewayClass: envoy)
         │
         ├──► HTTPRoute: argocd.lab.local     → argocd-server:80   (ns: argocd)
         └──► HTTPRoute: headlamp.lab.local   → headlamp:80        (ns: headlamp)

Kubernetes Cluster
├── kube-system        ← Cilium CNI (kubeProxyReplacement=true)
├── envoy-gateway-system  ← Envoy Gateway controller + proxy pods
├── argocd             ← GitOps CD
└── headlamp           ← Kubernetes Web UI

Talos Nodes
├── 192.168.64.19  control-plane  (allowSchedulingOnControlPlanes: true)
├── 192.168.64.20  worker-1
└── 192.168.64.21  worker-2
```

---

## Key File Paths

| File | Purpose |
|------|---------|
| `$WORK_DIR/secrets.yaml` | Talos PKI secrets — **never lose or regenerate** |
| `$WORK_DIR/talosconfig` | talosctl auth config |
| `$WORK_DIR/kubeconfig` | kubectl auth config |
| `$WORK_DIR/controlplane.yaml` | Control plane machine config |
| `$WORK_DIR/worker.yaml` | Worker machine config |
| `$WORK_DIR/cluster-patch.yaml` | CNI=none + kube-proxy disabled patch |
| `$WORK_DIR/cp-schedule-patch.yaml` | allowSchedulingOnControlPlanes patch |
