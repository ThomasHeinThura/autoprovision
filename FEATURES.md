# Features

What the Autoprovision control plane does, and how confident you should be in each part.

| Mark | Meaning |
| ---- | ------- |
| ✅ | **Working and lab-tested** — run against real VMs |
| 🧪 | **Written and tested at the planner level, not yet run against real VMs** — the console builds a correct plan and the playbook asserts its own preconditions, but no lab run has proved it end to end |
| ⚠️ | Working, with a known gap — see the note |
| 🔨 | Specified, not built |
| 🧭 | Awaiting a decision from you |

**The distinction between ✅ and 🧪 is the important one.** Everything marked 🧪 has
unit tests for the decision logic and assertions in the playbook, but a playbook
is not proven until it has run against a real machine. Treat 🧪 as "ready to
trial in UAT", not "ready for Production".

---

## 1 · Execution engine

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | **Parallel workloads** | Independent and concurrent. Each run gets its own inventory and its own log. |
| ✅ | **Per-step install status** | SQLite. A re-run skips completed steps, so a failure resumes rather than restarts. |
| ✅ | **Force re-run** | Overrides the skip when a step reported success but produced a broken result. |
| ✅ | **Always-run steps** | Scale and backup workloads never skip — "already done" is the wrong answer for them. |
| ✅ | **Live plan** | The resolved inventory and playbook order update as you type, before anything runs. |
| ✅ | **Dependency awareness** | A workload reports `Waiting on 4 · RKE2 cluster` instead of appearing runnable and failing later. Advisory for a single run, **enforced** for bulk runs. |
| ✅ | **Destructive protection** | Excluded from bulk run and gated behind typed confirmation, **enforced in the API** so a direct call cannot skip it. |
| ✅ | **Live output streaming** | Server-sent events, sending only what is new. |
| ✅ | **Run history** | Duration per workload, surfaced on the run sheet. |
| ✅ | **Single registry** | Every workload declared once in `app/workloads.py`. A test fails if an action has no planner, or if a dependency does not exist. |
| 🔨 | **Preflight** | Read-only sweep: reachability, OS release, sudo, disk, clock skew, DNS. |
| 🔨 | **Host bootstrap** | Creates `autoprovision` and installs the jump host key across every VM. |

## 2 · Kubernetes

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | RKE2 cluster install | Canal CNI, bundled ingress disabled, kubeconfig retrieved |
| ✅ | Cluster scaling | Already-joined nodes skipped; only new addresses join |
| ✅ | MetalLB | FRR-K8s mode |
| ✅ | Istio ambient 1.30 | ztunnel and istio-cni, no sidecars |
| ✅ | Shared Gateway API gateway | One address serving every host |
| ✅ | cert-manager + internal CA | Automatic renewal |
| ✅ | ArgoCD · Headlamp | Routed over the shared gateway |
| ✅ | etcd snapshots | Scheduled and on-demand, pruned by retention |
| 🧪 | Odd control-plane count enforced | An even count is refused with the etcd-quorum reason stated |
| 🧭 | Cilium | Documented alternative. Not chosen — see techstack.md A1 |

## 3 · Applications

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | WSO2 API Manager | Control plane and both gateways, ambient-enrolled |
| ✅ | WSO2 Identity Server | |
| ✅ | GitLab CE + runner + registry | |
| ✅ | SonarQube | Install, reinstall, and a purge that never touches GitLab's database |
| ✅ | Dockhand + PostgreSQL | Platform stack |
| 🧭 | GitHub · Azure DevOps | Supported as the customer's source platform; not installed by the console |

## 4 · Data tier

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | SQL Server single instance | Native, Ubuntu 24.04 |
| ✅ | SQL Server availability group | 3 nodes, Pacemaker, `CLUSTER_TYPE=EXTERNAL`, synchronous, automatic failover |
| ✅ | SQL Server teardown | Clean rebuild possible |
| ✅ | WSO2 database provisioning | Identical login SID on every replica, so a failover never orphans the user |
| ✅ | SQL Server backups | Full daily, log every 15 minutes, primary-aware |
| ⚠️ | AG listener | `sys.availability_group_listeners` stays empty under `CLUSTER_TYPE=EXTERNAL`. The Pacemaker VIP is the working endpoint. |
| ✅ | **Engine and topology selection** | Engine → OS → mode → HA shape, with invalid combinations refused and the reason stated |
| ✅ | **Windows stops with a pointer** | SQL Server on Windows names the runbook rather than silently assuming Linux |
| 🧪 | **PostgreSQL 17** | Single · streaming replication · Patroni with etcd |
| 🧪 | **MySQL 8.4** | Single · semi-synchronous · InnoDB Cluster · multi-primary |
| 🧪 | **Two-tier users** | Provisioning admin, then one DML-only login per component. Over-privilege is asserted against and fails the run. |
| 🧪 | **Built-in superusers locked** | `sa` disabled, `postgres` set `NOLOGIN`, MySQL `root` restricted to loopback — only after a named admin is proven to work |
| 🧪 | **Engine hardening** | Transparent huge pages off, swappiness, file limits, chrony — the clock-skew class of failure |
| 🧪 | **pgBackRest · XtraBackup** | Incremental with point-in-time recovery, primary-aware, weekly verification |
| 🧪 | **Object storage** | MinIO or SeaweedFS, standalone or distributed across 2–4 nodes. Four-drive minimum and symmetric-layout rules enforced before anything runs. |
| 🧪 | **Object replication** | Mirror every bucket to a second site |

