# Version Matrix — RKE2 / Istio (New)

Version delta for the new requirement. This document **replaces only the Kubernetes layer**
of [planning/version.md](../version.md) and **adds** SQL Server. Everything not listed here
keeps the pinned version from the old version matrix.

> Treat the old `planning/version.md` as the source of truth for ELK, GitLab, WSO2, SonarQube,
> PostgreSQL, ElastAlert2, Dockhand, Traefik, cert-manager, ArgoCD, Headlamp, OpenTelemetry,
> and the Python/Ansible runtime. This file overrides the cluster + ingress + database rows.

---

## Removed (no longer used)

| Component | Old pin | Reason |
| --------- | ------- | ------ |
| Talos OS | v1.13.3 | Replaced by RKE2 |
| Cilium | 1.19.4 | Replaced by RKE2 default CNI (Canal) |
| Envoy Gateway | v1.8.0 | Replaced by Istio for Kubernetes ingress |

---

## Added / Changed

### Kubernetes cluster

| Component | Version | Notes |
| --------- | ------- | ----- |
| RKE2 | **`v1.36.1+rke2r2`** (Latest) | Installs Kubernetes + Canal CNI + kube-proxy by default. Pinned in the Ansible var `rke2_version`. |
| Kubernetes | v1.36.1 | Shipped with `v1.36.1+rke2r2` |
| etcd | v3.6.7-k3s1 | Bundled |
| containerd | v2.2.3-k3s1 | Bundled |
| runc | v1.4.2 | Bundled |
| CNI — Canal (default) | rke2-canal `v3.32.0-build2026051100` (Flannel v0.28.4 + Calico v3.32.0) | Default CNI. Do **not** set `cni: none`. |
| CoreDNS | v1.14.3 | Bundled |

> The Ansible playbook reads `rke2_version` so the pin lives in one place. Other CNI options on
> this release if ever needed: Calico v3.32.0, Cilium v1.19.3, Multus v4.2.4 — we use **Canal**.

### Bundled ingress in RKE2 v1.36 (important)

As of RKE2 **v1.36**, the bundled/default ingress controller changed from ingress-nginx to
**Traefik** (`rke2-traefik` v39.0.703 → Traefik v3.6.16), because ingress-nginx was retired
upstream in March 2026 and will be removed entirely in v1.37 for community users.

**We use Istio for Kubernetes ingress**, so the RKE2-bundled ingress is not needed. To avoid two
ingress controllers contending for node ports / LoadBalancer IPs (RKE2 ServiceLB binds 80/443 on
the nodes), disable the bundled ingress in the server `config.yaml`. The Ansible playbook does
this by default (`rke2_disable_bundled_ingress: true` → adds
`disable: [rke2-ingress-nginx, rke2-traefik]`).

> This bundled Traefik is **not** the same as the Docker-platform Traefik (v3.7.1) on the
> GitLab/ELK VMs — that one is unchanged.

### Kubernetes ingress (workloads)

| Component | Version | Helm/Install | Notes |
| --------- | ------- | ------------ | ----- |
| Istio | **1.30** | `istioctl` (default profile) — installs `istio-ingressgateway` in `istio-system` | Replaces Envoy Gateway. The team's `WSO2_APIM_KUBE_ISTIO` repo expects the ingress gateway + TLS secret in **`istio-system`**, so use the istioctl default profile. Routes via `Gateway`/`VirtualService` on a `LoadBalancer` service (RKE2 ServiceLB / external LB / MetalLB). |

### Database

| Component | Version | Image/Package | Notes |
| --------- | ------- | ------------- | ----- |
| SQL Server | 2022 (16.x) | `mssql-server` apt package (Ubuntu 22.04) | Prod = 3-node Always On AG; UAT = single instance. Installed by Ansible. |
| MSSQL JDBC Driver | 13.4.0 | `mssql-jdbc-13.4.0.jre11.jar` | Unchanged from old matrix — baked into the WSO2 custom image. |

---

## Unchanged (carried from old version matrix)

These keep their old pins (see [planning/old/version.md](../old/version.md)):

- WSO2 API Manager 4.7.0, WSO2 Identity Server 7.3.0.
- Elasticsearch / Kibana / Logstash / Fleet / APM / Elastic Agent — all 9.1.4.
- GitLab CE 19.0.1, GitLab Runner v19.0.1.
- SonarQube 26.4.0.121862 (community branch plugin).
- PostgreSQL 17.10 (shared platform DB on the GitLab/Docker VM).
- ElastAlert2 2.29.0, Dockhand v0.29.4, Traefik v3.7.1.
- cert-manager v1.20.2, ArgoCD v3.4.2, Headlamp v1.7.3.
- OpenTelemetry Collector v0.152.0.
- ansible-core 2.20.6, ansible-runner 2.4.3, Python 3.13.13.

---

## Compatibility rules (updated)

1. Elastic stack components all remain on 9.1.4.
2. WSO2 APIM 4.7.0 / IS 7.3.0 remain compatible with MSSQL JDBC 13.4.0 and **SQL Server 2022**.
3. RKE2 default CNI (Canal) is used — do not layer a second CNI.
4. **Istio** is the only Kubernetes ingress. **Traefik** remains the Docker-platform ingress.
   Do not mix their responsibilities.
5. Pin `rke2_version` and the Istio chart version in one place each (Ansible var / runbook header)
   and review before each environment rollout.
