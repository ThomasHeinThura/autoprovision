# 📋 Final MVP — Project Scope & Process Document

***

## 1. Project Overview

| Item            | Detail                                             |
| --------------- | -------------------------------------------------- |
| **Project**     | Infrastructure Automation & Migration              |
| **Prep Period** | May 19 – May 31 (Lab + script development)         |
| **Execution**   | June 1 – June 11 (11 working days)                 |
| **Delivery**    | Automated provisioning via Python Web UI → Ansible |
| **Day-2 Ops**   | Dokploy (Docker) / ArgoCD (K8s) / Omni (Cluster)   |

***

## 2. Infrastructure

### 2.1 Production (10 VMs + External)

| VM           | Role                                | Spec                       | OS       |
| ------------ | ----------------------------------- | -------------------------- | -------- |
| VM-1,2,3     | Talos Control Plane × 3             | 4 vCPU / 8GB / 200GB       | Talos OS |
| VM-4,5,6,7,8 | Talos Worker × 5                    | 8 vCPU / 32GB / 500GB      | Talos OS |
| VM-9         | Jump Host (Omni + Web UI + Ansible) | 4 vCPU / 8GB / 100GB       | Linux    |
| VM-10        | All Docker Services + Dokploy       | 24 vCPU / 96GB / 1TB + NFS | Linux    |
| External     | NAS / NFS Storage                   | Customer-provided          | —        |
| External     | SQL Server                          | Customer-provided          | —        |

### 2.2 Lab (5 VMs)

| VM     | Role                                | Spec                  |
| ------ | ----------------------------------- | --------------------- |
| VM-1   | Talos CP × 1                        | 4 vCPU / 8GB / 200GB  |
| VM-2,3 | Talos Worker × 2                    | 8 vCPU / 32GB / 500GB |
| VM-4   | Jump Host (Omni + Web UI + Ansible) | 4 vCPU / 8GB / 100GB  |
| VM-5   | All Docker Services + Dokploy       | 24 vCPU / 96GB / 1TB  |

### 2.3 Docker Resource Limits (VM-10: 24c / 96GB)

| Service                | CPU Rsv | CPU Lmt | MEM Rsv | MEM Lmt        |
| ---------------------- | ------- | ------- | ------- | -------------- |
| Elasticsearch          | 6       | 8       | 32G     | 40G            |
| Logstash               | 0.5     | 1       | 1G      | 2G             |
| Kibana                 | 0.5     | 1       | 1G      | 2G             |
| Fleet Server           | 0.5     | 1       | 512M    | 1G             |
| APM Server             | 0.5     | 1       | 1G      | 2G             |
| GitLab CE + Registry   | 2       | 4       | 8G      | 12G            |
| GitLab Runner          | 1       | 2       | 2G      | 4G             |
| SonarQube              | 1       | 2       | 4G      | 6G             |
| PostgreSQL (SonarQube) | 0.5     | 1       | 1G      | 2G             |
| Stalwart SMTP          | 0.25    | 0.5     | 256M    | 512M           |
| ElastAlert2            | 0.25    | 0.5     | 512M    | 1G             |
| Dokploy + Traefik      | —       | 1       | —       | 1G             |
| **TOTAL**              | **13**  | **23**  | **52G** | **73.5G**      |
| **OS + Cache**         | —       | —       | —       | **22.5G free** |

***

## 3. Architecture

### 3.1 Overall

    ┌──────────────────────────────────────────────────────────────┐
    │                                                               │
    │  VM-9: JUMP HOST                                              │
    │  ┌─────────────────────────────────────────────────────────┐ │
    │  │  Python Web UI (FastAPI)                                 │ │
    │  │  Ansible + ansible-runner                                │ │
    │  │  Omni (manages Talos cluster)                            │ │
    │  └──────────┬──────────────────────────┬───────────────────┘ │
    │             │ SSH                       │ Omni/gRPC           │
    │             ▼                          ▼                     │
    │  ┌──────────────────────┐   ┌──────────────────────────┐    │
    │  │ VM-10: DOCKER VM      │   │ TALOS KUBERNETES CLUSTER  │    │
    │  │ 24c / 96GB / 1TB      │   │                          │    │
    │  │                       │   │ CP: VM-1,2,3             │    │
    │  │ Dokploy (manages all) │   │ WR: VM-4,5,6,7,8        │    │
    │  │ ├─ Traefik (SSL/RP)  │   │                          │    │
    │  │ ├─ Elasticsearch      │   │ ┌──────────────────────┐ │    │
    │  │ ├─ Logstash           │◄──┤ │ Cilium CNI + Hubble  │ │    │
    │  │ ├─ Kibana             │   │ │ Envoy Gateway        │ │    │
    │  │ ├─ Fleet + APM        │   │ │ cert-manager (SSL)   │ │    │
    │  │ ├─ GitLab + Registry  │   │ │ OTel Collector       │ │    │
    │  │ ├─ GitLab Runner      │   │ │ ArgoCD               │ │    │
    │  │ ├─ SonarQube + PG     │   │ │ WSO2 APIM ←→ SQL    │ │    │
    │  │ ├─ Stalwart SMTP      │   │ │ WSO2 IS   ←→ SQL    │ │    │
    │  │ ├─ ElastAlert2        │   │ └──────────────────────┘ │    │
    │  │ └─ NFS → External NAS │   │                          │    │
    │  └──────────────────────┘   └──────────────────────────┘    │
    │                                                               │
    └──────────────────────────────────────────────────────────────┘

