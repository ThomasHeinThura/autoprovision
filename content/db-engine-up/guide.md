# Guide

Provisioning a database engine, start to finish. Fifteen minutes for a single
node, closer to forty for a three-node cluster.

> **Run this before WSO2.** WSO2 needs a reachable database and its own login
> before its first pod starts, or it crash-loops on schema initialisation.

## 1 · Prepare the machines

Run **Host bootstrap** if you have not already. It creates the `autoprovision`
account and installs the jump host's key across every VM at once, which is the
alternative to nineteen manual SSH sessions.

Attach the data disk and leave it unmounted. The playbook formats and mounts it.

## 2 · Choose the engine and the topology

Each answer changes the next question and the Requirements tab, so read
Requirements again after you change anything — the VM count moves with it.

- **Engine** — whatever your estate and your team already know. There is no
  technically correct answer here.
- **Deploy mode** — single node for UAT, high availability for Production.
- **High availability shape** — a managed cluster unless you have a specific
  reason. Two-node replication has no arbiter and fails over by hand.

Choosing **SQL Server on Windows** stops here and points at the manual runbook.
That path needs a Windows failover cluster and a domain, which this console does
not automate.

## 3 · Fill in the fields

**Node IPs** — one per line. The first is the initial primary.

**Data directory** — point at the dedicated disk. Putting it on the system disk
works, and then a full root filesystem takes the whole VM down instead of just the
database.

**Provisioning admin** — this is *not* the account your application will use. It
exists so Ansible can create databases and roles, and it gets disabled once the
runtime logins exist.

**Virtual IP** — an unassigned address on the node subnet, outside DHCP. This is
what applications connect to, and it moves with the primary during a failover.

## 4 · Read the plan, then run

The right-hand panel shows the exact playbooks and the resolved inventory before
anything executes. Check the host list matches what you expect — this is the last
cheap moment to catch a typo.

Then **Run workload**. Watch the first few tasks: the assertions fail fast on a
wrong Ubuntu release or an even node count, rather than leaving a half-installed
engine behind.

## 5 · Verify

The final task queries the engine and prints its version and edition. For a
cluster it also prints the member list and their roles — confirm every node is
present and exactly one is primary.

## 6 · Create the users

Go straight to **Database users**. The engine is not usable by an application
until it has a login that is not a superuser, and this workload deliberately
creates none.

---

## If the run fails partway

Fix the cause and run again. Completed steps are skipped, so it resumes rather
than restarting.

Use **Force** only when a step reported success but produced a broken result — for
example a cluster that returned `rc=0` before the node-ready check existed.

**Clear install history** goes further: it forgets every recorded step so the next
run reinstalls from scratch. It changes no infrastructure by itself.

For a cluster that has drifted badly, the **Danger zone** has a teardown that
removes the cluster manager and its state so a clean rebuild is possible. It
leaves the engine installed and your databases intact.
