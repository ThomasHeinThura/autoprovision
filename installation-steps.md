# Installation Steps

## Purpose

This document describes the full operator flow for installing and operating the MVP from the jump host.

It covers:

1. How to start from a fresh jump host
2. How to clone the repository and run the bootstrap script
3. How the Python web UI should behave after bootstrap
4. Which services should be installed directly and which should be GitOps-managed
5. How migration and lifecycle tasks should be triggered
6. What external storage is required for backup and retention

## Recommended Approach

The cleanest model is:

1. Bootstrap the jump host from GitHub
2. Use the Python web UI to collect environment data
3. Install the minimum direct dependencies first
4. Create GitLab repositories and push deployment sources there
5. Let Dockhand deploy as many Docker services as possible from GitLab
6. Keep only the bootstrap-critical services outside the GitOps path

### Direct install first

These services should be installed directly by Ansible or the Python web UI during bootstrap:

- Dockhand
- GitLab CE
- Shared PostgreSQL for Dockhand, GitLab, and SonarQube

Reason:

- GitLab must exist before other services can be deployed from Git
- PostgreSQL should be provisioned directly as the shared database backend for Dockhand, GitLab, and SonarQube
- Dockhand must exist before Dockhand can pull anything from GitLab

### Network and ingress baseline

- Use one shared Docker network for Dockhand, GitLab, SonarQube, PostgreSQL, and related services.
- Expose external HTTPS only through Traefik on port 443.

### GitOps after bootstrap

After GitLab and Dockhand are working, deploy these through Git repositories whenever possible:

- ELK stack
- SonarQube
- GitLab Runner
- ElastAlert2
- Kubernetes manifests or Helm values for ArgoCD
- WSO2 APIM Kubernetes YAML pushed to GitLab
- WSO2 IS Kubernetes YAML pushed to GitLab

## Step 1: SSH Into the Jump Host

SSH into the jump host from your local machine.

```bash
ssh <username>@<jump-host-ip>
```

Example:

```bash
ssh ubuntu@10.10.10.20
```

## Step 2: Clone the Repository

On the jump host, clone the automation repository.

```bash
git clone https://github.com/ThomasHeinThura/autoprovision.git
cd autoprovision
```

## Step 3: Run the Jump Host Bootstrap Script

After cloning the repo, run one bootstrap shell script from the project root.

Recommended entrypoint:

```bash
sh bootstrap-jumphost.sh
```

If the final repository uses a different script name, keep the same idea: one script should prepare the jump host end to end.

## What the Bootstrap Script Should Do

The bootstrap script should install and configure the jump host so the operator does not need to prepare dependencies manually.

### Required bootstrap tasks

1. Update OS packages
2. Install Git
3. Install Python 3 and pip
4. Create a Python virtual environment
5. Install Python dependencies for the web UI
6. Install Ansible
7. Install ansible-runner
8. Install any required system packages for SSH and build dependencies
9. Install cert or certificate helper dependencies if needed for setup tasks
10. Create application directories for logs, state, inventory, and generated files
11. Initialize the SQLite database
12. Start the Python web UI service on port 3000
13. Validate that external NFS or NAS archive storage can be mounted from the Docker VM

### Suggested directory layout on the jump host

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

## Expected Output From the Bootstrap Script

At the end of the script, print the jump host URL clearly so the operator can open it in a browser.

Example:

```text
Bootstrap complete
Open: http://<jump-host-ip>:3000/
```

The operator then copies that IP and opens:

```text
http://<jump-host-ip>:3000/
```

## Step 4: Open the Python Web UI

After bootstrap finishes:

1. Copy the jump host IP shown by the script
2. Open a browser
3. Visit `http://<jump-host-ip>:3000/`

The UI should become the main operating console for installation and updates.

## What the Python Web UI Should Show

The home page should show service cards with current state.

### Suggested status cards

- Headlamp status
- Docker host status
- Dockhand status
- Traefik status
- PostgreSQL status
- GitLab status
- GitLab Runner status
- Elasticsearch status
- Logstash status
- Kibana status
- Fleet status
- APM status
- SonarQube status
- ElastAlert2 status
- Talos cluster status
- cert-manager status
- Envoy Gateway status
- ArgoCD status
- WSO2 APIM status
- WSO2 IS status
- Migration status

