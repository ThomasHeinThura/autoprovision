# 📋 Project Scope & MVP Document

***

## 🎯 Project Overview

| Item               | Detail                                             |
| ------------------ | -------------------------------------------------- |
| **Project Name**   | Infrastructure Automation & Migration              |
| **Duration**       | 11 working days (June 1 – June 11)                 |
| **Prep Period**    | May 19 – May 31 (Lab testing + script development) |
| **Delivery Model** | Automated provisioning via Python Web UI → Ansible |

***

## 🖥️ Final VM Inventory

### Production (13 VMs + External Storage)

| VM           | Role                           | Spec              | Storage   | Platform                |
| ------------ | ------------------------------ | ----------------- | --------- | ----------------------- |
| VM-1,2,3     | Talos Control Plane            | 4 vCPU / 8GB × 3  | 200GB × 3 | Talos OS                |
| VM-4,5,6,7,8 | Talos Workers                  | 8 vCPU / 32GB × 5 | 500GB × 5 | Talos OS                |
| VM-9         | **Jump Host + Omni**           | 4 vCPU / 8GB      | 100GB     | Linux + Docker          |
| VM-10        | SMTP + SonarQube + ElastAlert2 | 8 vCPU / 16GB     | 200GB     | Docker (all containers) |
| VM-11        | ELK Stack                      | 8 vCPU / 64GB     | 1TB + NFS | Docker (all containers) |
| VM-12        | GitLab + Registry              | 8 vCPU / 16GB     | 500GB     | Docker or native        |
| VM-13        | GitLab Runner                  | 4 vCPU / 8GB      | 100GB     | Docker                  |
| External     | NAS / NFS Storage              | Customer-provided | —         | NFS export              |
| External     | SQL Server                     | Customer-provided | —         | WSO2 databases          |

### Lab (8 VMs — mirrors production)

| VM     | Role                           | Spec                      |
| ------ | ------------------------------ | ------------------------- |
| VM-1   | Talos CP                       | 4 vCPU / 8GB / 200GB × 1  |
| VM-2,3 | Talos Workers                  | 8 vCPU / 32GB / 500GB × 2 |
| VM-4   | Jump Host + Omni               | 4 vCPU / 8GB / 100GB      |
| VM-5   | SMTP + SonarQube + ElastAlert2 | 8 vCPU / 16GB / 200GB     |
| VM-6   | ELK Stack                      | 8 vCPU / 64GB / 1TB       |
| VM-7   | GitLab + Registry              | 8 vCPU / 16GB / 500GB     |
| VM-8   | GitLab Runner                  | 4 vCPU / 8GB / 100GB      |

***

## 🏗️ Architecture

                             ┌──────────────────────────┐
                             │   DNS / Domain Records    │
                             └────────┬─────────────────┘
                                      │
                  ┌───────────────────┼───────────────────┐
                  ▼                                       ▼
       ┌─────────────────────┐              ┌──────────────────────────┐
       │   DOCKER VMs         │              │   KUBERNETES CLUSTER      │
       │                      │              │   (Talos + Cilium CNI)    │
       │   SSL: Traefik       │              │                          │
       │   Let's Encrypt ACME │              │   SSL: Envoy Gateway     │
       │   Auto-renewal       │              │   cert-manager           │
       │                      │              │   ClusterIssuer (LE)     │
       │ ┌──────────────────┐ │              │                          │
       │ │ VM-10: SMTP      │ │              │ ┌──────────────────────┐ │
       │ │  Stalwart        │ │              │ │ Envoy Gateway        │ │
       │ │  SonarQube       │ │              │ │ OTel Collector       │ │
       │ │  ElastAlert2     │ │              │ │ ArgoCD               │ │
       │ │  PostgreSQL      │ │              │ │ WSO2 APIM ←→ SQL    │ │
       │ ├──────────────────┤ │              │ │ WSO2 IS   ←→ SQL    │ │
       │ │ VM-11: ELK       │ │              │ │ Cilium + Hubble(OBI)│ │
       │ │  Elasticsearch   │◄├──────────────┤ │                      │ │
       │ │  Logstash        │ │  OTel data   │ └──────────────────────┘ │
       │ │  Kibana          │ │              │                          │
       │ │  Fleet + APM     │ │              │  CP × 3  |  Worker × 5  │
       │ │  NFS → NAS       │ │              └──────────────────────────┘
       │ ├──────────────────┤ │
       │ │ VM-12: GitLab    │ │         ┌──────────────────────────┐
       │ │  GitLab CE       │◄├─────────┤  VM-9: Jump Host         │
       │ │  Registry        │ │         │  Python Web UI (FastAPI)  │
       │ ├──────────────────┤ │         │  Ansible + ansible-runner │
       │ │ VM-13: Runner    │ │         │  Omni CLI                 │
       │ └──────────────────┘ │         │  Traefik (for Docker VMs) │
       └──────────────────────┘         └──────────────────────────┘

