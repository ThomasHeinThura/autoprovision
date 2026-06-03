# RKE2 In-Cluster Add-ons — Istio + cert-manager + ArgoCD + Headlamp + WSO2

Shared runbook referenced by both
[prod-rke2-installation.md](prod-rke2-installation.md) and
[uat-rke2-installation.md](uat-rke2-installation.md).

This is the **new-requirement** replacement for the Cilium/Envoy parts of the old
[talos-cluster/](../talos-cluster/) guides. The ArgoCD and Headlamp steps are taken from those
guides; only the CNI and ingress layers change.

> **Prerequisite:** the RKE2 cluster is already installed by Ansible
> (`ansible/rke2_cluster.yml`) and all nodes are `Ready`. RKE2 ships the **default CNI (Canal)**
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

## 1. Install Istio (ingress replaces Envoy Gateway)

Two supported paths — pick one. Helm is preferred for repeatability.

### Option A — Helm (recommended)

```bash
helm repo add istio https://istio-release.storage.googleapis.com/charts
helm repo update

kubectl create namespace istio-system --dry-run=client -o yaml | kubectl apply -f -

# Istio base CRDs
helm upgrade --install istio-base istio/base \
  -n istio-system --set defaultRevision=default --version 1.30.0

# istiod control plane
helm upgrade --install istiod istio/istiod \
  -n istio-system --wait --version 1.30.0

# Ingress gateway (LoadBalancer service)
kubectl create namespace istio-ingress --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install istio-ingressgateway istio/gateway \
  -n istio-ingress --version 1.30.0
```

### Option B — istioctl

```bash
istioctl install --set profile=default -y
kubectl label namespace istio-ingress istio-injection=enabled --overwrite 2>/dev/null || true
```

### Verify

```bash
kubectl get pods -n istio-system
kubectl get svc -n istio-ingress istio-ingressgateway
# EXTERNAL-IP should populate from RKE2 ServiceLB / your LB / MetalLB
```

> **External IP / LoadBalancer:** RKE2 enables ServiceLB (Klipper) by default, which can expose
> the ingress gateway on the node IPs. For a dedicated LB IP on the LAN, install MetalLB or use
> the customer load balancer. Production should use a stable VIP for the ingress gateway.
>
> **Bundled ingress:** RKE2 v1.36 bundles Traefik as the default ingress. We disable it in the
> RKE2 server `config.yaml` (`disable: [rke2-ingress-nginx, rke2-traefik]`) so it does not contend
> with the Istio ingress gateway for node ports 80/443. The Ansible playbook does this by default.

> **WSO2 repo requirement — use the istioctl default profile (Option B):** the team's
> [WSO2_APIM_KUBE_ISTIO](../WSO2_APIM_KUBE_ISTIO/README.md) repo expects the ingress gateway pod
> **and** the TLS secret `wso2-ingress-cert` to live in the **`istio-system`** namespace. The
> `istioctl install --set profile=default` path puts `istio-ingressgateway` in `istio-system`, so
> prefer **Option B with Istio 1.30** for any cluster that will run WSO2:
>
> ```bash
> curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.30.0 TARGET_ARCH=x86_64 sh -
> export PATH=$PWD/istio-1.30.0/bin:$PATH
> istioctl install --set profile=default -y
> ```

---

## 2. Install cert-manager

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update
kubectl create namespace cert-manager --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager --version v1.20.2 --set crds.enabled=true
kubectl get pods -n cert-manager
```

Why: TLS for ArgoCD, Headlamp, and WSO2 ingress via Istio.

---

## 3. Install ArgoCD (from the old Talos guide, unchanged)

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl get pods -n argocd

# Initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

ArgoCD often needs insecure server mode behind a TLS-terminating gateway:

```bash
kubectl patch configmap argocd-cmd-params-cm -n argocd \
  --type merge -p '{"data":{"server.insecure":"true"}}'
