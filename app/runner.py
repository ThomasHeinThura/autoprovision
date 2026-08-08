"""Job execution — writes a per-run inventory, runs each playbook step, streams output.

Each run gets its own inventory file and appends to a per-workload log, so several
workloads running at once never collide on either.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from . import state
from .planner import PlanError, plan
from .workloads import BY_ID

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVENTORY_DIR = os.path.join(BASE_DIR, "data", "inventory")
LOG_DIR = os.path.join(BASE_DIR, "data", "logs")
CERTS_DIR = os.path.join(BASE_DIR, "data", "certs")

JOBS: dict[str, dict] = {}


def log_path(workload: str) -> str:
    return os.path.join(LOG_DIR, f"workload-{workload}.log")


def read_log(workload: str, max_chars: int = 400_000) -> str:
    p = log_path(workload)
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as f:
        content = f.read()
    return content if len(content) <= max_chars else content[-max_chars:]


def _append(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def write_inventory(run_id: str, groups: dict[str, list[str]],
                    ssh_user: str, ssh_pass: str) -> str:
    os.makedirs(INVENTORY_DIR, exist_ok=True)
    path = os.path.join(INVENTORY_DIR, f"{run_id}.ini")
    user = ssh_user or "autoprovision"
    with open(path, "w", encoding="utf-8") as f:
        for group, hosts in groups.items():
            f.write(f"[{group}]\n")
            for host in hosts:
                line = f"{host} ansible_user={user}"
                if ssh_pass:
                    line += f" ansible_password={ssh_pass} ansible_become_password={ssh_pass}"
                f.write(line + " ansible_become=true ansible_become_method=sudo\n")
            f.write("\n")
    os.chmod(path, 0o600)   # holds ansible_password when keys are not in use
    return path


def stage_cert(workload: str, cert_pem: str, key_pem: str) -> None:
    if not (cert_pem or "").strip() or not (key_pem or "").strip():
        raise PlanError("Both the certificate and the private key are required.")
    d = os.path.join(CERTS_DIR, workload)
    os.makedirs(d, exist_ok=True)
    crt, key = os.path.join(d, "tls.crt"), os.path.join(d, "tls.key")
    with open(crt, "w", encoding="utf-8") as f:
        f.write(cert_pem.strip() + "\n")
    with open(key, "w", encoding="utf-8") as f:
        f.write(key_pem.strip() + "\n")
    os.chmod(key, 0o600)


async def run_step(playbook_rel: str, inventory: str, log: str,
                   extra_vars: dict | None) -> int:
    playbook = os.path.join(BASE_DIR, playbook_rel)
    if not os.path.exists(playbook):
        _append(log, f"\n✗ {playbook_rel} does not exist yet.\n"
                     f"  This engine or stack is declared in the registry but its playbook has "
                     f"not been written.\n")
        return 2
    cmd = ["ansible-playbook", "-i", inventory, playbook]
    if extra_vars:
        cmd += ["--extra-vars", json.dumps(extra_vars)]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=BASE_DIR,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    with open(log, "a", encoding="utf-8") as lf:
        lf.write(f"\n===== ansible-playbook {playbook_rel} =====\n")
        lf.flush()
        async for chunk in proc.stdout:
            lf.write(chunk.decode("utf-8", errors="replace"))
            lf.flush()
    await proc.wait()
    return proc.returncode


async def execute(run_id: str, workload_id: str, body: dict) -> None:
    job = JOBS[run_id]
    wl = BY_ID[workload_id]
    force = bool(body.get("force"))
    log = log_path(workload_id)
    started = time.monotonic()

    os.makedirs(LOG_DIR, exist_ok=True)
    with open(log, "w", encoding="utf-8") as f:
        f.write(f"===== {wl.title} · {wl.action}"
                f"{'  [force: re-run every step]' if force else ''} =====\n"
                f"Completed steps are skipped unless Force is set.\n")

    try:
        resolved = plan(wl.action, body)
        job["status"] = "running"
        inventory = write_inventory(run_id, resolved["inventory"],
                                    body.get("ssh_user", "autoprovision"),
                                    body.get("ssh_pass", ""))
        job["inventory"] = inventory

        if resolved.get("needs_cert"):
            stage_cert(workload_id, body.get("cert_pem", ""), body.get("key_pem", ""))

        done = state.steps_done(workload_id)
        rc = 0
        for step in resolved["steps"]:
            label = step["label"]
            if not force and not step.get("always") and done.get(label) == "completed":
                _append(log, f"\n✓ Skipped — '{label}' is already installed. Use Force to re-run.\n")
                job["step"] = f"skipped: {label}"
                continue
            job["step"] = label
            _append(log, f"\n▶ {label}\n")
            rc = await run_step(step["playbook"], inventory, log, step.get("extra_vars"))
            state.set_step_status(workload_id, label, "completed" if rc == 0 else "failed")
            if rc != 0:
                break

        job["rc"] = rc
        job["status"] = "completed" if rc == 0 else "failed"
    except PlanError as e:
        job["status"] = "failed"
        job["error"] = str(e)
        _append(log, f"\n✗ {e}\n")
    except Exception as e:                                    # noqa: BLE001 — surfaced to the UI
        job["status"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"
        _append(log, f"\n✗ {type(e).__name__}: {e}\n")
    finally:
        job["finished"] = True
        state.run_finished(run_id, job["status"], time.monotonic() - started)


def start(workload_id: str, body: dict) -> str:
    wl = BY_ID[workload_id]
    run_id = str(uuid.uuid4())
    JOBS[run_id] = {
        "run_id": run_id, "workload": workload_id, "action": wl.action,
        "status": "queued", "rc": None, "error": None, "step": None,
        "started_at": state.utc_now(), "finished": False,
    }
    state.run_started(run_id, workload_id, wl.action)
    JOBS[run_id]["task"] = asyncio.create_task(execute(run_id, workload_id, body))
    return run_id


def job_view(run_id: str) -> dict | None:
    job = JOBS.get(run_id)
    if not job:
        return None
    return {k: v for k, v in job.items() if k != "task"}


def is_busy(workload_id: str) -> bool:
    return any(j["workload"] == workload_id and j["status"] in ("queued", "running")
               for j in JOBS.values())
