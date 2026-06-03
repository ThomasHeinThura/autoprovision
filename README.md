# Autoprovision — RKE2 + Istio Control Plane

End-to-end automation for the production + UAT rollout: one jump host runs a Python control plane
that installs **RKE2 Kubernetes clusters, Docker platform stacks (GitLab + ELK), and SQL Server**
— all in **parallel** — then per-cluster add-ons (Istio, cert-manager, ArgoCD, Headlamp) and
**WSO2** are deployed from the team's repo.

> **What changed from the original design:** the Kubernetes layer moved from
> **Talos + Cilium + Envoy Gateway** to **RKE2 + default CNI (Canal) + Istio**. SQL Server now
> runs on dedicated VMs installed by Ansible. The control plane now runs multiple stacks at once.
> Old docs are preserved under [`planning/old/`](planning/old/) and [`talos-cluster/`](talos-cluster/);
> the new requirement docs are under [`planning/news/`](planning/news/). Start with
> [planning/news/00-old-vs-new.md](planning/news/00-old-vs-new.md).

---

## Versions (pinned)

| Layer | Pin |
| ----- | --- |
| RKE2 | **v1.36.1+rke2r2** (Kubernetes v1.36.1) |
| CNI | **Canal** (default, bundled with RKE2) — kube-proxy kept |
| K8s ingress | **Istio 1.30** (istioctl default profile, gateway in `istio-system`) |
| SQL Server | **2022** — Prod read-scale AG (3 nodes), UAT single instance |
| WSO2 | APIM 4.7.0 / IS 7.3.0 via [`WSO2_APIM_KUBE_ISTIO/`](WSO2_APIM_KUBE_ISTIO/README.md) |
| Docker platform | GitLab CE 19.0.1, ELK 9.1.4, PostgreSQL 17.10, Traefik v3.7.1, SonarQube, ElastAlert2 |

Full matrix: [planning/news/version-rke2.md](planning/news/version-rke2.md).

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

Sizing: [planning/news/vm-requirements-rke2.md](planning/news/vm-requirements-rke2.md).

## What is automated vs documented

| Step | How |
| ---- | --- |
| Docker base + GitLab + SonarQube + ELK | **Ansible** (web UI tracks) |
| SQL Server (single + read-scale AG) | **Ansible** (web UI tracks) |
| RKE2 cluster install (servers + agents) | **Ansible** (web UI tracks) |
| Istio, cert-manager, ArgoCD, Headlamp, OTel | **Runbook** ([rke2-cluster/](rke2-cluster/)) |
| WSO2 APIM + IS | **Team repo** [WSO2_APIM_KUBE_ISTIO](WSO2_APIM_KUBE_ISTIO/README.md) |

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
- Legacy single-Docker page is still at `http://<jump-host-ip>:3000/docker`.

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
| **Prod MSSQL AG** | SQL Server 2022 on 3 nodes + read-scale Always On AG (first IP = primary) | 3 node IPs, SA password, AG name |
| **UAT MSSQL** | SQL Server 2022 single instance | VM IP, SA password |

> **Every Docker VM runs Traefik.** Traefik is installed as its own stack right after Docker base
> and **owns the shared `platform` network** that the service stacks attach to. Each service is
> reachable over HTTPS at its domain (GitLab/registry/Dockhand/SonarQube on the GitLab VM; Kibana
> on each ELK VM) — no raw service ports. The GitLab VM's platform stack is **PostgreSQL + Dockhand
> only** (Traefik is separate). This Traefik (v3.7.1) is the Docker-platform ingress and is
> unrelated to Istio (Kubernetes ingress).

> **Order tip:** start **GitLab** first (it hosts manifests/registry), then fire everything else.
> All tracks are independent and run together.

### CLI equivalent (optional)

The same playbooks can run directly from the jump host with a hand-written inventory
(see [ansible/inventory](ansible/inventory) for example groups):

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

## Step 4 — Per-cluster add-ons (runbook)

For **each** cluster, follow the runbook. Production:
[rke2-cluster/prod-rke2-installation.md](rke2-cluster/prod-rke2-installation.md) · UAT:
[rke2-cluster/uat-rke2-installation.md](rke2-cluster/uat-rke2-installation.md) · shared detail:
[rke2-cluster/rke2-addons-istio-argocd-headlamp.md](rke2-cluster/rke2-addons-istio-argocd-headlamp.md).

Order (per cluster, `KUBECONFIG` pointed at it):

```bash
# 1. Istio 1.30 — istioctl default profile (ingressgateway lands in istio-system, as WSO2 expects)
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.30.0 TARGET_ARCH=x86_64 sh -
export PATH=$PWD/istio-1.30.0/bin:$PATH
istioctl install --set profile=default -y

# 2. cert-manager  3. ArgoCD  4. Headlamp  5. OpenTelemetry Collector
#    (Helm commands in rke2-addons-istio-argocd-headlamp.md; ArgoCD/Headlamp exposed via Istio)
```

## Step 5 — WSO2 (team's repo — her steps)

