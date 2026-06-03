# Installation Steps

## Purpose

This document describes the full operator flow for installing and operating the MVP from the jump host.

It covers:

1. How to start from a fresh jump host.
2. How to clone the repository and run the bootstrap script.
3. How the Python web UI should behave after bootstrap.
4. Which services are installed directly from Ansible and which are managed via GitLab + ArgoCD.
5. How migration and lifecycle tasks should be triggered.
6. What external storage is required for backup and retention.

---

## Recommended Approach

The cleanest model is:

1. Bootstrap the jump host from GitHub.
2. Use the Python web UI to collect environment data (Lab, UAT, Production).
3. Install all Docker platform services once via Ansible in a fixed sequence.
4. Use GitLab only for Kubernetes manifests (WSO2 APIM and WSO2 IS) and ArgoCD applications.
5. Use talosctl + Helm (Cilium) + ArgoCD for Kubernetes deployment.

No GitOps for Docker. All Docker workloads are one-time Ansible deployments.

### Direct Ansible deployment (Docker platform)

These services are installed directly by Ansible or via the Python web UI:

- Docker CE and base OS prerequisites.
- Shared PostgreSQL for GitLab, SonarQube, and platform state.
- Traefik as the only external HTTPS entry point on port 443.
- Dockhand (Docker management and monitoring UI).
- GitLab CE, GitLab Runner, and GitLab Container Registry.
- SonarQube.
- ELK stack (Elasticsearch, Logstash, Kibana, Fleet/APM).
- ElastAlert2.

### Network and ingress baseline (Docker)

- Use one shared Docker network for Dockhand, GitLab, SonarQube, PostgreSQL, ELK, ElastAlert2, and related services.
- Expose external HTTPS only through Traefik on port 443.
- Traefik terminates TLS and routes to backend services on the shared network.

### GitLab + ArgoCD for Kubernetes

After GitLab is working and the Docker platform is online:

- Push Kubernetes manifests (WSO2 APIM and WSO2 IS) into GitLab repositories.
- Define ArgoCD `Application` objects pointing to those repositories/paths.
- Let ArgoCD sync APIM and IS deployments into the Talos cluster.

Kubernetes is Git-based; Docker is not.

---

## Step 1: SSH Into the Jump Host

SSH into the jump host from your local machine.

```bash
ssh <username>@<jump-host-ip>
```

Example:

```bash
ssh ubuntu@10.10.10.20
```

---

## Step 2: Clone the Repository

On the jump host, clone the automation repository.

```bash
git clone https://github.com/ThomasHeinThura/autoprovision.git
cd autoprovision
```

---

## Step 3: Run the Jump Host Bootstrap Script

After cloning the repo, run one bootstrap shell script from the project root.

Recommended entrypoint:

```bash
sh bootstrap-jumphost.sh
```

If the final repository uses a different script name, keep the same idea: one script prepares the jump host end to end.

### What the Bootstrap Script Should Do

The bootstrap script should install and configure the jump host so the operator does not prepare dependencies manually.

#### Required bootstrap tasks

1. Update OS packages.
2. Install Git.
3. Install Python 3 and pip.
4. Create a Python virtual environment.
5. Install Python dependencies for the web UI.
6. Install Ansible.
7. Install ansible-runner.
8. Install `talosctl` for Talos cluster management.
9. Install any required system packages for SSH and build dependencies.
10. Install certificate helper dependencies if needed.
11. Create application directories for logs, state, inventory, and generated files.
12. Initialize the SQLite database.
13. Start the Python web UI service on port 3000.
14. Validate that external NFS or NAS archive storage can be mounted from the Docker VM.

#### Suggested directory layout on the jump host

```text
~/autoprovision/
├── app/
├── ansible/
├── scripts/
├── data/
│   ├── state.db
│   ├── inventory/
│   ├── generated-env/
│   └── logs/
├── .venv/
└── bootstrap-jumphost.sh
```

### Expected Output From the Bootstrap Script

At the end of the script, print the jump host URL clearly so the operator can open it in a browser.

Example:

```text
Bootstrap complete
Open: http://<jump-host-ip>:3000/
```

The operator then opens:

```text
http://<jump-host-ip>:3000/
```

---

## Step 4: Open the Python Web UI

After bootstrap finishes:

1. Copy the jump host IP shown by the script.
2. Open a browser.
3. Visit `http://<jump-host-ip>:3000/`.

The UI becomes the main operating console for installation and updates.

### What the Python Web UI Should Show

The home page should show service cards with current state.

#### Suggested status cards

- Docker host status.
- Dockhand status.
- Traefik status.
- PostgreSQL status.
- GitLab status.
- GitLab Runner status.
- Elasticsearch status.
- Logstash status.
- Kibana status.
- Fleet status.
- APM status.
- SonarQube status.
- ElastAlert2 status.
- Talos cluster status.
- Cilium status.
- cert-manager status.
- Envoy Gateway status.
- ArgoCD status.
- Headlamp status.
- WSO2 APIM status.
- WSO2 IS status.
- Migration status.

