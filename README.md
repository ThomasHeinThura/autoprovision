# Autoprovision — RKE2 + Istio Control Plane

End-to-end automation for the production + UAT rollout: one jump host runs a Python control plane
that installs **RKE2 Kubernetes clusters, Docker platform stacks (GitLab + ELK), and SQL Server**
— all in **parallel** — then per-cluster add-ons (Istio, cert-manager, ArgoCD, Headlamp) and
**WSO2** are deployed from the team's repo.

> **What changed from the original design:** the Kubernetes layer moved from
> **Talos + Cilium + Envoy Gateway** to **RKE2 + default CNI (Canal) + Istio ambient**. SQL Server
> runs on dedicated VMs installed by Ansible, and the control plane runs multiple stacks at once.
> The requirement docs are under [`planning/`](planning/) — start with
> [planning/00-old-vs-new.md](planning/00-old-vs-new.md) for the old-vs-new summary.

---

## Versions (pinned)

| Layer | Pin |
| ----- | --- |
| RKE2 | **v1.36.1+rke2r2** (Kubernetes v1.36.1) |
| CNI | **Canal** (default, bundled with RKE2) — kube-proxy kept |
| K8s ingress | **Istio 1.30 ambient** (`profile=ambient`; ingress via Kubernetes Gateway API) |
| SQL Server | **2025** (default; 2022 selectable per card) — Prod HA AG (3 nodes, Pacemaker), UAT single instance |
| WSO2 | APIM 4.7.0 / IS 7.3.0 via [`WSO2_APIM_KUBE_ISTIO/`](WSO2_APIM_KUBE_ISTIO/README.md) |
| Docker platform | GitLab CE 19.0.1, ELK 9.1.4, PostgreSQL 17.10, Traefik v3.7.1, SonarQube, ElastAlert2 |

Full matrix: [planning/version-rke2.md](planning/version-rke2.md).

> **RKE2 v1.36 note:** the RKE2-bundled ingress is now Traefik (ingress-nginx retired upstream).
> Because **Istio** owns Kubernetes ingress, the RKE2 server config disables the bundled ingress
> (`disable: [rke2-ingress-nginx, rke2-traefik]`) — handled automatically by `rke2_cluster.yml`.
> This is unrelated to the Docker-platform Traefik on the GitLab/ELK VMs.

---

## Topology (19 VMs)

| Env | VMs |
| --- | --- |
| **Production (12)** | 3 RKE2 control plane + 5 RKE2 workers · 1 ELK · 3 MSSQL (read-scale AG) |
| **UAT (5)** | 1 RKE2 control plane + 2 RKE2 workers · 1 MSSQL (single) · 1 ELK |
| **Shared (2)** | 1 GitLab (Docker) · 1 jump host |

Sizing: [planning/vm-requirements-rke2.md](planning/vm-requirements-rke2.md).

## What is automated vs documented

| Step | How |
| ---- | --- |
| Docker base + GitLab + SonarQube + ELK | **Ansible** (web UI tracks) |
| SQL Server (single + HA AG + cleanup/reset) | **Ansible** (web UI tracks) |
| RKE2 cluster install + scale (servers + agents) | **Ansible** (web UI tracks) |
| MetalLB, Istio **ambient** + shared Gateway, cert-manager + internal CA, ArgoCD, Headlamp | **Ansible** (web UI cards → `k8s_addons.yml`); runbook = manual reference ([rke2-cluster/](rke2-cluster/)) |
| WSO2 APIM + IS | **Ansible** (web UI cards → `k8s_wso2.yml`, renders the team repo [WSO2_APIM_KUBE_ISTIO](WSO2_APIM_KUBE_ISTIO/README.md)) |
| TLS certs (Traefik VMs + K8s secret, PEM or cert-manager auto-renew) | **Ansible** (web UI Certificates cards) |
| Backups — RKE2 etcd snapshots + MSSQL FULL/LOG | **Ansible** (web UI Backups & DR cards) |
| OpenTelemetry Collector | **Runbook** ([rke2-cluster/](rke2-cluster/)) |

---

# Operator flow (start to finish)

## Step 0 — Prepare each target VM (one-time)

On **every** target VM (RKE2 nodes, ELK VMs, GitLab VM, MSSQL VMs), create the automation user
Ansible logs in as:

```bash
ssh <existing-admin>@<vm-ip>
sudo adduser autoprovision
sudo usermod -aG sudo autoprovision
echo 'autoprovision ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/autoprovision
```

