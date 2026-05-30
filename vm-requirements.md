# VM Requirements

## Purpose

This document defines the minimum VM and external infrastructure requirements needed to deliver the MVP described in [updated-mvp.md](/Users/heinthura/Documents/lab/EID/updated-mvp.md).

It separates requirements for:

1. Lab environment for build and rehearsal
2. Production environment for final rollout
3. External dependencies that must be available before deployment

## Core Assumptions

1. Talos nodes are dedicated to Kubernetes only.
2. The Docker platform runs on a single large VM managed by Dockhand.
3. The jump host is separate from the Docker platform.
4. External SQL Server is provided by the customer.
5. External NAS or NFS storage is provided by the customer.
6. Internet or controlled outbound access is available for package pulls, certificates, and container images.

## Testing Lab VM Requirements

The lab environment is intended for development, integration testing, and migration rehearsal.

| VM   | Role                | vCPU |   RAM |   Disk | Notes                                                 |
| ---- | ------------------- | ---: | ----: | -----: | ----------------------------------------------------- |
| VM-1 | Talos control plane |    2 |  4 GB |  50 GB | Single control plane for lab validation only          |
| VM-2 | Talos worker        |    8 | 24 GB | 100 GB | Worker node for Kubernetes workloads                  |
| VM-3 | Talos worker        |    8 | 24 GB | 100 GB | Worker node for Kubernetes workloads                  |
| VM-4 | Jump host           |    2 |  4 GB |  50 GB | Runs Python Web UI, Ansible, ansible-runner, and Headlamp |
| VM-5 | Docker platform     |   12 | 32 GB |   2 TB | Runs Dockhand-managed Docker services with external archive storage |

### Lab Totals

- 32 vCPU
- 88 GB RAM
- 2.3 TB disk

## Lab VM Requirements

The lab environment is intended for development, integration testing, and migration rehearsal.

| VM   | Role                | vCPU |   RAM |   Disk | Notes                                                 |
| ---- | ------------------- | ---: | ----: | -----: | ----------------------------------------------------- |
| VM-1 | Talos control plane |    4 |  8 GB | 200 GB | Single control plane for lab validation only          |
| VM-2 | Talos worker        |    8 | 32 GB | 500 GB | Worker node for Kubernetes workloads                  |
| VM-3 | Talos worker        |    8 | 32 GB | 500 GB | Worker node for Kubernetes workloads                  |
| VM-4 | Jump host           |    4 |  8 GB | 100 GB | Runs Python Web UI, Ansible, ansible-runner, and Headlamp |
| VM-5 | Docker platform     |   24 | 96 GB |   2 TB | Runs Dockhand-managed Docker services with external archive storage |

### Lab Totals

- 48 vCPU
- 176 GB RAM
- 3.3 TB disk

## Production VM Requirements

The production environment is intended to support the full MVP rollout and operational handover.

| VM    | Role                | vCPU |   RAM |   Disk | Notes                                                 |
| ----- | ------------------- | ---: | ----: | -----: | ----------------------------------------------------- |
| VM-1  | Talos control plane |    4 |  8 GB | 200 GB | Kubernetes control plane node                         |
| VM-2  | Talos control plane |    4 |  8 GB | 200 GB | Kubernetes control plane node                         |
| VM-3  | Talos control plane |    4 |  8 GB | 200 GB | Kubernetes control plane node                         |
| VM-4  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                  |
| VM-5  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                  |
| VM-6  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                  |
| VM-7  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                  |
| VM-8  | Talos worker        |    8 | 32 GB | 500 GB | Kubernetes workloads                                  |
| VM-9  | Jump host           |    4 |  8 GB | 100 GB | Runs Python Web UI, Ansible, ansible-runner, and Headlamp |
| VM-10 | Docker platform     |   24 | 96 GB |   2 TB | Runs Dockhand-managed Docker services with external archive storage |

### Production Totals

- 80 vCPU
- 280 GB RAM
- 5.2 TB disk

## Docker Platform Capacity

The Docker platform VM hosts these services:

