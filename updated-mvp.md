## Updated MVP

### Objective

Deliver a workable MVP for infrastructure automation and migration that can be prepared in the lab, repeated in UAT and production, and operated through a simple control plane.

The MVP should prove five things:

1. Core infrastructure can be provisioned reliably from a single jump host.
2. Docker services can be deployed once via Ansible in a fixed sequence.
3. Kubernetes services can be deployed in a controlled sequence using talosctl and ArgoCD.
4. Observability and migration paths are functional.
5. Operations can be triggered and monitored from a lightweight Python web UI.

***

### Target Outcome

The MVP is successful when the team can:

1. Bootstrap a jump host, one Docker platform VM, and a Talos cluster in one day per environment.
2. Deploy all Docker workloads via Ansible from the jump host in a fixed sequence.
3. Deploy Kubernetes workloads through talosctl, Helm, and ArgoCD.
4. Observe logs, metrics, traces, and alerts in Elasticsearch and Kibana.
5. Run the entire rollout from a Python web UI that captures inputs and executes Ansible playbooks.
6. Complete UAT and production deployments in parallel on the same day.

***

### Environment Model

#### Lab

- 1 jump host — Python Web UI, Ansible, ansible-runner, talosctl
- 1 Docker VM — one-time Ansible deployment of all Docker services
- 1 Talos control plane node
- 2 Talos worker nodes

#### UAT

- 1 jump host — Python Web UI, Ansible, ansible-runner, talosctl
- 1 Docker VM — one-time Ansible deployment of all Docker services
- 1 Talos control plane node
- 2 Talos worker nodes
- External NAS or NFS mounted for snapshots and archive retention
- External SQL Server for WSO2 data services

#### Production

- 1 jump host — Python Web UI, Ansible, ansible-runner, talosctl
- 1 Docker VM — one-time Ansible deployment of all Docker services
- Docker VM uses 2 TB local SSD storage for active platform data
- 3 Talos control plane nodes
- 5 Talos worker nodes
- External NAS or NFS mounted for snapshots, backups, and long-term archive retention
- External SQL Server for WSO2 data services

UAT and production deployments run in parallel on the same day. Customer VMs are pre-booted with Talos ISO and waiting for talosctl machine config apply.

***

### Deployment Strategy

#### Phase A: Jump Host Bootstrap

Operator SSHs into the jump host and runs one script:

```bash
ssh <username>@<jump-host-ip>
git clone https://github.com/ThomasHeinThura/autoprovision.git
cd autoprovision
sh bootstrap-jumphost.sh
```

The script installs all required dependencies and starts the Python web UI as a background service.

The operator then opens the web UI at `http://<jump-host-ip>:3000/` to continue.

#### Phase B: Docker Platform Deployment

From the web UI, the operator provides the Docker VM IP, SSH username, and SSH password.

Ansible deploys all Docker services to the Docker VM in this fixed sequence:

1. Install Docker CE and base OS prerequisites.
2. Install PostgreSQL (shared instance for GitLab, SonarQube, and platform state).
3. Install Traefik with CORS enabled and HTTPS configuration on port 443.
4. Install Dockhand (Docker container management and resource monitoring UI).
5. Install GitLab CE, GitLab Runner, and GitLab Container Registry — using `https://github.com/ThomasHeinThura/gitlab-compose`.
6. Install SonarQube.
7. Install ELK stack — using `https://github.com/deviantony/docker-elk` as the stable base compose.

Each step is a separate Ansible playbook triggered from the web UI. The UI shows live log streaming and updates the service card status on completion.

No GitOps for Docker. All Docker services are deployed once via Ansible. Dockhand is used for container management and resource monitoring only, not for GitOps orchestration.

#### Phase C: Talos Cluster and Kubernetes Rollout

From the web UI, the operator provides control plane IPs, worker IPs, and cluster name.

Talos VMs are pre-booted with the Talos ISO by the customer. The jump host applies machine configs using talosctl.

Kubernetes components are deployed in this sequence:

1. Apply Talos machine configs via talosctl from the jump host.
2. Bootstrap the Talos cluster.
3. Install Cilium CNI.
4. Install cert-manager.
5. Install Envoy Gateway.
6. Install ArgoCD and expose the ArgoCD UI.
7. Install Headlamp via Sidero-provided Helm chart.
8. Install WSO2 API Manager from Kubernetes YAML stored in GitLab.
9. Install WSO2 Identity Server from Kubernetes YAML stored in GitLab.
10. Expose WSO2 APIM and WSO2 IS through Envoy Gateway.
11. Install OpenTelemetry Collector.
12. Run autoprovision Kubernetes manifests.

UAT cluster and production cluster are created in parallel.

#### Phase D: Observability, Migration, and Validation

1. Configure Elasticsearch ILM lifecycle and retention policies.
2. Configure log, metrics, and trace archive paths to external NFS or NAS.
3. Run Elasticsearch migration from old 8.14 environment to 9.1.4 using snapshot and restore.
4. Validate index compatibility and reindex where needed.
5. Run WSO2 APIM credential migration into the new Kubernetes deployment.
6. Create initial ElastAlert2 rule set.
7. Validate end-to-end alert flow.
8. Test out and sign off.

***

### MVP Scope

#### 1. Platform Foundation

- Jump host with Python Web UI, Ansible, ansible-runner, and talosctl.
- Docker VM with all Docker services deployed once via Ansible.
- Docker VM with 2 TB local SSD storage for active Elasticsearch and platform workloads.
- GitLab CE with registry and runner.
- Talos cluster with Cilium networking.
- External NFS or NAS mounted for backups, Elasticsearch snapshots, and archive tiers.

#### 2. Docker Services

Deployed once via Ansible in fixed sequence. No ongoing GitOps management.

