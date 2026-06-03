# New Requirements — Index (Old vs New)

This folder holds the **updated requirements**. The original requirements are still valid
as a record and are **not modified**. Use this page to understand what changed.

## What changed

The **only** technology change is the Kubernetes layer:

| Layer | Old requirement | New requirement |
| ----- | --------------- | --------------- |
| Node OS / cluster | Talos OS | **RKE2** (installed by Ansible) |
| CNI | Cilium | **Default CNI (Canal)** shipped with RKE2 |
| Kubernetes ingress | Envoy Gateway | **Istio** (ingress gateway + `Gateway`/`VirtualService`) |

Everything else in the stack is unchanged in intent:

- **Per cluster:** ArgoCD, Headlamp, WSO2 API Manager, WSO2 Identity Server.
- **Docker platform:** PostgreSQL, Traefik, Dockhand, GitLab, SonarQube, ELK, ElastAlert2.
- **Observability / migration:** Elasticsearch lifecycle, retention, WSO2 key migration.

Two requirements were added/clarified:

1. **MSSQL on customer VMs** — instead of treating SQL Server as fully external, the new
   topology includes SQL Server VMs that Ansible installs:
   - Production: **3-node SQL Server Always On Availability Group**.
   - UAT: **1 single SQL Server instance**.
2. **Parallel install** — the control-plane app must run several stacks **at the same time**
   on execution day: **2 Kubernetes clusters + 2 ELK + 1 GitLab** in parallel.

## What stays as documentation only

Ansible automates **RKE2 cluster install** and **MSSQL install** only.

The in-cluster add-ons (Istio, ArgoCD, Headlamp, WSO2) remain **step-by-step runbooks**
under [`rke2-cluster/`](../../rke2-cluster/), the same way the old Talos guides were runbooks.

## File map

### New requirement docs (this folder)

- [updated-mvp-rke2.md](updated-mvp-rke2.md) — updated MVP scope and execution model.
- [vm-requirements-rke2.md](vm-requirements-rke2.md) — 19-VM topology and sizing.
- [installation-steps-rke2.md](installation-steps-rke2.md) — new operator flow.
- [version-rke2.md](version-rke2.md) — version delta (RKE2 / Canal / Istio / SQL Server).
- [wso2-rke2.md](wso2-rke2.md) — WSO2 exposure via Istio.
- [parallel-installation.md](parallel-installation.md) — parallel workload model and UI tracks.

### New cluster runbooks

- [rke2-cluster/prod-rke2-installation.md](../../rke2-cluster/prod-rke2-installation.md)
- [rke2-cluster/uat-rke2-installation.md](../../rke2-cluster/uat-rke2-installation.md)
- [rke2-cluster/rke2-addons-istio-argocd-headlamp.md](../../rke2-cluster/rke2-addons-istio-argocd-headlamp.md)

### Old requirement docs (kept, unchanged)

- [planning/updated-mvp.md](../updated-mvp.md)
- [planning/vm-requirements.md](../vm-requirements.md)
- [planning/installation-steps.md](../installation-steps.md)
- [planning/version.md](../version.md)
- [planning/wso2_apim.md](../wso2_apim.md)
- [talos-cluster/prod-talos-installation.md](../../talos-cluster/prod-talos-installation.md)
- [talos-cluster/uat-talos-installation.md](../../talos-cluster/uat-talos-installation.md)

## VM count note

The brief said "18 VMs" but the itemized list totals **19**. We document **19** as the
authoritative count (the 18 was an undercount). See
[vm-requirements-rke2.md](vm-requirements-rke2.md) for the breakdown.