### Status values

Each card should show one of these states:

- Not configured
- Ready to install
- Installing
- Installed
- Failed
- Needs update

## Step 5: Click a Service and Provide Inputs

When the operator clicks a service card such as Headlamp or Docker status, the UI should open a form.

### Common form inputs

- Target VM IP
- SSH username
- SSH password or SSH key reference
- Environment name: lab or production
- Required variables for that service

### Service-specific examples

For Docker host setup:

- Docker VM IP
- SSH username
- SSH password
- Domain
- Admin email

For Headlamp or Talos:

- Control plane IPs
- Worker IPs
- Cluster name

For WSO2:

- SQL Server host
- SQL username
- SQL password
- Domain names

For migration:

- Old Elasticsearch endpoint
- Old API Manager export location
- Snapshot repository path

## Step 6: Install by Running Ansible From the Web UI

When the operator clicks Install, the web UI should:

1. Validate required inputs
2. Save the environment and service variables
3. Generate runtime inventory and variable files
4. Launch ansible-runner for the matching playbook
5. Stream logs back to the browser
6. Update the service status when the playbook succeeds or fails

### Important behavior

The UI should not just store data. It should execute the playbooks and remember the last successful state for future updates.

## State and Variable Storage

Yes, the UI should remember `.env` values, runtime state, and the latest installation results.

### Recommended storage model

Use SQLite for:

- Environments
- Host inventory
- Service variables
- Job history
- Current status
- Last run timestamps
- Migration checkpoints

### Recommended handling for secrets

Do not store plain production secrets in Git.

Preferred options:

1. Store non-secret variables in SQLite
2. Store sensitive values encrypted at rest
3. Generate `.env` files only when needed for a deployment run
4. Pass secrets to Ansible or Dockhand at runtime

This gives the UI memory for updates without turning Git into a secret store.

## Step 7: Installation Order in the Web UI

The UI should guide the user through a fixed sequence.

### Phase A: Jump host and base setup

1. Bootstrap jump host from GitHub repo
2. Open Python web UI
3. Save lab or production environment values

### Phase B: Docker platform bootstrap

1. Install Docker host base packages
2. Install Docker CE
3. Install Dockhand
4. Install Traefik if managed separately
5. Mount external NFS or NAS backup and archive storage
6. Install PostgreSQL directly
7. Install GitLab directly

### Phase C: Git-first setup

1. Create GitLab group or projects
2. Let the Python web UI update the Docker Compose YAML templates with environment-specific values
3. Push docker compose repositories to GitLab
3. Push Helm values or Kubernetes manifests to GitLab
4. Push WSO2 APIM and WSO2 IS Kubernetes YAML to GitLab
4. Push Ansible roles and infrastructure code to GitLab
5. Connect Dockhand to GitLab

### Phase D: Docker service deployment from Git

Deploy as much as possible from GitLab through Dockhand:

1. ELK stack
2. SonarQube
3. GitLab Runner
4. ElastAlert2

### Phase E: Kubernetes rollout

1. Create Talos cluster through Headlamp
2. Install cert-manager
3. Install Envoy Gateway
4. Install OpenTelemetry Collector
5. Install ArgoCD
6. Install WSO2 APIM from GitLab-managed Kubernetes YAML
7. Install WSO2 IS from GitLab-managed Kubernetes YAML
8. Connect APIM and IS

### Phase F: Migration and policy tasks

1. Add index templates if needed
2. Configure tracing lifecycle before migration
3. Configure log and metrics retention and archive policies
4. Run Elasticsearch migration
5. Restore snapshots or migrate old data
6. Run API migration for WSO2
7. Create base ElastAlert2 rules

## Retention and Archive Policy

The lifecycle policy needs to be configured after base setup and before migration.

### Required retention targets

