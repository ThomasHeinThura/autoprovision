# Installation Steps — RKE2 / Istio (New)

Updated operator flow for the new requirement. Supersedes
[planning/installation-steps.md](../installation-steps.md) for Production and UAT execution.
The old document remains valid as the previous flow.

## Summary of the new flow

1. Bootstrap the jump host from GitHub (now installs `kubectl`, `helm`, `istioctl` — not `talosctl`).
2. Open the Python web UI (multi-track dashboard).
3. Install Docker platform stacks (GitLab + 2 ELK) **in parallel** via Ansible.
4. Install MSSQL (Prod AG + UAT single) **in parallel** via Ansible.
5. Install RKE2 clusters (Prod + UAT) **in parallel** via Ansible.
6. Per cluster, follow the in-cluster runbook (Istio → cert-manager → ArgoCD → Headlamp → WSO2).
7. Run observability lifecycle + migration tasks.

Automation boundary: **Ansible installs Docker stacks, MSSQL, and RKE2.** The in-cluster
add-ons are **runbooks** under [rke2-cluster/](../../rke2-cluster/); WSO2 is **GitOps via ArgoCD**.

---

## Step 1 — SSH into the jump host

```bash
ssh <username>@<jump-host-ip>
git clone https://github.com/ThomasHeinThura/autoprovision.git
cd autoprovision
sh bootstrap-jumphost.sh
```

The bootstrap script prepares the jump host and starts the web UI on port 3000.

### Bootstrap tasks (updated)

Same as the old flow, except the Kubernetes tooling:

- Install `kubectl`, `helm`, and `istioctl` (instead of `talosctl`).
- Everything else (Python venv, Ansible, ansible-runner, SQLite, data dirs) is unchanged.

---

## Step 2 — Open the web UI

```
http://<jump-host-ip>:3000/
```

The home page is the **multi-track dashboard**. Each track is a card you can run independently
and concurrently. See [parallel-installation.md](parallel-installation.md).

Legacy single-Docker page is still available at `http://<jump-host-ip>:3000/docker`.

---

## Step 3 — Fill per-track inputs

| Track | Inputs |
| ----- | ------ |
| GitLab | VM IP, SSH user/pass, GitLab domain, registry domain, runner token (optional) |
| Prod ELK / UAT ELK | VM IP, SSH user/pass, Kibana domain |
| Prod RKE2 | cluster name, 3 control-plane IPs, 5 worker IPs, SSH user/pass, RKE2 token, registration address |
| UAT RKE2 | cluster name, 1 control-plane IP, 2 worker IPs, SSH user/pass, RKE2 token |
| Prod MSSQL AG | 3 VM IPs, SSH user/pass, SA password, AG name, listener name/IP |
| UAT MSSQL | VM IP, SSH user/pass, SA password |

Inputs persist per track in SQLite.

---

## Step 4 — Run tracks (parallel)

### 4a. Docker platform tracks

- **GitLab** — runs base → **Traefik** → platform (PostgreSQL + Dockhand) → GitLab → SonarQube.
- **Prod ELK** and **UAT ELK** — run base → **Traefik** → ELK stack on each ELK VM (Kibana via Traefik).

Traefik is installed on **every** Docker VM right after the Docker base and owns the shared
`platform` network; each service is exposed over HTTPS at its domain through Traefik. The GitLab
VM's platform stack is **PostgreSQL + Dockhand only**.

These three run concurrently. GitLab should be started first since ArgoCD will later pull
WSO2 manifests from it.

### 4b. MSSQL tracks

- **Prod MSSQL AG** — installs SQL Server 2022 on 3 nodes and bootstraps the Always On AG.
  See the manual verification checklist in [ansible/mssql_ag.yml](../../ansible/mssql_ag.yml)
  output and [rke2-cluster runbooks].
- **UAT MSSQL** — installs a single SQL Server 2022 instance.

### 4c. RKE2 cluster tracks

For each cluster the web UI triggers `ansible/rke2_cluster.yml`, which:

1. Installs RKE2 **server** on the first control-plane node — bootstraps the cluster with the
   **default CNI (Canal)** (no `cni: none` override) and kube-proxy enabled.
2. Joins remaining **servers** (Prod: 2 more) using the registration address + token.
3. Joins **agents** (workers) using the registration address + token.
4. Copies `/etc/rancher/rke2/rke2.yaml` back to the jump host as the cluster kubeconfig under
   `data/k8s/<cluster>/kubeconfig` (server address rewritten to the registration address).

After this, `kubectl --kubeconfig data/k8s/<cluster>/kubeconfig get nodes` shows all nodes Ready
(Canal provides networking immediately — no separate CNI install needed).

---

## Step 5 — In-cluster add-ons (runbook, per cluster)

Follow the matching guide:

- Production: [rke2-cluster/prod-rke2-installation.md](../../rke2-cluster/prod-rke2-installation.md)
- UAT: [rke2-cluster/uat-rke2-installation.md](../../rke2-cluster/uat-rke2-installation.md)
- Shared add-on detail: [rke2-cluster/rke2-addons-istio-argocd-headlamp.md](../../rke2-cluster/rke2-addons-istio-argocd-headlamp.md)

Order per cluster:

1. Install Istio (`base`, `istiod`, ingress `gateway`).
2. Install cert-manager.
3. Install ArgoCD; expose via Istio `Gateway`/`VirtualService`.
4. Install Headlamp; expose via Istio.
5. Install OpenTelemetry Collector.
6. Define ArgoCD `Application`s for WSO2 APIM/IS (manifests in GitLab); sync; expose WSO2 via Istio.

---

## Step 6 — Kubernetes Git setup (GitLab + ArgoCD)

Same as the old flow, with Istio resources in place of Envoy `HTTPRoute`:

1. Create/select GitLab project(s) for Kubernetes manifests.
2. Push WSO2 APIM/IS Kubernetes YAML (including Istio `Gateway`/`VirtualService`) to GitLab.
3. Push ArgoCD `Application` manifests pointing to those paths.
4. ArgoCD syncs WSO2 into each cluster.

See [wso2-rke2.md](wso2-rke2.md) for the Istio exposure manifests and MSSQL connection notes.

---

## Step 7 — Observability, migration, validation

Unchanged from the old flow:

1. Configure Elasticsearch ILM lifecycle + retention (per ELK stack).
2. Configure archive paths to external NFS/NAS.
3. ELK migration 8.14 → 9.1.4 via snapshot/restore; validate index compatibility.
4. WSO2 APIM credential migration (Python job).
5. Create base ElastAlert2 rules; validate end-to-end alert flow.

---

## Automation vs manual (quick reference)

| Item | Where |
| ---- | ----- |
| Docker base, platform, GitLab, SonarQube, ELK | Ansible (existing playbooks) |
| MSSQL single + AG | Ansible (`mssql_single.yml`, `mssql_ag.yml`) |
| RKE2 cluster | Ansible (`rke2_cluster.yml`) |
| Istio, cert-manager, ArgoCD, Headlamp, OTel | Runbook (markdown) |
| WSO2 APIM/IS | GitOps via ArgoCD |
| DNS, firewall, NFS/NAS, TLS handover | Customer prerequisites (checklist) |
