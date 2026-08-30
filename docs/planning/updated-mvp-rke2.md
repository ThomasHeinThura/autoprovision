# Updated MVP — RKE2 / Istio (New)

Supersedes the original Talos-era MVP doc (removed in cleanup). The old MVP
remains valid as the previous record.

## Objective

Deliver the same infrastructure-automation MVP, with the Kubernetes layer changed from
**Talos + Cilium + Envoy Gateway** to **RKE2 + default CNI (Canal) + Istio**, plus
SQL Server VMs installed by Ansible, and a control plane that can install **multiple stacks
in parallel** on execution day.

The MVP proves:

1. Core infrastructure provisioned reliably from a single jump host.
2. Docker services deployed once via Ansible in a fixed sequence (per Docker VM).
3. **RKE2 clusters** installed via Ansible; in-cluster services (MetalLB → Istio **ambient** +
   shared Gateway → cert-manager → ArgoCD → Headlamp → WSO2) deployed via web-UI workloads
   (`k8s_addons.yml` / `k8s_wso2.yml`), with the runbooks as the manual CLI reference.
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

### Phase E — In-cluster add-ons (via Ansible web-UI workloads; runbooks = manual reference)
Per cluster, via [ansible/k8s_addons.yml](../../ansible/k8s/addons.yml) /
[ansible/k8s_wso2.yml](../../ansible/k8s/wso2.yml) (runbook: [rke2-cluster/](../../docs/runbooks/)):
1. MetalLB (LoadBalancer IPs) — RKE2 ServiceLB disabled.
2. Istio **1.30 ambient** (istiod + istio-cni + ztunnel; no sidecars, no ingressgateway) +
   **one shared Gateway API `Gateway`** in `istio-system` (one MetalLB IP for ALL hosts; TLS
   secret `wso2-ingress-cert` in `istio-system`).
3. cert-manager + internal CA (`ca-issuer`) — the Certificate workload auto-issues/renews.
4. ArgoCD (exposed via `HTTPRoute` on the shared gateway).
5. Headlamp (same; skipped gracefully if the chart repo is blocked).
6. WSO2 APIM + IS — rendered from `WSO2_APIM_KUBE_ISTIO/` and applied; namespaces enrolled in
   ambient (`istio.io/dataplane-mode=ambient`); exposed via the shared gateway.
7. OpenTelemetry Collector (runbook).

### Phase F — Observability, migration, validation
Same as old MVP: ILM/retention, ELK 8.14 → 9.1.4 snapshot/restore, WSO2 key migration,
ElastAlert2 rules, end-to-end alert validation.

---

## What is automated vs documented

| Step | Automation |
| ---- | ---------- |
| Docker platform (GitLab, SonarQube, ELK, ElastAlert2) | **Ansible** (web UI tracks) |
| MSSQL (single + HA AG + cleanup/reset) | **Ansible** (web UI tracks) |
| RKE2 cluster install + scale | **Ansible** (web UI tracks) |
| MetalLB, Istio ambient + shared Gateway, cert-manager + internal CA, ArgoCD, Headlamp | **Ansible** (`k8s_addons.yml`, web UI cards; runbook = manual reference) |
| WSO2 APIM/IS | **Ansible** (`k8s_wso2.yml` renders the team repo, web UI cards); ArgoCD GitOps as follow-up |
| TLS certs (Traefik VMs + K8s secret, PEM or cert-manager auto-renew) | **Ansible** (web UI cards) |
| Backups (RKE2 etcd snapshots, MSSQL FULL/LOG) | **Ansible** (`k8s_etcd_backup.yml`, `mssql_backup.yml`, web UI cards) |
| OTel collector | **Runbook** |

---

## Definition of Done — status as of 2026-06-10 (lab)

1. ✅ Jump host triggers Docker, MSSQL, and RKE2 tracks **in parallel** from the web UI.
2. ✅ All Docker services running on the GitLab VM and the ELK VM(s) (GitLab, SonarQube,
   Dockhand, ELK behind Traefik — verified in [service-status.md](../../docs/status/service-status.md)).
3. ✅ MSSQL **HA AG** (Pacemaker, `CLUSTER_TYPE=EXTERNAL`) healthy; Pacemaker VIP is the
   working endpoint (T-SQL listener registration still flaky on Linux — VIP covers it).
   UAT single instance reachable.
4. ✅ RKE2 cluster(s) running with default CNI (Canal); nodes Ready on v1.36.1+rke2r2.
5. ✅ MetalLB, Istio **ambient** + shared Gateway, cert-manager + internal CA, ArgoCD,
   Headlamp installed via the web-UI workloads.
6. ✅ WSO2 APIM/IS deployed (web-UI workloads rendering `WSO2_APIM_KUBE_ISTIO/`) on Istio
   ambient, connected to MSSQL — **tested working in the lab**. (ArgoCD-GitOps handover is a
   follow-up, not a blocker.)
7. ✅ Elasticsearch, Kibana functional behind Traefik; alerting/ILM baseline in place.
8. ⬜ Migration steps documented and at least one dry run validated (**pending** — next lab
   cycle: full reroll from restore point, then migration rehearsal).

Production-grade additions now available (run them in the next cycle): RKE2 **etcd snapshot**
workload and **MSSQL FULL/LOG backup** workload (web UI → "Backups & DR").

---

## Out of scope (unchanged from old MVP)

- Full self-service portal beyond deployment operations.
- Advanced RBAC in the web UI.
- Full DR orchestration beyond backup/restore validation.
- Ongoing GitOps management of Docker services.