### 3.2 SSL Strategy

| Platform      | Tool                                     | Method                          |
| ------------- | ---------------------------------------- | ------------------------------- |
| Docker VM     | Traefik (via Dokploy)                    | Let's Encrypt ACME auto-renewal |
| Kubernetes    | Envoy Gateway + cert-manager             | ClusterIssuer + Let's Encrypt   |
| Public access | Customer-provided external SSL if needed | PEM cert + key                  |

### 3.3 Observability Pipelines

| # | Pipeline    | Source                     | Collector                          | ES Index           |
| - | ----------- | -------------------------- | ---------------------------------- | ------------------ |
| 1 | Netflow     | Cilium Hubble (OBI)        | OTel `hubble` receiver             | `netflow-cilium-*` |
| 2 | Tracing     | Envoy Gateway OTel         | OTel `otlp` receiver               | `traces-apm-*`     |
| 3 | K8s Metrics | Kubelet, K8s API           | OTel `kubeletstats`, `k8s_cluster` | `metrics-k8s-*`    |
| 4 | K8s Logs    | Container stdout/stderr    | OTel `filelog`                     | `logs-k8s-*`       |
| 5 | WSO2 Logs   | WSO2 APIM Filebeat sidecar | Logstash                           | `logs-wso2-*`      |
| 6 | Alerts      | ElastAlert2                | Direct to ES                       | `elastalert_*`     |

### 3.4 Backup Strategy

| What                   | Method                    | Destination           | Managed By        |
| ---------------------- | ------------------------- | --------------------- | ----------------- |
| ES data (cold/frozen)  | ILM lifecycle (3-day hot) | NFS → External NAS    | Elasticsearch ILM |
| ES snapshots           | Scheduled snapshot        | NFS → External NAS    | ES cron           |
| GitLab repos + config  | gitlab-backup create      | NFS or S3 via Dokploy | Dokploy           |
| PostgreSQL (SonarQube) | pg\_dump scheduled        | NFS or S3 via Dokploy | Dokploy           |
| Docker volumes         | Volume backup             | NFS or S3 via Dokploy | Dokploy           |

***

## 4. Python Web UI — Complete Specification

### 4.1 Tech Stack

| Component         | Technology                                              |
| ----------------- | ------------------------------------------------------- |
| Backend           | FastAPI (Python)                                        |
| Frontend          | Jinja2 templates + HTMX (lightweight, no SPA framework) |
| Ansible execution | ansible-runner (Python library)                         |
| Job tracking      | SQLite (local on Jump Host)                             |
| Live logs         | WebSocket (FastAPI → browser)                           |
| Auth              | Basic auth (single admin user)                          |