***

## 📦 MVP Scope

### MVP-1: Core Infrastructure (Must-Have)

> **Goal:** All services installed, configured, and communicating.

| #  | Component                  | VM            | Container Limits                                             | Deliverable                                          |
| -- | -------------------------- | ------------- | ------------------------------------------------------------ | ---------------------------------------------------- |
| 1  | **Jump Host Setup**        | VM-9          | —                                                            | Python Web UI + Ansible + Omni CLI installed         |
| 2  | **Stalwart SMTP**          | VM-10         | CPU: 0.5–1 / MEM: 512MB–1GB                                  | SMTP relay via Gmail, verified send                  |
| 3  | **SonarQube + PostgreSQL** | VM-10         | SQ: CPU 1–2 / MEM 4–6GB, PG: CPU 0.5–1 / MEM 1–2GB           | Admin login, project scan works                      |
| 4  | **ElastAlert2**            | VM-10         | CPU: 0.5–1 / MEM: 512MB–1GB                                  | Connected to ES, base alert indices created          |
| 5  | **Elasticsearch 9.1.4**    | VM-11         | CPU: 4–6 / MEM: 31–40GB                                      | Running, indices created, ILM configured             |
| 6  | **Logstash**               | VM-11         | CPU: 1–2 / MEM: 2–4GB                                        | Pipelines receiving data                             |
| 7  | **Kibana**                 | VM-11         | CPU: 0.5–1 / MEM: 1–2GB                                      | Dashboards accessible                                |
| 8  | **Fleet Server + APM**     | VM-11         | Fleet: CPU 0.5–1 / MEM 512MB–1GB, APM: CPU 0.5–1 / MEM 1–2GB | Agent enrollment, APM traces visible                 |
| 9  | **NFS Mount**              | VM-11         | —                                                            | Mounted to external NAS, ES snapshot repo configured |
| 10 | **ILM Lifecycle**          | VM-11         | —                                                            | 3-day hot → warm → cold(NFS) → delete policy active  |
| 11 | **GitLab CE + SMTP**       | VM-12         | CPU: 4–6 / MEM: 8–12GB                                       | Admin account, email notifications via Stalwart      |
| 12 | **GitLab Registry**        | VM-12         | CPU: 0.5–1 / MEM: 1–2GB                                      | Push/pull images working                             |
| 13 | **GitLab Runner**          | VM-13         | CPU: 2–4 / MEM: 4–6GB                                        | Registered, CI pipeline runs                         |
| 14 | **Talos Cluster**          | VM-1→8        | —                                                            | 3 CP + 5 Workers via Omni, Cilium CNI active         |
| 15 | **Envoy Gateway**          | K8s           | Per cluster resources                                        | Ingress routing working                              |
| 16 | **cert-manager**           | K8s           | —                                                            | ClusterIssuer + Let's Encrypt certs issued           |
| 17 | **Traefik**                | VM-9 (Docker) | CPU: 0.5–1 / MEM: 256–512MB                                  | Reverse proxy for Docker VMs, ACME SSL               |
| 18 | **ArgoCD**                 | K8s           | —                                                            | Synced with GitLab repos                             |
| 19 | **WSO2 APIM**              | K8s           | —                                                            | Connected to SQL Server, APIs publishable            |
| 20 | **WSO2 IS**                | K8s           | —                                                            | Connected to SQL Server, linked to APIM              |

