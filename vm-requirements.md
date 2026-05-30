# VM Requirements

## Purpose

This document defines the minimum VM and external infrastructure requirements needed to deliver the MVP described in `updated-mvp.md`.

It separates requirements for:

1. Lab environment — for build and rehearsal
2. UAT environment — for user acceptance testing and pre-production validation
3. Production environment — for final rollout and operational handover
4. External dependencies — must be available before deployment begins

## Core Assumptions

1. Talos nodes are dedicated to Kubernetes only.
2. The Docker platform runs on a single VM. Docker services are deployed once via Ansible from the jump host.
3. The jump host is separate from the Docker platform VM.
4. External SQL Server is provided by the customer.
5. External NAS or NFS storage is provided by the customer.
6. Internet or controlled outbound access is available for package pulls, certificates, and container images.

---

## Lab VM Requirements — Minimum Baseline

The lab environment is intended for development, integration testing, and deployment rehearsal.

| VM   | Role                | vCPU | RAM   | Disk   | Notes                                                        |
| ---- | ------------------- | ---: | ----: | -----: | ------------------------------------------------------------ |
| VM-1 | Talos control plane |    2 |  4 GB |  50 GB | Single control plane for lab validation only                 |
| VM-2 | Talos worker        |    8 | 24 GB | 200 GB | Kubernetes workloads including WSO2 image pulls              |
| VM-3 | Talos worker        |    8 | 24 GB | 200 GB | Kubernetes workloads including WSO2 image pulls              |
| VM-4 | Jump host           |    2 |  4 GB | 100 GB | Python Web UI, Ansible, ansible-runner, talosctl             |
| VM-5 | Docker platform     |   16 | 48 GB |   2 TB | GitLab, ELK stack, SonarQube, PostgreSQL, Dockhand, Traefik  |

### Lab Totals

- 36 vCPU
- 104 GB RAM
- 2.55 TB disk

### Lab Notes

- Docker platform is sized at 16 vCPU / 48 GB as the minimum to run Elasticsearch alongside GitLab CE without OOM risk. Do not reduce further.
- Talos worker disks are 200 GB to accommodate WSO2 APIM and WSO2 IS image pulls and persistent volumes.
- Jump host disk is 100 GB minimum for Ansible state, logs, inventory, and generated files.

---

## UAT VM Requirements — Recommended Baseline

The UAT environment is intended for user acceptance testing and pre-production validation.

| VM   | Role                | vCPU | RAM   | Disk   | Notes                                                        |
| ---- | ------------------- | ---: | ----: | -----: | ------------------------------------------------------------ |
| VM-1 | Talos control plane |    4 |  8 GB | 200 GB | Single control plane for UAT validation only                 |
| VM-2 | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                         |
| VM-3 | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                         |
| VM-4 | Jump host           |    4 |  8 GB | 100 GB | Python Web UI, Ansible, ansible-runner, talosctl             |
| VM-5 | Docker platform     |   24 | 96 GB |   2 TB | GitLab, ELK stack, SonarQube, PostgreSQL, Dockhand, Traefik  |

### UAT Totals

- 48 vCPU
- 176 GB RAM
- 3.3 TB disk

---

## Production VM Requirements

The production environment is intended to support the full MVP rollout and operational handover.

| VM    | Role                | vCPU | RAM   | Disk   | Notes                                                        |
| ----- | ------------------- | ---: | ----: | -----: | ------------------------------------------------------------ |
| VM-1  | Talos control plane |    4 |  8 GB | 200 GB | Kubernetes control plane node                                |
| VM-2  | Talos control plane |    4 |  8 GB | 200 GB | Kubernetes control plane node                                |
| VM-3  | Talos control plane |    4 |  8 GB | 200 GB | Kubernetes control plane node                                |
| VM-4  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                         |
| VM-5  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                         |
| VM-6  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                         |
| VM-7  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                         |
| VM-8  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                         |
| VM-9  | Jump host           |    4 |  8 GB | 100 GB | Python Web UI, Ansible, ansible-runner, talosctl             |
| VM-10 | Docker platform     |   24 | 96 GB |   2 TB | GitLab, ELK stack, SonarQube, PostgreSQL, Dockhand, Traefik  |

### Production Totals

- 80 vCPU
- 280 GB RAM
- 5.2 TB disk

---

## Docker Platform Capacity

The Docker platform VM hosts these services, deployed once via Ansible:

- Elasticsearch
- Logstash
- Kibana
- Fleet Server
- APM Server
- GitLab CE with container registry
- GitLab Runner
- SonarQube
- Shared PostgreSQL for GitLab, SonarQube, and platform state
- ElastAlert2
- Dockhand (Docker container management and resource monitoring UI)
- Traefik reverse proxy on port 443

It also hosts the active hot storage tier for short-retention traces, logs, and metrics before archive movement to external NFS or NAS.

### Recommended Docker Host Baseline