### 4.2 Pages & Flow

    ┌─────────────────────────────────────────────────────────┐
    │  PYTHON WEB UI — http://jumphost:8080                    │
    │                                                           │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │  🏠 DASHBOARD                                        │ │
    │  │  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐           │ │
    │  │  │Jump   │ │Docker │ │Talos  │ │Jobs   │           │ │
    │  │  │Host   │ │VM     │ │Cluster│ │History│           │ │
    │  │  │ ✅    │ │ ✅    │ │ ⏳    │ │ 8/13  │           │ │
    │  │  └───────┘ └───────┘ └───────┘ └───────┘           │ │
    │  └─────────────────────────────────────────────────────┘ │
    │                                                           │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │  📋 INVENTORY                                        │ │
    │  │                                                       │ │
    │  │  Environment: [Lab ▼] / [Production ▼]               │ │
    │  │                                                       │ │
    │  │  Jump Host IP:     [____________]                    │ │
    │  │  Docker VM IP:     [____________]                    │ │
    │  │  Docker VM SSH:    [key ▼] / [password ▼]            │ │
    │  │  Talos CP IPs:     [______] [______] [______]        │ │
    │  │  Talos WR IPs:     [______] [______] [______]        │ │
    │  │                    [______] [______]                  │ │
    │  │  NFS Server:       [____________]                    │ │
    │  │  NFS Export Path:  [____________]                    │ │
    │  │  SQL Server IP:    [____________]                    │ │
    │  │  SQL Username:     [____________]                    │ │
    │  │  SQL Password:     [____________]                    │ │
    │  │  Domain:           [____________]                    │ │
    │  │  Gmail Account:    [____________]                    │ │
    │  │  Gmail App Pass:   [____________]                    │ │
    │  │  Old ES 8.14 IP:   [____________]                    │ │
    │  │  Old WSO2 Backup:  [____________]                    │ │
    │  │                                                       │ │
    │  │  [💾 Save Inventory]                                 │ │
    │  └─────────────────────────────────────────────────────┘ │
    │                                                           │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │  ⚙️ PROVISIONING STEPS                               │ │
    │  │                                                       │ │
    │  │  ── PHASE 1: JUMP HOST SETUP ──                      │ │
    │  │  Step 1:  Install Omni            [▶ Run] [✅ Done]  │ │
    │  │                                                       │ │
    │  │  ── PHASE 2: DOCKER VM SETUP ──                      │ │
    │  │  Step 2:  Base OS Setup           [▶ Run] [—]        │ │
    │  │  Step 3:  Install Docker CE       [▶ Run] [—]        │ │
    │  │  Step 4:  Install Dokploy         [▶ Run] [—]        │ │
    │  │  Step 5:  Mount NFS               [▶ Run] [—]        │ │
    │  │  Step 6:  Deploy ELK Stack        [▶ Run] [—]        │ │
    │  │  Step 7:  Configure ELK           [▶ Run] [—]        │ │
    │  │           (ILM, indices, alerts,                      │ │
    │  │            snapshot repo, templates)                   │ │
    │  │  Step 8:  Deploy GitLab + Registry [▶ Run] [—]       │ │
    │  │  Step 9:  Deploy GitLab Runner    [▶ Run] [—]        │ │
    │  │  Step 10: Deploy Stalwart SMTP    [▶ Run] [—]        │ │
    │  │  Step 11: Deploy SonarQube        [▶ Run] [—]        │ │
    │  │  Step 12: Deploy ElastAlert2      [▶ Run] [—]        │ │
    │  │                                                       │ │
    │  │  ── PHASE 3: KUBERNETES CLUSTER ──                   │ │
    │  │  Step 13: Install Talos Cluster   [▶ Run] [—]        │ │
    │  │           (via Omni + Cilium CNI)                     │ │
    │  │  Step 14: Install cert-manager    [▶ Run] [—]        │ │
    │  │  Step 15: Install Envoy Gateway   [▶ Run] [—]        │ │
    │  │  Step 16: Install OTel Collector  [▶ Run] [—]        │ │
    │  │           (netflow + tracing +                        │ │
    │  │            k8s metrics/logs)                           │ │
    │  │  Step 17: Install ArgoCD          [▶ Run] [—]        │ │
    │  │  Step 18: Install WSO2 APIM      [▶ Run] [—]        │ │
    │  │  Step 19: Install WSO2 IS        [▶ Run] [—]        │ │
    │  │  Step 20: Connect APIM ↔ IS      [▶ Run] [—]        │ │
    │  │                                                       │ │
    │  │  ── PHASE 4: MIGRATION ──                            │ │
    │  │  Step 21: Migrate ES 8.14→9.1.4  [▶ Run] [—]        │ │
    │  │           (snapshot + restore)                        │ │
    │  │  Step 22: Migrate WSO2 APIM      [▶ Run] [—]        │ │
    │  │  Step 23: Create ElastAlert Rules [▶ Run] [—]        │ │
    │  │                                                       │ │
    │  │  ── PHASE 5: FINALIZE ──                             │ │
    │  │  Step 24: Clone & Push Repos      [▶ Run] [—]        │ │
    │  │           to GitLab                                   │ │
    │  │                                                       │ │
    │  │  [▶▶ Run All Phases]                                 │ │
    │  └─────────────────────────────────────────────────────┘ │
    │                                                           │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │  📄 JOB LOGS                                         │ │
    │  │                                                       │ │
    │  │  Job: Step 6 - Deploy ELK Stack                      │ │
    │  │  Status: ⏳ Running                                   │ │
    │  │  Started: 2026-06-03 10:15:00                        │ │
    │  │  ┌─────────────────────────────────────────────┐     │ │
    │  │  │ PLAY [Deploy ELK Stack] *****                │     │ │
    │  │  │                                              │     │ │
    │  │  │ TASK [Pull elasticsearch:9.1.4] ****         │     │ │
    │  │  │ changed: [192.168.1.10]                      │     │ │
    │  │  │                                              │     │ │
    │  │  │ TASK [Start elasticsearch container] ****    │     │ │
    │  │  │ changed: [192.168.1.10]                      │     │ │
    │  │  │                                              │     │ │
    │  │  │ TASK [Wait for ES health] ****               │     │ │
    │  │  │ ok: [192.168.1.10] => green                  │     │ │
    │  │  │ ...                                          │     │ │
    │  │  └─────────────────────────────────────────────┘     │ │
    │  └─────────────────────────────────────────────────────┘ │
    │                                                           │
    │  ┌─────────────────────────────────────────────────────┐ │
    │  │  📜 JOB HISTORY                                      │ │
    │  │                                                       │ │
    │  │  #  │ Step                  │ Status │ Duration │ Time│ │
    │  │  1  │ Install Omni          │ ✅     │ 3m 22s  │ ... │ │
    │  │  2  │ Base OS Setup         │ ✅     │ 5m 10s  │ ... │ │
    │  │  3  │ Install Docker CE     │ ✅     │ 2m 45s  │ ... │ │
    │  │  4  │ Install Dokploy       │ ✅     │ 4m 18s  │ ... │ │
    │  │  5  │ Mount NFS             │ ✅     │ 1m 05s  │ ... │ │
    │  │  6  │ Deploy ELK Stack      │ ⏳     │ —       │ ... │ │
    │  │  7  │ Configure ELK         │ —      │ —       │ ... │ │
    │  │  ...│                       │        │         │     │ │
    │  └─────────────────────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────────┘

