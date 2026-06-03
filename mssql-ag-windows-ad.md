# SQL Server Always On AG on Windows Server + Active Directory — 2-Node Synchronous Commit

A step-by-step guide to build a **2-node SQL Server Always On Availability Group** on **Windows
Server** joined to **Active Directory**, with **synchronous commit + automatic failover** and an
**AG listener**.

> This is the **Windows/WSFC** path (full HA: automatic failover + virtual listener). It is
> different from the Linux `CLUSTER_TYPE=NONE` read-scale AG built by
> [ansible/mssql_ag.yml](../../ansible/mssql_ag.yml). Use this guide when the customer wants
> Windows + AD with automatic failover.

---

## Architecture

```
                 Active Directory Domain (corp.local)
                          │  (DNS + computer objects)
        ┌─────────────────┼──────────────────┐
        │                 │                   │
   ┌─────────┐       ┌─────────┐         ┌──────────────┐
   │ SQLNODE1│◄─────►│ SQLNODE2│         │ File Share   │
   │ primary │ sync  │secondary│         │ Witness (FSW)│
   └────┬────┘ commit└────┬────┘         └──────────────┘
        │  Hadr endpoint :5022 (cert/Windows auth)
        └──────────────┬──────────────┘
              Windows Server Failover Cluster (WSFC)
                        │
              AG Listener: AGLISTENER (VNN) + VIP :1433
                        │
                   Applications (WSO2, etc.)
```

| Component | Value (example) |
| --------- | --------------- |
| Domain | `corp.local` |
| Node 1 | `SQLNODE1` — 10.0.10.11 |
| Node 2 | `SQLNODE2` — 10.0.10.12 |
| WSFC name (CNO) | `SQLCLUSTER` — 10.0.10.20 |
| AG name | `AG1` |
| AG Listener (VNN) | `AGLISTENER` — 10.0.10.21, port 1433 |
| File Share Witness | `\\FSWHOST\QuorumFSW` |
| SQL service account | `CORP\svc_sql` (domain user) |
| Hadr endpoint port | 5022 |

---

## Prerequisites

1. **Two Windows Servers** (2019 or 2022), same patch level, joined to the **same AD domain**.
2. **Active Directory domain** reachable (a DC for DNS + Kerberos). You need rights to:
   - Join machines to the domain.
   - Create a domain service account.
   - Either pre-stage the cluster computer object (CNO) **or** grant the cluster permission to
     create computer objects in the target OU.
3. **SQL Server edition:**
   - **Enterprise** — full Availability Groups (multiple DBs per AG, readable secondaries,
     automatic failover). Use this for the topology above.
   - **Standard** — only **Basic Availability Groups** (1 database per AG, 2 replicas, no readable
     secondary). If using Standard, see the note at the end.
4. **Static IPs** for both nodes, the cluster, and the listener; **DNS** working via the DC.
5. **Identical drive letters/paths** on both nodes for SQL data/log/backup (e.g. `E:\Data`,
   `F:\Log`, `G:\Backup`).
6. A **file share** for the witness on a third machine (the DC or a file server).
7. **Time sync** (both nodes via the domain — automatic when domain-joined).

### Firewall ports to open (both nodes)

| Port | Purpose |
| ---- | ------- |
| TCP 1433 | SQL Server + AG listener |
| TCP 5022 | Always On endpoint (mirroring) |
| TCP/UDP 3343 | WSFC cluster communication |
| UDP 137, TCP 445 | File share witness (SMB) / name resolution |
| TCP 135 + dynamic RPC | WSFC management |
| ICMPv4 | Cluster health checks |

```powershell
# Run on each node (PowerShell, elevated). Enables the built-in clustering rules + SQL/endpoint.
Enable-NetFirewallRule -DisplayGroup "Failover Clusters"
New-NetFirewallRule -DisplayName "SQL Server 1433"  -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow
New-NetFirewallRule -DisplayName "SQL AG Endpoint 5022" -Direction Inbound -Protocol TCP -LocalPort 5022 -Action Allow
New-NetFirewallRule -DisplayName "AG Listener 1433" -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow
```

---

## Step 1 — Network & DNS

On **both nodes**:

1. Set a **static IPv4** address, subnet, gateway, and the **DC as the DNS server**.
2. Set a clear hostname (`SQLNODE1`, `SQLNODE2`).
3. Verify name resolution:
   ```powershell
   Resolve-DnsName corp.local
   Test-NetConnection SQLNODE2 -Port 5022   # from node 1
   ```