### MVP-2: Observability (Must-Have)

> **Goal:** Full visibility — netflow, tracing, metrics, logs all in Kibana.

| # | Pipeline        | Source                  | OTel Receiver                 | ES Index           | What You See                                   |
| - | --------------- | ----------------------- | ----------------------------- | ------------------ | ---------------------------------------------- |
| 1 | **Netflow**     | Cilium Hubble (OBI)     | `hubble`                      | `netflow-cilium-*` | L3/L4/L7 network flows between pods            |
| 2 | **Tracing**     | Envoy Gateway OTel      | `otlp` (gRPC/HTTP)            | `traces-apm-*`     | Full request traces including backend services |
| 3 | **K8s Metrics** | Kubelet, K8s API        | `kubeletstats`, `k8s_cluster` | `metrics-k8s-*`    | CPU, memory, pod status, node health           |
| 4 | **K8s Logs**    | Container stdout/stderr | `filelog`                     | `logs-k8s-*`       | All pod logs                                   |
| 5 | **Alerts**      | ElastAlert2             | —                             | `elastalert_*`     | Alert history, status, errors                  |

### MVP-3: Migration (Must-Have)

| # | Task                       | Source        | Target         | Method                                                  |
| - | -------------------------- | ------------- | -------------- | ------------------------------------------------------- |
| 1 | ES Data Migration          | ES 8.14 (old) | ES 9.1.4 (new) | Snapshot → Restore                                      |
| 2 | ES Index Compatibility     | —             | —              | Verify/reindex if needed for 9.x breaking changes       |
| 3 | ElastAlert2 Index Creation | —             | ES 9.1.4       | Create `elastalert_*` indices (no existing rules/index) |
| 4 | Alert Rules Setup          | —             | ElastAlert2    | Create new base rules from scratch                      |
| 5 | WSO2 APIM Migration        | Old APIM      | New APIM (K8s) | Export/import APIs + configs                            |
| 6 | WSO2 APIM ↔ IS             | —             | K8s            | Configure Key Manager + Identity Provider               |
| 7 | ILM Tracing Lifecycle      | —             | ES 9.1.4       | 3-day retention → NFS cold tier                         |

### MVP-4: Automation Platform (Must-Have)

> **Goal:** Python Web UI on Jump Host — click to deploy everything.

| # | Feature                          | Detail                                                                 |
| - | -------------------------------- | ---------------------------------------------------------------------- |
| 1 | **Inventory Management**         | Add/edit VM IPs, roles, SSH credentials via UI                         |
| 2 | **Variable Input Forms**         | Per-playbook custom variables (domain, IPs, passwords, NFS path, etc.) |
| 3 | **One-Click Playbook Execution** | Each provisioning step = one button + variable form → triggers Ansible |
| 4 | **Live Job Logs**                | Stream ansible-runner output to browser in real-time (WebSocket)       |
| 5 | **Job History & Status**         | Track pass/fail for each playbook run                                  |
| 6 | **Repo Clone & Push**            | Clone VM configs / Helm charts → push to GitLab                        |
| 7 | **Environment Toggle**           | Switch between Lab and Production inventory                            |

***

## 🐳 Docker Resource Limits — Complete Reference

### VM-10: SMTP + SonarQube + ElastAlert2 (8 vCPU / 16GB)

```yaml
services:
  stalwart-smtp:
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "512M" }
        limits:      { cpus: "1",   memory: "1G" }

  sonarqube:
    deploy:
      resources:
        reservations: { cpus: "1",   memory: "4G" }
        limits:      { cpus: "2",   memory: "6G" }
    environment:
      SONAR_SEARCH_JAVAOPTS: "-Xms1g -Xmx1g"
      SONAR_CE_JAVAOPTS: "-Xms1g -Xmx1g"
      SONAR_WEB_JAVAOPTS: "-Xms512m -Xmx512m"

  sonarqube-db:  # PostgreSQL
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "1G" }
        limits:      { cpus: "1",   memory: "2G" }

  elastalert2:
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "512M" }
        limits:      { cpus: "1",   memory: "1G" }

  traefik:  # Reverse proxy for this VM
    deploy:
      resources:
        reservations: { cpus: "0.25", memory: "128M" }
        limits:      { cpus: "0.5",  memory: "256M" }

# Total Reserved:  2.75 vCPU / 6.15 GB
# Total Limit:     5.5 vCPU  / 10.25 GB
# OS Headroom:     2.5 vCPU  / 5.75 GB  ✅
```