- Elasticsearch
- Logstash
- Kibana
- Fleet Server
- APM Server
- GitLab CE
- GitLab Container Registry
- GitLab Runner
- SonarQube
- Shared PostgreSQL for Dockhand, GitLab, and SonarQube
- ElastAlert2
- Dockhand
- Traefik reverse proxy exposed on port 443

It also hosts the active hot storage tier for short-retention traces, logs, and metrics before archive movement to external storage.

### Recommended Docker Host Baseline

- 24 vCPU
- 96 GB RAM
- 2 TB local SSD storage
- External NFS or NAS mount available for snapshots, backups, and long-term archive retention

### Why this sizing is needed

- Elasticsearch requires the largest memory share and local disk performance.
- GitLab and SonarQube both need predictable memory and disk I/O.
- Consolidating Docker services onto one VM simplifies MVP operations, but only if enough headroom is reserved.
- Trace data stays hot in Elasticsearch for 7 days, then needs to move to external storage for 2 to 3 years.
- Long log and metrics retention requires external archive storage beyond the Docker VM local disk.

## Jump Host Requirements

The jump host is the control node for provisioning and operations.

### Minimum baseline

- 4 vCPU
- 8 GB RAM
- 100 GB disk

### Software hosted on the jump host

- Python Web UI
- FastAPI application runtime
- Ansible
- ansible-runner
- Headlamp CLI or Headlamp management components
- SSH keys and inventory data

## Kubernetes Node Requirements

### Control plane nodes

- 4 vCPU
- 8 GB RAM
- 200 GB disk
- Talos OS

### Worker nodes

- 8 vCPU
- 32 GB RAM
- 500 GB disk
- Talos OS

### Kubernetes workloads expected in MVP

- cert-manager
- Envoy Gateway
- OpenTelemetry Collector
- ArgoCD
- WSO2 API Manager from GitLab-managed Kubernetes YAML
- WSO2 Identity Server from GitLab-managed Kubernetes YAML

## External Infrastructure Requirements

These are not hosted in the MVP VM count, but they are mandatory dependencies.

| Dependency      | Requirement                       | Purpose                                                |
| --------------- | --------------------------------- | ------------------------------------------------------ |
| SQL Server      | Reachable from Kubernetes nodes   | WSO2 APIM and WSO2 IS databases                        |
| NAS or NFS      | Reachable from Docker platform VM | Elasticsearch snapshots, backups, and long-term archive retention |
| DNS             | Public or internal records ready  | Service hostnames and certificate issuance             |
| Internet egress | Controlled outbound access        | Container pulls, package install, certificate issuance |

## Docker Network and Ingress Requirements

1. All Docker platform services must use one shared Docker network.
2. External HTTPS exposure for Docker services must be through Traefik on port 443.

## Retention Requirements

| Data Type | Hot Retention | Archive Retention | Archive Location |
| --- | --- | --- | --- |
| Tracing | 7 days in Elasticsearch | 2 to 3 years | External NFS or NAS |
| Basic platform and application logs | 1 year | Archive after 1 year | External NFS or NAS |
| WSO2 logs from Logstash | Active search as needed | 10 years | External NFS or NAS |
| OpenTelemetry metrics | Searchable retention based on capacity | 1 to 2 years | External NFS or NAS |
| OpenTelemetry container logs | 1 year | Archive after 1 year if required | External NFS or NAS |

## Network Requirements

1. Jump host must SSH to the Docker platform and any Linux management targets.
2. Jump host must reach Headlamp and Talos management endpoints.
3. Kubernetes nodes must reach the Docker platform services where integrations exist.
4. Docker platform must reach NFS storage and required external endpoints.
5. Public or internal DNS must resolve all required service names.

## Storage Notes

1. Use SSD-backed storage for the Docker platform local disk.
2. Keep Elasticsearch data on local fast disk, not directly on NFS.
3. Use external NFS or NAS for snapshots, backups, and archive paths.
4. Ensure enough growth room for GitLab repositories, container registry images, trace archives, long-term log retention, and metrics retention.

## Recommendation

If budget pressure exists, do not reduce the Docker platform below the recommended baseline first. The single Docker VM is the most capacity-sensitive part of this MVP.

The safest cost optimization is to keep the lab environment smaller while preserving the production sizing above.