### 4.3 API Endpoints

| Method | Endpoint                   | Purpose                        |
| ------ | -------------------------- | ------------------------------ |
| GET    | `/`                        | Dashboard                      |
| GET    | `/inventory`               | Inventory form                 |
| POST   | `/inventory/save`          | Save inventory to YAML         |
| GET    | `/provision`               | Provisioning steps page        |
| POST   | `/provision/run/{step_id}` | Trigger single step            |
| POST   | `/provision/run-all`       | Trigger all steps sequentially |
| GET    | `/jobs/{job_id}/status`    | Job status (polling)           |
| WS     | `/ws/jobs/{job_id}/logs`   | Live log stream (WebSocket)    |
| GET    | `/history`                 | Job history page               |

### 4.4 Step → Ansible Mapping

| Step                        | Playbook                   | Target           | Variables from Inventory                    |
| --------------------------- | -------------------------- | ---------------- | ------------------------------------------- |
| **Phase 1: Jump Host**      |                            |                  |                                             |
| 1. Install Omni             | `01-install-omni.yml`      | localhost (VM-9) | —                                           |
| **Phase 2: Docker VM**      |                            |                  |                                             |
| 2. Base OS Setup            | `02-base-setup.yml`        | VM-10            | `docker_vm_ip`, `ssh_key`                   |
| 3. Install Docker CE        | `03-install-docker.yml`    | VM-10            | `docker_vm_ip`                              |
| 4. Install Dokploy          | `04-install-dokploy.yml`   | VM-10            | `docker_vm_ip`, `domain`, `admin_email`     |
| 5. Mount NFS                | `05-mount-nfs.yml`         | VM-10            | `nfs_server`, `nfs_path`                    |
| 6. Deploy ELK Stack         | `06-deploy-elk.yml`        | VM-10            | `domain`, `es_heap: 20g`                    |
| 7. Configure ELK            | `07-configure-elk.yml`     | VM-10            | `nfs_path`, `ilm_hot_days: 3`               |
| 8. Deploy GitLab + Registry | `08-deploy-gitlab.yml`     | VM-10            | `domain`, `admin_email`, `smtp_*`           |
| 9. Deploy GitLab Runner     | `09-deploy-runner.yml`     | VM-10            | `gitlab_url`, `runner_token`                |
| 10. Deploy Stalwart SMTP    | `10-deploy-smtp.yml`       | VM-10            | `gmail_account`, `gmail_app_pass`, `domain` |
| 11. Deploy SonarQube        | `11-deploy-sonarqube.yml`  | VM-10            | `domain`                                    |
| 12. Deploy ElastAlert2      | `12-deploy-elastalert.yml` | VM-10            | `es_host`                                   |
| **Phase 3: Kubernetes**     |                            |                  |                                             |
| 13. Install Talos Cluster   | `13-talos-cluster.yml`     | Omni → VM-1→8    | `cp_ips`, `wr_ips`, `cluster_name`          |
| 14. Install cert-manager    | `14-cert-manager.yml`      | K8s              | `domain`, `le_email`                        |
| 15. Install Envoy Gateway   | `15-envoy-gateway.yml`     | K8s              | `domain`                                    |
| 16. Install OTel Collector  | `16-otel-collector.yml`    | K8s              | `es_host`, `es_port`                        |
| 17. Install ArgoCD          | `17-argocd.yml`            | K8s              | `gitlab_url`, `domain`                      |
| 18. Install WSO2 APIM       | `18-wso2-apim.yml`         | K8s              | `sql_ip`, `sql_user`, `sql_pass`, `domain`  |
| 19. Install WSO2 IS         | `19-wso2-is.yml`           | K8s              | `sql_ip`, `sql_user`, `sql_pass`, `domain`  |
| 20. Connect APIM ↔ IS       | `20-wso2-connect.yml`      | K8s              | `apim_url`, `is_url`                        |
| **Phase 4: Migration**      |                            |                  |                                             |
| 21. Migrate ES 8.14 → 9.1.4 | `21-migrate-es.yml`        | VM-10            | `old_es_ip`, `old_es_port`                  |
| 22. Migrate WSO2 APIM       | `22-migrate-wso2.yml`      | K8s              | `old_wso2_backup_path`                      |
| 23. Create ElastAlert Rules | `23-elastalert-rules.yml`  | VM-10            | `es_host`                                   |
| **Phase 5: Finalize**       |                            |                  |                                             |
| 24. Clone & Push to GitLab  | `24-clone-repos.yml`       | VM-9 → VM-10     | `gitlab_url`, `repo_names`                  |