- PostgreSQL (shared instance for GitLab, SonarQube, and platform state).
- Traefik on port 443 for external HTTPS exposure.
- Dockhand (container management and resource monitoring UI).
- GitLab CE with container registry and GitLab Runner.
- SonarQube.
- Elasticsearch, Logstash, Kibana.
- Fleet Server and APM Server (via Elastic Agent).
- ElastAlert2.

**Docker Network Standard**

- Use one shared Docker network for all Docker platform services.
- Publish all external HTTPS traffic through Traefik on port 443 only.

#### 3. Kubernetes Services

- Cilium CNI.
- cert-manager.
- Envoy Gateway (Kubernetes ingress only).
- ArgoCD.
- Headlamp (via Sidero-provided Helm chart).
- OpenTelemetry Collector.
- WSO2 API Manager — Kubernetes YAML stored in GitLab.
- WSO2 Identity Server — Kubernetes YAML stored in GitLab.

#### 4. Observability

The MVP must ingest and expose:

- Kubernetes metrics.
- Kubernetes logs.
- Cilium Hubble flow data.
- Tracing data from Envoy.
- Alert events from ElastAlert2.

Retention policy:

| Data Type                    | Hot Retention           | Archive Retention    | Archive Location    |
| ---------------------------- | ----------------------- | -------------------- | ------------------- |
| Tracing                      | 7 days in Elasticsearch | 2 to 3 years         | External NFS or NAS |
| Basic platform and app logs  | 1 year                  | Archive after 1 year | External NFS or NAS |
| WSO2 logs from Logstash      | Active search as needed | 10 years             | External NFS or NAS |
| OpenTelemetry metrics        | Based on capacity       | 1 to 2 years         | External NFS or NAS |
| OpenTelemetry container logs | 1 year                  | Archive after 1 year | External NFS or NAS |

Success conditions:

- Data is searchable in Elasticsearch.
- Dashboards are visible in Kibana.
- At least one alert flow is verified end to end.
- Lifecycle and archive policies are configured before migration starts.

#### 5. Migration

- Tracing lifecycle and retention policies configured before any migration step.
- Elasticsearch migration from old 8.14 environment to 9.1.4 using snapshot and restore.
- Validation for index compatibility and reindex needs.
- WSO2 API Manager credential migration into the new Kubernetes deployment.
- Initial ElastAlert2 rule set created for the new environment.

***

### Python Web UI MVP

The web UI is an operations console for repeatable deployment. It is not a full platform product.

**Required Capabilities**

- Inventory form for lab, UAT, and production values.
- Variable input for Docker VM IP, SSH credentials, domain names, NFS paths, and migration inputs.
- One-click execution for individual Ansible steps.
- Run-all flow for the standard deployment sequence.
- Live job log streaming via WebSocket.
- Service card status display per environment.
- Job status and history.

**Suggested Stack**

- FastAPI.
- Jinja2 templates.
- HTMX for lightweight interactivity.
- SQLite for job state and environment variables.
- WebSocket log streaming.

***

### Delivery Sequence

#### Prep Period — Lab

Complete in the lab before UAT and production execution:

1. Docker compose repositories and templates.
2. Helm values and Kubernetes manifests including WSO2 APIM and WSO2 IS YAML.
3. Ansible inventory, roles, and playbooks.
4. Python Web UI.
5. Bootstrap script for jump host.
6. Lab validation of each deployment phase end to end.

#### Execution Day — UAT and Production in Parallel

Both environments follow the same sequence simultaneously:

1. SSH into jump host.
2. Clone autoprovision repo and run bootstrap script.
3. Open Python web UI.
4. Enter Docker VM IP, SSH credentials, and environment values.
5. Run Phase B Docker deployment sequence (PostgreSQL → Traefik → Dockhand → GitLab → SonarQube → ELK).
6. Apply Talos machine configs via talosctl to pre-booted VMs.
7. Bootstrap Talos cluster.
8. Deploy Kubernetes services in sequence (Cilium → cert-manager → Envoy Gateway → ArgoCD → Headlamp → WSO2 APIM → WSO2 IS → OTel Collector).
9. Configure observability lifecycle and retention policies.
10. Run migration tasks.
11. Test and validate.

***

### Definition of Done

The MVP is complete when all of the following are true:

1. Jump host can trigger the full deployment flow from the web UI.
2. All Docker services are deployed and running on the Docker VM.
3. GitLab stores the Kubernetes deployment sources for WSO2 and platform services.
4. Talos cluster is running and reachable via talosctl.
5. WSO2 APIM and WSO2 IS are deployed and connected to SQL Server.
6. Elasticsearch, Kibana, alerting, and lifecycle policies are functional.
7. Backup, snapshot, and long-term archive paths are mounted and tested.
8. Migration steps are documented and at least one dry run is validated in the lab.
9. UAT and production environments both pass validation on execution day.

***

### Out of Scope for MVP

- Full self-service portal features beyond deployment operations.
- Advanced role-based access control in the web UI.
- Full disaster recovery orchestration beyond backup and restore validation.
- Broad CI or release engineering beyond GitLab setup.
- Ongoing GitOps management of Docker services.

***

### Immediate Next Build Focus

Shortest path to a credible MVP, in order:

1. Jump host bootstrap script and autoprovision repo skeleton.
2. Python Web UI shell — status cards, inventory form, Ansible runner wiring.
3. Ansible playbooks for Docker VM — Phase B sequence.
4. Docker compose templates — PostgreSQL, Traefik, Dockhand, GitLab, SonarQube, ELK.
5. talosctl cluster bootstrap playbook and Cilium install.
6. Kubernetes manifests — cert-manager, Envoy Gateway, ArgoCD, Headlamp, WSO2.
7. Lab dry run — full sequence end to end.
8. UAT and production execution day.