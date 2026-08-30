# SQL Server on Linux — Manual Install + AG Theory

The automation for everything below lives in
[`ansible/db/mssql_single.yml`](../../ansible/db/mssql_single.yml) (UAT single instance),
[`ansible/db/mssql_ag.yml`](../../ansible/db/mssql_ag.yml) (3-node HA Availability Group with
Pacemaker), [`ansible/db/mssql_ag_clean.yml`](../../ansible/db/mssql_ag_clean.yml) (AG teardown/reset),
[`ansible/db/mssql_backup.yml`](../../ansible/db/mssql_backup.yml) (FULL/LOG backups), and
[`ansible/db/mssql_wso2_db.yml`](../../ansible/db/mssql_wso2_db.yml) (WSO2 databases + the
failover-safe application login — see "WSO2 login on an AG" below). This page is
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

## WSO2 login on an AG — the orphaned-user trap (why `mssql_wso2_db.yml` exists)

WSO2 (APIM control plane, gateways, Identity Server) connects to MSSQL as a **SQL login**
(default `wso2carbon`). On an Availability Group this login is the classic failover foot-gun:

- A **database-level user** (`CREATE USER ... FOR LOGIN`) lives *inside* the database and carries a
  **SID**. The database — and that user — are replicated to every replica by AG seeding.
- A **server-level login** is **not** part of any database, so the AG does **not** replicate it.
  It must be created **independently on each node**.
- `CREATE LOGIN ... WITH PASSWORD` (no explicit SID) assigns a **random SID per server**. So the
  login on the secondary has a *different* SID than the replicated database user expects. After a
  failover the user is **orphaned** → WSO2 fails with `Login failed for user 'wso2carbon'` /
  `Cannot open database` even though the login clearly exists.

**Fix:** create the login on **every** replica with the **same explicit SID** and password, and
create it **before** the contained user so the user inherits that SID. Then the user maps to the
login on whichever node is primary.

[`ansible/db/mssql_wso2_db.yml`](../../ansible/db/mssql_wso2_db.yml) does exactly this, in four phases:

1. **All nodes** — `CREATE LOGIN [wso2carbon] WITH PASSWORD=..., SID=0x…` with one fixed
   `wso2_db_sid`. If a login with the wrong SID already exists (an earlier no-SID run), it is
   dropped and recreated with the correct SID.
2. **Primary** — load `mssql/apim_mssql.sql`, `shared_mssql.sql`, `is_mssql.sql`. Each takes the
   user/password/SID as `sqlcmd -v` variables, so `CREATE USER ... FOR LOGIN` inherits the fixed SID.
3. **Primary** — set FULL recovery, take a full backup, and `ALTER AVAILABILITY GROUP ADD DATABASE`
   for each WSO2 DB so it is protected by failover and auto-seeds to the secondaries.
4. **All nodes** — verify no orphaned users remain (`SUSER_SNAME(sid)` resolves for the contained
   user in each DB), proving a failover is safe *before* WSO2 ever connects.

Run it from the autoprovision UI (**"7b · WSO2 DB user + schemas"**, between the AG and the WSO2
cards) or by hand:

```bash
ansible-playbook ansible/mssql_wso2_db.yml -l mssql_ag \
  -e sa_password='<sa-pw>' -e wso2_db_password='<db-pw>' -e ag_name=prodag
```

The `wso2_db_user` / `wso2_db_password` you set here **must equal** the values injected into the
WSO2 `deployment.toml` (the WSO2 APIM/IS cards, i.e. the `<WSO2_DB_USER>`/`<WSO2_DB_PASSWORD>`
tokens substituted by [`ansible/k8s/wso2.yml`](../../ansible/k8s/wso2.yml)). Keep `wso2_db_sid`
identical for the life of the AG — a re-seeded secondary re-maps against it.

Verify by hand (a healthy secondary is readable in a synchronous AG):

```sql
-- On EACH replica: the contained user's SID must resolve to a server login (non-NULL = mapped).
USE WSO2AM_DB;
SELECT dp.name, SUSER_SNAME(dp.sid) AS mapped_login
FROM sys.database_principals dp WHERE dp.name = 'wso2carbon';   -- mapped_login NULL => orphaned
-- Compare the login SID across nodes — it must be identical everywhere:
SELECT CONVERT(varchar(66), sid, 1) FROM sys.server_principals WHERE name = 'wso2carbon';
```

## Backups (theory)

The AG replicates corruption and deletes just as faithfully as good data — HA is **not** a
backup. `mssql_backup.yml` installs FULL (daily) + LOG (15 min) backups with retention; only
the current PRIMARY backs up, so the schedule survives failover. Restore chain: latest FULL
`WITH NORECOVERY` → each LOG in order `WITH NORECOVERY` (use `STOPAT` for point-in-time) →
final `WITH RECOVERY`. Keep the backup directory on NFS/NAS, not the data disk.
