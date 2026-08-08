# Autoprovision

On-premise infrastructure provisioning. A FastAPI control plane on a jump host
drives Ansible against customer VMs, installing RKE2 clusters, databases, object
storage, monitoring and WSO2 — several stacks at once, on execution day.

## Layout

| Path | What it is |
| ---- | ---------- |
| `app/workloads.py` | **The registry — the single source of truth.** Every workload is declared once. The API serves it to the browser; the planner and dependency checker read it. |
| `app/planner.py` | Resolves an action plus form values into playbooks and an inventory. Pure — no filesystem, no subprocess. **The highest-value thing to test.** |
| `app/runner.py` | Writes a per-run inventory, executes steps, streams output. |
| `app/state.py` | SQLite: saved values, per-step install status, run history. |
| `app/deps.py` | Which workloads are ready, and what a blocked one is waiting on. |
| `app/main.py` | HTTP routes. Thin — validate, delegate, serialise. |
| `app/dist/` | **Built console. Committed.** The jump host has no Node. |
| `console/` | React and TypeScript source for the console. |
| `content/<slug>/` | `requirements.md`, `guide.md`, `theory.md` per workload, rendered in its tabs. |
| `ansible/` | Playbooks, grouped by domain: `db/`, `k8s/`, `platform/`, `monitoring/`, `object/`, `certs/`. |
| `docs/` | `docs/planning/` requirements · `runbooks/` manual procedures · `specs/` designs · `status/` lab state. |
| `tests/` | pytest. Run with `.venv/bin/python -m pytest tests/ -q`. |

## Working here

**Adding or changing a workload is a registry change.** Add a `Workload` to
`WORKLOADS` in `app/workloads.py` and an action handler in `app/planner.py`. Never
add a workload to the frontend — it reads the registry. Two entries once existed
in the UI and not the backend, and their settings were silently discarded for
months. `tests/test_planner.py` now fails if an action has no planner.

**The planner must stay pure.** It decides what runs against production
infrastructure. Every branch deserves a test, and a test there is worth ten
anywhere else in this codebase.

**Destructive workloads set `destructive=True` and a `confirm_field`.** The
enforcement is in `app/main.py`, not the browser, so a direct API call cannot skip
it. Bulk run excludes them in `app/deps.py` for the same reason.

**Rebuild the console after changing anything under `console/`:**

```bash
cd console && npm run build      # writes app/dist/, which is committed
node smoke.mjs                   # browser test against a running server
```

**Secrets never reach SQLite.** Any field of type `password` is filtered in
`state.save_target`. Passwords still travel via `--extra-vars` and are visible in
`ps` for the length of a run — that is a known gap, fixed by the Infisical
workload.

## Conventions

- Prose is sans; every machine fact — IP, version, hostname, playbook path — is
  monospace in the UI. If you must type it exactly right, it is monospace.
- Error messages explain what to do, not just what failed. `"A managed cluster
  needs at least three nodes; 2 was given. Two nodes cannot arbitrate a split
  brain"` beats `"invalid node count"`.
- Playbooks assert their preconditions in `pre_tasks` and fail fast, rather than
  half-installing and leaving the operator to work out what state they are in.
- UAT and Production are separate environments with the same capabilities. Shared
  services holds only what both genuinely share.

## Documents

- `README.md` — operator flow, start to finish
- `techstack.md` — every component, with Selected / Alternative / Planned and why
- `FEATURES.md` — what works, what is specified, what is still a decision
- `CHANGELOG.md` — what changed and the reasoning
- `docs/status/service-status.md` — what has actually been tested in the lab
