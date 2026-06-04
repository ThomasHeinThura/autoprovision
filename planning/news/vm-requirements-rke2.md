# VM Requirements — RKE2 / Istio (New)

Updated VM topology for the new requirement. Supersedes
[planning/vm-requirements.md](../vm-requirements.md) for Production and UAT execution.
The old document remains valid as the previous baseline.

## Core changes from the old baseline

1. Kubernetes nodes run **RKE2** (not Talos). RKE2 is installed by Ansible from the jump host.
2. CNI is the **RKE2 default (Canal)**. Kube-proxy is kept (RKE2 default).
3. Kubernetes ingress is **Istio**, not Envoy Gateway.
4. SQL Server runs on **dedicated Ubuntu 22.04 VMs** that Ansible installs (native, no Docker):
   - Production: **3-node read-scale Always On Availability Group**.
   - UAT: **2-node read-scale Always On Availability Group** (also VM Ubuntu + AG, not single, not Docker).
5. GitLab runs on its own **shared Docker VM "in between"** Production and UAT.

---

## Total VM count: 20

| Environment | VMs | Count |
| ----------- | --- | ----: |
| Production  | 3 RKE2 control plane + 5 RKE2 worker + 1 ELK + 3 MSSQL AG | 12 |
| UAT         | 1 RKE2 control plane + 2 RKE2 worker + 2 MSSQL AG + 1 ELK | 6 |
| Shared      | 1 GitLab (Docker) + 1 jump host | 2 |
| **Total**   |     | **20** |

> Note: the brief said "18 VMs"; the itemized list totals 19. We use **19** as the
> authoritative count. If a single VM must be removed to reach 18, the safest candidate is
> co-locating GitLab on the jump host — but that is **not** the recommended layout.

---

## Production VM Requirements (12 VMs)

| VM    | Role                     | vCPU | RAM   | Disk   | Notes |
| ----- | ------------------------ | ---: | ----: | -----: | ----- |
| VM-1  | RKE2 control plane (server) | 4 | 8 GB | 200 GB | etcd + control plane, first server bootstraps cluster |
| VM-2  | RKE2 control plane (server) | 4 | 8 GB | 200 GB | Joins via registration address |
| VM-3  | RKE2 control plane (server) | 4 | 8 GB | 200 GB | Joins via registration address |
| VM-4  | RKE2 worker (agent)      |    8 | 32 GB | 500 GB | Kubernetes workloads incl. WSO2 |
| VM-5  | RKE2 worker (agent)      |    8 | 32 GB | 500 GB | Kubernetes workloads incl. WSO2 |
| VM-6  | RKE2 worker (agent)      |    8 | 32 GB | 500 GB | Kubernetes workloads |
| VM-7  | RKE2 worker (agent)      |    8 | 32 GB | 500 GB | Kubernetes workloads |
| VM-8  | RKE2 worker (agent)      |    8 | 32 GB | 500 GB | Kubernetes workloads |
| VM-9  | ELK (Docker)             |   16 | 48 GB |   2 TB | Elasticsearch, Logstash, Kibana, Fleet/APM (production ELK) |
| VM-10 | MSSQL AG node 1 (primary) | 8 | 32 GB | 500 GB | SQL Server 2022, Always On AG primary |
| VM-11 | MSSQL AG node 2 (secondary) | 8 | 32 GB | 500 GB | SQL Server 2022, Always On AG secondary |
| VM-12 | MSSQL AG node 3 (secondary) | 8 | 32 GB | 500 GB | SQL Server 2022, Always On AG secondary |

### Production notes

- Control plane: do not schedule workloads on servers (RKE2 servers carry etcd; keep them clean).
- Prefer a **registration address / VIP** (or LB) for the 3 control-plane servers so agents and
  joining servers use one stable endpoint (`tls-san` includes it).
- Run Istio ingress gateway and other HA add-ons with ≥2 replicas.
- ELK is on its own VM in production (separate from GitLab).
- The 3 MSSQL VMs form one Always On Availability Group; WSO2 APIM/IS connect to the AG primary
  (read-scale AG has no virtual listener — see [mssql-ag-windows-ad.md](mssql-ag-windows-ad.md)
  for the Windows/listener path).