***

## 5. Provisioning Steps — Detailed

### Phase 1: Jump Host Setup

#### Step 1: Install Omni on Jump Host

    Target: VM-9 (localhost)
    Purpose: Install Omni to manage Talos cluster lifecycle

    Tasks:
    ├── Install Omni dependencies
    ├── Download and install Omni
    ├── Configure Omni (cluster endpoint, auth)
    ├── Start Omni service (systemd or Docker)
    ├── Verify Omni is running and accessible
    └── Output: Omni URL + credentials

### Phase 2: Docker VM Setup

#### Step 2: Base OS Setup

    Target: VM-10
    Purpose: Prepare OS for Docker workloads

    Tasks:
    ├── Update packages (apt/yum update)
    ├── Install base tools (curl, wget, htop, jq, net-tools)
    ├── Configure NTP/chrony
    ├── Set sysctl (vm.max_map_count=262144 for ES)
    ├── Configure firewall rules
    ├── Set hostname
    └── Reboot if kernel update

#### Step 3: Install Docker CE

    Target: VM-10
    Tasks:
    ├── Add Docker repository
    ├── Install Docker CE + Docker Compose plugin
    ├── Configure Docker daemon (log rotation, storage driver)
    ├── Add user to docker group
    ├── Start and enable Docker service
    └── Verify: docker run hello-world

#### Step 4: Install Dokploy

    Target: VM-10
    Tasks:
    ├── Run Dokploy installer
    ├── Configure admin account (email + password)
    ├── Configure base domain
    ├── Traefik auto-configured by Dokploy
    ├── Verify Dokploy UI accessible
    └── Output: Dokploy URL + admin credentials

#### Step 5: Mount NFS

    Target: VM-10
    Tasks:
    ├── Install nfs-common / nfs-utils
    ├── Create mount points:
    │   ├── /mnt/nfs/elk-snapshots
    │   ├── /mnt/nfs/elk-cold
    │   ├── /mnt/nfs/gitlab-backups
    │   └── /mnt/nfs/dokploy-backups
    ├── Add to /etc/fstab (persistent mount)
    ├── Mount all NFS shares
    └── Verify: write test file to each mount

#### Step 6: Deploy ELK Stack

    Target: VM-10
    Tasks:
    ├── Create docker-compose-elk.yml with resource limits
    ├── Pull images:
    │   ├── elasticsearch:9.1.4
    │   ├── logstash:9.1.4
    │   ├── kibana:9.1.4
    │   ├── elastic/fleet-server
    │   └── elastic/apm-server
    ├── Configure elasticsearch.yml (cluster name, paths, security)
    ├── Configure ES JVM: -Xms20g -Xmx20g
    ├── Configure logstash pipeline (WSO2 filebeat input → ES output)
    ├── Configure kibana.yml (ES connection, server host)
    ├── Start all containers
    ├── Wait for ES cluster health: green
    ├── Verify Kibana accessible
    └── Register with Dokploy for domain routing

#### Step 7: Configure ELK

    Target: VM-10
    Tasks:
    ├── Create index templates:
    │   ├── netflow-cilium-*
    │   ├── traces-apm-*
    │   ├── metrics-k8s-*
    │   ├── logs-k8s-*
    │   ├── logs-wso2-*
    │   └── elastalert_*
    ├── Create ILM policy:
    │   ├── hot: 3 days (local SSD)
    │   ├── warm: 7 days (shrink + forcemerge)
    │   ├── cold: 30 days (NFS searchable snapshot)
    │   └── delete: 90 days (configurable)
    ├── Create ES snapshot repository → /mnt/nfs/elk-snapshots
    ├── Create snapshot schedule (every 6 hours)
    ├── Create ElastAlert2 indices:
    │   ├── elastalert_status
    │   ├── elastalert_status_status
    │   ├── elastalert_status_error
    │   ├── elastalert_status_past
    │   └── elastalert_status_silence
    ├── Configure Fleet Server enrollment
    ├── Configure APM Server
    └── Verify: all indices created, ILM policy attached

