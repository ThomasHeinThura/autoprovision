# Object storage

## Why an S3 API on your own hardware

Three unrelated things in this platform want the same shape of storage: cheap,
enormous, write-once, addressed by name rather than by path. Log chunks, database
backups, cluster snapshots.

A filesystem is the wrong answer for all three — it needs a mount on every client,
it has no useful access control across machines, and it cannot be replicated
without a second product. An S3 API is what every one of these tools already
speaks natively, so nothing needs adapting.

## Why erasure coding rather than replication

Replication keeps N whole copies: three copies costs 3× the raw capacity for the
ability to lose two.

Erasure coding splits each object into data and parity shards spread across all
drives. A typical layout survives losing half the drives while costing about 1.5×
raw capacity. For a monitoring stack retaining thirty days of logs, that
difference decides whether the retention policy is affordable.

The cost is that recovery is arithmetic rather than a copy, so a rebuild is CPU
work rather than a straight read. That trade is right for archival data and wrong
for a hot database, which is why the databases in this platform are on their own
disks and not here.

## Why four drives, and why four nodes

The parity budget is fixed at write time. It has to cover every failure happening
*simultaneously*, and failures are not independent — a node reboot for patching
and a drive failing during the rebuild is a Tuesday, not a coincidence.

With four nodes and four drives each, one node offline still leaves enough parity
that a drive can fail during the outage. With two nodes, the node outage alone
consumes the budget. Two-node distributed gives you the operational complexity of
a cluster with the durability of a single machine.

## Why not RAID underneath

RAID and erasure coding solve the same problem, and running both means paying for
redundancy twice while getting less than either alone.

Worse, RAID hides drive failures from MinIO. The array silently degrades, MinIO
believes it has full redundancy, and both layers are one failure from data loss
while every dashboard reads green. Give the object store raw disks and let it
manage its own failure domain.

## Why this is not a backup

Distributed object storage survives drives failing and nodes failing. It does not
survive: a fire in the rack, a mistaken `mc rm --recursive --force`, a ransomware
process with valid credentials, or a firmware bug that corrupts every node
identically.

Every one of those is a real way to lose everything in this cluster. That is what
the replication workload is for, and why it targets a *different site* rather than
a second cluster in the same room.

## Why it runs before monitoring

If you chose LGTM, Loki, Tempo and Mimir all store here. Without their buckets
they do not start — they crash-loop, which looks like a monitoring problem and is
a storage problem. The console makes Monitoring depend on this workload so the
ordering is visible rather than learned.
