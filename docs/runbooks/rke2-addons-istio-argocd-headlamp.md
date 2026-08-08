# RKE2 In-Cluster Add-ons — Istio (ambient) + cert-manager + ArgoCD + Headlamp + WSO2

Shared runbook referenced by both
[prod-rke2-installation.md](prod-rke2-installation.md) and
[uat-rke2-installation.md](uat-rke2-installation.md).

> **Now automated — the web UI does all of this.** The dashboard cards
> *Istio (+MetalLB)*, *cert-manager (internal CA)*, *ArgoCD*, *Headlamp*, and *WSO2 APIM/IS*
> run [ansible/k8s_addons.yml](../../ansible/k8s/addons.yml) and
> [ansible/k8s_wso2.yml](../../ansible/k8s/wso2.yml) against the cluster kubeconfig on the
> jump host. This runbook is the **manual CLI equivalent** (and the reference for what the
> automation does) — use it for troubleshooting or air-gapped installs.

**Architecture (matches the automation — tested and working):** Istio **1.30 ambient**
(`profile=ambient`: istiod + istio-cni + ztunnel, **no sidecars, no istio-ingressgateway**).
North-south ingress is **ONE shared Kubernetes Gateway API `Gateway`** (`shared-gateway` in
`istio-system`) that Istio reconciles into a single ingress proxy with **one LoadBalancer
Service** (`shared-gateway-istio` → one MetalLB IP for ALL hosts). Every app (WSO2, ArgoCD,
Headlamp) attaches an `HTTPRoute` by hostname. TLS terminates at the shared gateway with the
secret `wso2-ingress-cert` in `istio-system` (Gateway API `certificateRefs` — the secret MUST
live in the Gateway's own namespace; there is no sidecar-era `credentialName`).

> **Prerequisite:** the RKE2 cluster is already installed by Ansible
> (`ansible/k8s/rke2_cluster.yml`) and all nodes are `Ready`. RKE2 ships the **default CNI (Canal)**
> and kube-proxy, so networking already works — there is **no separate CNI install**.

## 0. Point kubectl at the cluster

The Ansible playbook copies the cluster kubeconfig to the jump host:

```bash
export KUBECONFIG="$HOME/autoprovision/data/k8s/$CLUSTER_NAME/kubeconfig"
kubectl get nodes -o wide        # all nodes Ready, CNI = Canal
```

RKE2 puts `kubectl`, `helm`, and config under `/var/lib/rancher/rke2/bin` and
`/etc/rancher/rke2/rke2.yaml` on the server node; on the jump host we use the copied kubeconfig.

---

## MetalLB (LoadBalancer IPs) — install first

RKE2 nodes have no cloud load balancer, so the shared gateway's Service would stay
`<pending>`. Install **MetalLB (FRR-K8s mode)** to hand out LAN IPs, and **disable RKE2 ServiceLB**
(it conflicts with MetalLB): follow [metallb-install.md](metallb-install.md). In short: set
`rke2_disable_servicelb: true` at cluster install, then apply MetalLB + an `IPAddressPool` +
`L2Advertisement` (or BGP). Do this **before** Istio so the gateway gets an IP immediately.
(The web UI's Istio card runs MetalLB first when you fill the IP-range field.)

## 1. Install Istio — AMBIENT profile (the automation's path)

> **Do NOT use `profile=default`** (sidecar mode + istio-ingressgateway) — the tested,
> working setup is ambient. If a sidecar Istio was ever installed on this cluster, it is
> uninstalled first (`istioctl uninstall --purge`).

```bash
# 1a. Gateway API CRDs (STANDARD channel — Gateway + HTTPRoute is all we use).
#     Skip if already present; do not layer the experimental bundle on top.
kubectl get crd gateways.gateway.networking.k8s.io &>/dev/null || \
  kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.1/standard-install.yaml

# 1b. istioctl 1.30
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.30.0 TARGET_ARCH=x86_64 sh -
export PATH=$PWD/istio-1.30.0/bin:$PATH

# 1c. Remove any pre-existing SIDECAR install (safe no-op on a clean cluster)
kubectl -n istio-system get deploy istiod &>/dev/null && istioctl uninstall --purge -y

# 1d. Ambient install. RKE2 is NOT in istioctl's platform list but uses the STANDARD CNI
#     paths (/etc/cni/net.d + /opt/cni/bin) — do NOT pass the k3s/rancher paths or
#     istio-cni-node hangs 0/1 NotReady.
istioctl install --set profile=ambient -y \
  --set values.cni.cniConfDir=/etc/cni/net.d \
  --set values.cni.cniBinDir=/opt/cni/bin

kubectl -n istio-system rollout status deploy/istiod --timeout=180s
kubectl -n istio-system rollout status ds/istio-cni-node --timeout=180s
kubectl -n istio-system rollout status ds/ztunnel --timeout=180s
```

### 1e. TLS secret + the single shared ingress Gateway

```bash
# The gateway TLS secret MUST be in istio-system (Gateway API reads certificateRefs from the
# Gateway's OWN namespace). Use your wildcard/multi-SAN PEM, or let cert-manager issue it
# (section 2 + the 'Certificate — Kubernetes' workload with empty PEM fields).
kubectl -n istio-system create secret tls wso2-ingress-cert \
  --cert=server.crt --key=server.key --dry-run=client -o yaml | kubectl apply -f -

# ONE shared Gateway for the whole cluster — the ambient equivalent of a single Ingress
# controller. One catch-all HTTPS listener serves ALL hosts with this one cert.
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata: { name: shared-gateway, namespace: istio-system }
spec:
  gatewayClassName: istio
  listeners:
    - name: https
      port: 443
      protocol: HTTPS
      allowedRoutes: { namespaces: { from: All } }
      tls:
        mode: Terminate
        certificateRefs:
          - { group: "", kind: Secret, name: wso2-ingress-cert, namespace: istio-system }
EOF
```

### Verify

```bash
kubectl get pods -n istio-system                       # istiod, istio-cni-node, ztunnel
kubectl get svc  -n istio-system shared-gateway-istio  # EXTERNAL-IP from MetalLB = THE ingress IP
kubectl get gateway -n istio-system shared-gateway     # PROGRAMMED=True
```

Point **all** DNS hosts (WSO2, ArgoCD, Headlamp, …) at that single EXTERNAL-IP.

> **Bundled ingress:** RKE2 v1.36 bundles Traefik as the default ingress. We disable it in the
> RKE2 server `config.yaml` (`disable: [rke2-ingress-nginx, rke2-traefik]`) so it does not
> contend for 80/443. The Ansible playbook does this by default.

---

## 2. Install cert-manager (+ internal CA)

The automation (`k8s_addons.yml`, component `certmanager`) installs cert-manager and a
self-signed **internal root CA** with a `ca-issuer` ClusterIssuer, so the *Certificate —
Kubernetes* workload can auto-issue + auto-renew TLS secrets when no PEM is pasted:

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml
kubectl -n cert-manager rollout status deploy/cert-manager deploy/cert-manager-webhook deploy/cert-manager-cainjector

cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata: { name: selfsigned-bootstrap }
spec: { selfSigned: {} }
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata: { name: internal-ca, namespace: cert-manager }
spec:
  isCA: true
  commonName: autoprovision-internal-ca
  secretName: internal-ca-secret
  duration: 87600h
  renewBefore: 8760h
  privateKey: { algorithm: ECDSA, size: 256 }
  issuerRef: { name: selfsigned-bootstrap, kind: ClusterIssuer, group: cert-manager.io }
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata: { name: ca-issuer }
spec:
  ca: { secretName: internal-ca-secret }
EOF
```

Trust the CA once by importing `ca.crt` from secret `internal-ca-secret` (ns `cert-manager`)
into your browsers/clients.

---

## 3. Install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl get pods -n argocd

# Initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo

# TLS terminates at the shared gateway → run argocd-server in insecure (plain HTTP) mode
kubectl patch configmap argocd-cmd-params-cm -n argocd \
  --type merge -p '{"data":{"server.insecure":"true"}}'
kubectl rollout restart deployment argocd-server -n argocd
```

### Expose ArgoCD via the shared gateway (HTTPRoute — no per-app Gateway, no extra IP)

```bash
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: { name: argocd, namespace: argocd }
spec:
  parentRefs: [ { name: shared-gateway, namespace: istio-system, sectionName: https } ]
  hostnames: [ "argocd.<env>.local" ]
  rules:
    - matches: [ { path: { type: PathPrefix, value: / } } ]
      backendRefs: [ { group: "", kind: Service, name: argocd-server, port: 80 } ]
EOF
```

---

## 4. Install Headlamp

```bash
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/
helm repo update
helm install headlamp headlamp/headlamp --namespace kube-system

# Login token
kubectl create token headlamp --namespace kube-system
```

(The automation skips Headlamp gracefully when the chart repo is blocked by a firewall.)

### Expose Headlamp via the shared gateway

```bash
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: { name: headlamp, namespace: kube-system }
spec:
  parentRefs: [ { name: shared-gateway, namespace: istio-system, sectionName: https } ]
  hostnames: [ "headlamp.<env>.local" ]
  rules:
    - matches: [ { path: { type: PathPrefix, value: / } } ]
      backendRefs: [ { group: "", kind: Service, name: headlamp, port: 80 } ]
EOF
```

Add the **shared gateway** external IP to `/etc/hosts` or DNS (same IP for every host):

```bash
GATEWAY_IP=$(kubectl -n istio-system get svc shared-gateway-istio -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "$GATEWAY_IP  argocd.<env>.local headlamp.<env>.local" | sudo tee -a /etc/hosts
```

---

## 5. Install OpenTelemetry Collector

```bash
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install otel-collector open-telemetry/opentelemetry-collector \
  -n observability --set mode=deployment
```

Configure exporters to the matching ELK stack (see old observability/retention docs).

---

## 6. WSO2 APIM + IS — use the team's WSO2_APIM_KUBE_ISTIO repo

WSO2 is deployed with the team's repo (Control Plane, Internal/External Gateway, Identity
Server manifests + the shared Gateway, certificate scripts, and MSSQL schemas).
**The web UI's WSO2 cards run [ansible/k8s_wso2.yml](../../ansible/k8s/wso2.yml)**, which renders
the repo with your hostnames/MSSQL address and applies it. Manual equivalent:

Repo: [WSO2_APIM_KUBE_ISTIO/README.md](../../WSO2_APIM_KUBE_ISTIO/README.md)

```bash
cd WSO2_APIM_KUBE_ISTIO

# 1. Istio ambient is already installed above (NO sidecars, NO ingressgateway).

# 2. Namespaces + AMBIENT mesh enrollment (NOT istio-injection — that is sidecar mode)
kubectl create ns wso2-cp; kubectl create ns wso2-is
kubectl create ns wso2-internal-gw; kubectl create ns wso2-external-gw
for ns in wso2-cp wso2-is wso2-internal-gw wso2-external-gw; do
  kubectl label ns $ns istio.io/dataplane-mode=ambient --overwrite
done

# 3. Generate local certs (or pass your domain: ./scripts/generate-local-certificates.sh example.com)
./scripts/generate-local-certificates.sh

# 4. Ingress TLS secret in istio-system. The Gateway API gateway reloads it via SDS —
#    NO restart needed (there is no istio-ingressgateway deployment to restart).
kubectl -n istio-system create secret tls wso2-ingress-cert \
  --cert=certificates/server.crt --key=certificates/server.key \
  --dry-run=client -o yaml | kubectl apply -f -

# 5. (Optional) build custom APIM images with the MSSQL JDBC driver baked in
#    ./scripts/build-apim-images.sh     # skip if images are already in the registry

# 6. Apply the shared Gateway (idempotent if section 1e already created it), then components
kubectl apply -f istio-gateway.yaml
kubectl apply -f control-plane/
kubectl apply -f internal-gw/
kubectl apply -f external-gw/
kubectl apply -f wso2-is/
```

### Database wiring (read-scale AG)

Load the repo's MSSQL schemas (`mssql/shared_mssql.sql`, `mssql/apim_mssql.sql`) into the
database, and point the WSO2 JDBC config at the SQL Server:

- **Production:** the read-scale AG (`CLUSTER_TYPE = NONE`) has **no virtual listener** — point
  WSO2 at the **AG primary node** and load the schemas there. With the Pacemaker-managed VIP
  (HA AG path, `CLUSTER_TYPE = EXTERNAL`), point at the **listener/VIP** instead — see the
  [ansible/mssql_ag.yml](../../ansible/db/mssql_ag.yml) checklist.
- **UAT:** point WSO2 at the single MSSQL instance.

DB notes and the host/route summary: [planning/wso2-rke2.md](../../docs/planning/wso2-rke2.md).

---

## 7. Final checks

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get svc -n istio-system shared-gateway-istio    # the ONE ingress IP
kubectl get gateway,httproute -A                        # Gateway API objects (not VirtualService)
istioctl ztunnel-config workloads | head                # ambient-enrolled workloads
kubectl get applications -n argocd
kubectl get pods -n wso2-cp; kubectl get pods -n wso2-is
```