#### Step 8: Deploy GitLab + Registry

    Target: VM-10
    Tasks:
    ├── Create docker-compose-gitlab.yml with resource limits
    ├── Pull gitlab/gitlab-ce image
    ├── Configure gitlab.rb:
    │   ├── external_url (domain)
    │   ├── SMTP settings (Stalwart relay)
    │   ├── Registry enabled + domain
    │   ├── Admin account (root + password)
    │   └── Backup settings
    ├── Start GitLab container
    ├── Wait for GitLab healthy (can take 5+ minutes)
    ├── Verify admin login
    ├── Verify registry push/pull
    ├── Register with Dokploy for domain routing
    └── Output: GitLab URL + admin credentials + registry URL

#### Step 9: Deploy GitLab Runner

    Target: VM-10
    Tasks:
    ├── Pull gitlab/gitlab-runner image
    ├── Start runner container with resource limits
    ├── Register runner with GitLab:
    │   ├── GitLab URL
    │   ├── Registration token
    │   ├── Executor: docker
    │   └── Default image: alpine:latest
    ├── Verify runner appears in GitLab → Admin → Runners
    └── Test: create test project, run .gitlab-ci.yml

#### Step 10: Deploy Stalwart SMTP

    Target: VM-10
    Tasks:
    ├── Pull stalwartlabs/mail-server image
    ├── Configure Stalwart:
    │   ├── Relay mode → Gmail SMTP (smtp.gmail.com:587)
    │   ├── Gmail account + app password
    │   ├── Domain configuration
    │   └── TLS settings
    ├── Start container with resource limits
    ├── Register with Dokploy for domain routing
    ├── Verify: send test email
    └── Output: SMTP host + port for other services

#### Step 11: Deploy SonarQube

    Target: VM-10
    Tasks:
    ├── Start PostgreSQL container (SonarQube DB)
    ├── Pull sonarqube:community image
    ├── Configure JVM opts:
    │   ├── SONAR_SEARCH_JAVAOPTS: -Xms512m -Xmx1g
    │   ├── SONAR_CE_JAVAOPTS: -Xms512m -Xmx1g
    │   └── SONAR_WEB_JAVAOPTS: -Xms256m -Xmx512m
    ├── Start SonarQube container with resource limits
    ├── Wait for SonarQube healthy
    ├── Register with Dokploy for domain routing
    ├── Verify: admin login (admin/admin → change password)
    └── Output: SonarQube URL

#### Step 12: Deploy ElastAlert2

    Target: VM-10
    Tasks:
    ├── Pull elastalert2 image
    ├── Configure elastalert.yml:
    │   ├── ES host + port
    │   ├── Rules folder
    │   ├── Alert index: elastalert_status
    │   └── Run frequency
    ├── Create base rules directory (empty, rules added in Step 23)
    ├── Start container with resource limits
    ├── Verify: connected to ES, writing to elastalert_status
    └── Output: ElastAlert2 status

### Phase 3: Kubernetes Cluster

#### Step 13: Install Talos Cluster via Omni

    Target: Omni (VM-9) → Talos nodes (VM-1→8)
    Tasks:
    ├── Generate Talos machine configs via Omni:
    │   ├── Control plane config (VM-1,2,3)
    │   └── Worker config (VM-4,5,6,7,8)
    ├── Apply configs to nodes via Omni
    ├── Bootstrap cluster
    ├── Install Cilium CNI:
    │   ├── Enable Hubble (OBI) for L3/L4/L7 observability
    │   ├── Enable Hubble UI
    │   └── Configure Cilium network policy
    ├── Wait for all nodes Ready
    ├── Export kubeconfig
    ├── Verify: kubectl get nodes (3 CP + 5 WR ready)
    └── Output: kubeconfig file, cluster status

#### Step 14: Install cert-manager

    Target: K8s cluster
    Tasks:
    ├── Install cert-manager via Helm
    ├── Create ClusterIssuer:
    │   ├── Let's Encrypt staging (for testing)
    │   └── Let's Encrypt production
    ├── Verify: ClusterIssuer ready
    └── Output: cert-manager status

#### Step 15: Install Envoy Gateway

    Target: K8s cluster
    Tasks:
    ├── Install Envoy Gateway via Helm
    ├── Configure GatewayClass
    ├── Create Gateway resource with HTTPS listener
    ├── Configure cert-manager integration (auto TLS)
    ├── Create HTTPRoute for services
    ├── Verify: gateway has external IP, TLS working
    └── Output: Gateway IP, configured routes

