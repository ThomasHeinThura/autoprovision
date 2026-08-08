# Spec E+F — Stateful provisioning and secrets

**Date:** 2026-08-08
**Status:** Awaiting approval
**Covers:** three database engines × single and HA topologies · S3-compatible object storage · the selection wizard · two-tier users · Infisical
**Depends on:** [Spec A+B](2026-08-08-foundation-design.md) (registry, bootstrap) and [Spec C+D](2026-08-08-console-design.md) (conditional requirements)

The largest of the three specs. Build it last.

> **One wizard, two products.** Databases and object storage share the same shape — choose the
> product, choose the topology, choose the size, then read the requirements the choice generates.
> They share one wizard component and one requirements rules engine. Object storage is specified
> in [§11](#11--object-storage).

---

## 1 · Goals

1. Provision **SQL Server, PostgreSQL or MySQL**, in a single-node or a highly-available topology,
   onto customer VMs.
2. Make the operator choose deliberately, through a wizard that reveals each decision only once
   the prior one is made — and that **states the requirements before anything runs**.
3. Never let an application connect as a superuser.
4. Stop passwords travelling through `--extra-vars`.

**Non-goals in this phase:** WSO2 on MySQL or PostgreSQL (MSSQL stays the tested path, per your
decision), database migration between engines, and in-cluster databases.

---

## 2 · The selection wizard

Progressive disclosure. Each answer determines the next question, and the requirements panel
recomputes at every step.

```text
1 · Engine        ─→  SQL Server │ PostgreSQL │ MySQL
                            │
2 · Platform      ─→  Linux │ Windows          ← SQL Server only
                            │                    Windows is a hard stop
3 · Deploy mode   ─→  Single node │ High availability
                            │
4 · HA shape      ─→  Bilateral (2 nodes) │ Cluster (3+) │ Multi-primary
                            │                ← options vary by engine;
                            │                  unavailable ones say why
5 · Requirements  ─→  VM count · sizing · quorum rules · ports · known traps
```

### Step 2 — the SQL Server platform question

SQL Server runs on Windows and on Linux, and they are genuinely different products: Windows uses
WSFC and Active Directory, Linux uses Pacemaker and certificate-based endpoint authentication.
Asking the question and then refusing is better than silently assuming, because an operator who
expected Windows needs to know **now**, not after the playbook fails on a missing `apt`.

Choosing Windows shows:

> **This console provisions SQL Server on Linux only.**
> The automation targets Ubuntu 24.04 with Pacemaker and Corosync. A Windows availability group
> needs Windows Server Failover Clustering and an Active Directory domain — a different product
> with different prerequisites, which this tool does not install.
> A manual runbook exists at `docs/runbooks/mssql/windows-ad-ag.md`.
> *Continue with Linux, or choose another engine.*

The **Run** button stays disabled while Windows is selected.

### Step 4 — HA shape by engine

| Engine | Bilateral (2 nodes) | Cluster (3+ nodes) | Multi-primary |
| ------ | ------------------- | ------------------ | ------------- |
| **SQL Server** | AG, `CLUSTER_TYPE=NONE` — read-scale. Synchronous commit, **manual failover only**, no listener, no VIP. | AG, `CLUSTER_TYPE=EXTERNAL` + Pacemaker. Automatic failover, VIP. **This is what your lab built and tested.** | **Not available.** SQL Server availability groups are single-primary by design. Only one replica accepts writes. |
| **PostgreSQL** | Streaming replication, primary + hot standby. Manual promote. | **Patroni** + etcd + HAProxy. Automatic leader election and failover. | **Not available** in core PostgreSQL. Multi-master needs BDR or pgEdge — commercial, and a different operational model. |
| **MySQL** | Semi-synchronous replication + MySQL Router. Manual failover. | **InnoDB Cluster** — Group Replication, single-primary, with MySQL Router. Automatic. | **Available.** InnoDB Cluster in multi-primary mode, or Percona XtraDB Cluster (Galera). Carries a warning — see below. |

Unavailable options are **shown and disabled with the reason visible**, not hidden. An operator
asking "can I do multi-master on SQL Server?" deserves the answer in the interface.

### The multi-primary warning

Selecting multi-primary on MySQL shows:

> **Every node accepts writes, and that changes your application's assumptions.**
> Two nodes updating the same row concurrently produce a certification failure — one transaction
> is rolled back *after* the client was told it committed. Applications written against a single
> writer generally do not handle this.
> Auto-increment steps are also spread across nodes, so identifiers are no longer monotonic.
> Choose **Cluster** unless you have a specific reason and the application has been tested for it.

### The bilateral warning — two nodes cannot arbitrate

This is the rule that most needs stating, on every engine:

> **Two nodes cannot decide which of them is alive.**
> When the link between them fails, each node sees the other as down. Neither has a majority, so
> neither can safely promote itself — automatic failover in this topology risks both nodes
> accepting writes and permanently diverging.
> Bilateral therefore gives you a **warm standby with manual failover**: real protection against
> losing a node, but a human decides when to promote.
> For automatic failover, use **Cluster** with three nodes, or add a witness.

---

## 3 · Requirements rules

The requirements panel is generated from rules, not written per combination — so it cannot
contradict the plan.

### Quorum

| Rule | Applies to |
| ---- | ---------- |
| Node count must be **odd** | Every cluster topology. Four nodes tolerate exactly the same single failure as three, and cost a VM. |
| **Minimum 3 nodes** | Every cluster topology |
| Two nodes give **no automatic failover** | Every bilateral topology |
| etcd needs **3 or 5 members** | PostgreSQL Patroni. Co-located with the database nodes by default; separate if you want database maintenance not to disturb the consensus layer. |
| Group Replication supports **at most 9 members** | MySQL cluster |

### Per-engine

| Engine | Rule | Why |
| ------ | ---- | --- |
| SQL Server 2025 | **Ubuntu 24.04 only** | Not packaged for 26.04. SQL Server 2022 needs 20.04 or 22.04 — selecting 2022 changes the required OS, and the panel updates. |
| SQL Server AG | Clock offset under **1 second** across nodes | Certificate-based endpoint authentication fails on skew, with an unhelpful error |
| SQL Server AG | `/etc/hosts` must not map the hostname to `127.0.1.1` | Ubuntu's default entry causes Corosync split brain. **You hit this in the lab** — recorded in `docs/status/service-status.md`. |
| SQL Server AG | All nodes on one L2 segment | The Pacemaker VIP moves by ARP and cannot cross a router |
| PostgreSQL | `pg_hba.conf` uses `scram-sha-256` | Never `trust`, never `md5` |
| MySQL cluster | GTID mode and row-based binary logging | Group Replication requires both; the playbook sets them and asserts |
| All | Data on a **separate, unmounted disk** | A full root filesystem takes the VM down, not just the database |

### Ports opened

| Engine | Ports |
| ------ | ----- |
| SQL Server | `1433` client · `5022` AG endpoint · Pacemaker `2224`, `3121`, `21064` · Corosync `5405/udp` |
| PostgreSQL | `5432` client · `8008` Patroni REST · etcd `2379`, `2380` |
| MySQL | `3306` client · `33061` Group Replication · `6446`, `6447` Router read-write and read-only |

Every one is restricted to application subnets. The requirements panel says so, and the playbook
does not open a firewall on the operator's behalf.

---

## 4 · Two-tier users

### The principle

Applications never connect as `sa`, `root`, or `postgres`. These are not merely privileged
accounts — each is a path to a shell on the host:

| Account | Escalation |
| ------- | ---------- |
| `sa` | `xp_cmdshell` executes operating system commands |
| `root` (MySQL) | `FILE` reads and writes any file the daemon can reach |
| `postgres` | `COPY … FROM PROGRAM` runs a shell command |

So one leaked configuration file or one SQL injection stops being a database incident and becomes
a data-centre incident.

### The two tiers

| Tier | Created by | Lifetime | Rights |
| ---- | ---------- | -------- | ------ |
| **Provisioning admin** | The engine workload, at install | Disabled or rotated when provisioning completes | Server-level admin |
| **Runtime login** | The `db-users` workload, one per consuming component | Life of the deployment | DML on its own schemas. No DDL, no server-level rights, no access to another component's data. |

One runtime login **per component** — WSO2 APIM, WSO2 IS, SonarQube, GitLab — not one shared
`wso2carbon`. A compromised APIM credential must not read the Identity Server's tables.

### Built-in lockdown, per engine

| Engine | Actions |
| ------ | ------- |
| SQL Server | Disable `sa`. Force encrypted connections. Disable `xp_cmdshell` and confirm it is off. |
| MySQL | Drop anonymous users. Drop the `test` database. Disallow remote `root`. Scope every user to a host or subnet — `'wso2'@'10.20.30.%'`, never `'%'`. |
| PostgreSQL | Revoke `CREATE` on `PUBLIC` from `PUBLIC`. Set `scram-sha-256`. `LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE` on every role. |

### The replica correctness problem

Each engine has a different way for a user to break at failover, and each needs its own handling:

- **SQL Server** — a login lives at server level, a user lives in the database, and they are
  joined by a SID. A database that fails over carries its users but meets a server with different
  SIDs, orphaning them. **Every login is created on every replica with an explicit, identical
  SID.** Already implemented in `ansible/db/mssql_wso2_db.yml`; it generalises to all components.
- **MySQL** — Group Replication propagates DDL, so **users are created on every node before it
  joins**. Creating a user on a live cluster after the fact works, but the bootstrap order matters
  and getting it wrong fails the join.
- **PostgreSQL** — roles are cluster-global and reach streaming replicas automatically, but must
  **exist before Patroni bootstraps a replica**.

---

## 5 · Playbooks

```text
ansible/db/
├── common/
│   ├── preflight.yml           OS release, disk, clock, hostname resolution
│   ├── data_disk.yml           format and mount the data disk
│   └── firewall_note.yml       report required ports; opens nothing
├── mssql/
│   ├── install.yml             engine + tools, provisioning admin
│   ├── ag_readscale.yml        bilateral — CLUSTER_TYPE=NONE
│   ├── ag_cluster.yml          cluster — CLUSTER_TYPE=EXTERNAL + Pacemaker + VIP
│   ├── users.yml               two-tier, fixed SID across replicas
│   ├── harden.yml
│   └── clean.yml               destructive — replaces mssql_ag_clean.yml
├── postgres/
│   ├── install.yml
│   ├── streaming.yml           bilateral
│   ├── patroni.yml             cluster — etcd + Patroni + HAProxy
│   ├── users.yml
│   └── harden.yml
└── mysql/
    ├── install.yml
    ├── replication.yml         bilateral — semi-synchronous + Router
    ├── innodb_cluster.yml      cluster — Group Replication + Router
    ├── users.yml
    └── harden.yml
```

The existing `mssql_single.yml`, `mssql_ag.yml`, `mssql_ag_clean.yml`, `mssql_wso2_db.yml` and
`mssql_backup.yml` are **moved and refactored, not rewritten**. They encode hard-won lab
knowledge — the Corosync fix, the SID handling, the primary-aware backup script — and that
knowledge is the asset. The refactor generalises `wso2_db` into `users.yml` with a component list.

### Workloads added to the registry

| Workload | Destructive | Notes |
| -------- | ----------- | ----- |
| `db_engine` | No | Engine and topology from the wizard. Per environment. |
| `db_users` | No | Two-tier users. Requires `db_engine`. |
| `db_backup` | No | Generalises `mssql_backup.yml` to all three engines |
| `db_clean` | **Yes** | Danger zone. Typed confirmation of the cluster or AG name. |

---

## 6 · Secrets — Infisical

### The problem

Passwords reach playbooks through `--extra-vars`, which puts them in the process list on the jump
host for the duration of the run:

```console
$ ps aux | grep ansible
... ansible-playbook ... --extra-vars {"sa_password":"…"} ...
```

Per-job inventories also contain `ansible_password=`. Both are documented in the README's own
security notes. Three engines with two topologies multiplies the surface, so this is fixed as part
of this work rather than after it.

### Design

**Infisical**, self-hosted as a Docker stack beside the existing platform services — chosen in
`techstack.md` A6 over OpenBao and HashiCorp Vault.

| Concern | Approach |
| ------- | -------- |
| Deployment | `ansible/infisical_stack.yml`, behind Traefik on the GitLab VM. A new `secrets` group in the console. |
| Authentication | A machine identity for the jump host. Its token is the only secret on disk, `0600`. |
| Reads | The playbook fetches at run time via lookup, so the value never appears in `--extra-vars` or in `ps` |
| Fallback | Infisical is **optional**. Without it, the current prompt-and-pass path remains, and the requirements panel shows an explicit unmet item saying passwords are exposed. |
| SSH | Spec A+B moves SSH to keys, so `ansible_password=` disappears from inventories independently |

Making it optional matters: a customer who will not run another service must still be able to
deploy, and should see plainly what they are giving up.

---

## 7 · Phasing

| Phase | Content | Ships |
| ----- | ------- | ----- |
| **E1** | Wizard, requirements rules engine, MSSQL refactored onto the new structure. No new engines. | The decision tree and the requirements panel working against the engine you already run |
| **E2** | PostgreSQL — single, streaming, Patroni | |
| **E3** | MySQL — single, semi-sync, InnoDB Cluster, multi-primary | |
| **E4** | Generalised users, hardening and backups across all three | |
| **F1** | Infisical stack and machine identity | |
| **F2** | Playbooks read secrets from the vault; `--extra-vars` path becomes the fallback | |

E1 is the highest-value phase: it delivers the wizard and the requirements checklist against the
tested MSSQL path, with no new engine risk. Each later phase is independently shippable.

---

## 8 · Verification

| Claim | Evidence |
| ----- | -------- |
| The wizard cannot produce an invalid combination | Test over the full engine × platform × mode × shape matrix; every combination is either runnable or disabled with a stated reason |
| Quorum rules hold | Test: an even node count in cluster mode fails validation before any host is contacted |
| Windows is a hard stop | Test: selecting Windows disables Run and returns 400 from the API |
| No superuser is left usable | Post-install assertion per engine: `sa` disabled, no anonymous MySQL users, no `trust` in `pg_hba.conf` |
| Failover does not orphan users | Lab: fail over, then reconnect as each runtime login and read from its own schema |
| Secrets are absent from the process list | Lab: `ps aux` during a vault-backed run shows no credential |
| Engine reachable after install | Every install ends with a version query whose output is printed to the log |

---

## 9 · Risks

| Risk | Mitigation |
| ---- | ---------- |
| Three engines × three topologies is a large test matrix | Phase per engine; each phase is independently shippable and separately validated |
| Refactoring the working MSSQL playbooks breaks a tested path | E1 refactors structure only, with no behaviour change, and is validated by a full lab re-run before E2 starts |
| Patroni's etcd is confused with the RKE2 cluster's etcd | Separate group, separate ports, stated in Theory. **Never share the Kubernetes control plane's etcd** — a database failover storm must not be able to take the cluster down. |
| Multi-primary is selected without understanding it | Explicit warning at selection, and it is not the default |
| Infisical becomes a hard dependency and blocks a deploy | Optional by design; the fallback path stays supported and its cost is shown in the requirements panel |

---

## 11 · Object storage

S3-compatible storage on customer VMs. Loki, Tempo, Mimir, database backups and RKE2 etcd
snapshots all write here — everything that would use a cloud bucket uses this instead, so the
architecture is the same on-premise and in a cloud.

Deployed in **Shared services**, and it runs **before the LGTM stack**, which cannot start
without its buckets.

### Wizard

```text
1 · Provider   ─→  MinIO │ SeaweedFS
2 · Mode       ─→  Standalone │ Distributed
3 · Nodes      ─→  2 │ 3 │ 4          ← distributed only
4 · Requirements
```

| Provider | Status | Notes |
| -------- | ------ | ----- |
| **MinIO** | Selected | The de-facto on-premise S3. Erasure coding, single binary. **Verify the licence and community-edition feature set before committing** — it is AGPLv3 and the vendor has been moving functionality into its commercial product. |
| **SeaweedFS** | Alternative | Replication rather than erasure coding. Lighter, strong with very large numbers of small objects. The fallback if MinIO's licensing becomes a problem. |

### Rules the requirements panel enforces

| Rule | Why |
| ---- | --- |
| **Minimum 4 drives in total** | Erasure coding has no valid striping below that. Two nodes × 2 drives satisfies it; two nodes × 1 drive does not. |
| **Identical drive count and size on every node** | Erasure sets stripe in a fixed pattern. MinIO refuses an uneven layout rather than silently producing uneven failure tolerance — refusing early is correct, however inconvenient. |
| **Sequential hostnames** | Distributed mode is configured by brace expansion, `http://minio-{1...4}/mnt/disk{1...4}`. Non-sequential names do not expand and the set will not start. |
| **Clock offset under 1 second** | S3 request signatures fail outside a 15-minute window, and drift compounds |
| Disks attached, **unformatted and unmounted** | The playbook formats XFS and mounts them |
| **Fewer than 4 nodes is parity-limited** | A warning, not a block. See below. |

### Why the node count matters more than it looks

Erasure coding splits each object into data and parity blocks across every drive, so protection is
expressed in **drives**, not nodes. Losing one node removes all of its drives at once:

| Nodes | Drives | Losing one node | Verdict |
| ----- | ------ | --------------- | ------- |
| 2 | 8 | Half the set | Meets the minimum, no real node-failure tolerance |
| 3 | 12 | A third of the set | Consumes the parity budget; a drive failure during the outage loses data |
| **4** | **16** | **A quarter of the set** | **Survives it, and still tolerates a drive failure while the node is down** |

The console offers 2 and 3 because you asked for the range, and warns clearly at both. Four is the
recommended default.

### Workloads

| Workload | Destructive | Notes |
| -------- | ----------- | ----- |
| `object_store` | No | Provider, mode and node count from the wizard |
| `object_buckets` | No | One bucket and one **scoped service account** per consumer — Loki, Tempo, Mimir, backups. Never the root credential. |
| `object_replication` | No | Bucket replication to a second site or an offline target. In **Backups & DR**, because erasure coding is not a backup. |
| `object_clean` | **Yes** | Danger zone. Typed confirmation. |

### Playbooks

```text
ansible/object/
├── common/preflight.yml         drive layout, hostname sequence, clock
├── minio/
│   ├── standalone.yml
│   ├── distributed.yml
│   ├── buckets.yml              buckets + scoped service accounts
│   ├── replication.yml
│   └── clean.yml                destructive
└── seaweed/
    ├── standalone.yml
    └── distributed.yml
```

### Phasing

Slots in as **E5**, after the database work and before F. It is a prerequisite for the LGTM stack,
so if observability is wanted sooner it moves ahead of E2 and E3.

---

## 12 · Decisions needed from you

1. **Do you actually need MySQL and PostgreSQL now**, or is E1 — the wizard and requirements
   against MSSQL — enough for the current rollout? E2 and E3 are real work, and building them
   before a customer asks is speculative.
2. **Where does the database tier get its VMs for HA?** Your current topology has 3 MSSQL VMs in
   production and 1 in UAT. A PostgreSQL Patroni cluster needs 3 plus etcd — co-located, or more
   VMs?
3. **Which components get their own runtime login?** My assumption: WSO2 APIM, WSO2 IS, SonarQube,
   GitLab. Confirm or extend.
4. **Infisical in this phase, or after the console ships?** It is the correct fix for a real
   exposure, but it is also a new service to operate.
5. **Object storage node count** — is 4 acceptable as the recommended default, and where do those
   VMs come from? The current 19-VM topology has no allocation for them. ([§11](#11--object-storage))
6. **Three log stacks is two too many.** LGTM, OpenSearch and the Elastic Stack all store and
   search logs. My assumption is LGTM for logs, traces and metrics, OpenSearch for search-heavy
   analytics, and **Elastic retired** — but that is a decision, not an inference, and it changes
   the VM budget and the per-environment topology. Confirm before any of the three is built for
   production.