- 24 vCPU
- 96 GB RAM
- 2 TB local SSD storage
- External NFS or NAS mount available for snapshots, backups, and long-term archive retention

### Why This Sizing Is Needed

- Elasticsearch requires the largest memory share and needs local SSD for index performance. It should not run on NFS-backed disks.
- GitLab CE with registry and SonarQube both require predictable memory and disk I/O alongside Elasticsearch.
- Consolidating all Docker services onto one VM simplifies MVP operations, but only if enough headroom is reserved.
- Trace data stays hot in Elasticsearch for 7 days, then moves to external storage for 2 to 3 years.
- Long log and metrics retention must not consume only local Docker VM disk.

---

## Jump Host Requirements

The jump host is the provisioning and operations control node.

### Baseline

- 4 vCPU
- 8 GB RAM
- 100 GB disk

### Software on the Jump Host

- Python Web UI (FastAPI + HTMX)
- ansible-core and ansible-runner
- `talosctl` for Talos cluster management
- SSH keys and inventory data
- SQLite for job state and environment variables

### Not on the Jump Host

- Headlamp — deployed inside the Kubernetes cluster via Helm, not on the jump host

---

## Kubernetes Node Requirements

### Control Plane Nodes

- 4 vCPU
- 8 GB RAM
- 200 GB disk
- Talos OS

### Worker Nodes

- 8 vCPU
- 32 GB RAM
- 500 GB disk
- Talos OS

### Kubernetes Workloads Expected in MVP

- Headlamp (Helm, cluster management UI)
- cert-manager
- Envoy Gateway
- Cilium (CNI)
- OpenTelemetry Collector
- ArgoCD
- WSO2 API Manager — Kubernetes YAML stored in GitLab
- WSO2 Identity Server — Kubernetes YAML stored in GitLab

---

## External Infrastructure Requirements

These are not included in the VM count above. They are mandatory customer-provided dependencies that must be ready before deployment begins.

| Dependency      | Requirement                          | Purpose                                                         |
| --------------- | ------------------------------------ | --------------------------------------------------------------- |
| SQL Server      | Reachable from Kubernetes nodes      | WSO2 APIM and WSO2 IS databases                                 |
| NAS or NFS      | Reachable from Docker platform VM    | Elasticsearch snapshots, backups, and long-term archive storage |
| DNS             | Internal or public records ready     | Service hostnames and TLS certificate issuance                  |
| Internet egress | Controlled outbound access available | Container image pulls, OS packages, certificate issuance        |

---

## Docker Network and Ingress Requirements

1. All Docker platform services must use one shared Docker network.
2. External HTTPS for all Docker services must be exposed through Traefik on port 443 only.

---

## Retention Requirements

| Data Type                    | Hot Retention                  | Archive Retention           | Archive Location     |
| ---------------------------- | ------------------------------ | --------------------------- | -------------------- |
| Tracing                      | 7 days in Elasticsearch        | 2 to 3 years                | External NFS or NAS  |
| Basic platform and app logs  | 1 year                         | Archive after 1 year        | External NFS or NAS  |
| WSO2 logs from Logstash      | Active search as needed        | 10 years                    | External NFS or NAS  |
| OpenTelemetry metrics        | Searchable based on capacity   | 1 to 2 years                | External NFS or NAS  |
| OpenTelemetry container logs | 1 year                         | Archive after 1 year        | External NFS or NAS  |

---

## Network Requirements

1. Jump host must SSH to the Docker platform VM and any Linux management targets.
2. Jump host must reach `talosctl` API endpoints on Talos nodes.
3. Kubernetes nodes must reach the Docker platform services where integrations exist (Elasticsearch, GitLab, Logstash).
4. Docker platform must reach NFS or NAS storage and required external endpoints.
5. Public or internal DNS must resolve all required service hostnames.

---

## Storage Notes

1. Use SSD-backed storage for the Docker platform local disk.
2. Keep Elasticsearch data on local fast disk — do not mount Elasticsearch data directories directly on NFS.
3. Use external NFS or NAS for Elasticsearch snapshots, application backups, and archive paths only.
4. Size NFS capacity to cover Elasticsearch snapshots, trace archives, GitLab backups, registry growth, long-term log retention, and database dumps.

---

## NFS Storage Request to Customer

The following NFS or NAS storage must be provisioned by the customer before production deployment begins:

- One reachable NFS or NAS export endpoint
- Network access from the Docker platform VM
- Capacity covering:
  - Elasticsearch snapshot repository
  - Trace archive for 2 to 3 years
  - Long-term log retention (including WSO2 10-year path)
  - GitLab backup storage
  - Database dump storage

---

## Recommendation

Do not reduce the Docker platform VM below the recommended baseline under budget pressure. It is the most capacity-sensitive component in the MVP.

The safest cost optimization across environments is:

- Keep the lab at minimum baseline sizing
- Keep UAT at recommended baseline
- Keep production at full spec
