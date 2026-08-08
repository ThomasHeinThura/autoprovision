# Requirements

## Before you run

- The **Database engine** workload has completed on every node.
- The provisioning admin password you set there — this workload authenticates with
  it, and cannot create anything without it.
- **Every node listed**, not just the primary. Accounts must exist on all of them.
  A login missing on one replica becomes a failed connection the first time that
  node is promoted, and the error will not mention the missing login.

## What you need to decide

**Which components need a database.** One login and one database each. The default
is `apim` and `is` for WSO2; add `sonarqube`, `gitlab`, or your own application
names as needed.

**The login name prefix.** `wso2` produces `wso2_apim`, `wso2_is`, and so on.

**Whether to lock the built-in superusers.** Yes, unless you are mid-migration and
still need `sa` or `root` for something. You can run this again later with it
enabled.

## What this creates

| Tier | Account | Rights |
| ---- | ------- | ------ |
| Provisioning | The admin you named | Server-level. Disabled or restricted after this runs. |
| Runtime | One per component | DML on its own database only. No DDL, no `FILE`, no `GRANT`, no `SUPER`. |

The playbook asserts afterwards that no runtime account holds a dangerous global
privilege, and fails the run if one does.

## SQL Server only — the login SID

On an availability group, every login is created with an **identical security
identifier on every replica**. Leave the SID field empty and one is derived
deterministically from the login name.

This is not a detail you can skip. Without it, a failover orphans the user: it
still exists inside the database, maps to no login on the new primary, and every
connection is refused.

## What this does not do

- Load application schemas beyond WSO2's. Other applications create their own on
  first start, which is why their account needs its own database rather than
  rights on someone else's.
- Rotate passwords. Run it again with a new one, then update the application.
- Grant cross-database access. If two components need to read each other's data,
  that is a design conversation, not a permission.