## Step 2 — Join both nodes to the domain

On **each node** (elevated PowerShell):

```powershell
Add-Computer -DomainName "corp.local" -Credential (Get-Credential CORP\Administrator) -Restart
```

After reboot, confirm membership:

```powershell
(Get-WmiObject Win32_ComputerSystem).Domain   # → corp.local
```

## Step 3 — Create the SQL service account (in AD)

On a DC (or via RSAT), create a **domain user** for the SQL Server service, e.g. `CORP\svc_sql`:

```powershell
New-ADUser -Name "svc_sql" -SamAccountName "svc_sql" `
  -UserPrincipalName "svc_sql@corp.local" `
  -AccountPassword (Read-Host -AsSecureString "Password") `
  -Enabled $true -PasswordNeverExpires $true
```

> Use the **same domain account** for the SQL Server service on **both** nodes — this lets the AG
> endpoints authenticate over Windows/Kerberos without certificates.

### CNO permissions (so the cluster + listener can create their AD objects)

Either **pre-stage** the cluster computer object `SQLCLUSTER` in the target OU and disable it, or
grant the OU permission so WSFC can create computer objects. Simplest reliable approach: pre-stage.

```powershell
# On a DC — pre-stage the cluster name object (CNO) and the listener VNN, then disable CNO.
New-ADComputer -Name "SQLCLUSTER" -Path "OU=SQL,DC=corp,DC=local" -Enabled $false
# Grant the CNO "Full Control" over the listener object, or let it self-create after the cluster
# is online. Also grant the account creating the cluster "Create Computer Objects" on the OU.
```

If you don't pre-stage, give the user creating the cluster **Create Computer Objects** on the OU,
and after the cluster is up, grant the **CNO** `Create Computer Objects` so it can create the
listener VNN.

## Step 4 — Install the Failover Clustering feature

On **both nodes**:

```powershell
Install-WindowsFeature -Name Failover-Clustering -IncludeManagementTools
```

## Step 5 — Validate and create the WSFC

From **Node 1** (elevated):

```powershell
# 1. Validate (fix anything flagged before continuing)
Test-Cluster -Node SQLNODE1, SQLNODE2

# 2. Create the cluster with a static management IP (no storage needed for AG)
New-Cluster -Name SQLCLUSTER -Node SQLNODE1, SQLNODE2 `
  -StaticAddress 10.0.10.20 -NoStorage
```

### Configure quorum — File Share Witness (recommended for 2 nodes)

A 2-node cluster needs a witness so a single node failure keeps quorum.

1. Create the share on a third host (DC/file server), grant the **CNO `SQLCLUSTER$`** and both node
   accounts **Full Control** (share + NTFS):
   ```powershell
   New-Item -Path "C:\QuorumFSW" -ItemType Directory
   New-SmbShare -Name "QuorumFSW" -Path "C:\QuorumFSW" -FullAccess "CORP\SQLCLUSTER$","CORP\SQLNODE1$","CORP\SQLNODE2$"
   ```
2. Set the witness on the cluster:
   ```powershell
   Set-ClusterQuorum -Cluster SQLCLUSTER -FileShareWitness "\\FSWHOST\QuorumFSW"
   ```
   (Cloud Witness is an alternative: `Set-ClusterQuorum -CloudWitness -AccountName ... -AccessKey ...`.)

Verify:

```powershell
Get-ClusterNode -Cluster SQLCLUSTER
Get-ClusterQuorum -Cluster SQLCLUSTER
```

## Step 6 — Install SQL Server on both nodes

Install a **standalone** SQL Server **Database Engine** instance on **each** node (default
instance `MSSQLSERVER`), using the **same domain service account** `CORP\svc_sql` for the SQL
Server service. Keep collation, paths, and instance names **identical** on both nodes.

After install, on both nodes set the service to run as the domain account (if not set during
install) and restart.

## Step 7 — Enable Always On in SQL Server

On **each node** (SQL Server Configuration Manager → SQL Server Services → *SQL Server* →
Properties → **AlwaysOn High Availability** tab → check **Enable Always On Availability Groups**),
then restart the SQL Server service. Or via PowerShell:

```powershell
Enable-SqlAlwaysOn -ServerInstance "SQLNODE1" -Force
Enable-SqlAlwaysOn -ServerInstance "SQLNODE2" -Force
```

