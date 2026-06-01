# Production Talos / Kubernetes Setup Guide

## Scope

Use this guide for the production topology: 3 Talos control-plane nodes and 5 Talos worker nodes.

## App or manual?

Recommended path: use the Python web UI as the operator console, then let it trigger the same Talos and Helm automation that this guide describes.

Use the app when you want:

1. One place to capture environment values.
2. Re-runnable actions with logs.
3. The same input flow for lab, UAT, and production.

Use manual commands when you want:

1. Full control over each step.
2. Easier recovery during a failure.
3. An auditable runbook you can follow line by line.

The commands below are the manual version. Each step includes why it exists.

## Production differences from lab

1. Do not enable `allowSchedulingOnControlPlanes`.
2. Prefer a control-plane VIP or load balancer endpoint if you have one.
3. Keep Cilium Gateway API disabled when Envoy Gateway owns the GatewayClass.
4. Run more than one replica for cluster add-ons that support HA, especially Cilium operator and Envoy Gateway.

## Prerequisites

You need these machines already installed with the Talos ISO and waiting in maintenance mode:

1. 3 control-plane nodes.
2. 5 worker nodes.
3. 1 jump host with `talosctl`, `kubectl`, `helm`, and `cilium` installed.
4. A control-plane VIP or stable API endpoint if available.

## Environment variables

```bash
export CLUSTER_NAME="prod-cluster"
export CONTROL_PLANE1_IP="192.168.64.11"
export CONTROL_PLANE2_IP="192.168.64.12"
export CONTROL_PLANE3_IP="192.168.64.13"
export WORKER1_IP="192.168.64.21"
export WORKER2_IP="192.168.64.22"
export WORKER3_IP="192.168.64.23"
export WORKER4_IP="192.168.64.24"
export WORKER5_IP="192.168.64.25"
export CONTROL_PLANE_ENDPOINT="192.168.64.11"
export DISK_NAME="vda"
export WORK_DIR="$HOME/autoprovision/data/k8s/$CLUSTER_NAME"
export L2_IP_POOL_START="192.168.64.100"
export L2_IP_POOL_END="192.168.64.120"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"
```

Why this matters: production should keep the node list explicit so you can see exactly which IPs were configured and which endpoint was used to bootstrap the cluster.

## Phase 1: verify maintenance mode

Check every node before applying config.

```bash
talosctl get disks --insecure --nodes "$CONTROL_PLANE1_IP"
talosctl get disks --insecure --nodes "$CONTROL_PLANE2_IP"
talosctl get disks --insecure --nodes "$CONTROL_PLANE3_IP"
talosctl get disks --insecure --nodes "$WORKER1_IP"
talosctl get disks --insecure --nodes "$WORKER2_IP"
talosctl get disks --insecure --nodes "$WORKER3_IP"
talosctl get disks --insecure --nodes "$WORKER4_IP"
talosctl get disks --insecure --nodes "$WORKER5_IP"
```

Why: you want the Talos maintenance API to be open before you apply the first machine config. If a node already has old state, wipe it first.

## Phase 2: generate cluster config

Create the production patch that disables the default CNI and kube-proxy.

```bash
cat > "$WORK_DIR/cluster-patch.yaml" <<'EOF'
cluster:
  network:
    cni:
      name: none
  proxy:
    disabled: true
EOF
```

Why: Cilium will replace the default CNI, and kube-proxy is not needed when Cilium handles service routing.

Generate secrets once.

```bash
talosctl gen secrets -o "$WORK_DIR/secrets.yaml"
```

Why: the Talos PKI must stay stable. Regenerating secrets later will break already-configured nodes.

Generate the Talos configs from the first control-plane endpoint or your VIP.

```bash
talosctl gen config "$CLUSTER_NAME" "https://$CONTROL_PLANE_ENDPOINT:6443" \
  --with-secrets "$WORK_DIR/secrets.yaml" \
  --install-disk "/dev/$DISK_NAME" \
  --config-patch @"$WORK_DIR/cluster-patch.yaml" \
  --force
```

Why: this creates the control-plane and worker machine configs that all nodes will use.

Set the Talos config context to the production endpoints.

```bash
export TALOSCONFIG="$WORK_DIR/talosconfig"
talosctl config endpoint "$CONTROL_PLANE1_IP" "$CONTROL_PLANE2_IP" "$CONTROL_PLANE3_IP" --talosconfig "$WORK_DIR/talosconfig"
talosctl config node "$CONTROL_PLANE1_IP" --talosconfig "$WORK_DIR/talosconfig"
```

Why: the endpoint list gives you HA access to the Talos API after the cluster is up.

## Phase 3: apply configs

Apply the control-plane config to all 3 control-plane nodes.

```bash
talosctl apply-config --insecure --nodes "$CONTROL_PLANE1_IP" --file "$WORK_DIR/controlplane.yaml"
talosctl apply-config --insecure --nodes "$CONTROL_PLANE2_IP" --file "$WORK_DIR/controlplane.yaml"
talosctl apply-config --insecure --nodes "$CONTROL_PLANE3_IP" --file "$WORK_DIR/controlplane.yaml"
```

Why: each control-plane node needs the same machine config so it can join the etcd quorum.

Apply the worker config to all 5 worker nodes.