#### Step 16: Install OTel Collector

    Target: K8s cluster
    Tasks:
    ├── Install OTel Collector as DaemonSet via Helm
    ├── Configure receivers:
    │   ├── hubble (Cilium netflow → netflow-cilium-*)
    │   ├── otlp gRPC:4317 + HTTP:4318 (Envoy traces → traces-apm-*)
    │   ├── kubeletstats (node/pod metrics → metrics-k8s-*)
    │   ├── k8s_cluster (K8s API metrics → metrics-k8s-*)
    │   ├── filelog /var/log/pods (container logs → logs-k8s-*)
    │   └── k8sobjects (K8s events → logs-k8s-*)
    ├── Configure processors:
    │   ├── k8sattributes (enrich with pod/ns/node labels)
    │   ├── batch (reduce API calls to ES)
    │   └── resource (add cluster name metadata)
    ├── Configure exporters:
    │   └── elasticsearch (ES host on VM-10, per-pipeline index)
    ├── Verify: data flowing into each ES index
    │   ├── Check: netflow-cilium-* has documents
    │   ├── Check: traces-apm-* has documents
    │   ├── Check: metrics-k8s-* has documents
    │   └── Check: logs-k8s-* has documents
    └── Output: OTel Collector status, index document counts

#### Step 17: Install ArgoCD

    Target: K8s cluster
    Tasks:
    ├── Install ArgoCD via Helm
    ├── Configure admin account
    ├── Add GitLab as repository source:
    │   ├── GitLab URL
    │   ├── SSH key or token auth
    │   └── Repo paths for Helm charts
    ├── Create ArgoCD Application resources
    ├── Configure auto-sync policy
    ├── Verify: ArgoCD UI accessible, repos synced
    └── Output: ArgoCD URL + admin credentials

#### Step 18: Install WSO2 APIM

    Target: K8s cluster
    Tasks:
    ├── Create namespace: wso2
    ├── Create K8s secrets (SQL credentials)
    ├── Deploy WSO2 APIM via Helm/manifests:
    │   ├── Configure SQL Server connector
    │   ├── Set JVM: -Xms2g -Xmx4g -XX:MaxMetaspaceSize=1g
    │   ├── Resource requests: 2 CPU / 4Gi
    │   ├── Resource limits: 4 CPU / 8Gi
    │   └── Configure domain + Envoy HTTPRoute
    ├── Wait for pods ready
    ├── Verify: APIM publisher + devportal accessible
    └── Output: APIM URLs

#### Step 19: Install WSO2 IS

    Target: K8s cluster
    Tasks:
    ├── Deploy WSO2 IS via Helm/manifests:
    │   ├── Configure SQL Server connector
    │   ├── Set JVM: -Xms1g -Xmx2g -XX:MaxMetaspaceSize=512m
    │   ├── Resource requests: 1 CPU / 2Gi
    │   ├── Resource limits: 2 CPU / 4Gi
    │   └── Configure domain + Envoy HTTPRoute
    ├── Wait for pods ready
    ├── Verify: IS console accessible
    └── Output: IS URL

#### Step 20: Connect APIM ↔ IS

    Target: K8s cluster
    Tasks:
    ├── Configure WSO2 APIM Key Manager → WSO2 IS
    ├── Configure WSO2 IS as Identity Provider in APIM
    ├── Test: Create API in APIM → authenticate via IS token
    ├── Verify: Token generation + API call succeeds
    └── Output: Integration status

### Phase 4: Migration

#### Step 21: Migrate ES 8.14 → 9.1.4

    Target: VM-10 (new ES) + old ES server
    Tasks:
    ├── Register snapshot repository on old ES 8.14
    ├── Create snapshot of all indices on old ES
    ├── Transfer snapshot to new ES (NFS or direct)
    ├── Restore snapshot on ES 9.1.4
    ├── Verify index compatibility (8.x indices OK in 9.x)
    ├── Reindex if any incompatible mappings found
    ├── Compare document counts: old vs new
    ├── Update any index settings for 9.x
    └── Output: Migration report (index counts, status)

#### Step 22: Migrate WSO2 APIM

    Target: K8s cluster
    Tasks:
    ├── Import old APIM API definitions
    ├── Import old APIM application configs
    ├── Re-create subscriptions
    ├── Test all migrated APIs
    ├── Verify: all APIs published and callable
    └── Output: Migration report (API list, status)

#### Step 23: Create ElastAlert Rules

    Target: VM-10
    Tasks:
    ├── Deploy alert rule files to ElastAlert2:
    │   ├── node_down_alert.yaml       (K8s node not ready)
    │   ├── pod_crashloop_alert.yaml   (CrashLoopBackOff)
    │   ├── high_error_rate.yaml       (>5% error rate)
    │   ├── envoy_5xx_spike.yaml       (Envoy 5xx spike)
    │   ├── cilium_drop_alert.yaml     (packet drops)
    │   ├── elk_disk_usage.yaml        (disk >80%)
    │   └── wso2_auth_failure.yaml     (auth failures)
    ├── Restart ElastAlert2 container
    ├── Verify: rules loaded, no errors in log
    └── Output: Active rules list