> The Enable checkbox is only available once the node is part of a WSFC (Step 5).

## Step 8 — Prepare the database

On the **primary (SQLNODE1)**:

```sql
-- Database must be FULL recovery and have at least one full backup before joining an AG.
ALTER DATABASE [AppDB] SET RECOVERY FULL;
BACKUP DATABASE [AppDB] TO DISK = N'G:\Backup\AppDB_full.bak' WITH INIT, COMPRESSION;
BACKUP LOG      [AppDB] TO DISK = N'G:\Backup\AppDB_log.trn'  WITH INIT;
```

## Step 9 — Grant the service account login on both instances

Make sure `CORP\svc_sql` is a login on **both** instances (used for the endpoint connection):

```sql
-- Run on BOTH nodes
IF SUSER_ID('CORP\svc_sql') IS NULL CREATE LOGIN [CORP\svc_sql] FROM WINDOWS;
GRANT CONNECT ON ENDPOINT::[Hadr_endpoint] TO [CORP\svc_sql];   -- after Step 10 creates the endpoint
```

## Step 10 — Create the Availability Group

### Option A — SSMS wizard (recommended)

1. SSMS → connect to **SQLNODE1** → **Always On High Availability** → right-click **Availability
   Groups** → **New Availability Group Wizard**.
2. **Name:** `AG1`. Cluster type: **Windows Server Failover Cluster**.
3. **Databases:** select `AppDB` (meets prerequisites: full recovery + backup).
4. **Replicas:** add **SQLNODE1** and **SQLNODE2**. For **both**:
   - **Availability Mode:** `Synchronous commit`
   - **Failover Mode:** `Automatic`
   - **Readable Secondary:** `Yes` (or `Read-intent only`) — Enterprise only.
5. **Endpoints:** wizard creates `Hadr_endpoint` on TCP **5022** with Windows authentication.
6. **Data synchronization:** choose **Automatic seeding** (or Full backup/restore via a shared path).
7. **Listener:** configure on the next step (or Step 11).
8. Validate → Finish.

### Option B — T-SQL

On the **primary (SQLNODE1)** — create the endpoint and AG:

```sql
-- 1) Endpoint on each node (run on BOTH, adjust as needed)
CREATE ENDPOINT [Hadr_endpoint]
    STATE = STARTED
    AS TCP (LISTENER_PORT = 5022, LISTENER_IP = ALL)
    FOR DATABASE_MIRRORING (ROLE = ALL, AUTHENTICATION = WINDOWS NEGOTIATE, ENCRYPTION = REQUIRED ALGORITHM AES);

-- 2) Create the AG on the primary
CREATE AVAILABILITY GROUP [AG1]
WITH (AUTOMATED_BACKUP_PREFERENCE = SECONDARY, DB_FAILOVER = ON, DTC_SUPPORT = NONE)
FOR DATABASE [AppDB]
REPLICA ON
  N'SQLNODE1' WITH (
      ENDPOINT_URL = N'TCP://SQLNODE1.corp.local:5022',
      AVAILABILITY_MODE = SYNCHRONOUS_COMMIT,
      FAILOVER_MODE = AUTOMATIC,
      SEEDING_MODE = AUTOMATIC,
      SECONDARY_ROLE (ALLOW_CONNECTIONS = ALL)),
  N'SQLNODE2' WITH (
      ENDPOINT_URL = N'TCP://SQLNODE2.corp.local:5022',
      AVAILABILITY_MODE = SYNCHRONOUS_COMMIT,
      FAILOVER_MODE = AUTOMATIC,
      SEEDING_MODE = AUTOMATIC,
      SECONDARY_ROLE (ALLOW_CONNECTIONS = ALL));
```

On the **secondary (SQLNODE2)** — join and grant seeding:

```sql
ALTER AVAILABILITY GROUP [AG1] JOIN;
ALTER AVAILABILITY GROUP [AG1] GRANT CREATE ANY DATABASE;   -- enables automatic seeding
```

> With `SYNCHRONOUS_COMMIT` + `FAILOVER_MODE = AUTOMATIC` on **both** replicas and a healthy
> witness, the cluster fails over automatically if the primary goes down — **no data loss** for
> committed transactions.

## Step 11 — Create the AG Listener

### SSMS