Customer prerequisites (manual): DNS records, firewall rules, NFS/NAS export, the RKE2
registration address / VIP, and TLS cert handover if not self-signing.

## Step 1 — SSH into the jump host and bootstrap

```bash
ssh <username>@<jump-host-ip>

# Base tooling
sudo apt update
sudo apt install -y git curl wget sshpass

# Get the repo and run the one-shot bootstrap
cd ~
git clone https://github.com/ThomasHeinThura/autoprovision.git
cd autoprovision
chmod +x bootstrap-jumphost.sh
./bootstrap-jumphost.sh
```

`bootstrap-jumphost.sh` installs Python + venv, Ansible + ansible-runner, **kubectl, helm,
istioctl**, creates `data/` (state, logs, per-job inventory), and starts the FastAPI web UI on
port **3000**. It prints:

```text
[INFO]  Bootstrap complete.
Open: http://<jump-host-ip>:3000/
```

Stop / restart the UI:

```bash
pkill -f "uvicorn app.main:app"     # stop
./bootstrap-jumphost.sh             # restart
```

## Step 2 — Open the parallel control plane

```text
http://<jump-host-ip>:3000/
```

The home page is the **multi-track dashboard**. Each track is a card you run independently and
**concurrently** — every job gets its own inventory file (`data/inventory/<job_id>.ini`) and its
own log (`data/logs/<job_id>.log`), so parallel runs never collide.

- Set the **Default SSH User/Password** at the top and click **Apply Defaults To Cards** to
  prefill all cards (default user `autoprovision`).

## Step 3 — Run the tracks in parallel

Fill each card and click **Run** (or **Preview** to see the inventory + playbook steps first).
Click **Run All Configured** to launch every card that has its target filled in.

| Card | What it installs | Key inputs |
| ---- | ---------------- | ---------- |
| **GitLab (shared)** | Docker base → **Traefik** → Platform (PostgreSQL + Dockhand) → GitLab CE+Runner+Registry → SonarQube | GitLab VM IP, domains, runner token (optional) |
| **Prod RKE2 Cluster** | RKE2 v1.36.1 on 3 servers + 5 agents, Canal CNI, kubeconfig pulled to jump host | cluster name, 3 CP IPs, 5 worker IPs, registration address, RKE2 token |
| **UAT RKE2 Cluster** | RKE2 on 1 server + 2 agents | cluster name, 1 CP IP, 2 worker IPs, RKE2 token |
| **Prod ELK** | Docker base → **Traefik** → Elasticsearch/Logstash/Kibana/Fleet/APM (Kibana via Traefik) | ELK VM IP, Kibana domain |
| **UAT ELK** | same, UAT ELK VM | ELK VM IP, Kibana domain |
| **Prod MSSQL AG** | SQL Server 2025 (or 2022) on 3 nodes + Always On HA AG with Pacemaker (first IP = primary) | 3 node IPs, SA password, AG name, listener/VIP |
| **UAT MSSQL** | SQL Server 2025 (or 2022) single instance | VM IP, SA password |
| **Istio / ArgoCD / Headlamp / WSO2 / cert cards** | Per-cluster add-ons + WSO2 (see Step 4–5) | cluster name, hosts, MetalLB range |
| **Backups & DR** | RKE2 etcd snapshots (scheduled + on-demand) · MSSQL FULL/LOG backups with retention | server/node IPs, SA password |

> **Every Docker VM runs Traefik.** Traefik is installed as its own stack right after Docker base
> and **owns the shared `platform` network** that the service stacks attach to. Each service is
> reachable over HTTPS at its domain (GitLab/registry/Dockhand/SonarQube on the GitLab VM; Kibana
> on each ELK VM) — no raw service ports. The GitLab VM's platform stack is **PostgreSQL + Dockhand
> only** (Traefik is separate). This Traefik (v3.7.1) is the Docker-platform ingress and is
> unrelated to Istio (Kubernetes ingress).

> **Order tip:** start **GitLab** first (it hosts manifests/registry), then fire everything else.
> All tracks are independent and run together.

### CLI equivalent (optional)

The same playbooks can run directly from the jump host with a hand-written INI inventory.
Groups: `docker_vm` (Docker stacks), `mssql` / `mssql_ag` / `mssql_backup` (SQL Server),
`rke2_servers` / `rke2_agents` (cluster) — one `ip ansible_user=autoprovision ansible_become=true`
line per host:

