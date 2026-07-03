# WSO2 on RKE2 + Istio (New)

> **Authoritative install: the team's repo.** WSO2 (APIM Control Plane, Internal/External
> Gateways, Identity Server), the Istio `Gateway`, the certificate scripts, the custom images
> (MSSQL JDBC baked in), and the MSSQL schemas all live in
> [WSO2_APIM_KUBE_ISTIO](../WSO2_APIM_KUBE_ISTIO/README.md). **Follow her README** —
> summarized in the add-ons runbook section 6:
> [rke2-cluster/rke2-addons-istio-argocd-headlamp.md](../rke2-cluster/rke2-addons-istio-argocd-headlamp.md).
> This file only records the design context and DB wiring; it does not replace her steps.

This document records the ingress/exposure + database layer of the WSO2 design (it supersedes
the Envoy-Gateway-era doc, removed in cleanup). Other WSO2 design decisions — custom image,
MSSQL JDBC 13.4.0, log4j2 config, Elastic Agent sidecar, key migration — are **unchanged**.

## What changed

| Aspect | Old (Envoy Gateway) | New (Istio **ambient**, team's repo) |
| ------ | ------------------- | ----------- |
| Ingress controller | Envoy Gateway | **One shared Gateway API `Gateway`** (`shared-gateway` in `istio-system`) reconciled by Istio ambient — no istio-ingressgateway, no sidecars |
| Route resource | Gateway API `HTTPRoute` / `TLSRoute` | Kubernetes Gateway API `HTTPRoute` attached to `shared-gateway` by hostname |
| TLS termination | Envoy Gateway `Gateway` listener | Shared `Gateway` HTTPS listener → `certificateRefs` secret `wso2-ingress-cert` in `istio-system` (must be in the Gateway's own namespace; no sidecar-era `credentialName`) |
| Deploy mechanism | ArgoCD GitOps (planned) | Web UI WSO2 cards (`ansible/k8s_wso2.yml` renders + applies the repo) or `kubectl apply -f` (her steps) |
| Database | External SQL Server | **MSSQL VMs installed by Ansible** — Prod AG (primary or Pacemaker VIP), UAT single instance |

## Database connection

The new requirement uses a **read-scale Availability Group** (`CLUSTER_TYPE = NONE`) in
production, which has **no virtual listener**. So:

- **Production:** point WSO2 APIM/IS JDBC URLs at the **AG primary node** (or the Pacemaker VIP /
  listener when configured), e.g. `jdbc:sqlserver://<ag-primary-ip>:1433;databaseName=...`. Create
  the databases + the application login and load the `mssql/*.sql` schemas with
  [`ansible/mssql_wso2_db.yml`](../ansible/mssql_wso2_db.yml) (UI card **"7b · WSO2 DB user +
  schemas"**) — do **not** just run the raw `.sql` on the primary. That playbook creates the
  `wso2carbon` login on **every** replica with the **same explicit SID**, which is what prevents the
  login from orphaning on failover (see [mssql/README.md](../mssql/README.md) → "WSO2 login on an AG").
- **UAT:** same playbook against the single MSSQL instance (its AG-add phase auto-skips).
- **Credentials are now variables, not hardcoded:** the DB user/password in each `deployment.toml`
  ConfigMap are `<WSO2_DB_USER>` / `<WSO2_DB_PASSWORD>` tokens substituted by
  [k8s_wso2.yml](../ansible/k8s_wso2.yml). They **must match** the login created by `mssql_wso2_db.yml`.
  (The keystore/truststore still use the literal `wso2carbon` — DB and keystore creds are decoupled.)
- JDBC driver remains `mssql-jdbc-13.4.0.jre11.jar`, baked into the custom image (the repo's
  `build-apim-images.sh` downloads and includes it).

## Istio hosts (from the repo's istio-gateway.yaml)

The repo's shared `Gateway` (in `istio-system`, TLS secret `wso2-ingress-cert`) serves these
hosts on 443 — set DNS / `/etc/hosts` to the **one** shared-gateway IP
(`kubectl -n istio-system get svc shared-gateway-istio`):

- `apim.example.com` (Control Plane / Publisher / DevPortal)
- `internal-gw.example.com`
- `external-gw.example.com`
- `wso2is.example.com` (Identity Server)

The reference manifests below are kept for design context; the **repo's**
`istio-gateway.yaml` (shared `Gateway` + `HTTPRoute`s) is what you actually apply.

## Exposing WSO2 via the shared ambient Gateway (Gateway API)

> These reference manifests match the repo's `istio-gateway.yaml` (the file you actually
> apply). Sidecar-era `Gateway` (networking.istio.io) + `VirtualService` with
> `selector: istio: ingressgateway` / `credentialName` are **obsolete on this setup** —
> ambient has no ingressgateway pods to select.

### The single shared Gateway (one per cluster, in istio-system)

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: shared-gateway
  namespace: istio-system          # the TLS secret MUST live in this same namespace
spec:
  gatewayClassName: istio
  listeners:
    - name: https
      port: 443
      protocol: HTTPS
      allowedRoutes: { namespaces: { from: All } }   # any namespace may attach an HTTPRoute
      tls:
        mode: Terminate
        certificateRefs:
          - { group: "", kind: Secret, name: wso2-ingress-cert, namespace: istio-system }
```

### HTTPRoute — APIM (per app, in the app's namespace)

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: wso2-apim
  namespace: wso2-cp
spec:
  parentRefs:
    - { name: shared-gateway, namespace: istio-system, sectionName: https }
  hostnames: ["apim.example.com"]
  rules:
    - matches: [{ path: { type: PathPrefix, value: / } }]
      backendRefs: [{ group: "", kind: Service, name: wso2am-service, port: 9443 }]
```

### HTTPRoute — Identity Server

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: wso2-is
  namespace: wso2-is
spec:
  parentRefs:
    - { name: shared-gateway, namespace: istio-system, sectionName: https }
  hostnames: ["wso2is.example.com"]
  rules:
    - matches: [{ path: { type: PathPrefix, value: / } }]
      backendRefs: [{ group: "", kind: Service, name: wso2is-service, port: 9443 }]
```

> WSO2 consoles use HTTPS on 9443. TLS terminates at the shared gateway; the backend hop
> re-encrypts to the pod's 9443. The gateway reloads a rotated `wso2-ingress-cert` via SDS —
> no restart needed.

## GitOps model (unchanged)

- WSO2 manifests live in GitLab, including the shared `Gateway` + per-app `HTTPRoute`s.
- ArgoCD syncs them into the cluster.
- The Python web UI knows the GitLab repo/branch and can update env-specific values (domains,
  JDBC URLs) before commit.

## Ambient enrollment note (replaces the old sidecar-injection note)

There is **no sidecar injection** on this setup. WSO2 namespaces join the mesh with the
namespace label `istio.io/dataplane-mode=ambient` (set automatically by
[ansible/k8s_wso2.yml](../ansible/k8s_wso2.yml)); ztunnel handles mTLS at L4 with **no
pod restarts and no per-pod proxies**, so the Elastic Agent/Filebeat log-shipping sidecar and
WSO2 inter-node clustering traffic work unmodified. Do **not** use the old
`istio-injection=enabled` label — mixing sidecar and ambient modes in one namespace causes
hard-to-debug traffic issues. If WSO2 ports ever need to bypass the mesh, exclude them via
ambient waypoint/policy configuration rather than sidecar annotations.
