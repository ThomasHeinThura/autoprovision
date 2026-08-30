"""Autoprovision control plane — HTTP API and static console.

Routes are thin: they validate, delegate to the planner or runner, and serialise.
Everything that decides what runs against real infrastructure lives in planner.py,
where it can be tested without a subprocess.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import content, deps, runner, state, topology
from .planner import PlanError, plan
from .workloads import BY_ID, DESTRUCTIVE, registry_payload

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(BASE_DIR, "app", "dist")

app = FastAPI(title="Autoprovision Control Plane", version="1.0.0")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# ── registry and state ───────────────────────────────────────────────────────

@app.get("/api/registry")
async def api_registry():
    return JSONResponse(registry_payload())


@app.get("/api/state")
async def api_state():
    return JSONResponse({
        "targets": state.read_targets(),
        "status": state.status_map(),
        "readiness": deps.readiness(),
        "busy": [w for w in BY_ID if runner.is_busy(w)],
    })


@app.post("/api/targets")
async def api_save_target(request: Request):
    body = await request.json()
    workload = (body.get("workload") or "").strip()
    if workload not in BY_ID:
        return JSONResponse({"error": f"Unknown workload '{workload}'."}, status_code=400)
    state.save_target(workload, body.get("values") or {})
    return JSONResponse({"workload": workload, "saved": True})


# ── planning and running ─────────────────────────────────────────────────────

def _resolve(workload_id: str, values: dict) -> tuple[dict | None, JSONResponse | None]:
    wl = BY_ID.get(workload_id)
    if not wl:
        return None, JSONResponse({"error": f"Unknown workload '{workload_id}'."}, status_code=400)
    try:
        return plan(wl.action, values), None
    except PlanError as e:
        return None, JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/preview")
async def api_preview(request: Request):
    """Compute the plan for a configuration.

    Returns 200 even when the configuration is not yet valid. The console calls
    this as the operator types, and "you have not finished filling this in" is a
    legitimate answer to a well-formed question — not a protocol error. Reserving
    4xx for genuine problems keeps the browser console and any error monitoring
    meaningful.
    """
    body = await request.json()
    workload_id = (body.get("workload") or "").strip()
    wl = BY_ID.get(workload_id)
    if not wl:
        return JSONResponse({"error": f"Unknown workload '{workload_id}'."}, status_code=400)

    try:
        resolved = plan(wl.action, body.get("values") or {})
    except PlanError as e:
        return JSONResponse({"workload": workload_id, "valid": False, "error": str(e),
                             "inventory": [], "steps": [], "needsCert": False,
                             "destructive": wl.destructive})

    done = state.steps_done(workload_id)
    return JSONResponse({
        "workload": workload_id,
        "valid": True,
        "error": None,
        "inventory": [{"group": g, "hosts": h} for g, h in resolved["inventory"].items()],
        "steps": [{
            "label": s["label"],
            "playbook": s["playbook"],
            "exists": os.path.exists(os.path.join(BASE_DIR, s["playbook"])),
            "always": bool(s.get("always")),
            "status": done.get(s["label"], "pending"),
        } for s in resolved["steps"]],
        "needsCert": bool(resolved.get("needs_cert")),
        "destructive": wl.destructive,
    })


@app.post("/api/run")
async def api_run(request: Request):
    body = await request.json()
    workload_id = (body.get("workload") or "").strip()
    values = body.get("values") or {}
    wl = BY_ID.get(workload_id)
    if not wl:
        return JSONResponse({"error": f"Unknown workload '{workload_id}'."}, status_code=400)

    # Destructive workloads require the operator to retype their target. Enforced
    # here rather than only in the browser, so a direct API call cannot skip it.
    if wl.destructive:
        expected = (values.get(wl.confirm_field) or "").strip()
        supplied = (body.get("confirm") or "").strip()
        if not expected:
            return JSONResponse(
                {"error": f"{wl.confirm_field} must be set before this can be confirmed."},
                status_code=400)
        if supplied != expected:
            return JSONResponse(
                {"error": f"Type '{expected}' to confirm. This workload destroys state."},
                status_code=400)

    if runner.is_busy(workload_id):
        return JSONResponse({"error": "This workload is already running."}, status_code=409)

    _, err = _resolve(workload_id, values)     # validate before queueing
    if err:
        return err

    state.save_target(workload_id, values)
    run_id = runner.start(workload_id, {**values,
                                        "ssh_user": body.get("ssh_user", "autoprovision"),
                                        "ssh_pass": body.get("ssh_pass", ""),
                                        "force": bool(body.get("force"))})
    return JSONResponse({"runId": run_id, "workload": workload_id, "status": "queued"})


@app.post("/api/run-ready")
async def api_run_ready(request: Request):
    """Start every workload that is configured, unblocked and not destructive."""
    body = await request.json()
    values_by_workload = state.read_targets()
    for wid, vals in (body.get("values") or {}).items():
        values_by_workload.setdefault(wid, {}).update(vals or {})

    started, skipped = [], []
    for wid in deps.bulk_runnable(values_by_workload):
        if runner.is_busy(wid):
            skipped.append({"workload": wid, "reason": "already running"})
            continue
        vals = values_by_workload.get(wid, {})
        try:
            plan(BY_ID[wid].action, vals)
        except PlanError as e:
            skipped.append({"workload": wid, "reason": str(e)})
            continue
        started.append({
            "workload": wid,
            "runId": runner.start(wid, {**vals,
                                        "ssh_user": body.get("ssh_user", "autoprovision"),
                                        "ssh_pass": body.get("ssh_pass", ""),
                                        "force": False}),
        })
    return JSONResponse({
        "started": started,
        "skipped": skipped,
        "excludedDestructive": sorted(DESTRUCTIVE),
    })


@app.get("/api/job/{run_id}")
async def api_job(run_id: str):
    job = runner.job_view(run_id)
    if not job:
        return JSONResponse({"error": "Run not found."}, status_code=404)
    return JSONResponse({**job, "log": runner.read_log(job["workload"])})


@app.post("/api/reset")
async def api_reset(request: Request):
    body = await request.json()
    workload_id = (body.get("workload") or "").strip()
    if workload_id not in BY_ID:
        return JSONResponse({"error": f"Unknown workload '{workload_id}'."}, status_code=400)
    return JSONResponse({"workload": workload_id, "cleared": state.reset_workload(workload_id)})


# ── logs ─────────────────────────────────────────────────────────────────────

@app.get("/api/log/{workload_id}", response_class=PlainTextResponse)
async def api_log(workload_id: str):
    if workload_id not in BY_ID:
        return PlainTextResponse("Unknown workload.", status_code=400)
    return PlainTextResponse(runner.read_log(workload_id))


@app.get("/api/stream/{workload_id}")
async def api_stream(workload_id: str):
    """Server-sent events carrying only what is new.

    The previous console re-sent the whole log every 1.5 seconds; with six parallel
    runs that was megabytes a second of the same bytes.
    """
    if workload_id not in BY_ID:
        return JSONResponse({"error": "Unknown workload."}, status_code=400)

    async def gen():
        offset = 0
        idle = 0
        while idle < 900:          # ~30 minutes of silence, then the client reconnects
            path = runner.log_path(workload_id)
            size = os.path.getsize(path) if os.path.exists(path) else 0
            if size < offset:      # log was truncated by a new run
                offset = 0
                yield "event: reset\ndata: \n\n"
            if size > offset:
                with open(path, encoding="utf-8", errors="replace") as f:
                    f.seek(offset)
                    chunk = f.read()
                offset = size
                idle = 0
                for line in chunk.splitlines():
                    yield f"data: {line}\n\n"
            else:
                idle += 1
            busy = runner.is_busy(workload_id)
            yield f"event: status\ndata: {'running' if busy else 'idle'}\n\n"
            if not busy and offset > 0 and idle > 2:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive",
    })


@app.get("/api/runs")
async def api_runs():
    return JSONResponse(state.recent_runs())


# ── topology ─────────────────────────────────────────────────────────────────

@app.get("/api/topology")
async def api_topology():
    """Every machine this control plane is managing, derived from configuration.

    At fifty machines nobody holds the estate in their head, and nothing else can
    answer "what am I actually managing?" — inventories are per-run and Ansible
    keeps no memory between them.
    """
    return JSONResponse({**topology.survey(),
                         "orphanedEnvironments": topology.unknown_environments()})


@app.get("/api/topology/inventory", response_class=PlainTextResponse)
async def api_topology_inventory():
    return PlainTextResponse(topology.as_inventory(),
                             headers={"Content-Disposition": "attachment; filename=estate.ini"})


# ── documentation ────────────────────────────────────────────────────────────

@app.get("/api/content/{slug}/{page}", response_class=PlainTextResponse)
async def api_content(slug: str, page: str):
    body = content.read(slug, page)
    if body is None:
        return PlainTextResponse(
            f"No {page} document has been written for this workload yet.\n\n"
            f"Add `content/{slug}/{page}.md` and it appears here.",
            status_code=200)
    return PlainTextResponse(body)


@app.get("/api/handbook")
async def api_handbook():
    return JSONResponse(content.handbook())


# ── console ──────────────────────────────────────────────────────────────────

if os.path.isdir(os.path.join(DIST_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    """Serve the built console, falling back to index.html so client routing works."""
    # An unmatched API path is a mistake, not a client route. Returning the console
    # HTML would let a typo look like a working request that returned odd data.
    if full_path.startswith("api/"):
        return JSONResponse({"error": f"No such endpoint: /{full_path}"}, status_code=404)

    index = os.path.join(DIST_DIR, "index.html")
    if not os.path.exists(index):
        return PlainTextResponse(
            "The console has not been built.\n\n"
            "  cd console && npm ci && npm run build\n\n"
            "The build writes to app/dist/, which is committed so the jump host needs "
            "neither Node nor internet access.", status_code=503)
    candidate = os.path.normpath(os.path.join(DIST_DIR, full_path))
    if full_path and candidate.startswith(DIST_DIR) and os.path.isfile(candidate):
        return FileResponse(candidate)
    return FileResponse(index)