## 5 · Observability

**One stack, chosen at deploy time.** The console installs the one you pick and
does not deploy the others.

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | Elastic Stack | 9.1.4 on a Docker VM. What the lab built and tested. |
| ✅ | ElastAlert2 | |
| ✅ | **Stack selection** | LGTM · OpenSearch · Elastic. Placement in-cluster or on a VM. Single or highly available. |
| 🧪 | **LGTM** | Loki, Grafana, Tempo, Mimir — object-storage backed, datasources pre-wired, refuses to start without buckets rather than crash-looping |
| 🧪 | **OpenSearch** | With Dashboards and an index lifecycle policy matching your retention |
| 🔨 | Log shippers | Alloy · Data Prepper · Filebeat, installed to match the chosen stack |
| 🔨 | OpenTelemetry Collector | Currently a manual runbook step |

## 6 · Certificates and secrets

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | Kubernetes gateway certificate | Paste a PEM, or cert-manager issues and renews |
| ✅ | Traefik default certificate | Pushed to every Docker VM |
| ✅ | Half-a-certificate refused | Both PEMs or neither — a silent fallback to cert-manager would be worse |
| ⚠️ | **Secret handling** | Passwords travel via `--extra-vars`, visible in `ps` during a run. Fixed by the vault below. |
| ✅ | Secrets never persisted | Every password field is filtered before SQLite, and asserted in tests |
| 🧪 | **Infisical** | Self-hosted vault, keys generated once on the host and never in the repository |
| 🔨 | Playbooks read from the vault | The change that closes the `--extra-vars` gap |

## 7 · Console

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | **Run sheet per environment** | UAT and Production are separate screens with identical capabilities |
| ✅ | **Step ribbon** | Discrete Ansible plays, not a percentage. Faded means "skipped, already installed". |
| ✅ | **Requirements · Guide · Theory tabs** | Markdown in the repository, rendered per workload |
| ✅ | **Handbook** | Every Theory page as one manual |
| ✅ | **Terminal** | Filter to changed or failed, find within output, follow, download |
| ✅ | **Deep links** | `/env/uat/uat_db` — paste a link to a failing workload into a chat |
| ✅ | **Wizard fields** | Conditional fields appear only when they apply |
| ✅ | **Empty form is a prompt, not an error** | Validation turns red only once you have typed something |
| ✅ | White and green, light only | No drop shadows anywhere — asserted in the browser test |
| ✅ | No Node on the jump host | Built off-host, `app/dist/` committed. A test fails if it goes stale. |
| ⚠️ | **No authentication** | Binds `0.0.0.0:3000` with no login. Restrict at the firewall. |
| 🧭 | Authentication | Reverse proxy with SSO. Not yet specified. |

## 8 · Development

| | Feature | Notes |
| - | ------- | ----- |
| ✅ | 89 backend tests | Planner branches, registry integrity, and the API's safety guarantees |
| ✅ | 29 browser checks | Theme, per-environment separation, wizard behaviour, destructive confirmation |
| ✅ | Link checker | 112 relative links across 43 files. Documentation cannot silently rot. |
| ✅ | Build freshness test | Fails if `app/dist/` is older than `console/src/` — this caught a real stale-build bug |
| ✅ | Ruff · pre-commit · gitleaks | |
| ✅ | AI-DLC | Generated `CLAUDE.md` plus `.aidlc-rule-details/`, regenerable so an upstream bump never loses project context |
| ✅ | One-shot jump host bootstrap | Warns clearly if the console was not built |

---

## Known gaps

| Gap | Impact | Fixed by |
| --- | ------ | -------- |
| Console has no authentication | Anyone reaching the jump host can deploy and read logs | Not yet specified |
| Passwords in `--extra-vars` | Visible in `ps` during a run | Playbooks reading from Infisical |
| Inventories hold `ansible_password=` | Plaintext on disk, `0600` | Host bootstrap workload, then key-only |
| `host_key_checking = False` | First contact accepts any host key | Pre-populate `known_hosts` |
| AG listener not registered | Pacemaker VIP is the endpoint instead | Documented, not fixed |
| Everything marked 🧪 | Not proven against real machines | A UAT lab run |

---

## Decisions still open

| Question | Why it matters |
| -------- | -------------- |
| **Which monitoring stack?** | LGTM is the recommendation; **Elastic is the lower-risk answer** because it is what the lab has tested. Every shipper and the WSO2 gateway sidecars point at whichever you choose. |
| **How is each environment sized?** | The console asks per workload rather than assuming, so this is a choice now rather than a contradiction. Worth writing the intended sizing down per environment so it is a decision and not an accident. |
| **Where do the object storage machines come from?** | Distributed object storage wants at least four nodes with four raw disks each. Confirm that capacity exists before committing to LGTM, which depends on it. |
| **Do you need MySQL and PostgreSQL now, or is SQL Server enough?** | Both are written but untested. Testing them costs lab time that could go to proving Production instead. |
