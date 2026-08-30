"""Dependency readiness.

A workload declares what it needs. The console shows `Waiting on 4 · RKE2 cluster`
instead of letting an operator start something that will fail confusingly ten
minutes in. Advisory for a single deliberate run, enforced for bulk runs.
"""

from __future__ import annotations

from . import state
from .workloads import BY_ID, DESTRUCTIVE, WORKLOADS


def readiness() -> dict[str, dict]:
    """Per-workload {ready, blockedBy: [{id, ordinal, title}]}."""
    status = state.status_map()
    out: dict[str, dict] = {}
    for wl in WORKLOADS:
        blocked = []
        for dep_id in wl.requires:
            dep = BY_ID.get(dep_id)
            if not dep:
                continue
            if status.get(dep_id, {}).get("status") != "completed":
                blocked.append({"id": dep.id, "ordinal": dep.ordinal, "title": dep.title})
        out[wl.id] = {"ready": not blocked, "blockedBy": blocked}
    return out


def bulk_runnable(values: dict[str, dict]) -> list[str]:
    """Workloads that a bulk run may start.

    Excludes anything destructive — always, and in the backend, so the guarantee
    survives a direct API call rather than living only in the browser. Also
    excludes workloads whose dependencies have not completed, and anything with
    no configuration entered.
    """
    ready = readiness()
    runnable = []
    for wl in WORKLOADS:
        if wl.id in DESTRUCTIVE:
            continue
        if not ready[wl.id]["ready"]:
            continue
        vals = values.get(wl.id) or {}
        if not _configured(wl, vals):
            continue
        runnable.append(wl.id)
    return runnable


def _configured(wl, vals: dict) -> bool:
    """A workload counts as configured when every field that has no default and is
    not a secret has been filled in. Secrets are excluded because they are never
    persisted, so their absence says nothing about intent."""
    required = [f for f in wl.fields
                if not f.default and f.type != "password" and not f.show_if]
    if not required:
        return bool(vals)
    return all((vals.get(f.key) or "").strip() for f in required)