### Phase 5: Finalize

#### Step 24: Clone & Push Repos to GitLab

    Target: VM-9 → VM-10 (GitLab)
    Tasks:
    ├── Create GitLab projects:
    │   ├── infra-ansible          (all playbooks + roles)
    │   ├── infra-helm-charts      (Helm values for ArgoCD)
    │   ├── infra-k8s-manifests    (raw K8s YAML)
    │   ├── elk-configs            (index templates, ILM, pipelines)
    │   ├── elastalert-rules       (alert rule definitions)
    │   └── docs                   (architecture + runbooks)
    ├── Push all configs to respective repos
    ├── Verify: all repos have content in GitLab
    ├── ArgoCD syncs from new repos
    └── Output: GitLab repo URLs

***

## 6. Day-2 Operations (Post-Provisioning)

| What                                  | Managed By                | How                             |
| ------------------------------------- | ------------------------- | ------------------------------- |
| Docker containers (start/stop/update) | **Dokploy**               | Dokploy UI                      |
| SSL for Docker services               | **Traefik** (via Dokploy) | Auto ACME renewal               |
| SSL for K8s services                  | **cert-manager**          | Auto renewal via ClusterIssuer  |
| Docker backups (GitLab, PG, volumes)  | **Dokploy**               | Scheduled → NFS or S3           |
| ES data lifecycle                     | **Elasticsearch ILM**     | Auto: hot→warm→cold(NFS)→delete |
| ES snapshots                          | **ES cron**               | Every 6 hours → NFS             |
| K8s app deployments                   | **ArgoCD**                | Git push → auto sync            |
| K8s cluster lifecycle                 | **Omni**                  | Omni UI on Jump Host            |
| Monitoring & alerts                   | **Kibana + ElastAlert2**  | Dashboards + email alerts       |
| Re-provisioning (if needed)           | **Python Web UI**         | Click step → Ansible runs again |

***

## 7. Customer Pre-Requisites

| #  | Item                                     | Required By   |
| -- | ---------------------------------------- | ------------- |
| 1  | 10 VMs provisioned with static IPs       | Before June 1 |
| 2  | SSH key-based access from VM-9 → all VMs | Before June 1 |
| 3  | NAS/NFS export path + IP                 | Before June 1 |
| 4  | SQL Server IP + credentials + empty DBs  | Before June 1 |
| 5  | Domain name(s) + DNS records             | Before June 1 |
| 6  | Gmail account + App Password             | Before June 1 |
| 7  | Old ES 8.14 IP + credentials             | Before Day 8  |
| 8  | Old WSO2 APIM backup                     | Before Day 8  |
| 9  | Firewall rules between VMs               | Before June 1 |
| 10 | Internet access on all VMs               | Before June 1 |

***

## 8. Success Criteria

| #  | Criteria                             | How to Verify                            |
| -- | ------------------------------------ | ---------------------------------------- |
| 1  | All 24 steps pass via Web UI         | All green ✅ in Web UI                    |
| 2  | All Docker services running with SSL | Dokploy UI shows healthy + HTTPS         |
| 3  | Talos cluster healthy                | `kubectl get nodes` → 8 Ready            |
| 4  | SMTP sends email                     | Test email from GitLab notification      |
| 5  | GitLab CI pipeline runs              | Push test project → pipeline passes      |
| 6  | SonarQube scans code                 | Run scan from GitLab CI                  |
| 7  | Netflow in Kibana                    | `netflow-cilium-*` has documents         |
| 8  | Traces in Kibana APM                 | `traces-apm-*` has documents             |
| 9  | K8s metrics + logs in Kibana         | `metrics-k8s-*` + `logs-k8s-*` have data |
| 10 | ILM lifecycle working                | ILM policy shows phase transitions       |
| 11 | ElastAlert2 alerting                 | Test alert triggers email                |
| 12 | ArgoCD synced                        | ArgoCD UI shows all apps synced          |
| 13 | WSO2 APIM publishes API              | Create + publish API succeeds            |
| 14 | WSO2 IS authenticates                | Token generation via IS succeeds         |
| 15 | APIM ↔ IS connected                  | API call with IS token succeeds          |
| 16 | ES migration complete                | Document counts match old → new          |
| 17 | WSO2 migration complete              | All old APIs functional on new           |
| 18 | All configs in GitLab                | All repos have content                   |
| 19 | Backups scheduled                    | Dokploy shows scheduled backups          |
| 20 | ES snapshots to NFS                  | Snapshot repository has snapshots        |

***

This is the **complete, final MVP scope and process**. Every step, every variable, every verification. Ready to build.

Want me to start with the **FastAPI Web UI skeleton** or the **first Ansible playbook**? 🚀