Right-click **AG1** → **Add Listener**:
- **DNS Name:** `AGLISTENER`
- **Port:** `1433`
- **Network Mode:** Static IP → add `10.0.10.21` (subnet mask matching the LAN).

### T-SQL

```sql
ALTER AVAILABILITY GROUP [AG1]
ADD LISTENER N'AGLISTENER' (
    WITH IP ((N'10.0.10.21', N'255.255.255.0')),
    PORT = 1433);
```

The cluster creates the **VNN computer object** + **DNS A record** for `AGLISTENER`. If it fails
with a permissions error, grant the **CNO `SQLCLUSTER$`** `Create Computer Objects` / `Full
Control` over the listener object in AD, then retry.

## Step 12 — Test failover

```sql
-- Planned manual failover (run ON the target secondary, SQLNODE2)
ALTER AVAILABILITY GROUP [AG1] FAILOVER;
```

For automatic failover, stop the SQL service on the primary and confirm the secondary takes the
primary role and the listener follows. Check:

```sql
SELECT ag.name, ar.replica_server_name, rs.role_desc,
       rs.operational_state_desc, rs.synchronization_health_desc
FROM sys.availability_groups ag
JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
JOIN sys.dm_hadr_availability_replica_states rs ON ar.replica_id = rs.replica_id;
```

```powershell
Get-ClusterGroup -Cluster SQLCLUSTER
Get-ClusterResource -Cluster SQLCLUSTER
```

Both replicas should show `synchronization_health_desc = HEALTHY`, one `PRIMARY`, one `SECONDARY`.

## Step 13 — Application connection string

Always connect through the **listener**, never a node directly:

```
Server=AGLISTENER,1433;Database=AppDB;Integrated Security=SSPI;MultiSubnetFailover=True;
```

- `MultiSubnetFailover=True` speeds up reconnect after failover (and is required for
  multi-subnet listeners).
- For WSO2 JDBC:
  `jdbc:sqlserver://AGLISTENER:1433;databaseName=AppDB;encrypt=true;trustServerCertificate=true;multiSubnetFailover=true`

---

## Verification checklist

- [ ] `Get-ClusterNode` shows both nodes `Up`.
- [ ] `Get-ClusterQuorum` shows the File Share Witness configured.
- [ ] AG dashboard (SSMS → Always On → AG1 → **Show Dashboard**) is green for both replicas.
- [ ] `synchronization_state_desc = SYNCHRONIZED` for the synchronous secondary.
- [ ] Listener `AGLISTENER` resolves in DNS and accepts connections on 1433.
- [ ] Manual failover succeeds and the listener follows the new primary.
- [ ] Automatic failover works when the primary SQL service stops.

## Troubleshooting

| Symptom | Cause / fix |
| ------- | ----------- |
| Enable Always On checkbox greyed out | Node not yet in a WSFC — complete Step 5 first. |
| Listener creation fails (`access denied` / `the network name cannot be created`) | CNO lacks AD rights — grant `SQLCLUSTER$` **Create Computer Objects** on the OU (or pre-stage the VNN), then retry. |
| Endpoint won't connect / `Login failed for NT AUTHORITY\ANONYMOUS` | SQL service not running as the domain account, or SPN/Kerberos issue — use `CORP\svc_sql` on both nodes and grant `CONNECT ON ENDPOINT`. |
| Secondary stuck `NOT SYNCHRONIZING` / seeding fails | Run `ALTER AVAILABILITY GROUP [AG1] GRANT CREATE ANY DATABASE;` on the secondary; ensure identical paths and open port 5022. |
| Cluster loses quorum on single failure | Witness missing/misconfigured — set the File Share or Cloud Witness (Step 5). |
| Automatic failover doesn't happen | Both replicas must be `SYNCHRONOUS_COMMIT` + `FAILOVER_MODE = AUTOMATIC`, and `DB_FAILOVER = ON` is recommended. |

## Note — SQL Server Standard edition (Basic AG)

If the edition is **Standard**, you can only create a **Basic Availability Group**:

- Exactly **2 replicas** (one primary, one secondary), **one database** per AG.
- Synchronous or asynchronous commit + automatic failover **are** supported.
- **No readable secondary**, no backups on secondary, no multi-DB AG.

Create with the same steps but in the AG wizard select **Basic Availability Group**, or in T-SQL
add `WITH (BASIC, ...)` and a single database. Everything else (WSFC, witness, listener) is the same.