```bash
talosctl apply-config --insecure --nodes "$WORKER1_IP" --file "$WORK_DIR/worker.yaml"
talosctl apply-config --insecure --nodes "$WORKER2_IP" --file "$WORK_DIR/worker.yaml"
talosctl apply-config --insecure --nodes "$WORKER3_IP" --file "$WORK_DIR/worker.yaml"
talosctl apply-config --insecure --nodes "$WORKER4_IP" --file "$WORK_DIR/worker.yaml"
talosctl apply-config --insecure --nodes "$WORKER5_IP" --file "$WORK_DIR/worker.yaml"
```

Why: workers need the same config so they can join the cluster and receive workloads.

## Phase 4: bootstrap etcd

Run bootstrap exactly once on the first control-plane node.

```bash
talosctl bootstrap \
  --talosconfig "$WORK_DIR/talosconfig" \
  --endpoints "$CONTROL_PLANE1_IP" \
  --nodes "$CONTROL_PLANE1_IP"
```

Why: this initializes the etcd quorum. Running it more than once can corrupt the cluster.

Wait for health.

```bash
talosctl health \
  --talosconfig "$WORK_DIR/talosconfig" \
  --endpoints "$CONTROL_PLANE1_IP" \
  --nodes "$CONTROL_PLANE1_IP"
```

Why: this confirms Talos and etcd are stable before you move to Kubernetes installs.

## Phase 5: get kubeconfig

```bash
talosctl kubeconfig "$WORK_DIR/kubeconfig" \
  --talosconfig "$WORK_DIR/talosconfig" \
  --endpoints "$CONTROL_PLANE1_IP" \
  --nodes "$CONTROL_PLANE1_IP"

export KUBECONFIG="$WORK_DIR/kubeconfig"
kubectl get nodes -o wide
```

Why: kubeconfig gives you Kubernetes API access, and the node list confirms the cluster is visible.

## Phase 6: install Gateway API CRDs

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gatewayclasses.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_gateways.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_httproutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_referencegrants.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/standard/gateway.networking.k8s.io_grpcroutes.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.0/config/crd/experimental/gateway.networking.k8s.io_tlsroutes.yaml
```

Why: Envoy Gateway needs the Gateway API resources before it can create Gateways and HTTPRoutes.

## Phase 7: install Cilium

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
  --helm-set=operator.replicas=2

cilium status --wait
kubectl get nodes -o wide
```

Why: Cilium provides the CNI, service handling, and L2 announcements. Gateway API stays off here because Envoy Gateway owns the GatewayClass.

## Phase 8: configure the L2 IP pool

```bash
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

cat <<EOF | kubectl apply -f -
apiVersion: "cilium.io/v2alpha1"
kind: CiliumL2AnnouncementPolicy
metadata:
  name: "l2-policy"
spec:
  interfaces:
    - ^e.*
  externalIPs: true
  loadBalancerIPs: true
EOF
```

Why: this gives LoadBalancer services a LAN IP so users can reach exposed apps without a cloud load balancer.

## Phase 9: install cert-manager

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update
kubectl create namespace cert-manager --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install cert-manager jetstack/cert-manager --namespace cert-manager --set crds.enabled=true
```

Why: Envoy Gateway, ArgoCD, and any TLS-backed app workflows need certificate management in production.

## Phase 10: install Envoy Gateway

```bash
helm install eg oci://docker.io/envoyproxy/gateway-helm \
  --version v1.8.0 \
  -n envoy-gateway-system \
  --create-namespace \
  --set config.envoyGateway.extensionApis.enableBackend=true \
  --set deployment.replicas=2

kubectl rollout status deployment/envoy-gateway -n envoy-gateway-system
```

Why: Envoy Gateway owns the GatewayClass and the production ingress layer.

Create the GatewayClass and Gateway.

```bash
cat <<EOF | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: envoy
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
EOF

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
```

Why: the Gateway object is what receives the external IP from Cilium and fronts your routes.

## Phase 11: install ArgoCD

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl get pods -n argocd
```

Why: ArgoCD is the GitOps controller for the Kubernetes workloads stored in GitLab.

## Phase 12: install Headlamp

```bash
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/
helm repo update
helm install headlamp headlamp/headlamp --namespace kube-system
kubectl create token headlamp --namespace kube-system
```

Why: Headlamp gives you a cluster UI for operations and quick inspection.

## Phase 13: expose apps

Create HTTPRoutes for ArgoCD and Headlamp. Replace the hostnames with your production DNS names.

Why: routing through Envoy Gateway gives you a stable ingress path with TLS termination.

## Final checks

```bash
talosctl --talosconfig "$WORK_DIR/talosconfig" --endpoints "$CONTROL_PLANE1_IP" "$CONTROL_PLANE2_IP" "$CONTROL_PLANE3_IP" --nodes "$CONTROL_PLANE1_IP" "$CONTROL_PLANE2_IP" "$CONTROL_PLANE3_IP" get members
kubectl get nodes -o wide
kubectl get pods -A
cilium status
kubectl get ciliumloadbalancerippool
kubectl get ciliuml2announcementpolicy
kubectl get gateway,svc -n envoy-gateway-system
```

Why: these checks tell you whether the control plane, workers, CNI, and ingress layer are healthy before you hand the cluster over.

## Recommended operator flow

1. Use the app to enter the production IPs, domains, and cluster name.
2. Trigger the Talos cluster action from the app, or run the same commands manually if you want explicit control.
3. Trigger the platform install action for cert-manager, Envoy Gateway, ArgoCD, and Headlamp.
4. Keep the lab guide only for rehearsal and troubleshooting.