```bash
# RKE2 cluster (first host in rke2_servers bootstraps; default CNI = Canal)
ansible-playbook -i <inv> ansible/rke2_cluster.yml \
  --extra-vars '{"cluster_name":"prod-cluster","rke2_token":"<token>","registration_address":"rke2-prod.example.local"}'

# SQL Server — read-scale AG (3 nodes) / single (UAT)
ansible-playbook -i <inv> ansible/mssql_ag.yml     --extra-vars '{"sa_password":"<pw>","ag_name":"ag1"}'
ansible-playbook -i <inv> ansible/mssql_single.yml --extra-vars '{"sa_password":"<pw>"}'

# Docker stacks — install Traefik right after the base, before any service stack
ansible-playbook -i <inv> ansible/docker_vm_base.yml
ansible-playbook -i <inv> ansible/traefik_stack.yml                  # every Docker VM; creates the shared `platform` network
ansible-playbook -i <inv> ansible/docker_platform_up.yml --extra-vars '{"dockhand_domain":"dockhand.example.com"}'  # GitLab VM: PostgreSQL + Dockhand
ansible-playbook -i <inv> ansible/elk_stack.yml      --extra-vars '{"kibana_domain":"kibana.example.com"}'
ansible-playbook -i <inv> ansible/gitlab_stack.yml   --extra-vars '{"gitlab_domain":"gitlab.example.com"}'
```

After the RKE2 track completes, the cluster kubeconfig is on the jump host at
`data/k8s/<cluster_name>/kubeconfig`:

```bash
export KUBECONFIG="$HOME/autoprovision/data/k8s/prod-cluster/kubeconfig"
kubectl get nodes -o wide      # all nodes Ready, CNI = Canal
```

## Step 4 — Per-cluster add-ons (web UI cards)

For **each** cluster, run the add-on cards in this order (each card runs
[ansible/k8s_addons.yml](ansible/k8s_addons.yml) against the cluster's kubeconfig on the
jump host — no SSH to the nodes):

1. **Istio** card (fill the MetalLB IP range) — installs MetalLB, then Istio **1.30 ambient**
   (istiod + istio-cni + ztunnel with the RKE2-correct CNI paths `/etc/cni/net.d` +
   `/opt/cni/bin`; any old sidecar install is purged first), the Gateway API CRDs
   (**standard** channel), and the **single shared ingress Gateway** (`shared-gateway` in
   `istio-system` → svc `shared-gateway-istio` → **one MetalLB IP for ALL hosts**).
2. **cert-manager (internal CA)** card — cert-manager + self-signed root CA
   (`ca-issuer` ClusterIssuer).
3. **Certificate — Kubernetes** card — the gateway TLS secret `wso2-ingress-cert` in
   **`istio-system`** (the shared Gateway only reads its own namespace — Gateway API
   `certificateRefs`). Paste a PEM, or leave it empty to auto-issue + auto-renew from the
   internal CA (use a wildcard `cert_dns` covering all hosts).
4. **ArgoCD** and **Headlamp** cards — each exposed via an `HTTPRoute` on the shared gateway
   (no extra IPs).
5. OpenTelemetry Collector — runbook step.

Manual CLI equivalent + troubleshooting detail:
[rke2-cluster/rke2-addons-istio-argocd-headlamp.md](rke2-cluster/rke2-addons-istio-argocd-headlamp.md)
(prod: [prod-rke2-installation.md](rke2-cluster/prod-rke2-installation.md) · uat:
[uat-rke2-installation.md](rke2-cluster/uat-rke2-installation.md)).

## Step 5 — WSO2 (web UI cards; manual = her steps)

WSO2 APIM (Control Plane + Internal/External Gateways) and Identity Server deploy from the
**WSO2 APIM / WSO2 IS cards** — they run [ansible/k8s_wso2.yml](ansible/k8s_wso2.yml), which
renders [`WSO2_APIM_KUBE_ISTIO/`](WSO2_APIM_KUBE_ISTIO/README.md) with your hostnames + MSSQL
address, enrolls the WSO2 namespaces in ambient, and applies everything. **Tested working**
(latest lab run). Manual equivalent with `KUBECONFIG` set and Istio already installed:

