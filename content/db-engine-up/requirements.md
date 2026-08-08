# Requirements

Everything below must be true before you run this. The playbook asserts most of it
and stops at the first failure rather than half-installing an engine.

## Machines

| Deploy mode | VMs | vCPU | RAM | Disk |
| ----------- | --- | ---- | --- | ---- |
| Single node | 1 | 4 | 16 GB | 80 GB system **plus a separate data disk** |
| Two-node replication | 2 | 8 | 32 GB | 120 GB system **plus a separate data disk** |
| Managed cluster | **3 or 5 — an odd number** | 8 | 32 GB | 120 GB system **plus a separate data disk** |

**High availability needs an odd node count.** Two nodes cannot arbitrate a split
brain: when the link between them breaks, each side sees the other as dead, both
promote themselves, and the data diverges. Three nodes give a majority, so the
minority side knows to stand down. Four nodes are no better than three — you have
paid for another machine and still lose quorum after two failures.

## Operating system

**Ubuntu Server 24.04 LTS on every node.** Not mixed, not 22.04 on one of them.

| Engine | Notes |
| ------ | ----- |
| SQL Server 2025 | Ubuntu 24.04 only. 26.04 is not supported by the packages. |
| SQL Server 2022 | Ubuntu 20.04 or 22.04. Choose 2025 unless something forces otherwise. |
| PostgreSQL 17 | Ubuntu 22.04 or newer, from the PGDG repository. |
| MySQL 8.4 LTS | Ubuntu 22.04 or newer, from the MySQL repository. |

**SQL Server on Windows Server is not automated here.** It needs a Windows failover
cluster and Active Directory, which is a different toolchain. The console stops
and points you at `docs/mssql/windows-ad-ag.md`.

## Before you run

- The `autoprovision` account exists on every node with passwordless sudo.
  Run **Host bootstrap** if you have not — it does this across every VM at once.
- The jump host reaches every node on `22/tcp` using its key.
- The data disk is attached and **unmounted**. The playbook formats and mounts it.
  Pointing the data directory at the system disk works and is a bad idea: a full
  root filesystem takes the whole VM down rather than just the database.
- **All nodes share one layer-2 segment** if you are building a cluster with a
  virtual IP. The address has to be able to move between them.
- The virtual IP is **unassigned** and outside your DHCP range.

### Two things that have bitten this lab

**Ubuntu maps the hostname to `127.0.1.1` by default.** Corosync binds to that,
each node believes it is alone, and you get split brain on a healthy network. The
playbook removes the mapping and pins each ring address to the LAN IP — but if you
have customised `/etc/hosts`, check it.

**Clock skew breaks the certificate exchange** during availability group setup.
The error names neither the clock nor the node. `harden.yml` installs and starts
chrony before anything else, and prints the offset.

## Ports this opens

| Engine | Port | Restrict to |
| ------ | ---- | ----------- |
| SQL Server | `1433/tcp` | Application subnets only |
| PostgreSQL | `5432/tcp` | Application subnets only |
| MySQL | `3306/tcp` | Application subnets only |
| Cluster traffic | `2379–2380` (etcd) · `33061` (Group Replication) · `5405` (Corosync) | Between database nodes only |

Never expose a database port to the whole LAN. The engine's authentication is the
last line, not the first.

## What this does not do

- **Create application logins.** That is **Database users**, which runs next. Until
  then the engine has a provisioning admin and nothing else, and no application can
  use it. That is deliberate.
- **Configure backups.** That is **Backups & DR**, and you should run it before
  go-live. High availability replicates a `DROP TABLE` faithfully to every replica.
- **Apply a purchased licence key.** SQL Server installs as Developer or
  Evaluation. See the README for `mssql-conf set-edition`.