### VM-11: ELK Stack (8 vCPU / 64GB / 1TB + NFS)

```yaml
services:
  elasticsearch:
    deploy:
      resources:
        reservations: { cpus: "4", memory: "40G" }
        limits:      { cpus: "6", memory: "48G" }
    environment:
      ES_JAVA_OPTS: "-Xms24g -Xmx24g"
      # Remaining memory → filesystem cache inside container

  logstash:
    deploy:
      resources:
        reservations: { cpus: "1",   memory: "2G" }
        limits:      { cpus: "2",   memory: "4G" }
    environment:
      LS_JAVA_OPTS: "-Xms1g -Xmx2g"

  kibana:
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "1G" }
        limits:      { cpus: "1",   memory: "2G" }

  fleet-server:
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "512M" }
        limits:      { cpus: "1",   memory: "1G" }

  apm-server:
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "1G" }
        limits:      { cpus: "1",   memory: "2G" }

# Total Reserved:  6.5 vCPU / 44.5 GB
# Total Limit:     11 vCPU  / 57 GB (burst OK with CPU shares)
# OS + cache:      ~7 GB headroom ✅
```

### VM-9: Jump Host + Omni (4 vCPU / 8GB)

```yaml
services:
  python-web-ui:  # FastAPI
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "512M" }
        limits:      { cpus: "1",   memory: "1G" }

  omni:
    deploy:
      resources:
        reservations: { cpus: "0.5", memory: "1G" }
        limits:      { cpus: "1",   memory: "2G" }

# Ansible runs as process, not container
# Reserved for Ansible + OS: 2 vCPU / 5 GB  ✅
```

***

## 📂 Ansible Role Structure

    /opt/automation/
    ├── ansible/
    │   ├── inventory/
    │   │   ├── lab.yml
    │   │   └── production.yml          # Generated by Web UI
    │   ├── group_vars/
    │   │   ├── all.yml                 # Shared: domain, NFS, SMTP config
    │   │   ├── lab.yml
    │   │   └── production.yml
    │   ├── roles/
    │   │   ├── common/                 # Base OS, Docker CE, NTP, SSH
    │   │   ├── traefik/                # Traefik + ACME for Docker VMs
    │   │   ├── stalwart-smtp/          # SMTP + Gmail relay
    │   │   ├── sonarqube/              # SonarQube + PostgreSQL
    │   │   ├── elastalert2/            # ElastAlert2 + index creation
    │   │   ├── elasticsearch/          # ES 9.1.4 container + config
    │   │   ├── logstash/               # Logstash + pipelines
    │   │   ├── kibana/                 # Kibana
    │   │   ├── fleet-apm/              # Fleet Server + APM
    │   │   ├── nfs-client/             # NFS mount + ES snapshot repo
    │   │   ├── ilm-lifecycle/          # ILM policies + index templates
    │   │   ├── gitlab/                 # GitLab CE + SMTP + Registry
    │   │   ├── gitlab-runner/          # Runner install + register
    │   │   ├── talos-cluster/          # Talos via Omni + Cilium
    │   │   ├── cert-manager/           # cert-manager + ClusterIssuer
    │   │   ├── envoy-gateway/          # Envoy Gateway + certs
    │   │   ├── otel-netflow/           # OTel: Cilium Hubble → ELK
    │   │   ├── otel-tracing/           # OTel: Envoy OTLP → ELK
    │   │   ├── otel-kube/              # OTel: K8s metrics+logs → ELK
    │   │   ├── argocd/                 # ArgoCD + GitLab integration
    │   │   ├── wso2-apim/              # WSO2 APIM + SQL connector
    │   │   ├── wso2-is/                # WSO2 IS + SQL connector
    │   │   ├── es-migration/           # Snapshot 8.14 → restore 9.1.4
    │   │   └── wso2-migration/         # Old APIM → new APIM
    │   └── playbooks/
    │       ├── 01-base-setup.yml
    │       ├── 02-smtp-sonarqube-elastalert.yml
    │       ├── 03-elk-stack.yml
    │       ├── 04-gitlab-full.yml
    │       ├── 05-talos-cluster.yml
    │       ├── 06-ssl-ingress.yml      # Traefik(Docker) + cert-manager + Envoy(K8s)
    │       ├── 07-observability.yml     # All 3 OTel pipelines
    │       ├── 08-argocd.yml
    │       ├── 09-wso2.yml
    │       ├── 10-migration-es.yml
    │       ├── 11-migration-wso2.yml
    │       └── 12-clone-repos.yml
    ├── web-ui/                          # FastAPI application
    │   ├── main.py
    │   ├── routers/
    │   ├── templates/
    │   ├── static/
    │   └── services/
    │       └── ansible_runner_service.py
    └── gitlab-repos/                    # To be pushed to GitLab
        ├── helm-charts/
        ├── k8s-manifests/
        ├── elk-configs/
        └── elastalert-rules/

