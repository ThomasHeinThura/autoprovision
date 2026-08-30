# MetalLB on RKE2 (FRR-K8s mode) — LoadBalancer IPs for Istio

RKE2 nodes have no cloud load balancer, so `LoadBalancer` Services (most importantly the
**shared ambient ingress Gateway**, svc `shared-gateway-istio`) have no external IP by default.
**MetalLB** assigns them a real IP from a pool on your LAN. This guide installs MetalLB in
**FRR-K8s mode** (BGP + BFD + IPv6 + the ability to merge extra FRR config) and points the
shared gateway at it.

> Run this **after the RKE2 cluster is up** and **before/with Istio** (the shared gateway's
> Service stays `<pending>` until MetalLB can hand it an IP). See the order in
> [rke2-addons-istio-argocd-headlamp.md](rke2-addons-istio-argocd-headlamp.md). The web UI's
> Istio card runs MetalLB automatically first when the IP-range field is filled.

## Prerequisites

- RKE2 cluster healthy, default CNI (Canal), `kubectl` pointed at the cluster:
  ```bash
  export KUBECONFIG="$HOME/autoprovision/data/k8s/$CLUSTER_NAME/kubeconfig"
  kubectl get nodes -o wide
  ```
- A **free IP range on the node LAN** for the pool (not used by DHCP or other hosts), in the same
  subnet as the nodes for L2 mode — e.g. `192.168.51.200-192.168.51.220`.
- **RKE2 ServiceLB (Klipper) disabled** — it competes with MetalLB for `LoadBalancer` Services.

---

## Step 0 — Disable RKE2's built-in ServiceLB (required)

MetalLB and RKE2's ServiceLB must not both manage `LoadBalancer` Services.

**Option A — at install (Ansible):** set `rke2_disable_servicelb: true` when running
`ansible/k8s/rke2_cluster.yml` (the playbook adds `servicelb` to the server `disable:` list). e.g. set
the **"Disable ServiceLB"** input / pass `-e rke2_disable_servicelb=true`.

**Option B — on an existing cluster (manual):** on **each server node**, edit
`/etc/rancher/rke2/config.yaml`:
```yaml
disable:
  - rke2-ingress-nginx
  - rke2-traefik
  - servicelb
```
then restart RKE2:
```bash
sudo systemctl restart rke2-server
```
Confirm ServiceLB is gone (no `svclb-*` pods):
```bash
kubectl get pods -A | grep svclb || echo "ServiceLB disabled (good)"
```

---

## Step 1 — Install MetalLB (FRR-K8s mode)

```bash
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.16.1/config/manifests/metallb-frr-k8s.yaml

# Wait for the controller, speakers, and frr-k8s pods
kubectl -n metallb-system rollout status deploy/controller --timeout=180s
kubectl -n metallb-system get pods
```
Expect (per node) a `speaker-*` and `frr-k8s-*` pod, plus one `controller-*`. All `Running`.

---

## Step 2 — Define the IP address pool

```bash
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: lan-pool
  namespace: metallb-system
spec:
  addresses:
    - 192.168.51.200-192.168.51.220     # adjust to a free range on your LAN
EOF
```

Then pick **Step 3a (L2)** for a flat LAN, or **Step 3b (BGP)** if you peer with a router.

### Step 3a — L2 mode (simplest; recommended for a flat LAN)

```bash
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: l2-adv
  namespace: metallb-system
spec:
  ipAddressPools:
    - lan-pool
EOF
```
MetalLB answers ARP for the pool IPs from whichever node holds the service — no router config needed.

### Step 3b — BGP mode (FRR-K8s; peer with your router)

```bash
# Optional BFD profile for fast failure detection
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: BFDProfile
metadata:
  name: bfd-fast
  namespace: metallb-system
spec:
  receiveInterval: 300
  transmitInterval: 300
EOF

# Peer with the upstream router/ToR (adjust ASNs + addresses)
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: BGPPeer
metadata:
  name: router1
  namespace: metallb-system
spec:
  myASN: 64512
  peerASN: 64512
  peerAddress: 192.168.51.1
  bfdProfile: bfd-fast
EOF

# Advertise the pool over BGP
cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: BGPAdvertisement
metadata:
  name: bgp-adv
  namespace: metallb-system
spec:
  ipAddressPools:
    - lan-pool
EOF
```

> FRR-K8s mode lets you also merge raw FRR config via the `FRRConfiguration` CRD (e.g. extra
> neighbors, route maps) — see the MetalLB FRR-K8s docs. Standard BGP/BFD above covers most needs.

---

## Step 4 — Give the shared gateway a MetalLB IP

On the ambient setup, ingress is the **shared Gateway API Gateway** (`shared-gateway` in
`istio-system`), which Istio reconciles into one `LoadBalancer` Service named
`shared-gateway-istio`. Once a pool exists MetalLB assigns it an IP automatically. To **pin a
specific IP**, annotate the Service:

```bash
kubectl -n istio-system annotate svc shared-gateway-istio \
  metallb.universe.tf/loadBalancerIPs=192.168.51.200 --overwrite
```

Verify the external IP is assigned:
```bash
kubectl -n istio-system get svc shared-gateway-istio
# EXTERNAL-IP should show 192.168.51.200 (not <pending>)
```

Point DNS / `/etc/hosts` for your hostnames at that IP (matches the WSO2 repo's Gateway hosts):
```bash
echo "192.168.51.200  apim.example.com internal-gw.example.com external-gw.example.com wso2is.example.com argocd.prod.local headlamp.prod.local" | sudo tee -a /etc/hosts
```

---

## Verify

```bash
kubectl -n metallb-system get pods                       # controller + speaker + frr-k8s Running
kubectl get ipaddresspool,l2advertisement -n metallb-system
kubectl get svc -A | grep LoadBalancer                   # each shows an EXTERNAL-IP, not <pending>
# L2: from a LAN host, the IP should answer ARP/ping
ping -c1 192.168.51.200
```

## Troubleshooting

| Symptom | Cause / fix |
| ------- | ----------- |
| `EXTERNAL-IP` stays `<pending>` | No pool / pool exhausted / pool overlaps another subnet; or **ServiceLB still enabled** — check `kubectl get pods -A \| grep svclb` and disable it (Step 0). |
| Two IPs / flapping external IP | RKE2 ServiceLB and MetalLB both active — disable ServiceLB (Step 0) and restart RKE2. |
| L2 IP not reachable | Pool IPs must be **free** and in the **node subnet**; check the speaker pod logs: `kubectl -n metallb-system logs ds/speaker`. |
| BGP session down | ASNs/peerAddress wrong, or router not configured to peer; check `kubectl -n metallb-system logs -l app=frr-k8s`. |
| Gateway IP changes after redeploy | Pin it with the `metallb.universe.tf/loadBalancerIPs` annotation (Step 4). |

---

## Where this fits

```
RKE2 cluster (Canal) → [ServiceLB disabled] → MetalLB (pool + L2/BGP)
   → shared-gateway-istio gets ONE LAN IP → shared Gateway + HTTPRoutes → ArgoCD / Headlamp / WSO2
```

Related: [rke2-addons-istio-argocd-headlamp.md](rke2-addons-istio-argocd-headlamp.md) ·
[planning/wso2-rke2.md](../../docs/planning/wso2-rke2.md)
