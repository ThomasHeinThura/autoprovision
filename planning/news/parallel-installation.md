# Parallel Installation Model (New)

The customer wants execution day to run **2 Kubernetes clusters + 2 ELK + 1 GitLab** (and the
MSSQL tracks) **at the same time**, with "no issues." This document defines how the control
plane achieves safe parallelism and how the UI tracks map to Ansible jobs.

## Tracks

Each track is an independent unit of work the operator can launch on its own. Tracks run
concurrently; one slow track never blocks another.

| Track key | Stack | Playbook | Target hosts |
| --------- | ----- | -------- | ------------ |
| `prod_k8s` | Prod RKE2 cluster | `ansible/rke2_cluster.yml` | 3 servers + 5 agents |
| `uat_k8s`  | UAT RKE2 cluster | `ansible/rke2_cluster.yml` | 1 server + 2 agents |
| `prod_elk` | Prod ELK | `ansible/elk_stack.yml` (+ base) | Prod ELK VM |
| `uat_elk`  | UAT ELK | `ansible/elk_stack.yml` (+ base) | UAT ELK VM |
| `gitlab`   | GitLab platform | `ansible/docker_vm_base.yml` → `docker_platform_up.yml` → `gitlab_stack.yml` → `sonarqube_stack.yml` | GitLab VM |
| `prod_sql` | Prod MSSQL AG | `ansible/mssql_ag.yml` | 3 MSSQL VMs |
| `uat_sql`  | UAT MSSQL | `ansible/mssql_single.yml` | UAT MSSQL VM |

## Why parallel runs are safe

The old control plane wrote a **single shared inventory file** (`ansible/inventory`) and a
**single per-action log** (e.g. `elk.log`). Two tracks running at once would overwrite each
other's inventory and log. The reworked app fixes this:

1. **Per-job inventory** — every job generates its own
   `data/inventory/<job_id>.ini` and runs `ansible-playbook -i data/inventory/<job_id>.ini`.
   No two jobs share an inventory file.
2. **Per-job logs** — every job writes `data/logs/<job_id>.log`. The UI tracks each job by its
   `job_id` and renders its log into that track's own panel.
3. **Async jobs** — the backend already launches each job with `asyncio.create_task`, so N jobs
   progress independently. `ansible.cfg` keeps `forks = 20`, enough for the largest track
   (8-node Prod cluster).

## UI behaviour

- The dashboard (`/`) shows one **card per track**.
- Each card has: target inputs, a Run button, a status badge (queued / running / completed /
  failed), and a log pane.
- Pressing Run on multiple cards starts multiple jobs; the page polls **all** active `job_id`s
  in parallel and updates each card independently.
- Per-track inputs persist to SQLite (`targets` table) so a browser refresh keeps the values.

## Recommended order within parallelism

Although tracks run together, a few soft dependencies help:

1. Start **GitLab** first (ArgoCD later pulls WSO2 manifests from it).
2. Start **RKE2 clusters**, **ELK** stacks, and **MSSQL** tracks immediately after — they have no
   dependency on each other.
3. Once a cluster is up, run the in-cluster add-on runbook (Istio → cert-manager → ArgoCD →
   Headlamp → WSO2). WSO2 needs both GitLab (manifests) and MSSQL (database) ready.

## Capacity note

Running all 7 tracks at once is well within `forks = 20`. The jump host needs enough CPU/RAM to
host the Python UI plus parallel `ansible-playbook` processes; the sizing in
[vm-requirements-rke2.md](vm-requirements-rke2.md) (4 vCPU / 8 GB) is the minimum — bump to
8 vCPU / 16 GB if running all tracks simultaneously feels tight.
