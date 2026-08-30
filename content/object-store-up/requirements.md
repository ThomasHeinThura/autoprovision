# Requirements

## Machines

| Deploy mode | Nodes | vCPU | RAM | Disks per node |
| ----------- | ----- | ---- | --- | -------------- |
| Standalone | 1 | 4 | 16 GB | 1 or more |
| Distributed | **2 or more** | 4 | 16 GB | **4 identical raw disks, minimum** |

**Four drives per node is a hard minimum in distributed mode**, and the playbook
refuses to run with fewer. Erasure coding spreads each object across every drive
with parity blocks; below four the parity budget cannot survive a node outage and
a drive failure at the same time.

**Four nodes is the smallest layout worth running.** With two or three, a single
node going down consumes the entire parity budget — so a disk failing *while that
node is down* loses data. The console warns rather than blocks, because two-node
is legitimate for a lab.

There is no upper bound. If you have sixteen storage nodes, use them — the console
checks the erasure-set arithmetic rather than capping the count.

## Disks

- **Raw, unformatted disks. Not a RAID volume.** Erasure coding is already doing
  what RAID does, and layering them wastes capacity while hiding failures from
  the layer that could act on them.
- **Identical count and size on every node.** MinIO computes its erasure set from
  a symmetric layout and refuses to start on an asymmetric one, with an error
  that does not name the odd node out.
- Directly attached. Not NFS, not iSCSI.

## Before you run

- The `autoprovision` account exists on every node with passwordless sudo.
- Every node resolves and reaches every other node — distributed mode blocks at
  startup until quorum forms, which is normal and can take a minute.
- Sequential hostnames or addresses. The expansion notation that defines the
  cluster assumes them.
- Disks attached and **unmounted**.

## Ports

| Port | Used by | Restrict to |
| ---- | ------- | ----------- |
| `9000/tcp` | S3 API | Applications and other nodes |
| `9001/tcp` | Console | Operators only |

## What writes here

| Consumer | Why it matters |
| -------- | -------------- |
| Loki, Tempo, Mimir | If you chose LGTM, all three store here and none start without it |
| Database backups | pgBackRest and XtraBackup repositories |
| etcd snapshots | Cluster state |
| GitLab | Artifacts, LFS, container registry blobs |

## What this does not do

- **Create buckets or service accounts** for individual consumers. The Monitoring
  workload creates its own, each scoped to one bucket.
- **Replicate to a second site.** A single cluster in one rack is not disaster
  recovery, whatever its parity. That is **Backups & DR → Object store
  replication**.
- Open a firewall. It tells you which ports it needs.
