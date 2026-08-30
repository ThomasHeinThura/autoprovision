# Database engine

Why the data tier is built the way it is.

## Why databases run on VMs rather than in the cluster

Kubernetes is excellent at rescheduling stateless workloads and merely adequate at
stateful ones. A database in a pod adds a storage layer, a CSI driver and an
operator between your data and the disk — three more things that can fail during a
failover, at exactly the moment you want the fewest surprises.

On-premise, with a fixed VM budget and no cloud block storage, running the engine
natively on its own VM is simpler and faster. The cluster then treats the database
as what it is: an external dependency at a stable address.

## Why you choose the engine per environment

Nothing in the platform requires one engine everywhere. WSO2 supports SQL Server,
PostgreSQL and MySQL; so do GitLab and SonarQube. The console provisions any of
them because the customer's existing estate, licensing and staff knowledge decide
this far more than technical merit does.

What it will not do is let you pick a topology the engine cannot actually deliver.
Multi-primary is offered for MySQL and refused for the others, because Group
Replication genuinely supports it and availability groups and Patroni genuinely do
not.

## Why "high availability" means three different things

| Shape | What it gives | What it costs |
| ----- | ------------- | ------------- |
| **Two-node replication** | A warm standby holding a current copy | Failover is manual, by design |
| **Managed cluster** | Automatic failover with a quorum-based arbiter | Three machines and a consensus layer |
| **Multi-primary** | Every node accepts writes | Write conflicts surface as errors your application must handle |

Two-node failover is manual **deliberately**. With two nodes there is no way to
distinguish "the primary died" from "the network between us died", and an
automatic promotion that guesses wrong gives two primaries writing divergent data
— the one failure mode that is genuinely hard to recover from. A human who can
check whether the primary is actually down is a better arbiter than a coin flip.

Multi-primary sounds like more availability and mostly is not. Two nodes writing
the same row concurrently are resolved by rolling one transaction back at
`COMMIT`. Applications that assume a single writer treat that as an unexpected
error rather than something to retry, and the failure shows up under load, in
production, in whichever code path nobody guarded.

## Why never connect as a superuser

The built-in accounts are not merely privileged. They are paths to a shell:

| Account | Escalation |
| ------- | ---------- |
| `sa` (SQL Server) | `xp_cmdshell` runs operating system commands |
| `root` (MySQL) | The `FILE` privilege reads and writes any file the daemon can reach |
| `postgres` | `COPY … FROM PROGRAM` runs a shell command |

One SQL injection in an application, or one leaked `deployment.toml`, stops being
a database incident and becomes a data-centre incident. The two-tier model keeps
the blast radius at "this application's own schema", which is why the engine ships
with no application login at all until **Database users** has run.

## Why the login SID must match across replicas

In SQL Server a *login* lives at server level and a *user* lives inside a
database, joined by a security identifier. When a database moves to another
replica during failover it carries its users — but the new server has its own
logins with their own SIDs. If they do not match, the user is **orphaned**: it
exists in the database, maps to no login, and the application's connections are
refused with an error that mentions neither failover nor SIDs.

Creating every login with an explicit, identical SID on every replica is what
makes failover invisible to the application. It is the single least obvious thing
in this entire codebase, and it is why `mssql_wso2_db.yml` looks the way it does.

The other engines have their own version of the same ordering problem. MySQL
propagates account DDL through Group Replication, so accounts must exist before a
node joins or it fails to sync. PostgreSQL roles are cluster-global and reach
streaming replicas automatically — but they must exist before Patroni bootstraps
a replica.

## Why high availability is not a backup

An availability group protects against a node dying. It replicates everything
faithfully — including a `DROP TABLE`, a corrupt page, and a ransomware encryption
pass. Those reach every replica in seconds.

Only backups, held somewhere the database server cannot reach and write to,
protect against the failure modes that actually destroy data. Run both. If you can
only run one, run backups.

## Why single-node UAT is a choice, not a shortcut

High availability costs three VMs, a consensus layer, and real operational
complexity. UAT does not need to survive a node failure at three in the morning —
it needs to exist, match Production's schema, and be quick to rebuild. Spending
Production's HA budget on a test environment would be the mistake.
