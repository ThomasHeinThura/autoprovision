# Capacity planning

How to size an environment. There is no fixed topology — you declare environments
in [`config/environments.yml`](../../config/environments.yml) and size each
workload for the machines you have. Three machines and fifty are the same amount
of configuration.

> The original engagement was scoped at 19 machines. That number is history, not a
> constraint: it survives in [`vm-requirements-rke2.md`](vm-requirements-rke2.md)
> as the record of one rollout. Use this document for anything new.

---

## Per-machine sizing

| Role | vCPU | RAM | System disk | Extra disks | Notes |
| ---- | ---- | --- | ----------- | ----------- | ----- |
| Jump host | 2 | 4 GB | 40 GB | — | Runs the control plane. One per estate, not per environment. |
| Kubernetes control plane | 4 | 8 GB | 80 GB | — | etcd is write-latency sensitive; give it SSD. |
| Kubernetes worker | 8 | 32 GB | 100 GB | — | Size for the pods you actually run. |
| Database, single | 4 | 16 GB | 80 GB | **Data disk** | Separate disk, always. |
| Database, clustered | 8 | 32 GB | 120 GB | **Data disk** | Same L2 segment if you use a virtual IP. |
| Object storage | 4 | 16 GB | 40 GB | **4+ raw disks** | Identical layout on every node. |
| Monitoring, on a VM | 8 | 32 GB | 500 GB | — | Sizing follows retention, not node count. |
| Docker host | 4 | 16 GB | 100 GB | — | GitLab wants more if CI is busy. |

**Every machine:** Ubuntu Server 24.04 LTS, an `autoprovision` account with
passwordless sudo, and reachable from the jump host on `22/tcp`.

---

## Counting rules

These are the constraints the console enforces. It refuses configurations that
break them, with the reason stated, rather than letting you discover them during a
change window.

| Component | Rule | Why |
| --------- | ---- | --- |
| Kubernetes control plane | **1, 3 or 5 — an odd count** | etcd needs a majority. Four gives you no more tolerance than three and one more machine to patch. |
| Kubernetes workers | Any number | Scale with the workload. |
| Database cluster | **3 or 5 — an odd count** | Two cannot arbitrate a split brain: both sides promote themselves and the data diverges. |
| Database, two-node | Exactly 2, **manual failover** | Deliberate. With no arbiter, an automatic promotion that guesses wrong gives two primaries. |
| Object storage | **2+ nodes, 4+ raw disks each** | Erasure coding needs the drives. Four *nodes* is the smallest layout that survives a node outage plus a drive failure during it. |
| Monitoring, clustered | **Odd count** | Cluster-manager election needs a majority. |
| Virtual IPs | One per clustered database | Unassigned, outside DHCP, on the node subnet. |
| MetalLB range | One contiguous block per cluster | Unassigned addresses on the node subnet. |

---

## Worked sizes

Same configuration effort in every case — only the numbers you type differ.

### Minimum viable — 3 machines

One environment, everything single-node. Useful for a demo or a proof of concept.

| Machines | Role |
| -------- | ---- |
| 1 | Jump host |
| 1 | Kubernetes: one control plane, workloads scheduled on it |
| 1 | Docker host: database, object storage and monitoring all co-located |

The topology view will flag that last machine as carrying several roles. That is
correct and fine here — it is a warning about production, not about a lab.

### Small — around 10 machines

One production environment with a highly available database, plus shared services.

| Machines | Role |
| -------- | ---- |
| 1 | Jump host |
| 1 | Shared: GitLab, registry, SonarQube |
| 1 | Kubernetes control plane |
| 2 | Kubernetes workers |
| 3 | Database cluster |
| 1 | Object storage, standalone |
| 1 | Monitoring |

### Medium — around 25 machines

Two complete environments, production highly available throughout.

| Machines | Role |
| -------- | ---- |
| 1 | Jump host |
| 1 | Shared services |
| 5 | UAT: 1 control plane, 2 workers, 1 database, 1 combined storage and monitoring |
| 17 | Production: 3 control planes, 5 workers, 3 database, 4 object storage, 2 monitoring |

### Large — 50 machines and beyond

Nothing changes structurally. Add environments to
[`config/environments.yml`](../../config/environments.yml) — each `stack: full`
entry gets its own complete workload set with no code change — and size each
workload as above.

At this scale two things start to matter that did not before:

- **Run the host bootstrap workload.** One SSH session per machine stops being
  viable somewhere around a dozen.
- **Use the topology view.** It is the only thing in the system that can answer
  "what am I actually managing?", and it flags machines carrying more than one
  role — which is how estates quietly become fragile.

---

## Adding an environment

```yaml
# config/environments.yml
  - id: dr
    title: Disaster recovery
    stack: full
    subnet: 10.90.7        # drives example addresses in form placeholders only
    blurb: Standby site. Object storage replicates here.
```

Restart the control plane. The environment appears with its full workload set, its
own screen, and its own recorded install status.

**Keep `id` stable once you have run anything.** It is part of every workload id
and URL, so renaming it orphans that environment's install history. The topology
view reports orphaned environments rather than hiding them.

---

## What is not automated

| Prerequisite | Why it stays manual |
| ------------ | ------------------- |
| Creating the machines | Hypervisor-specific. The control plane provisions *onto* machines, it does not make them. |
| DNS records | Customer-controlled. |
| Firewall rules | Customer-controlled. Each workload's Requirements tab lists the ports it needs. |
| NFS or NAS exports for backups | Storage-team territory, and a backup target you do not control is not a backup target. |
| TLS certificate handover | Unless you self-sign, which the console supports. |
