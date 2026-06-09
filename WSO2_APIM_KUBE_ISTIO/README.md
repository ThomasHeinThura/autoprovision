# WSO2 API Manager with Istio Ambient on Kubernetes (MsSQL)

This repository contains Kubernetes deployment configurations for WSO2 API Manager integrated with **Istio in ambient mode**. Ingress is handled by the **Kubernetes Gateway API** (`gatewayClassName: istio`); there is **no `istio-ingressgateway`** and **no sidecars** — workload namespaces join the mesh via the `istio.io/dataplane-mode=ambient` label (ztunnel provides L4 mTLS).

> In this lab these steps are normally run for you by the Ansible playbooks
> [`ansible/k8s_addons.yml`](../ansible/k8s_addons.yml) (`component=istio`) and
> [`ansible/k8s_wso2.yml`](../ansible/k8s_wso2.yml). The manual steps below are the equivalent.

## Prerequisites

- Kubernetes cluster (1.20 or higher)
- kubectl CLI
- Docker CLI (for building custom images)
- Istio 1.26.0 or higher (ambient profile)
- Kubernetes Gateway API CRDs (experimental channel)
- openssl (for certificate generation)

## Architecture Overview

The deployment consists of:

- **WSO2 API Manager Control Plane** - Manages APIs, applications, and subscriptions
- **WSO2 API Manager Gateway** - Handles API traffic and security enforcement
- **WSO2 Identity Server** - Provides identity and access management
- **Istio ambient mesh** - ztunnel mTLS for pod-to-pod traffic, no sidecars
- **Kubernetes Gateway API** - North-south ingress (`Gateway` + per-component `HTTPRoute`)
- **Microsoft SQL Server** - Database backend for WSO2 API Manager

Each component directory ships a `gateway.yaml` = an `HTTPRoute` (attaches to the shared
`wso2-gateway` by host) plus a `DestinationRule` that re-originates TLS to the backend HTTPS port
(CP/IS `9443`, gateways `8243`, `insecureSkipVerify` for WSO2's self-signed certs). The control
plane's `DestinationRule` also pins a `consistentHash` `SERVERID` cookie for session affinity across
the two CP replicas.

## Quick Start

### 1. Install the Gateway API CRDs and Istio (ambient)

```bash
# Gateway API CRDs (experimental channel — required for gatewayClassName: istio)
kubectl get crd gateways.gateway.networking.k8s.io &> /dev/null || \
  kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.5.1/experimental-install.yaml

curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.26.0 TARGET_ARCH=x86_64 sh -
export PATH=$PWD/istio-1.26.0/bin:$PATH

# If a previous SIDECAR install exists, remove it first:
istioctl uninstall --purge -y

istioctl install --set profile=ambient -y
```

### 2. Create WSO2 namespaces and enroll them in the ambient mesh

```bash
for ns in wso2-cp wso2-is wso2-internal-gw wso2-external-gw; do
  kubectl create ns $ns
  kubectl label ns $ns istio-injection-                       # drop any old sidecar label
  kubectl label ns $ns istio.io/dataplane-mode=ambient --overwrite
done
```

### 3. Generate local certificates

```bash
./scripts/generate-local-certificates.sh
```

This creates:
- certificates/server.crt
- certificates/server.key

### 4. Create the ingress TLS Secret (consumed by the Gateway API Gateway)

```bash
kubectl -n istio-system create secret tls wso2-ingress-cert \
  --cert=certificates/server.crt \
  --key=certificates/server.key \
  --dry-run=client -o yaml | kubectl apply -f -
```

No gateway restart is needed — the Gateway API `Gateway` picks the secret up automatically.

### 5. Build APIM Images (Optional)

If pre-built images are already pushed to Docker Hub, this step can be skipped. Otherwise, build images with MsSQL JDBC included:

```bash
./scripts/build-apim-images.sh
```

Note: The script automatically downloads the MsSQL JDBC driver and includes it in the images.

### 7. Deploy the ingress Gateway and WSO2 Components

```bash
# Shared Gateway API Gateway (provisions svc wso2-gateway-istio in istio-system, MetalLB EXTERNAL-IP)
kubectl apply -f istio-gateway.yaml

# Deploy Control Plane (HTTPRoute + DestinationRule live in control-plane/gateway.yaml)
kubectl apply -f control-plane/

# Deploy Internal Gateway
kubectl apply -f internal-gw/

# Deploy External Gateway
kubectl apply -f external-gw/

# Deploy WSO2 IS (Identity Server)
kubectl apply -f wso2-is/
```

Point DNS / `/etc/hosts` for `apim.example.com`, `internal-gw.example.com`,
`external-gw.example.com`, `wso2is.example.com` at the ingress IP:

```bash
kubectl -n istio-system get svc wso2-gateway-istio   # EXTERNAL-IP from MetalLB
```

## Customization

### Database Configuration

This deployment uses Microsoft SQL Server as the backend database. The database schemas are located in the `mssql/` directory:
- `mssql/shared_mssql.sql` - Shared database schema
- `mssql/apim_mssql.sql` - APIM specific database schema

## Configuration Files

The repository is organized as follows:
- `istio-gateway.yaml` - Shared Gateway API `Gateway` (ambient ingress, TLS termination)
- `control-plane/` - Control Plane deployment + `gateway.yaml` (HTTPRoute + DestinationRule)
- `external-gw/` - External Gateway deployment + `gateway.yaml` (HTTPRoute + DestinationRule)
- `internal-gw/` - Internal Gateway deployment + `gateway.yaml` (HTTPRoute + DestinationRule)
- `wso2-is/` - WSO2 Identity Server deployment + `gateway.yaml` (HTTPRoute + DestinationRule)
- `images/` - Custom Docker images with MsSQL driver
- `mssql/` - MsSQL database schema files
- `scripts/` - Helper scripts for certificate generation and image building

## Troubleshooting

### Common Issues

1. **Certificate Issues**: If you encounter certificate errors, regenerate the certificates using:
   ```bash
   ./scripts/generate-local-certificates.sh example.com
   ```

2. **Image Pull Errors**: If the images are not available, build them locally:
   ```bash
   ./scripts/build-apim-images.sh
   ```