- **MSSQL VM OS: Ubuntu 22.04 LTS (or 20.04).** SQL Server 2022 on Linux is **not** supported on
  Ubuntu 24.04/25.04 (missing OpenLDAP 2.5 → `sqlservr` exits 127). The MSSQL VMs must be
  **dedicated** — do not co-locate SQL Server on the RKE2 nodes. The playbook enforces this with
  an OS preflight.

### Production totals

- 84 vCPU, 328 GB RAM, ~7.7 TB disk (approximate; depends on storage class).

---

## UAT VM Requirements (6 VMs)

| VM   | Role                     | vCPU | RAM   | Disk   | Notes |
| ---- | ------------------------ | ---: | ----: | -----: | ----- |
| VM-1 | RKE2 control plane (server) | 4 | 8 GB | 200 GB | Single control plane for UAT |
| VM-2 | RKE2 worker (agent)      |    8 | 32 GB | 500 GB | Kubernetes workloads |
| VM-3 | RKE2 worker (agent)      |    8 | 32 GB | 500 GB | Kubernetes workloads |
| VM-4 | MSSQL AG node 1 (primary)   | 8 | 32 GB | 500 GB | SQL Server 2022, read-scale AG primary |
| VM-5 | MSSQL AG node 2 (secondary) | 8 | 32 GB | 500 GB | SQL Server 2022, read-scale AG secondary |
| VM-6 | ELK (Docker)             |   16 | 48 GB |   2 TB | UAT ELK stack |

### UAT notes

- Single control plane is acceptable for UAT.
- **UAT MSSQL is a 2-node read-scale AG** (like prod, just fewer nodes) — VM Ubuntu, **native install, not Docker**. WSO2 connects to the AG **primary** (read-scale AG has no virtual listener).
- **UAT MSSQL VM OS: Ubuntu 22.04 LTS (or 20.04)** — same SQL Server 2022 OS support rule as prod. (Docker engine is only a fallback for unsupported host OS.)
- UAT ELK is independent from production ELK.

### UAT totals

- 44 vCPU, 152 GB RAM, ~3.7 TB disk (approximate).

---

## Shared VMs (2 VMs)

| VM | Role | vCPU | RAM | Disk | Notes |
| -- | ---- | ---: | --: | ---: | ----- |
| Shared-1 | GitLab (Docker) | 8 | 24 GB | 1 TB | GitLab CE + Runner + Container Registry, "in between" Prod and UAT |
| Shared-2 | Jump host | 4 | 8 GB | 100 GB | Python Web UI, Ansible, ansible-runner, RKE2/MSSQL automation, kubectl/helm/istioctl |

### Jump host software

- Python Web UI (FastAPI + multi-track dashboard).
- ansible-core, ansible-runner.
- `kubectl`, `helm`, `istioctl` for Kubernetes add-on runbooks.
- SSH keys and per-job generated inventory.
- SQLite for per-track state and job history.

> `talosctl` is no longer required (RKE2 replaces Talos).

---

## Kubernetes Workloads Expected (per RKE2 cluster)

- Default CNI (Canal) — shipped with RKE2.
- Istio (ingress gateway + control plane).
- cert-manager.
- ArgoCD.
- Headlamp (cluster UI).
- OpenTelemetry Collector.
- WSO2 API Manager (GitOps via ArgoCD from GitLab).
- WSO2 Identity Server (GitOps via ArgoCD from GitLab).

---

## External Infrastructure Requirements

| Dependency | Requirement | Purpose |
| ---------- | ----------- | ------- |
| NAS or NFS | Reachable from ELK + GitLab VMs | Elasticsearch snapshots, backups, archive |
| DNS | Internal/public records ready | Service hostnames, TLS, MSSQL listener, RKE2 registration address |
| Internet egress | Controlled outbound | RKE2/Istio/image pulls, OS packages, SQL Server packages |

The SQL Server VMs are **now provided as part of the 19 VMs** and installed by Ansible, rather
than being a fully external customer dependency.

---

## Networking Requirements

1. Jump host SSHs to all 19 VMs.
2. RKE2 agents and joining servers reach the control-plane registration address on `6443`/`9345`.
3. WSO2 pods reach the MSSQL listener (Prod) / instance (UAT) on `1433`.
4. WSO2 log sidecars reach Logstash on the matching ELK VM (`5044`).
5. DNS resolves all service hostnames, the RKE2 registration address, and the MSSQL AG listener.