```bash
cd WSO2_APIM_KUBE_ISTIO

# namespaces + ambient mesh enrollment (no sidecars)
kubectl create ns wso2-cp; kubectl create ns wso2-is
kubectl create ns wso2-internal-gw; kubectl create ns wso2-external-gw
for ns in wso2-cp wso2-is wso2-internal-gw wso2-external-gw; do kubectl label ns $ns istio.io/dataplane-mode=ambient --overwrite; done

# certs + ingress TLS secret in istio-system (the Gateway API Gateway picks it up automatically)
./scripts/generate-local-certificates.sh
kubectl -n istio-system create secret tls wso2-ingress-cert \
  --cert=certificates/server.crt --key=certificates/server.key --dry-run=client -o yaml | kubectl apply -f -

# (optional) build images with MSSQL JDBC baked in: ./scripts/build-apim-images.sh
kubectl apply -f istio-gateway.yaml            # single shared ingress Gateway → svc shared-gateway-istio
kubectl apply -f control-plane/ -f internal-gw/ -f external-gw/ -f wso2-is/
```

**Database wiring (read-scale AG):** load `mssql/shared_mssql.sql` and `mssql/apim_mssql.sql`,
then point WSO2 JDBC at the **AG primary node** in Production (no listener with `CLUSTER_TYPE=NONE`)
or the **single instance** in UAT. Details: [planning/wso2-rke2.md](planning/wso2-rke2.md).

WSO2 ingress hosts (from the repo's `istio-gateway.yaml`, all TLS on 443 →
secret `wso2-ingress-cert` in `istio-system`): `apim.example.com`, `internal-gw.example.com`,
`external-gw.example.com`, `wso2is.example.com`. Point DNS / `/etc/hosts` at the Gateway API
ingress IP (`kubectl -n istio-system get svc shared-gateway-istio`).

## Step 6 — Backups (production-grade — run once per environment)

Web UI → **Backups & DR**:

- **RKE2 etcd Snapshots** ([ansible/k8s_etcd_backup.yml](ansible/k8s_etcd_backup.yml)) —
  schedules a daily etcd snapshot on every RKE2 server (drop-in config under
  `config.yaml.d/`, rolling restart so the API stays up), takes one snapshot immediately, and
  prunes by retention. etcd holds ALL cluster state — without snapshots a lost etcd means
  rebuilding from scratch. Restore: `rke2 server --cluster-reset --cluster-reset-restore-path=…`.
- **MSSQL Scheduled Backups** ([ansible/mssql_backup.yml](ansible/mssql_backup.yml)) — FULL
  daily + LOG every 15 min + retention pruning via a root-only script + cron. Install on **all**
  AG nodes: only the current PRIMARY backs up, so backups follow failover (a standalone/UAT
  instance counts as primary). The AG protects against node loss only — backups are what protect
  against corruption / accidental `DELETE` / ransomware. **Point the backup dir at NFS/NAS.**

## Step 7 — Observability, migration, validation

Per ELK stack: configure Elasticsearch ILM/retention, archive paths to NFS/NAS, run the 8.14 →
9.1.4 snapshot/restore migration, the WSO2 APIM credential migration job, and the base
ElastAlert2 rules. See [planning/installation-steps-rke2.md](planning/installation-steps-rke2.md).

---

## Health checks

```bash
# Kubernetes (per cluster)
kubectl get nodes -o wide                                   # Ready, CNI = Canal
kubectl get pods -A
kubectl get svc -n istio-system shared-gateway-istio          # EXTERNAL-IP populated (Gateway API)
kubectl get gateway,httproute -A                            # Gateway API ingress objects
kubectl get pods -n istio-system                            # istiod, ztunnel, istio-cni (ambient)
kubectl get pods -n wso2-cp; kubectl get pods -n wso2-is

# SQL Server read-scale AG (on the primary)
/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P '<pw>' -C \
  -Q "SELECT ag.name, ar.replica_server_name, rs.role_desc, rs.synchronization_health_desc
      FROM sys.availability_groups ag
      JOIN sys.availability_replicas ar ON ag.group_id=ar.group_id
      JOIN sys.dm_hadr_availability_replica_states rs ON ar.replica_id=rs.replica_id;"

# Docker stacks
docker ps | grep -E 'pg-platform|traefik|dockhand|gitlab|elk-'
curl -u elastic:changeme http://<elk-vm>:9200/_cluster/health
```

## SQL Server — apply a real license key

