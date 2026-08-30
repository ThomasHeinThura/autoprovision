# Changelog

All notable changes to the Autoprovision control plane.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning is [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Capability status lives in [FEATURES.md](FEATURES.md); the stack itself in [techstack.md](techstack.md).

---

## [Unreleased]

Planned work, agreed in [docs/specs/](docs/specs/) and awaiting approval. Nothing below is built.

### Phase A+B — Foundation · [spec](docs/specs/2026-08-08-foundation-design.md)

**Fixed**

- **Bulk run can no longer start destructive workloads.** `Run All Configured` treated
  `mssql_ips` and `docker_ip` as "configured", and both are fields on the availability-group
  teardown and the SonarQube purge — so filling those cards once and clicking Run All executed
  them with no confirmation. Destructive workloads are now flagged in the registry, excluded from
  bulk run **in the backend**, and require a typed confirmation token that `POST /tracks/start`
  enforces, so the guarantee survives a direct API call.
- **Workload registry drift.** `sonarqube_up` and `sonarqube_clean` existed in the UI but not in
  `ALL_TRACKS`, so their settings were silently discarded, and reset and log endpoints returned
  400 while the runs themselves appeared to succeed. Rather than adding two strings, `workloads.py`
  becomes the single source of truth and `ALL_TRACKS` is derived from it — the whole class of bug
  is removed.
- **README described a different product in three places** — the `ansible.cfg` path, the UAT
  database topology, and `CLUSTER_TYPE`. The last is the material one: the README described a
  read-scale group with manual failover while the UI and the lab record both describe a Pacemaker
  cluster with automatic failover. The lab record is authoritative.
- Removed the dead `mssql_ip` key from the bulk-run detection set.
- `.gitignore` no longer excludes `.claude`, which would have silently dropped the AI-DLC assets.

**Added**

- **Preflight workload** — a read-only sweep across every host reporting reachability, OS release,
  sudo, free disk, clock skew and DNS resolution. Catches the wrong-Ubuntu-release and
  clock-skew-broke-the-certificate-exchange failures before 40 minutes are spent installing.
- **Host bootstrap workload** — creates the `autoprovision` account and installs the jump host's
  SSH key across every machine, then reconnects as it and asserts `sudo -n true`. Replaces one
  manual SSH session per machine, and moves the whole estate to key-based authentication.
- **AI-DLC** installed as a generated `CLAUDE.md` plus `.aidlc-rule-details/`, with
  `scripts/install-aidlc.sh` regenerating it deterministically so an upstream version bump never
  loses project context.
- Contract tests asserting every registry entry is routable and destructive workloads cannot be
  bulk-run.
- A link checker in pre-commit, so documentation links cannot silently rot.

**Changed**

- Repository reorganised: documentation under `docs/` split into `planning`, `runbooks`, `specs`
  and `status`; loose root files moved to `examples/`, `assets/` and `scripts/`. Every relative
  link rewritten as part of the move.
- The README's workload table is generated from the registry rather than maintained by hand.

### Phase C+D — Console · [spec](docs/specs/2026-08-08-console-design.md)

**Added**

- **Run sheet** replacing the flat sidebar — one environment per screen, workloads as rows with
  ordinals hanging in a left margin, and a segmented step ribbon showing discrete Ansible plays
  rather than a percentage.
- **Dependency awareness** — a workload reports `Waiting on 3 · RKE2 cluster` instead of appearing
  runnable and then failing. Advisory for single runs, enforced for bulk run.
- **Requirements, Guide and Theory tabs** on every workload. Requirements states VM count, sizing,
  ports and a pre-run checklist, generated from the configuration you chose. Lab findings — the
  Corosync `127.0.1.1` split brain, the clock-skew rule — are carried into it so a discovery
  reaches the operator who needs it.
- **Handbook** assembling every Theory page into one manual.
- Log search, filtering to changed or failed, follow, and download.
- Deep links to a workload, so a failing run can be pasted into a chat.

**Changed**

- Rewritten in React and TypeScript, built off-host with the output committed, so the jump host
  still needs neither Node nor internet access.
- Job polling replaced by server-sent events. The previous approach re-sent the entire log every
  1.5 seconds — roughly a megabyte per interval with six parallel runs.
- `main.py` split into `workloads`, `planner`, `runner`, `state`, `deps` and `content`.
- Plan preview moved out of the log pane, which it used to overwrite.

**Removed**

- `app/ui_parallel.html`, deleted rather than left to rot.

### Phase E — Stateful provisioning · [spec](docs/specs/2026-08-08-database-secrets-design.md)

**Added**

- **Database selection wizard** — engine, then platform, then mode, then HA shape, with each
  answer revealing the next and the requirements panel recomputing at every step. Unavailable
  combinations are shown disabled with the reason visible rather than hidden.
- Choosing **SQL Server on Windows** is an explicit stop naming the manual runbook, rather than a
  silent assumption of Linux.
- **PostgreSQL** — single, streaming replication, and Patroni with etcd and HAProxy.
- **MySQL** — single, semi-synchronous replication, InnoDB Cluster, and multi-primary with a
  warning about write-conflict semantics.
- **Two-tier database users** — a provisioning admin disabled after install, and one
  least-privilege runtime login per component. Built-in superusers disabled, renamed or scoped.
- **Object storage** — MinIO or SeaweedFS, standalone or distributed across 2–4 nodes, with the
  minimum-4-drives, identical-layout and sequential-hostname rules enforced before anything runs.
- **Monitoring wizard** — choose **one** stack (LGTM, OpenSearch or Elastic), choose whether it
  runs in the cluster or on a Docker VM, choose single-node or HA. The console integrates the one
  you picked and does not deploy the others.

**Changed**

- Existing MSSQL playbooks moved under `ansible/db/mssql/` and refactored — structure only, with
  no behaviour change, validated by a full lab re-run before any new engine is added. They encode
  the Corosync fix, the SID handling and the primary-aware backup script, and that knowledge is
  the asset.

### Not sized for one estate

**Changed**

- **Environments are declared in [`config/environments.yml`](config/environments.yml), not
  hardcoded.** Adding one gives it a complete workload set, its own screen and its own recorded
  state with no code change. The registry builds itself from the config, and example addresses in
  form placeholders come from each environment's own subnet rather than another environment's.
- **Removed the four-node cap on object storage.** That was one engagement's machine budget, not
  a property of erasure coding. The planner now checks the erasure-set arithmetic and accepts
  whatever node count you actually have — tested at 4, 6, 8, 12, 16 and 24.
- [`docs/planning/vm-requirements-rke2.md`](docs/planning/vm-requirements-rke2.md) is marked as
  the historical record of one 19-machine rollout. New sizing lives in
  [`capacity-planning.md`](docs/planning/capacity-planning.md): per-role sizing, the counting
  rules the console enforces and why each exists, and worked examples from 3 machines to 50+.

**Added**

- **Topology view** — every machine you have configured, with its roles, the workloads that
  reference it, the networks actually in use, and a downloadable inventory of the whole estate.
  It flags machines carrying more than one role, and reports environments that saved state refers
  to but the config no longer declares.
- Fields carrying machine addresses are marked in the registry, so topology is derived rather
  than guessed from field-name patterns — and stays correct as workloads are added.

### Phase F — Secrets · [spec](docs/specs/2026-08-08-database-secrets-design.md)

**Added**

- **Infisical**, self-hosted, with a machine identity for the jump host.

**Fixed**

- Playbooks read credentials from the vault at run time, so passwords no longer appear in
  `--extra-vars` and are no longer visible in `ps` for the length of a run. Optional — the
  existing path remains, and the requirements panel shows what you give up without it.

---

## [0.9.0] — 2026-06-10

The current lab state, recorded in [docs/status/service-status.md](./docs/status/service-status.md).

### Added

- Parallel multi-workload execution with per-job inventories and per-workload logs.
- Per-step install status in SQLite, so a re-run skips completed steps unless forced.
- RKE2 cluster install and scaling — Canal CNI, bundled ingress disabled, kubeconfig retrieved.
- In-cluster add-ons: MetalLB in FRR-K8s mode, Istio 1.30 ambient with a single shared Gateway API
  gateway, cert-manager with an internal CA, ArgoCD, and Headlamp.
- WSO2 API Manager and Identity Server, rendered from the team repository with environment
  hostnames and database address, enrolled in the ambient mesh.
- SQL Server 2025 — single instance, and a three-node availability group with Pacemaker,
  `CLUSTER_TYPE=EXTERNAL`, synchronous commit and automatic failover.
- WSO2 database provisioning with a login SID identical across every replica, so a failover does
  not orphan the user.
- Docker platform stacks: base, Traefik, PostgreSQL with Dockhand, GitLab CE with runner and
  registry, SonarQube, and the Elastic Stack.
- Certificate workloads for the shared Istio gateway and for Traefik.
- Backups: RKE2 etcd snapshots, and primary-aware SQL Server FULL and LOG backups.

### Fixed

- **Corosync split brain** caused by Ubuntu's default `127.0.1.1` hostname mapping. Removed the
  mapping and pinned each ring address to the LAN IP.

### Known issues

- The AG listener is not registered by the playbook — `sys.availability_group_listeners` stays
  empty under `CLUSTER_TYPE=EXTERNAL`. The Pacemaker virtual IP is the working endpoint.
- The console has no authentication and binds `0.0.0.0:3000`.
- Provisioning passwords travel via `--extra-vars` and are visible in `ps` during a run.

---

## Migration from the Talos design

The Kubernetes layer moved from **Talos with Cilium and Envoy Gateway** to **RKE2 with the default
Canal CNI and Istio ambient**. Everything else — ArgoCD, Headlamp, WSO2, the Docker platform, the
observability tier — kept its intent. Two requirements were added: SQL Server installed by Ansible
onto customer VMs rather than treated as external, and parallel installation of every stack on
execution day.

Detail in [docs/planning/00-old-vs-new.md](./docs/planning/00-old-vs-new.md).