WSO2 APIM (Control Plane + Internal/External Gateways) and Identity Server are deployed from
[`WSO2_APIM_KUBE_ISTIO/`](WSO2_APIM_KUBE_ISTIO/README.md). With `KUBECONFIG` set to the cluster
and Istio already installed:

```bash
cd WSO2_APIM_KUBE_ISTIO

# namespaces + sidecar injection
kubectl create ns wso2-cp; kubectl create ns wso2-is
kubectl create ns wso2-internal-gw; kubectl create ns wso2-external-gw
for ns in wso2-cp wso2-is wso2-internal-gw wso2-external-gw; do kubectl label ns $ns istio-injection=enabled --overwrite; done

# certs + Istio ingress TLS secret in istio-system, then restart the gateway
./scripts/generate-local-certificates.sh
kubectl -n istio-system create secret tls wso2-ingress-cert \
  --cert=certificates/server.crt --key=certificates/server.key --dry-run=client -o yaml | kubectl apply -f -
kubectl -n istio-system rollout restart deploy/istio-ingressgateway

# (optional) build images with MSSQL JDBC baked in: ./scripts/build-apim-images.sh
kubectl apply -f istio-gateway.yaml
kubectl apply -f control-plane/ -f internal-gw/ -f external-gw/ -f wso2-is/
```

**Database wiring (read-scale AG):** load `mssql/shared_mssql.sql` and `mssql/apim_mssql.sql`,
then point WSO2 JDBC at the **AG primary node** in Production (no listener with `CLUSTER_TYPE=NONE`)
or the **single instance** in UAT. Details: [planning/news/wso2-rke2.md](planning/news/wso2-rke2.md).

WSO2 ingress hosts (from the repo's `istio-gateway.yaml`, all TLS on 443 →
secret `wso2-ingress-cert` in `istio-system`): `apim.example.com`, `internal-gw.example.com`,
`external-gw.example.com`, `wso2is.example.com`. Point DNS / `/etc/hosts` at the Istio ingress
gateway external IP.

## Step 6 — Observability, migration, validation

Per ELK stack: configure Elasticsearch ILM/retention, archive paths to NFS/NAS, run the 8.14 →
9.1.4 snapshot/restore migration, the WSO2 APIM credential migration job, and the base
ElastAlert2 rules. See [planning/news/installation-steps-rke2.md](planning/news/installation-steps-rke2.md).

---

## Health checks

```bash
# Kubernetes (per cluster)
kubectl get nodes -o wide                                   # Ready, CNI = Canal
kubectl get pods -A
kubectl get svc -n istio-system istio-ingressgateway        # EXTERNAL-IP populated
kubectl get gateway,virtualservice -A
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

## Troubleshooting (common)

| Symptom | Fix |
| ------- | --- |
| RKE2 node `NotReady` | Check `rke2-server`/`rke2-agent` service + token; Canal pods in `kube-system`. |
| Two ingress controllers fighting for 80/443 | Confirm the RKE2 bundled ingress was disabled (`disable:` in `/etc/rancher/rke2/config.yaml`). |
| Istio gateway has no EXTERNAL-IP | RKE2 ServiceLB or MetalLB must back the `LoadBalancer`; production uses a VIP. |
| WSO2 TLS errors | Secret `wso2-ingress-cert` must be in **`istio-system`** and the gateway restarted. |
| AG replica not HEALTHY | Re-check cert exchange + `Hadr_endpoint` on all nodes (see `mssql_ag.yml` checklist). |
| GitLab Runner `404/403` on job request | Create a new instance runner token in GitLab UI, paste into the GitLab card, re-run. |
| Kibana Fleet `encrypted saved object api key` | Set a 32+ char `xpack.encryptedSavedObjects.encryptionKey` in `docker/elk/kibana/config/kibana.yml`. |

---

## Repository map

| Path | Purpose |
| ---- | ------- |
| `bootstrap-jumphost.sh` | One-shot jump host prep + start the web UI |
| `app/` | FastAPI control plane — `ui_parallel.html` (`/`, multi-track) + legacy `ui_docker.html` (`/docker`) |
| `ansible/rke2_cluster.yml` | RKE2 servers + agents install (Canal, bundled ingress disabled) |
| `ansible/mssql_single.yml`, `ansible/mssql_ag.yml` | SQL Server 2022 single / read-scale AG |
| `ansible/traefik_stack.yml` | Traefik edge proxy — every Docker VM, right after base; owns the `platform` network |
| `ansible/docker_*.yml`, `elk_stack.yml`, `gitlab_stack.yml`, `sonarqube_stack.yml` | Docker platform stacks (platform = PostgreSQL + Dockhand only) |
| `rke2-cluster/` | RKE2 cluster + Istio/ArgoCD/Headlamp/WSO2 runbooks (prod, uat, shared) |
| `WSO2_APIM_KUBE_ISTIO/` | Team's WSO2 + Istio deployment repo (authoritative for WSO2) |
| `planning/news/` | New-requirement docs (RKE2/Istio/MSSQL/parallel) |
| `planning/old/`, `talos-cluster/` | Original requirement docs (kept for reference) |
| `docker/` | Docker compose for the platform + ELK |