kubectl rollout restart deployment argocd-server -n argocd
```

### Expose ArgoCD via Istio

```bash
cat <<EOF | kubectl apply -f -
apiVersion: networking.istio.io/v1
kind: Gateway
metadata:
  name: argocd-gateway
  namespace: argocd
spec:
  selector:
    istio: ingressgateway
  servers:
    - port: { number: 80, name: http, protocol: HTTP }
      hosts: ["argocd.<env>.local"]
---
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: argocd
  namespace: argocd
spec:
  hosts: ["argocd.<env>.local"]
  gateways: ["argocd-gateway"]
  http:
    - route:
        - destination:
            host: argocd-server
            port: { number: 80 }
EOF
```

---

## 4. Install Headlamp (from the old Talos guide, unchanged)

```bash
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/
helm repo update
helm install headlamp headlamp/headlamp --namespace kube-system

# Login token
kubectl create token headlamp --namespace kube-system
```

### Expose Headlamp via Istio

```bash
cat <<EOF | kubectl apply -f -
apiVersion: networking.istio.io/v1
kind: Gateway
metadata:
  name: headlamp-gateway
  namespace: kube-system
spec:
  selector:
    istio: ingressgateway
  servers:
    - port: { number: 80, name: http, protocol: HTTP }
      hosts: ["headlamp.<env>.local"]
---
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: headlamp
  namespace: kube-system
spec:
  hosts: ["headlamp.<env>.local"]
  gateways: ["headlamp-gateway"]
  http:
    - route:
        - destination:
            host: headlamp
            port: { number: 80 }
EOF
```

Add the ingress-gateway external IP to `/etc/hosts` or DNS:

```bash
echo "<INGRESS_IP>  argocd.<env>.local headlamp.<env>.local" | sudo tee -a /etc/hosts
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

WSO2 is deployed with the team's repo, which contains the Control Plane, Internal/External
Gateway, and Identity Server manifests plus the Istio Gateway, certificate scripts, and MSSQL
schemas. **Follow its README — do not hand-roll WSO2 manifests.**

Repo: [WSO2_APIM_KUBE_ISTIO/README.md](../WSO2_APIM_KUBE_ISTIO/README.md)

Summary of her steps (run from the repo directory, with `KUBECONFIG` set to this cluster):

```bash
cd WSO2_APIM_KUBE_ISTIO

# 1. Istio is already installed above (istioctl default profile, 1.30, ingressgateway in istio-system).

# 2. Namespaces + sidecar injection
kubectl create ns wso2-cp; kubectl create ns wso2-is
kubectl create ns wso2-internal-gw; kubectl create ns wso2-external-gw
for ns in wso2-cp wso2-is wso2-internal-gw wso2-external-gw; do
  kubectl label ns $ns istio-injection=enabled --overwrite
done

# 3. Generate local certs (or pass your domain: ./scripts/generate-local-certificates.sh example.com)
./scripts/generate-local-certificates.sh

# 4. Istio ingress TLS secret in istio-system, then restart the gateway
kubectl -n istio-system create secret tls wso2-ingress-cert \
  --cert=certificates/server.crt --key=certificates/server.key \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n istio-system rollout restart deploy/istio-ingressgateway
kubectl -n istio-system rollout status  deploy/istio-ingressgateway

# 5. (Optional) build custom APIM images with the MSSQL JDBC driver baked in
#    ./scripts/build-apim-images.sh     # skip if images are already in the registry

# 6. Apply the shared Istio Gateway, then deploy components in order
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
  WSO2 at the **AG primary node** and load the schemas there. (A Pacemaker-managed listener is a
  later HA upgrade — see [ansible/mssql_ag.yml](../ansible/mssql_ag.yml) checklist.)
- **UAT:** point WSO2 at the single MSSQL instance.

DB notes and the Istio host/route summary: [planning/news/wso2-rke2.md](../planning/news/wso2-rke2.md).

---

## 7. Final checks

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get svc -n istio-system istio-ingressgateway
kubectl get gateway,virtualservice -A
kubectl get applications -n argocd
kubectl get pods -n wso2-cp; kubectl get pods -n wso2-is
```
