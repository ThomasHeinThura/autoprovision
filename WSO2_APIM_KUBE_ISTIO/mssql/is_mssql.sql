-- WSO2 Identity Server 7.2.0 — MSSQL database bootstrap for the SQL Server Always On AG.
-- Creates the two IS databases + the shared login/user. The login user/password and its SID are
-- passed as sqlcmd variables so EVERY AG replica gets the SAME login SID (else the contained user
-- orphans on failover). ansible/mssql_wso2_db.yml passes them; for a MANUAL run supply them:
--   sqlcmd -S <primary> -U sa -P '<sa-pw>' -C -b -i is_mssql.sql \
--     -v WSO2_USER=wso2carbon -v WSO2_PW='<db-pw>' -v WSO2_SID=0x57534F3243415242000000000000ABCD
-- WSO2_USER/WSO2_PW MUST match the [database.*] blocks in wso2-is/cm-is.yaml; WSO2_SID MUST be the
-- same value used by apim_mssql.sql / shared_mssql.sql and on every node.
--
-- IMPORTANT: this script only creates the databases, login and grants. It does NOT contain the
-- IS table schema (that is thousands of lines of vendor DDL). After running this, load the IS
-- 7.2.0 pack's MSSQL dbscripts into the matching database:
--   <IS_HOME>/dbscripts/mssql.sql                  -> WSO2_IS_IDENTITY_DB   (IDN_* identity tables)
--   <IS_HOME>/dbscripts/consent/mssql.sql          -> WSO2_IS_IDENTITY_DB   (consent tables)
--   <IS_HOME>/dbscripts/identity/mssql.sql (if present) -> WSO2_IS_IDENTITY_DB
--   <IS_HOME>/dbscripts/mssql.sql (registry + UM)  -> WSO2_IS_SHARED_DB     (REG_* + UM_* tables)
-- (Exact file layout varies by pack; identity-side tables go to WSO2_IS_IDENTITY_DB, registry and
--  user-management tables to WSO2_IS_SHARED_DB.)
--
-- Run against the AG PRIMARY (the listener/VIP) with sqlcmd -C. The AG replicates to secondaries.
-- Add both databases to the availability group afterward if you want them protected by failover.

-- ── Login (server-level; created once, used by both DBs) ─────────────────────────
IF NOT EXISTS (SELECT * FROM sys.server_principals WHERE name = '$(WSO2_USER)')
BEGIN
    CREATE LOGIN [$(WSO2_USER)] WITH PASSWORD = '$(WSO2_PW)', SID = $(WSO2_SID), CHECK_POLICY = OFF;
END;
GO

-- ── WSO2_IS_IDENTITY_DB (identity, consent, agent-identity tables) ───────────────
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'WSO2_IS_IDENTITY_DB')
BEGIN
    CREATE DATABASE WSO2_IS_IDENTITY_DB COLLATE Latin1_General_CS_AS;
END;
GO
USE WSO2_IS_IDENTITY_DB;
GO
IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = '$(WSO2_USER)')
    CREATE USER [$(WSO2_USER)] FOR LOGIN [$(WSO2_USER)];
GO
ALTER ROLE db_owner ADD MEMBER [$(WSO2_USER)];
GO
-- Read-committed snapshot avoids reader/writer blocking (WSO2 recommends RCSI for IS on MSSQL).
ALTER DATABASE WSO2_IS_IDENTITY_DB SET READ_COMMITTED_SNAPSHOT ON;
GO

-- ── WSO2_IS_SHARED_DB (registry + user management tables) ────────────────────────
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'WSO2_IS_SHARED_DB')
BEGIN
    CREATE DATABASE WSO2_IS_SHARED_DB COLLATE Latin1_General_CS_AS;
END;
GO
USE WSO2_IS_SHARED_DB;
GO
IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = '$(WSO2_USER)')
    CREATE USER [$(WSO2_USER)] FOR LOGIN [$(WSO2_USER)];
GO
ALTER ROLE db_owner ADD MEMBER [$(WSO2_USER)];
GO
ALTER DATABASE WSO2_IS_SHARED_DB SET READ_COMMITTED_SNAPSHOT ON;
GO
