# WSO2 on RKE2 + Istio (New)

> **Authoritative install: the team's repo.** WSO2 (APIM Control Plane, Internal/External
> Gateways, Identity Server), the Istio `Gateway`, the certificate scripts, the custom images
> (MSSQL JDBC baked in), and the MSSQL schemas all live in
> [WSO2_APIM_KUBE_ISTIO](../../WSO2_APIM_KUBE_ISTIO/README.md). **Follow her README** —
> summarized in the add-ons runbook section 6:
> [rke2-cluster/rke2-addons-istio-argocd-headlamp.md](../../rke2-cluster/rke2-addons-istio-argocd-headlamp.md).
> This file only records the design context and DB wiring; it does not replace her steps.

This document updates the ingress/exposure + database layer of
[planning/old/wso2_apim.md](../old/wso2_apim.md). Other WSO2 design decisions — custom image,
MSSQL JDBC 13.4.0, log4j2 config, Elastic Agent sidecar, key migration — are **unchanged**.

## What changed

| Aspect | Old (Envoy Gateway) | New (Istio, team's repo) |
| ------ | ------------------- | ----------- |
| Ingress controller | Envoy Gateway | Istio ingress gateway (in `istio-system`) |
| Route resource | Gateway API `HTTPRoute` / `TLSRoute` | Istio `Gateway` + `VirtualService` (in the repo) |
| TLS termination | Envoy Gateway `Gateway` listener | Istio `Gateway` `tls` → secret `wso2-ingress-cert` in `istio-system` |
| Deploy mechanism | ArgoCD GitOps (planned) | `kubectl apply -f` from `WSO2_APIM_KUBE_ISTIO` (her steps) |
| Database | External SQL Server | **MSSQL VMs installed by Ansible** — Prod read-scale AG primary, UAT single instance |

## Database connection

The new requirement uses a **read-scale Availability Group** (`CLUSTER_TYPE = NONE`) in
production, which has **no virtual listener**. So:

- **Production:** point WSO2 APIM/IS JDBC URLs at the **AG primary node**, e.g.
  `jdbc:sqlserver://<ag-primary-ip>:1433;databaseName=...`. Load the repo's `mssql/*.sql` schemas
  on the primary. (When a Pacemaker-managed listener is later added — see the
  [mssql_ag.yml](../../ansible/mssql_ag.yml) checklist — switch the URL to the listener name.)
- **UAT:** point at the single MSSQL instance.
- JDBC driver remains `mssql-jdbc-13.4.0.jre11.jar`, baked into the custom image (the repo's
  `build-apim-images.sh` downloads and includes it).

## Istio hosts (from the repo's istio-gateway.yaml)

The repo's shared `Gateway` (in `istio-system`, TLS secret `wso2-ingress-cert`) serves these
hosts on 443 — set DNS / `/etc/hosts` to the Istio ingress gateway external IP:

- `apim.example.com` (Control Plane / Publisher / DevPortal)
- `internal-gw.example.com`
- `external-gw.example.com`
- `wso2is.example.com` (Identity Server)

The reference manifests below are kept for design context; the **repo's** `Gateway`/`VirtualService`
are what you actually apply.

## Exposing WSO2 via Istio

Replace the Envoy `HTTPRoute` examples in the old doc with an Istio `Gateway` + `VirtualService`.

### Gateway (shared, in the istio-ingress namespace)

```yaml
apiVersion: networking.istio.io/v1
kind: Gateway
metadata:
  name: wso2-gateway
  namespace: wso2
spec:
  selector:
    istio: ingressgateway        # matches the Istio ingress gateway pods
  servers:
    - port:
        number: 443
        name: https
        protocol: HTTPS
      tls:
        mode: SIMPLE
        credentialName: wso2-tls   # k8s TLS secret (cert-manager or provided)
      hosts:
        - "apim.example.com"
        - "is.example.com"
```

### VirtualService — APIM

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: wso2-apim
  namespace: wso2
spec:
  hosts:
    - "apim.example.com"
  gateways:
    - wso2-gateway
  http:
    - route:
        - destination:
            host: wso2am-service     # APIM Service in ns wso2
            port:
              number: 9443
```

### VirtualService — Identity Server

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: wso2-is
  namespace: wso2
spec:
  hosts:
    - "is.example.com"
  gateways:
    - wso2-gateway
  http:
    - route:
        - destination:
            host: wso2is-service
            port:
              number: 9443
```

> WSO2 consoles use HTTPS on 9443. If you terminate TLS at the Istio gateway and re-encrypt to
> the pod, use `tls` passthrough or configure a `DestinationRule` with the right TLS mode. For
> the MVP, SIMPLE termination at the gateway + HTTP/HTTPS to the backend service is acceptable;
> confirm WSO2's expected scheme and adjust the `DestinationRule` accordingly.

## GitOps model (unchanged)

- WSO2 manifests live in GitLab, including the Istio `Gateway`/`VirtualService` (instead of Envoy
  `HTTPRoute`).
- ArgoCD syncs them into the cluster.
- The Python web UI knows the GitLab repo/branch and can update env-specific values (domains,
  JDBC URLs) before commit.

## Sidecar injection note

If the `wso2` namespace has Istio sidecar injection enabled, the Elastic Agent log-shipping
sidecar and WSO2 inter-node clustering traffic both pass through the mesh. For the MVP, either:

- Label the `wso2` namespace **without** automatic injection and expose only via the ingress
  gateway, or
- Enable injection and add `PeerAuthentication`/`DestinationRule` as needed for WSO2 clustering.

Pick one explicitly during lab rehearsal; mixed states cause hard-to-debug clustering issues.