- Tracing: 7 days hot in Elasticsearch, then archive to external NFS or NAS for 2 to 3 years
- Basic logs: 1 year, then archive
- WSO2 logs from Logstash: 10 years
- OpenTelemetry metrics: 1 to 2 years
- OpenTelemetry container logs: 1 year

### Why this matters

- Tracing volume is high and should not stay in hot Elasticsearch for years
- WSO2 logs are long-lived operational records and need extended retention
- Metrics and container logs need separate retention policies from tracing

## GitLab and Dockhand Flow

The intended sequence should be:

1. Install GitLab directly first
2. Create repositories inside GitLab
3. Let the Python web UI render or update the compose templates for the selected environment
4. Push compose files there
4. Push WSO2 Kubernetes YAML there
4. Connect Dockhand to GitLab
5. Create Dockhand projects from Git repositories
6. Set runtime environment variables in Dockhand or through the API
7. Trigger deploy from Git source

### Important exception

GitLab itself cannot depend on GitLab for its first install.

That is why GitLab must be deployed directly first, then become the source of truth for later deployments.

## PostgreSQL and GitLab Direct Deployment

Your direction makes sense:

- GitLab should be installed directly first
- PostgreSQL can be installed directly first
- Other services should move to Git-based deployment wherever practical

This gives you a mostly GitOps model without creating a bootstrap deadlock.

## Status and Update Model

The UI should also support updates after initial install.

### Each service record should remember

- Current status
- Installed version
- Last playbook used
- Last input variables
- Last successful run time
- Last failed run time
- Log reference

### Update flow

1. Open a service card
2. Review current saved variables
3. Change only the needed values
4. Click Update or Re-run
5. The UI runs the Ansible playbook again
6. Status and logs are refreshed

## Migration Functions

The UI should provide dedicated actions for migration work.

### API migration

- Import or migrate WSO2 API definitions
- Track migration status separately from base install

### ELK migration

- Register snapshot repository
- Confirm external NFS or NAS archive mount is available
- Configure tracing lifecycle before migration starts
- Restore from old Elasticsearch backups
- Run compatibility checks
- Apply ILM lifecycle policies after restore

## Manual Configuration Boundaries

Not everything needs to be automated in the first version.

It is reasonable for these to stay manual if needed:

- Customer DNS record creation
- Firewall rule requests
- External SQL Server preparation
- External storage provisioning
- Customer SSL certificate handover if not using Let's Encrypt

The web UI can still show them as prerequisites or checklists.

## NFS Requirement for Dockhand Backups

Yes, you should request NFS or NAS storage for Dockhand-related backups.

Why it is needed:

- Elasticsearch snapshots need external storage
- Tracing archive for 2 to 3 years needs external storage
- GitLab backups should not live only on the local Docker VM
- PostgreSQL and application backups should survive host failure
- Dockhand-managed volumes need a backup target outside the main VM
- Long-term logs and metrics retention should not consume only local Docker VM disk

### Minimum request to the customer

- One reachable NFS or NAS endpoint
- Export path for backup storage
- Capacity sized for Elasticsearch snapshots, trace archives, long-term log retention, GitLab backups, registry growth, and database dumps
- Network access from the Docker platform VM

## Final Recommended Operator Flow

```text
1. SSH into jump host
2. git clone https://github.com/ThomasHeinThura/autoprovision.git
3. cd autoprovision
4. sh bootstrap-jumphost.sh
5. Open http://<jump-host-ip>:3000/
6. Enter environment, VM, and credential details
7. Install Docker platform prerequisites
8. Install GitLab and PostgreSQL directly
9. Create GitLab repos and push deployment code
10. Connect Dockhand to GitLab
11. Deploy remaining Docker services from Git
12. Build Talos cluster and Kubernetes services
13. Run ELK and API migration tasks
14. Use saved state for later updates and re-runs
```

## Recommendation

This design is sound for an MVP.

The main adjustment I would make is this:

- Use direct deployment only for the bootstrap-critical services
- Push everything else toward GitLab and Dockhand or GitLab and ArgoCD
- Use SQLite as the operational memory for state and variables
- Keep manual customer-owned infrastructure steps clearly separated

That gives you a workable first version without losing the long-term GitOps direction.