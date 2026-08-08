# Autoprovision

On-premise infrastructure provisioning, driven from one jump host.

A FastAPI control plane runs Ansible against your VMs and installs RKE2 clusters,
databases, object storage, monitoring, the Docker platform stack and WSO2 —
several at once, on execution day. Every workload carries its own requirements,
operator guide and design reasoning, so the person running it does not need the
person who built it.

- **[techstack.md](techstack.md)** — every component, why it was chosen, and what was rejected
- **[FEATURES.md](FEATURES.md)** — what works, what is specified, what is still a decision
- **[CHANGELOG.md](CHANGELOG.md)** — what changed and why
- **[docs/status/service-status.md](docs/status/service-status.md)** — what has actually been tested in the lab

---

## Start here

### 1 · Prepare one VM

You need a **jump host** — 2 vCPU, 4 GB RAM, Ubuntu 24.04 — that can reach every
target on `22/tcp`. Nothing else is required to begin.

### 2 · Bootstrap it

```bash
ssh <you>@<jump-host>
sudo apt update && sudo apt install -y git curl
git clone https://github.com/ThomasHeinThura/autoprovision.git
cd autoprovision
./bootstrap-jumphost.sh
```

This installs Python, Ansible, `kubectl`, `helm` and `istioctl`, then starts the
console on port **3000**. It needs no Node and no npm registry — the console is
built off-host and committed, so an air-gapped jump host works.

```text
[INFO]  Bootstrap complete.
Open: http://<jump-host-ip>:3000/
```

Stop it with `scripts/stop-console.sh`; start it again by re-running the bootstrap.

### 3 · Prepare the targets

The console's **Host bootstrap** workload creates the `autoprovision` account and
installs the jump host's SSH key across every VM at once. That replaces nineteen
manual SSH sessions and moves the whole system onto key authentication.

To do it by hand instead, on each target:

```bash
sudo adduser autoprovision
sudo usermod -aG sudo autoprovision
echo 'autoprovision ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/autoprovision
```

Customer prerequisites stay manual: DNS records, firewall rules, NFS or NAS
exports, the cluster registration address, and TLS certificate handover if you are
not self-signing.

### 4 · Work through the run sheet

The console opens on **Shared services**. Each environment is its own screen, and
each workload is a row you open, configure and run. Workloads run independently
and in parallel — every run gets its own inventory and its own log, so nothing
collides.

Four tabs on every workload:

| Tab | What it holds |
| --- | ------------- |
| **Configure** | The form, the resolved plan, the inventory, and live output |
| **Requirements** | VM count, sizing, ports, and what must be true before you run |
| **Guide** | The operator walkthrough |
| **Theory** | Why it is designed this way, and what it does not protect against |

A workload that is waiting on another says so — `Waiting on 4 · RKE2 cluster` —
rather than appearing runnable and failing ten minutes in.

**Run ready workloads** starts everything that is configured and unblocked. It
never starts anything destructive; that exclusion is enforced in the API, not the
browser.

---

## What it installs

### Environments

**Shared services** holds only what both environments genuinely share: GitLab, the
container registry, and SonarQube.

**UAT** and **Production** are complete, separate environments. Each has its own
cluster, database, object storage and monitoring, and neither depends on the other
at runtime. They offer identical capabilities; only the sizing differs.

| # | Workload | What it does |
| - | -------- | ------------ |
| 1 | Docker + Traefik | Docker CE, then Traefik owning the shared `platform` network |
| 2 | Object storage | MinIO or SeaweedFS — standalone, or distributed across 2–4 nodes |
| 3 | Monitoring | **One** stack: LGTM, OpenSearch or Elastic |
| 4 | RKE2 cluster | Kubernetes with Canal CNI, bundled ingress disabled |
| 4b | Add or scale nodes | Joins new addresses; existing nodes are skipped |
| 5 | MetalLB + Istio ambient | LoadBalancer addresses, ambient mesh, one shared gateway |
| 6 | ArgoCD | GitOps delivery over the shared gateway |
| 7 | Headlamp | Cluster dashboard, optional |
| 8 | Database engine | SQL Server, PostgreSQL or MySQL — single or highly available |
| 8b | Database users | A provisioning admin, then one least-privilege login per component |
| 9 | WSO2 API Manager | Control plane and both gateways |
| 10 | WSO2 Identity Server | |

### Platform operations

**Certificates** — cert-manager with an internal CA, the Kubernetes gateway
certificate, and the Traefik default certificate.
**Secrets** — self-hosted Infisical.
**Backups & DR** — etcd snapshots, database backups, object store replication.
**Danger zone** — teardown workloads, excluded from bulk runs and gated behind
typed confirmation.

### Databases

Three engines, each in several shapes. The console refuses combinations that
cannot work rather than letting you discover them at 2am:

| | Single | Two-node | Managed cluster | Multi-primary |
| --- | --- | --- | --- | --- |
| **SQL Server** | ✓ | Availability group | Availability group + Pacemaker | — |
| **PostgreSQL** | ✓ | Streaming replication | Patroni + etcd | — |
| **MySQL** | ✓ | Semi-synchronous | InnoDB Cluster | ✓ |

