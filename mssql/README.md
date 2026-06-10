# SQL Server on Linux — Manual Install + AG Theory

The automation for everything below lives in
[`ansible/mssql_single.yml`](../ansible/mssql_single.yml) (UAT single instance),
[`ansible/mssql_ag.yml`](../ansible/mssql_ag.yml) (3-node HA Availability Group with
Pacemaker), [`ansible/mssql_ag_clean.yml`](../ansible/mssql_ag_clean.yml) (AG teardown/reset),
and [`ansible/mssql_backup.yml`](../ansible/mssql_backup.yml) (FULL/LOG backups). This page is
the **manual/theory reference**: what the playbooks do, why, and how to verify each phase by
hand. Official docs: [SQL Server on Linux](https://learn.microsoft.com/sql/linux/) ·
[AG configuration on Linux](https://learn.microsoft.com/sql/linux/sql-server-linux-availability-group-configure-ha).

An alternative design (Windows Server + Active Directory + WSFC) is documented in
[windows-ad-ag.md](windows-ad-ag.md) — not used in this deployment, kept as theory.

## Versions / OS support

| SQL Server | Supported Ubuntu | OpenLDAP runtime |
| ---------- | ---------------- | ---------------- |
| **2025** (playbook default) | 22.04 / **24.04** | `libldap-2.6-0` |
| 2022 (`mssql_version=2022`) | 20.04 / 22.04 | `libldap-2.5-0` |

Mismatch symptom: `sqlservr` fails to start with a missing `liblber` library — rebuild the VM
on a supported release.

## Manual single-instance install (what `mssql_single.yml` does)

```bash
# 1. Repo + engine
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft.gpg
curl -fsSL https://packages.microsoft.com/config/ubuntu/24.04/mssql-server-2025.list | sudo tee /etc/apt/sources.list.d/mssql-server-2025.list
sudo apt update && sudo apt install -y mssql-server

# 2. Setup (Enterprise eval; apply a real PID later — see README "license key" section)
sudo MSSQL_PID=Enterprise ACCEPT_EULA=Y MSSQL_SA_PASSWORD='<strong-pw>' /opt/mssql/bin/mssql-conf -n setup

# 3. Tools (sqlcmd 18 needs -C to trust the self-signed cert)
sudo apt install -y mssql-tools18 unixodbc-dev
/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P '<pw>' -C -Q "SELECT @@VERSION;"

# 4. Firewall
sudo ufw allow 1433/tcp
```

## AG theory — the three cluster types

| `CLUSTER_TYPE` | Failover | Listener | Use |
| -------------- | -------- | -------- | --- |
| `WSFC` | automatic | yes (cluster-managed) | Windows only ([windows-ad-ag.md](windows-ad-ag.md)) |
| `EXTERNAL` | automatic, via **Pacemaker** | Pacemaker **VIP** resource (+ optional T-SQL listener) | **this deployment (prod)** |
| `NONE` | manual only | none | read-scale / DR |

On Linux there is no WSFC, so HA = SQL Server (`CLUSTER_TYPE=EXTERNAL`) + **Pacemaker/Corosync**
for quorum, failover, and the floating IP. The Pacemaker VIP is the connection endpoint
(WSO2 JDBC points at it).

## What `mssql_ag.yml` does, phase by phase

1. **Install + prep (all nodes):** engine + tools install (as above), `hadr.hadrenabled=1`,
   AlwaysOn_health XEvent session, ufw openings (1433 SQL, 5022 endpoint, 2224/3121/5403-5405
   Pacemaker/Corosync), optional named sysadmin login (`db_admin_user`/`db_admin_password` —
   both or neither).
2. **Certificate auth between replicas:** master key + cert on the primary; cert copied to all
   replicas; `Hadr_endpoint` (TCP 5022) created on every node, authenticated by the cert (no AD
   on Linux).
3. **Create the AG** on the primary with `CLUSTER_TYPE = EXTERNAL`,
   `FAILOVER_MODE = EXTERNAL`, synchronous commit; join the secondaries
   (`JOIN ... WITH (CLUSTER_TYPE = EXTERNAL)`); grant `ALTER ANY AVAILABILITY GROUP` to the
   Pacemaker SQL login.
4. **Pacemaker/Corosync cluster:** `pcs host auth` of all nodes (hacluster), cluster create,
   STONITH disabled by default in the lab (**enable fencing in production** —
   `enable_fencing=true`), `ocf:mssql:ag` promotable clone resource + **VIP resource**
   (`listener_ip`) colocated with the primary.
5. **Listener (optional T-SQL `ADD LISTENER`)** — on SQL 2022/2025 use netmask `0.0.0.0`
   (the VIP is owned by Pacemaker, not SQL). KNOWN GAP: on EXTERNAL clusters the T-SQL listener
   registration can silently not persist; the **Pacemaker VIP works regardless** and is the
   supported endpoint.

### Verify by hand

```bash
sudo crm status            # or: sudo pcs status — 3 nodes online, ag_cluster-clone promoted, VIP Started
sudo corosync-cfgtool -s   # ring0 MUST bind the LAN IP, NOT 127.0.1.1 (Ubuntu /etc/hosts trap)
/opt/mssql-tools18/bin/sqlcmd -S <vip> -U sa -P '<pw>' -C -Q \
  "SELECT ag.name, ar.replica_server_name, rs.role_desc, rs.synchronization_health_desc
   FROM sys.availability_groups ag
   JOIN sys.availability_replicas ar ON ag.group_id=ar.group_id
   JOIN sys.dm_hadr_availability_replica_states rs ON ar.replica_id=rs.replica_id;"
```

### Known traps (hit in this lab, fixed in the playbooks)

- **Corosync binds 127.0.1.1** → split-brain (each node sees only itself). Cause: Ubuntu's
  default `/etc/hosts` maps the hostname to 127.0.1.1. Fix: remove that mapping and pin
  `ring0_addr`/`addr=` to the LAN IP. Check `corosync-cfgtool -s` first when AG nodes diverge.
- **HADR enable restart hangs** → use a non-blocking restart with a memory cap; D-Bus can hang
  a synchronous `systemctl restart mssql-server` during heavy init.
- **`mssql-conf setup` fails** when an old `sqlservr` is still running — stop it first.

## Backups (theory)

The AG replicates corruption and deletes just as faithfully as good data — HA is **not** a
backup. `mssql_backup.yml` installs FULL (daily) + LOG (15 min) backups with retention; only
the current PRIMARY backs up, so the schedule survives failover. Restore chain: latest FULL
`WITH NORECOVERY` → each LOG in order `WITH NORECOVERY` (use `STOPAT` for point-in-time) →
final `WITH RECOVERY`. Keep the backup directory on NFS/NAS, not the data disk.
