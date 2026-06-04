# WSO2 API Manager with Istio on Kubernetes

This repository contains Kubernetes deployment configurations for WSO2 API Manager integrated with Istio service mesh. The setup includes deployment manifests for WSO2 API Manager Control Plane and Gateway components, along with Istio configurations for traffic management and security.

## Prerequisites

- Kubernetes cluster (1.20 or higher)
- kubectl CLI
- Docker CLI (for building custom images)
- Istio 1.26.0 or higher
- openssl (for certificate generation)

## Architecture Overview

The deployment consists of:

- **WSO2 API Manager Control Plane** - Manages APIs, applications, and subscriptions
- **WSO2 API Manager Gateway** - Handles API traffic and security enforcement
- **WSO2 Identity Server** - Provides identity and access management
- **Istio Service Mesh** - Provides traffic management, security, and observability
- **Microsoft SQL Server** - Database backend for WSO2 API Manager

## Quick Start

### 1. Install Istio

Download and install Istio:

```bash
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.26.0 TARGET_ARCH=x86_64 sh -
export PATH=$PWD/istio-1.26.0//bin:$PATH
```

The installation directory contains:
- Sample applications in samples/
- The istioctl client binary in the bin/ directory.

### 2. Create WSO2 namespaces and enable Istio sidecar injection

```bash
kubectl create ns wso2-cp 
kubectl create ns wso2-is 
kubectl create ns wso2-internal-gw 
kubectl create ns wso2-external-gw
kubectl label ns wso2-cp istio-injection=enabled --overwrite
kubectl label ns wso2-is istio-injection=enabled --overwrite
kubectl label ns wso2-internal-gw istio-injection=enabled --overwrite
kubectl label ns wso2-external-gw istio-injection=enabled --overwrite
```

This ensures Istio sidecars are automatically injected into APIM pods.

### 3. Generate local certificates

```bash
./scripts/generate-local-certificates.sh
```

This creates:
- certificates/server.crt
- certificates/server.key

### 4. Create Istio Ingress Gateway TLS Secret

Create the Istio ingress TLS secret in istio-system namespace:

```bash
kubectl -n istio-system create secret tls wso2-ingress-cert \
  --cert=certificates/server.crt \
  --key=certificates/server.key \
  --dry-run=client -o yaml | kubectl apply -f -
```

Restart the Istio ingress gateway to apply the secret:

```bash
kubectl -n istio-system rollout restart deploy/istio-ingressgateway
kubectl -n istio-system rollout status deploy/istio-ingressgateway
```

### 5. Build APIM Images (Optional)

If pre-built images are already pushed to Docker Hub, this step can be skipped. Otherwise, build images with MsSQL JDBC included:

```bash
./scripts/build-apim-images.sh
```

Note: The script automatically downloads the MsSQL JDBC driver and includes it in the images.

### 7. Deploy WSO2 Components

Deploy each component in order:

```bash
# Deploy Control Plane
kubectl apply -f control-plane/

# Deploy Internal Gateway
kubectl apply -f internal-gw/

# Deploy External Gateway
kubectl apply -f external-gw/

# Deploy WSO2 IS (Identity Server)
kubectl apply -f wso2-is/
```

## Customization

### Database Configuration

This deployment uses Microsoft SQL Server as the backend database. The database schemas are located in the `mssql/` directory:
- `mssql/shared_mssql.sql` - Shared database schema
- `mssql/apim_mssql.sql` - APIM specific database schema

## Configuration Files

The repository is organized as follows:
- `control-plane/` - Control Plane deployment configurations
- `external-gw/` - External Gateway deployment configurations
- `internal-gw/` - Internal Gateway deployment configurations
- `images/` - Custom Docker images with MsSQL driver
- `mssql/` - MsSQL database schema files
- `scripts/` - Helper scripts for certificate generation and image building
- `wso2-is/` - WSO2 Identity Server configurations

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