The playbooks install SQL Server with `MSSQL_PID=Enterprise` (the Enterprise **evaluation** edition).
To activate a purchased license, apply the product key. On **Linux (Ubuntu 24.04)** the Windows GUI
"Edition Upgrade" path does **not** apply — use `mssql-conf` on each node:

```bash
# 1. Stop SQL Server
sudo systemctl stop mssql-server

# 2. Set the edition / product key. In current builds `set-edition` is INTERACTIVE — it lists the
#    editions and lets you choose a number OR paste a 25-character product key:
sudo /opt/mssql/bin/mssql-conf set-edition

#    Non-interactive alternative (set the PID, then re-run setup): the PID may be an edition name
#    (Enterprise, Standard, Developer, Express, EnterpriseCore) or a product key:
sudo MSSQL_PID='<edition-name-or-25-char-product-key>' /opt/mssql/bin/mssql-conf set-edition

# 3. Start it back
sudo systemctl start mssql-server

# 4. Verify the edition (this repo ships mssql-tools18; -C trusts the self-signed cert)
/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P '<pw>' -C \
  -Q "SELECT SERVERPROPERTY('Edition'), SERVERPROPERTY('ProductVersion');"
```

> Apply the key on **every** AG node (run it on each of the 3 replicas), one at a time. SQL Server
> restarts on each node anyway, so do it during a maintenance window; Pacemaker will keep the AG
> primary available on the others while one node restarts.

### Check edition, license, and evaluation expiry

Run with `sqlcmd` (e.g. `/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P '<pw>' -C -Q "<query>"`).

```sql
-- Edition / version / license type
SELECT
    SERVERPROPERTY('Edition')        AS Edition,
    SERVERPROPERTY('ProductVersion') AS ProductVersion,
    SERVERPROPERTY('ProductLevel')   AS ProductLevel,
    SERVERPROPERTY('LicenseType')    AS LicenseType,
    SERVERPROPERTY('NumLicenses')    AS NumLicenses,
    @@VERSION                        AS FullVersion;
```

> Note: `LicenseType` always returns `DISABLED` on SQL Server 2012+ — Microsoft stopped tracking it
> in the engine. Use `Edition` to tell evaluation from licensed (e.g. `Enterprise Evaluation Edition`
> vs `Enterprise Edition`).

```sql
-- How long it has been installed (NT AUTHORITY\SYSTEM is created at install time)
SELECT
    @@SERVERNAME                          AS ServerName,
    create_date                           AS InstallDate,
    DATEDIFF(DAY, create_date, GETDATE()) AS DaysRunning,
    SERVERPROPERTY('Edition')             AS Edition
FROM sys.server_principals
WHERE name = 'NT AUTHORITY\SYSTEM';
```

```sql
-- Evaluation expiry — ONLY meaningful if Edition is 'Enterprise Evaluation Edition' (180-day trial)
SELECT
    @@SERVERNAME                          AS ServerName,
    create_date                           AS InstallDate,
    DATEADD(DD, 180, create_date)         AS ExpiryDate,
    DATEDIFF(DAY, GETDATE(),
        DATEADD(DD, 180, create_date))    AS DaysLeft
FROM sys.server_principals
WHERE SID = 0x010100000000000512000000;   -- NT AUTHORITY\SYSTEM
```

```sql
-- Days remaining direct from the engine (extended proc)
DECLARE @daysleft INT;
DECLARE @instancename SYSNAME = CONVERT(SYSNAME, SERVERPROPERTY('InstanceName'));
EXEC @daysleft = xp_qv '2715127595', @instancename;
SELECT @daysleft AS DaysLeft;
```

## Security notes (read before a production rollout)

The lab defaults favor automation speed; harden these for production:

- **Web UI**: `bootstrap-jumphost.sh` binds uvicorn to `0.0.0.0:3000` with **no
  authentication** — anyone who can reach the jump host can trigger deployments and read job
  logs. Restrict port 3000 to operator IPs at the firewall (or bind to `127.0.0.1` and use SSH
  port-forwarding: `ssh -L 3000:localhost:3000 <jump-host>`).
- **Inventories**: per-job inventory files under `data/inventory/` contain the SSH password
  (`ansible_password=`); they are written `0600`. Prefer SSH keys for the `autoprovision` user
  in production and leave the password fields empty.
- **SSH host keys**: `ansible/ansible.cfg` sets `host_key_checking = False` for first-contact
  automation. For production, pre-populate `known_hosts` and set it back to `True`.
