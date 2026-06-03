# Updated MVP — RKE2 / Istio (New)

Supersedes [planning/updated-mvp.md](../updated-mvp.md) for the new requirement. The old MVP
remains valid as the previous record.

## Objective

Deliver the same infrastructure-automation MVP, with the Kubernetes layer changed from
**Talos + Cilium + Envoy Gateway** to **RKE2 + default CNI (Canal) + Istio**, plus
SQL Server VMs installed by Ansible, and a control plane that can install **multiple stacks
in parallel** on execution day.

The MVP proves:

1. Core infrastructure provisioned reliably from a single jump host.
2. Docker services deployed once via Ansible in a fixed sequence (per Docker VM).
3. **RKE2 clusters** installed via Ansible; in-cluster services deployed via runbooks
   (Istio → cert-manager → ArgoCD → Headlamp → WSO2) and ArgoCD GitOps.
4. **MSSQL** installed via Ansible (Prod AG, UAT single).
5. Observability and migration paths functional.
6. **Parallel** operations triggered and monitored from the Python web UI.

---

## Environment Model

### Production (12 VMs)
- 3 RKE2 control plane (servers) + 5 RKE2 workers (agents).
- 1 ELK Docker VM.
- 3 MSSQL VMs (Always On Availability Group).

### UAT (5 VMs)
- 1 RKE2 control plane + 2 RKE2 workers.
- 1 MSSQL single instance.
- 1 ELK Docker VM.

### Shared (2 VMs)
- 1 GitLab Docker VM ("in between").
- 1 jump host.

See [vm-requirements-rke2.md](vm-requirements-rke2.md) for sizing.

---

## Parallel Execution Model

On execution day the operator runs these **at the same time** from the multi-track dashboard:

- **Track 1:** Prod RKE2 cluster (Ansible install).
- **Track 2:** UAT RKE2 cluster (Ansible install).
- **Track 3:** Prod ELK (Ansible Docker deploy).
- **Track 4:** UAT ELK (Ansible Docker deploy).
- **Track 5:** GitLab (Ansible Docker deploy).
- **Track 6:** Prod MSSQL AG (Ansible).
- **Track 7:** UAT MSSQL single (Ansible).

Each track is an independent job with its **own inventory file and its own log**, so they do
not collide. See [parallel-installation.md](parallel-installation.md).

GitLab should be installed first (or early) because the RKE2 clusters' ArgoCD pulls WSO2
manifests from it — but cluster install and ELK/MSSQL tracks can all run while GitLab is coming up.

---

## Deployment Strategy

### Phase A — Jump host bootstrap
SSH to jump host, clone repo, run `bootstrap-jumphost.sh`, open the web UI. The bootstrap now
installs `kubectl`, `helm`, and `istioctl` (instead of `talosctl`).

### Phase B — Docker platform (per Docker VM, via Ansible)
For GitLab VM and each ELK VM, in fixed order where applicable:
1. Docker CE + base packages.
2. **Traefik** — installed on every Docker VM right after the base; owns the shared `platform`
   network. Each service is exposed over HTTPS at its domain via Traefik.
3. (GitLab VM) Platform = **PostgreSQL + Dockhand only**, then GitLab CE + Runner + Registry, then SonarQube.
4. (ELK VMs) ELK stack (Elasticsearch, Logstash, Kibana via Traefik, Fleet/APM), ElastAlert2.

Prod ELK, UAT ELK, and GitLab run as three parallel tracks.

### Phase C — MSSQL (via Ansible)
1. Prod: install SQL Server 2022 on 3 VMs, configure Always On AG + listener.
2. UAT: install SQL Server 2022 single instance.

### Phase D — RKE2 clusters (via Ansible)
For each cluster (Prod and UAT, in parallel):
1. Install RKE2 **server** on the first control-plane node (bootstraps cluster, default CNI).
2. Join remaining **servers** (Prod only) via the registration address.
3. Join **agents** (workers).
4. Fetch kubeconfig back to the jump host.

### Phase E — In-cluster add-ons (via runbooks, not Ansible)
Per cluster, following [rke2-cluster/](../../rke2-cluster/):
1. Istio (base, istiod, ingress gateway).
2. cert-manager.
3. ArgoCD (+ expose via Istio).
4. Headlamp (+ expose via Istio).
5. OpenTelemetry Collector.
6. WSO2 APIM + IS via ArgoCD (manifests in GitLab), exposed via Istio `Gateway`/`VirtualService`.

### Phase F — Observability, migration, validation
Same as old MVP: ILM/retention, ELK 8.14 → 9.1.4 snapshot/restore, WSO2 key migration,
ElastAlert2 rules, end-to-end alert validation.

---

## What is automated vs documented

| Step | Automation |
| ---- | ---------- |
| Docker platform (GitLab, SonarQube, ELK, ElastAlert2) | **Ansible** (existing playbooks) |
| MSSQL (single + AG) | **Ansible** (new playbooks) |
| RKE2 cluster install | **Ansible** (new playbook) |
| Istio, cert-manager, ArgoCD, Headlamp, OTel | **Runbook** (markdown, manual/scripted) |
| WSO2 APIM/IS | **GitOps via ArgoCD** (manifests in GitLab) |

---

## Definition of Done

1. Jump host triggers Docker, MSSQL, and RKE2 tracks **in parallel** from the web UI.
2. All Docker services running on the GitLab VM and both ELK VMs.
3. Prod MSSQL AG healthy with a working listener; UAT MSSQL reachable.
4. Both RKE2 clusters running with default CNI; nodes Ready.
5. Istio, cert-manager, ArgoCD, Headlamp installed per runbook in both clusters.
6. WSO2 APIM/IS deployed via ArgoCD and connected to SQL Server (AG listener / UAT instance).
7. Elasticsearch, Kibana, alerting, lifecycle policies functional in both ELK stacks.
8. Migration steps documented and at least one dry run validated.

---

## Out of scope (unchanged from old MVP)

- Full self-service portal beyond deployment operations.
- Advanced RBAC in the web UI.
- Full DR orchestration beyond backup/restore validation.
- Ongoing GitOps management of Docker services.
