# Database users

## Why the application never gets a superuser

The built-in accounts are remote code execution with a password in front:

| Account | Escalation |
| ------- | ---------- |
| `sa` | `xp_cmdshell` runs operating system commands |
| `root` | `FILE` reads and writes any file the daemon can reach |
| `postgres` | `COPY … FROM PROGRAM` runs a shell command |

An application connecting as one of these means a single SQL injection, or one
leaked configuration file, escalates from "someone read a table" to "someone has a
shell on the database host". The database is usually the machine with the most
valuable data and the fewest outbound firewall rules.

## Why two tiers rather than one account

A single account has to be powerful enough to create schemas at install time, and
that power then sits in a configuration file for the life of the deployment.
Splitting it means the powerful account exists for the twenty minutes provisioning
takes and is then disabled, while the account that lives in the config file can do
nothing but read and write its own rows.

## Why one account per component

Shared credentials remove your ability to answer three questions: which component
made this change, which component is causing this load, and what breaks if this
password is rotated. They also mean a compromise of the least-defended component
reaches every other component's data.

WSO2 API Manager and Identity Server get separate logins for exactly this reason,
even though they are the same vendor and deploy together.

## Why the SID has to match

A SQL Server *login* is a server-level object. A *user* is a database-level object.
They are joined by a security identifier, and the database carries its users with
it when it fails over.

The new primary has its own logins, created independently, with independently
generated SIDs. The user inside the database points at a SID that server has never
heard of. The user is **orphaned** — present, mapped to nothing, and every
connection attempt is refused.

Pinning the SID explicitly, identically, on every replica is what makes failover
invisible to the application. It is the least obvious requirement in this platform,
and the symptom when it is missing — an application that works fine until the
first failover, then cannot connect — sends people looking at networking.

## Why the other engines differ

**MySQL** propagates account DDL through Group Replication, so accounts created
after a node joined will reach it. But an account created while a node was offline
may not, and a node that cannot authenticate cannot rejoin. So accounts are
created on every node, before the group forms.

**PostgreSQL** roles are cluster-global and reach streaming replicas
automatically. The ordering constraint is different: a role must exist before
Patroni bootstraps a replica, or the replica starts without it.

## Why locking the built-ins comes last

Disabling `sa` before a working replacement exists locks you out of your own
database, with no recovery short of single-user mode. The playbook confirms the
named admin can actually authenticate before it touches anything, and refuses to
run at all if the replacement admin is itself named `sa`, `root` or `postgres`.