- **Derived passwords**: `mssql_ag.yml` derives Pacemaker/hacluster/cert/master-key passwords
  from the AG name when not provided (`<ag>-…-Pa55!`). Always pass explicit strong values for
  production (`pacemaker_password`, `hacluster_password`, `cert_password`,
  `master_key_password`).
- **Secrets in logs/process list**: playbook passwords travel via `--extra-vars` (visible in
  `ps` on the jump host while a job runs) and job logs are world-readable in the UI; sensitive
  tasks use `no_log`, but treat jump-host shell access as privileged.
- **PEMs**: pasted certs are staged to `data/certs/<track>/` (key `0600`) and are NOT stored in
  the DB; delete them after rotation if the jump host is shared.
- **Backups**: run the **Backups & DR** cards (etcd + MSSQL) and point targets at NFS/NAS —
  same-disk backups don't survive the VM.

## Troubleshooting (common)

| Symptom | Fix |
| ------- | --- |
| RKE2 node `NotReady` | Check `rke2-server`/`rke2-agent` service + token; Canal pods in `kube-system`. |
| Two ingress controllers fighting for 80/443 | Confirm the RKE2 bundled ingress was disabled (`disable:` in `/etc/rancher/rke2/config.yaml`). |
| `shared-gateway-istio` has no EXTERNAL-IP | MetalLB must back the `LoadBalancer` (apply `istio-gateway.yaml` to create it); production uses a VIP. |
| WSO2 TLS errors | Secret `wso2-ingress-cert` must be in **`istio-system`**; the Gateway API `Gateway` reloads it automatically (no restart needed). |
| HTTPRoute not routing | Gateway API CRDs must be installed and pods must carry the `istio.io/dataplane-mode=ambient` namespace label (`istioctl ztunnel-config workloads`). |
| AG replica not HEALTHY | Re-check cert exchange + `Hadr_endpoint` on all nodes (see `mssql_ag.yml` checklist). |
| GitLab Runner `404/403` on job request | Create a new instance runner token in GitLab UI, paste into the GitLab card, re-run. |
| Kibana Fleet `encrypted saved object api key` | Set a 32+ char `xpack.encryptedSavedObjects.encryptionKey` in `docker/elk/kibana/config/kibana.yml`. |

---

## Repository map

| Path | Purpose |
| ---- | ------- |
| `bootstrap-jumphost.sh` | One-shot jump host prep + start the web UI |
| `app/` | FastAPI control plane — `main.py` + `ui_parallel.html` (the multi-track dashboard at `/`) |
| `ansible/rke2_cluster.yml` | RKE2 servers + agents install (Canal, bundled ingress disabled) |
| `ansible/k8s_addons.yml` | Per-cluster add-ons: MetalLB · Istio ambient + shared Gateway · cert-manager + internal CA · ArgoCD · Headlamp |
| `ansible/k8s_wso2.yml` | WSO2 APIM/IS — renders `WSO2_APIM_KUBE_ISTIO/` and applies (ambient enrollment) |
| `ansible/k8s_cert.yml` | TLS secret for the shared gateway (`istio-system`) — PEM or cert-manager auto-renew |
| `ansible/k8s_etcd_backup.yml`, `ansible/mssql_backup.yml` | Backups: RKE2 etcd snapshots · MSSQL FULL/LOG + retention |
| `ansible/mssql_single.yml`, `ansible/mssql_ag.yml`, `ansible/mssql_ag_clean.yml` | SQL Server 2025/2022 single · HA AG (Pacemaker) · AG cleanup/reset |
| `ansible/traefik_stack.yml` | Traefik edge proxy — every Docker VM, right after base; owns the `platform` network |
| `ansible/docker_*.yml`, `elk_stack.yml`, `gitlab_stack.yml`, `sonarqube_stack.yml` | Docker platform stacks (platform = PostgreSQL + Dockhand only) |
| `rke2-cluster/` | RKE2 cluster + Istio/ArgoCD/Headlamp/WSO2 runbooks (prod, uat, shared) |
| `WSO2_APIM_KUBE_ISTIO/` | Team's WSO2 + Istio deployment repo (authoritative for WSO2) |
| `planning/` | Requirement docs (RKE2/Istio/MSSQL/parallel) — start with `00-old-vs-new.md` |
| `mssql/` | SQL Server manual-install + theory guides (Linux AG, Windows-AD alternative) |
| `docker/` | Docker compose for the platform + ELK |
