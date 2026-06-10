# Requirements — Index (Old vs New)

This folder holds the **current requirements**. The original (Talos-era) design is summarized
here for context; its full docs were removed when the repo was cleaned for publication.

## What changed

The **only** technology change is the Kubernetes layer:

| Layer | Old requirement | New requirement |
| ----- | --------------- | --------------- |
| Node OS / cluster | Talos OS | **RKE2** (installed by Ansible) |
| CNI | Cilium | **Default CNI (Canal)** shipped with RKE2 |
| Kubernetes ingress | Envoy Gateway | **Istio 1.30 ambient** — one shared Kubernetes Gateway API `Gateway` (`shared-gateway` in `istio-system`) + per-app `HTTPRoute`s |

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

## Automation status

Ansible (driven by the web UI) automates the **RKE2 cluster install**, **MSSQL** (single + HA
AG), the **Docker stacks**, the **in-cluster add-ons** (MetalLB, Istio ambient + shared
Gateway, cert-manager + internal CA, ArgoCD, Headlamp), **WSO2 APIM/IS**, **TLS cert
rotation**, and **backups** (etcd snapshots, MSSQL FULL/LOG). The step-by-step runbooks under
[`rke2-cluster/`](../rke2-cluster/) are kept as the manual/theory reference for each
automated step.

## File map

### New requirement docs (this folder)

- [updated-mvp-rke2.md](updated-mvp-rke2.md) — MVP scope, execution model, Definition of Done status.
- [vm-requirements-rke2.md](vm-requirements-rke2.md) — 19-VM topology and sizing.
- [installation-steps-rke2.md](installation-steps-rke2.md) — operator flow.
- [version-rke2.md](version-rke2.md) — pinned version matrix (RKE2 / Canal / Istio ambient / SQL Server).
- [wso2-rke2.md](wso2-rke2.md) — WSO2 exposure via the shared ambient Gateway + MSSQL wiring.
- [parallel-installation.md](parallel-installation.md) — parallel workload model and UI tracks.

### Cluster runbooks (manual/theory reference)

- [rke2-cluster/prod-rke2-installation.md](../rke2-cluster/prod-rke2-installation.md)
- [rke2-cluster/uat-rke2-installation.md](../rke2-cluster/uat-rke2-installation.md)
- [rke2-cluster/rke2-addons-istio-argocd-headlamp.md](../rke2-cluster/rke2-addons-istio-argocd-headlamp.md)
- [rke2-cluster/metallb-install.md](../rke2-cluster/metallb-install.md)
- [mssql/](../mssql/) — SQL Server manual-install + AG theory guides

## VM count note

The brief said "18 VMs" but the itemized list totals **19**. We document **19** as the
authoritative count (the 18 was an undercount). See
[vm-requirements-rke2.md](vm-requirements-rke2.md) for the breakdown.