#### Status values

Each card should show:

- Not configured.
- Ready to install.
- Installing.
- Installed.
- Failed.
- Needs update.

---

## Step 5: Click a Service and Provide Inputs

When the operator clicks a service card (e.g., Docker host, Talos cluster, WSO2), the UI opens a form.

### Common form inputs

- Target VM IP.
- SSH username.
- SSH password or SSH key reference.
- Environment name: `lab`, `uat`, or `prod`.
- Required variables for that service (domain, NFS paths, SQL endpoints, etc.).

### Service-specific examples

For Docker host setup:

- Docker VM IP.
- SSH username.
- SSH password.
- Public domain.
- Admin email.
- NFS/NAS export path.

For Talos cluster:

- Control plane IPs.
- Worker IPs.
- Cluster name.

For WSO2:

- SQL Server host.
- SQL username.
- SQL password.
- Domain names.
- GitLab repo/branch for WSO2 manifests.

For migration:

- Old Elasticsearch endpoint.
- Old API Manager export location.
- Snapshot repository path.

---

## Step 6: Install by Running Ansible From the Web UI

When the operator clicks **Install**, the web UI should:

1. Validate required inputs.
2. Save environment and service variables.
3. Generate runtime inventory and variable files.
4. Launch ansible-runner for the matching playbook.
5. Stream logs back to the browser.
6. Update the service status when the playbook succeeds or fails.

The UI is not just a form store; it executes playbooks and remembers the last successful state for future updates.

---

## State and Variable Storage

The UI should remember `.env` values, runtime state, and the latest installation results.

### Recommended storage model

Use SQLite for:

- Environments.
- Host inventory.
- Service variables.
- Job history.
- Current status.
- Last run timestamps.
- Migration checkpoints.

### Recommended handling for secrets

Do not store plain production secrets in Git.

Preferred options:

1. Store non-secret variables in SQLite.
2. Store sensitive values encrypted at rest.
3. Generate `.env` files on the Docker VM only when needed for deployment.
4. Pass secrets to Ansible at runtime.

---

## Step 7: Installation Order in the Web UI

The UI should guide the operator through a fixed sequence aligned with the MVP.

### Phase A: Jump host and base setup

1. Bootstrap jump host from GitHub repo.
2. Open Python web UI.
3. Save Lab/UAT/Prod environment values.

### Phase B: Docker platform deployment (Ansible-only)

For the selected environment (Lab, UAT, or Prod):

1. Install Docker host base packages.
2. Install Docker CE.
3. Create shared Docker network for platform services.
4. Install PostgreSQL (shared instance for GitLab, SonarQube, and platform state).
5. Install Traefik (HTTPS on port 443, with TLS and CORS configured).
6. Install Dockhand.
7. Install GitLab CE, GitLab Runner, and GitLab Container Registry (using the GitLab compose from your repo).
8. Install SonarQube.
9. Install ELK stack (using the `deviantony/docker-elk` compose as base).
10. Install ElastAlert2.

Each item is a button or step in the UI that triggers the corresponding Ansible playbook.

### Phase C: Kubernetes Git setup (GitLab + ArgoCD)

1. Create or select GitLab project(s) for Kubernetes manifests.
2. Push WSO2 APIM Kubernetes YAML to GitLab.
3. Push WSO2 IS Kubernetes YAML to GitLab.
4. Push ArgoCD `Application` manifests pointing to those paths.
5. Register ArgoCD to track those repositories.

This phase can be partially automated (e.g., the web UI pushes template manifests) or manual, but the end state is: WSO2 manifests and ArgoCD apps are in GitLab.

### Phase D1: Talos cluster + Cilium (three technical steps, one UI action)

From the web UI, the operator clicks **"Create Talos Cluster"**. Behind that button, Ansible should:

1. Run `talosctl gen config` with a patch that sets:
   ```yaml
   cluster:
     network:
       cni:
         name: none
     proxy:
       disabled: true
   ```
2. Run `talosctl apply-config` to all control plane and worker nodes using the generated configs.
3. Run `talosctl bootstrap` on the first control plane node.
4. Run `talosctl kubeconfig` to fetch kubeconfig onto the jump host.
5. Run `helm install cilium ...` with a Talos-safe `cilium-values.yaml` that enables `kubeProxyReplacement=true` and correct cgroup/capabilities.

From the operator perspective this is **one step**; internally it is three main technical stages: Talos config, Talos bootstrap, Cilium Helm install.

### Phase D2: Kubernetes platform services (Envoy and friends)

After Talos + Cilium is healthy, the operator clicks **"Install Kubernetes Platform"**. Ansible should:

1. Install cert-manager via Helm.
2. Install Envoy Gateway via Helm (Kubernetes ingress only).
3. Install ArgoCD and expose the ArgoCD UI.
4. Install Headlamp via the Sidero-provided Helm chart.
5. Install OpenTelemetry Collector.

### Phase E: WSO2 rollout via ArgoCD

1. Ensure ArgoCD applications for WSO2 APIM and WSO2 IS are defined and pointing to the GitLab repos from Phase C.
2. Trigger ArgoCD sync (or let it auto-sync) to deploy WSO2 APIM and WSO2 IS.
3. Expose APIM and IS via Envoy Gateway routes.

### Phase F: Migration and policy tasks

1. Add index templates if needed.
2. Configure tracing lifecycle before migration.
3. Configure log and metrics retention and archive policies.
4. Run Elasticsearch migration from old 8.14 to 9.1.4 via snapshot and restore.
5. Restore snapshots or migrate old data.
6. Run WSO2 application credential migration job.
7. Create base ElastAlert2 rules.

---

## Retention and Archive Policy

Lifecycle policy is configured **after base setup and before migration**.

### Required retention targets

- Tracing: 7 days hot in Elasticsearch, then archive to external NFS or NAS for 2–3 years.
- Basic logs: 1 year, then archive.
- WSO2 logs from Logstash: 10 years.
- OpenTelemetry metrics: 1–2 years.
- OpenTelemetry container logs: 1 year.

Why this matters:

- Tracing volume is high; keeping it hot for years is too expensive.
- WSO2 logs are long-lived operational records and require extended retention.
- Metrics and container logs have different value/volume characteristics and need their own policies.

---

## Docker Platform Flow (per environment)

For each environment (Lab, UAT, Prod):

1. Web UI collects Docker VM IP, SSH credentials, domain, and NFS path.
2. Ansible ensures the `autoprovision` repo is present on the Docker VM.
3. Ansible runs Docker compose stacks for PostgreSQL, Traefik, Dockhand, GitLab, SonarQube, ELK, and ElastAlert2 in fixed order.
4. All services attach to the shared Docker network and are reachable via Traefik on port 443.

No Dockhand Git integration is required or used.

---

## Status and Update Model

Each service card remembers:

- Current status.
- Installed version.
- Last playbook used.
- Last input variables.
- Last successful run time.
- Last failed run time.
- Log reference.

Update flow:

1. Open a service card.
2. Review current saved variables.
3. Change only what is required.
4. Click **Update** or **Re-run**.
5. Web UI runs the Ansible playbook again and refreshes status and logs.

---

## Migration Functions

The UI should provide dedicated actions for migration work.

### API migration (WSO2)

- Trigger a Python job that reads exported application credentials from the old APIM.
- Creates applications in 4.7.
- Calls `generate-keys` with old `clientId`/`clientSecret`.
- Stores results in SQLite.

### ELK migration

- Register snapshot repository.
- Confirm external NFS/NAS archive mount.
- Configure ILM for traces/logs/metrics before restore.
- Restore old indices and perform compatibility checks.

---

## Manual Configuration Boundaries

Reasonable to keep manual (customer side) in MVP:

- DNS record creation.
- Firewall rules.
- External SQL Server preparation.
- External storage (NFS/NAS) provisioning.
- Customer SSL certificate handover if not using Let’s Encrypt.

UI can expose these as prerequisite checklists, not automated steps.

---

## NFS Requirement for Backups and Archives

Request NFS or NAS storage for:

- Elasticsearch snapshots.
- Trace archives (2–3 years).
- GitLab backups.
- PostgreSQL and application backups.
- Long-term WSO2 log retention.

Minimum request to the customer:

- One reachable NFS/NAS endpoint.
- Export path for backup storage.
- Capacity sized for Elasticsearch snapshots, trace archives, WSO2 logs, GitLab backups, registry growth, and DB dumps.
- Network access from the Docker VM.

---

## Final Recommended Operator Flow

1. SSH into jump host.
2. `git clone https://github.com/ThomasHeinThura/autoprovision.git`.
3. `cd autoprovision`.
4. `sh bootstrap-jumphost.sh`.
5. Open `http://<jump-host-ip>:3000/`.
6. Enter environment, VM, and credential details.
7. Run Phase B to install Docker platform (PostgreSQL → Traefik → Dockhand → GitLab → SonarQube → ELK → ElastAlert2).
8. Run Phase C to push WSO2 manifests and ArgoCD apps to GitLab.
9. Run Phase D1 to build Talos cluster and install Cilium.
10. Run Phase D2 to install Kubernetes platform services (cert-manager, Envoy Gateway, ArgoCD, Headlamp, OTel).
11. Run Phase E to deploy WSO2 via ArgoCD.
12. Run Phase F to execute ELK and APIM migration tasks.
13. Use saved state for later updates and re-runs across Lab, UAT, and Production.