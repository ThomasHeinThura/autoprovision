# Guide

## 1 · Attach the disks

Four raw disks per node, identical in count and size across every node. Leave them
unformatted and unmounted — the playbook handles both.

Do not build a RAID array first. Erasure coding already does that job, and RAID
underneath hides drive failures from the layer that could act on them.

## 2 · Choose the topology

**Standalone** for a lab or a single-purpose store. No redundancy: losing the node
loses the data.

**Distributed** for anything real. Four nodes if you can — with two or three, a
single node outage consumes the entire parity budget, so a drive failing during
that outage loses data. The console warns rather than blocks.

## 3 · Fill in the fields

**Node IPs** — one per line, sequential addresses.

**Drives per node** — four minimum in distributed mode. The playbook refuses fewer.

**Root password** — this account can read and delete every bucket. Treat it like a
database superuser and put it in the vault.

## 4 · Run

First start in distributed mode blocks until every node has joined and quorum
forms. A minute of apparent silence is normal, not a hang.

## 5 · Verify

The final task prints the cluster layout — node count, drive count, and the
erasure set size. Confirm every node is listed. A node missing here is a node that
will not be there when you need its parity.

## 6 · Point consumers at it

Object storage on its own does nothing. Next:

- **Monitoring**, if you chose LGTM — it creates its own buckets here
- **Backups & DR** — database and etcd repositories
- **Object store replication** — mirror to a second site, because one cluster in
  one rack is not disaster recovery