An even node count is refused with the reason stated. SQL Server on Windows stops
and points at [docs/mssql/windows-ad-ag.md](docs/mssql/windows-ad-ag.md) rather
than silently assuming Linux.

**Applications never connect as `sa`, `root` or `postgres`.** Those accounts reach
a shell on the host — `xp_cmdshell`, `FILE`, `COPY … FROM PROGRAM`. The Database
users workload creates a provisioning admin that is disabled afterwards, and one
DML-only login per component.

---

## Layout

| Path | What it is |
| ---- | ---------- |
| `bootstrap-jumphost.sh` | One-shot jump host prep, then starts the console |
| `app/workloads.py` | **The registry — every workload declared once** |
| `app/planner.py` | Resolves a workload plus its values into playbooks and an inventory |
| `app/runner.py`, `state.py`, `deps.py`, `content.py` | Execution, persistence, dependencies, docs |
| `app/dist/` | Built console. Committed, so the jump host needs no Node |
| `console/` | React and TypeScript source |
| `content/<workload>/` | `requirements.md`, `guide.md`, `theory.md` |
| `ansible/db/` | SQL Server, PostgreSQL, MySQL — install, users, backup, teardown |
| `ansible/k8s/` | RKE2, add-ons, WSO2, etcd snapshots |
| `ansible/platform/` | Docker, Traefik, GitLab, SonarQube, Infisical |
| `ansible/monitoring/` | LGTM, OpenSearch, Elastic |
| `ansible/object/` | MinIO, SeaweedFS, replication |
| `ansible/certs/` | Kubernetes and Traefik certificates |
| `docs/planning/` | Requirements — start with `00-old-vs-new.md` |
| `docs/runbooks/` | Manual procedures for what is not automated |
| `docs/specs/` | Design documents |
| `docs/mssql/` | SQL Server theory and the Windows path |
| `WSO2_APIM_KUBE_ISTIO/` | The team's WSO2 repository — authoritative for WSO2 |
| `tests/` | pytest — the planner and the API's safety guarantees |
| `scripts/install-aidlc.sh` | Regenerates `CLAUDE.md` from project context plus AI-DLC |

---

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q                    # 88 tests
.venv/bin/python -m uvicorn app.main:app --port 3000

cd console && npm ci
npm run dev                                             # proxies /api to :3000
npm run build                                           # writes app/dist/, commit it
node smoke.mjs                                          # 28 browser checks
```

**Adding a workload is a registry change.** Add a `Workload` to `WORKLOADS` in
`app/workloads.py` and an action handler in `app/planner.py`. Never add one to the
frontend — it renders from the registry the API serves. The tests fail if an
action has no planner, or if a workload depends on something that does not exist.

---

## Security

Read this before a production rollout. The lab defaults favour speed.

| Gap | Impact | What to do |
| --- | ------ | ---------- |
| **The console has no authentication** | Anyone who reaches the jump host can deploy and read logs | Restrict port 3000 to operator addresses, or bind to localhost and use `ssh -L 3000:localhost:3000` |
| **Passwords travel via `--extra-vars`** | Visible in `ps` on the jump host for the length of a run | Run the Infisical workload; playbooks then fetch at run time |
| **Inventories contain `ansible_password=`** | Plaintext on disk, mode `0600` | Use the host bootstrap workload and leave passwords empty |
| **`host_key_checking = False`** | First contact accepts any host key | Pre-populate `known_hosts` and set it back to `True` |
| Derived cluster passwords | Predictable when explicit values are not passed | Always pass explicit values |
| Pasted PEMs | Staged to `data/certs/`, key `0600`, never in the database | Delete after rotation if the jump host is shared |

Backups are not optional. High availability replicates a `DROP TABLE` faithfully
to every replica; only backups held somewhere the database cannot write protect
against corruption, mistakes and ransomware.

---

## Troubleshooting

| Symptom | Cause |
| ------- | ----- |
| RKE2 node `NotReady` | Check the service and token; Canal pods in `kube-system` |
| Two ingress controllers fighting for 443 | The RKE2 bundled ingress was not disabled |
| Gateway has no external address | MetalLB must back the `LoadBalancer` service |
| WSO2 TLS errors | The secret must be in `istio-system` — the gateway reads only its own namespace |
| `HTTPRoute` not routing | Namespace needs `istio.io/dataplane-mode=ambient` |
| Availability group replica unhealthy | Re-check certificate exchange and endpoints on every node |
| Corosync split brain on a healthy network | Ubuntu's default `127.0.1.1` hostname mapping |
| Certificate exchange fails during cluster setup | Clock skew. `harden.yml` installs chrony and prints the offset |
| Application cannot connect after a failover | Orphaned login — the SID differs between replicas |
| Monitoring pods crash-looping | LGTM was installed before object storage had buckets |