***

## ✅ Customer Pre-Requisites Checklist

| #  | Item                                             | Required By          |
| -- | ------------------------------------------------ | -------------------- |
| 1  | 13 VMs provisioned with static IPs               | Before June 1        |
| 2  | SSH key-based access from Jump Host → all VMs    | Before June 1        |
| 3  | NAS/NFS export path + IP + credentials           | Before June 1        |
| 4  | SQL Server IP + credentials + empty DBs for WSO2 | Before June 1        |
| 5  | Domain name(s) for all services                  | Before June 1        |
| 6  | DNS records (A/CNAME) pointing to ingress        | Before June 1        |
| 7  | Gmail account + App Password for SMTP            | Before June 1        |
| 8  | Old ES 8.14 IP + credentials                     | Before migration day |
| 9  | Old WSO2 APIM backup/export                      | Before migration day |
| 10 | Firewall rules opened between VMs                | Before June 1        |
| 11 | Internet access on all VMs (or offline packages) | Before June 1        |

***

## 🎯 Success Criteria

| #  | Criteria                                            | Verification                               |
| -- | --------------------------------------------------- | ------------------------------------------ |
| 1  | All services reachable via domain with valid SSL    | Browser HTTPS check                        |
| 2  | SMTP sends email via Gmail relay                    | Test email from GitLab                     |
| 3  | SonarQube scans a test project from GitLab CI       | Pipeline passes                            |
| 4  | GitLab CI/CD pipeline runs on Runner                | Push → build → pass                        |
| 5  | Talos cluster healthy (3 CP + 5 WR)                 | `kubectl get nodes`                        |
| 6  | Cilium netflow visible in Kibana                    | `netflow-cilium-*` index has data          |
| 7  | Envoy traces visible in Kibana APM                  | `traces-apm-*` index has data              |
| 8  | K8s metrics + logs in Kibana                        | `metrics-k8s-*` and `logs-k8s-*` have data |
| 9  | ILM lifecycle rotating data → NFS after 3 days      | ILM policy status in Kibana                |
| 10 | ElastAlert2 indices created and alerting functional | `elastalert_*` indices exist               |
| 11 | ArgoCD syncs Helm charts from GitLab                | ArgoCD UI shows synced                     |
| 12 | WSO2 APIM publishes API, authenticates via WSO2 IS  | API call with token succeeds               |
| 13 | ES 8.14 data migrated to 9.1.4                      | Data count matches                         |
| 14 | Old WSO2 APIM APIs migrated to new                  | APIs functional                            |
| 15 | Python Web UI triggers all playbooks successfully   | Click each → green status                  |

***

This is your **complete project scope and MVP**. Shall I start building the **first Ansible role** or the **FastAPI Web UI skeleton** so you can begin testing in your lab? 🚀
