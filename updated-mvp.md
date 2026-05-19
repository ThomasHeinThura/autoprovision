# Updated MVP

## Objective

Deliver a workable MVP for infrastructure automation and migration that can be prepared in the lab, repeated in production, and operated through a simple control plane.

The MVP should prove five things:

1. Core infrastructure can be provisioned reliably.
2. Docker services can be deployed through Git-based workflows.
3. Kubernetes services can be deployed in a controlled sequence.
4. Observability and migration paths are functional.
5. Operations can be triggered from a lightweight Python web UI.

## Target Outcome

The MVP is successful when the team can:

1. Bootstrap a jump host, one Docker platform, and a Talos cluster.
2. Deploy Docker workloads from GitLab through Dokploy.
3. Deploy Kubernetes workloads through Ansible and ArgoCD.
4. Observe logs, metrics, traces, and alerts in Elasticsearch and Kibana.
5. Run the rollout from a Python web UI that captures inputs and executes Ansible playbooks.

## Environment Model

### Lab

- 1 jump host for Python Web UI, Ansible, and Omni
- 1 Docker VM for Dokploy-managed services
- 1 Talos control plane node
- 2 Talos worker nodes

### Production

- 1 jump host for Python Web UI, Ansible, and Omni
- 1 Docker VM for Dokploy-managed services
- 3 Talos control plane nodes
- 5 Talos worker nodes
- External NAS or NFS for snapshots and backups
- External SQL Server for WSO2 data services

## Deployment Strategy

Use a two-phase model for Docker services:

### Phase A: Bootstrap

Ansible installs the base platform directly:

1. Base OS prerequisites
2. Docker CE
3. Dokploy
4. GitLab CE and container registry
5. GitLab Runner
6. NFS mount and backup paths

This avoids the bootstrap problem where Dokploy would otherwise depend on a GitLab instance that does not exist yet.

### Phase B: GitOps for Docker

After GitLab is available, Dokploy pulls compose projects from GitLab and manages Docker service deployments.

Recommended pattern:

- Keep compose files in GitLab
- Keep secrets out of Git where possible
- Prefer Dokploy-managed environment variables over committed `.env.production` files

### Phase C: Kubernetes Rollout

Use Omni to create Talos clusters and use Ansible plus ArgoCD to apply Kubernetes components in a controlled order.

## MVP Scope

### 1. Platform Foundation

- Jump host with Python Web UI, Ansible, ansible-runner, and Omni
- Docker host with Dokploy and reverse proxy
- GitLab CE with registry and runner
- Talos cluster with Cilium networking
- External NFS mounted for backups and Elasticsearch snapshots

### 2. Docker Services

- Elasticsearch
- Logstash
- Kibana
- Fleet Server and APM
- GitLab CE and registry
- GitLab Runner
- SonarQube with PostgreSQL
- Stalwart SMTP
- ElastAlert2

### 3. Kubernetes Services

- cert-manager
- Envoy Gateway
- OpenTelemetry Collector
- ArgoCD
- WSO2 API Manager
- WSO2 Identity Server

### 4. Observability

The MVP must ingest and expose:

- Kubernetes metrics
- Kubernetes logs
- Netflow or Cilium Hubble flow data
- Tracing data from Envoy
- Alert events from ElastAlert2

Success condition:

- Data is searchable in Elasticsearch
- Dashboards are visible in Kibana
- At least one alert flow is verified end to end

### 5. Migration

- Elasticsearch migration from the old 8.14 environment to 9.1.4 using snapshot and restore
- Validation for index compatibility and reindex needs
- WSO2 API Manager migration into the new Kubernetes deployment
- Initial ElastAlert2 rule set created for the new environment

## Python Web UI MVP

The web UI is not a full platform product. It is an operations console for repeatable deployment.

### Required capabilities

- Inventory form for lab and production values
- Variable input for domains, IPs, credentials, NFS paths, and migration inputs
- One-click execution for individual Ansible steps
- Run-all flow for the standard deployment sequence
- Live job log streaming
- Job status and history

### Suggested stack

- FastAPI
- Jinja2 templates
- HTMX for lightweight interactivity
- SQLite for local job tracking
- WebSocket log streaming

## Delivery Sequence

### Prep Period

Complete in the lab before production execution:

1. Docker compose repositories
2. Helm values and Kubernetes manifests
3. Ansible inventory, roles, and playbooks
4. Python Web UI
5. Lab validation for each deployment phase

### Production Execution

1. Prepare jump host
2. Prepare Docker host
3. Install Dokploy, GitLab, runner, and NFS integration
4. Push deployment repositories to GitLab
5. Connect Dokploy to GitLab
6. Deploy Docker services from Git
7. Create Talos cluster
8. Deploy Kubernetes platform services
9. Deploy WSO2 services
10. Run data migration and final validation

## Definition of Done

The MVP is complete when all of the following are true:

1. Jump host can trigger the deployment flow from the web UI.
2. GitLab stores the compose, infrastructure, and Kubernetes deployment sources.
3. Dokploy deploys Docker workloads from GitLab successfully.
4. Talos cluster is running and reachable.
5. WSO2 APIM and WSO2 IS are deployed and connected to SQL Server.
6. Elasticsearch, Kibana, and alerting are functional.
7. Backup and snapshot paths are mounted and tested.
8. Migration steps are documented and at least one dry run is validated in the lab.

## Out of Scope for MVP

- Full self-service portal features beyond deployment operations
- Advanced role-based access control in the web UI
- Full disaster recovery orchestration beyond backup and restore validation
- Broad CI or release engineering beyond what is required for GitLab and GitOps deployment

## Immediate Next Build Focus

If the team wants the shortest path to a credible MVP, build in this order:

1. GitLab bootstrap and Dokploy connection
2. ELK stack deployment from Git
3. Python Web UI execution flow
4. Talos cluster creation
5. ArgoCD and WSO2 deployment
6. Migration rehearsal and final validation