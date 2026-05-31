from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
INVENTORY_FILE = os.path.join(ANSIBLE_DIR, "inventory")
STATE_DB = os.path.join(BASE_DIR, "data", "state.db")

app = FastAPI(title="Autoprovision Control Plane", version="0.6.0")

# ─── helpers ──────────────────────────────────────────────────────────────────

def _env_to_group(env: str) -> str:
    m = {"lab": "docker_lab", "uat": "docker_uat", "prod": "docker_prod"}
    return m.get((env or "").lower(), "docker_lab")


def _ensure_state_db() -> None:
    os.makedirs(os.path.dirname(STATE_DB), exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                env TEXT NOT NULL DEFAULT 'lab',
                docker_ip TEXT NOT NULL DEFAULT '',
                ssh_user TEXT NOT NULL DEFAULT 'autoprovision',
                dockhand_domain TEXT NOT NULL DEFAULT '',
                kibana_domain TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO ui_state (id, env, docker_ip, ssh_user, dockhand_domain, kibana_domain, updated_at)
            SELECT 1, 'lab', '', 'autoprovision', '', '', ?
            WHERE NOT EXISTS (SELECT 1 FROM ui_state WHERE id = 1)
            """,
            (_utc_now(),),
        )
        conn.commit()
    finally:
        conn.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_ui_state() -> dict:
    _ensure_state_db()
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT env, docker_ip, ssh_user, dockhand_domain, kibana_domain, updated_at FROM ui_state WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {
            "env": "lab",
            "docker_ip": "",
            "ssh_user": "autoprovision",
            "dockhand_domain": "",
            "kibana_domain": "",
            "updated_at": None,
        }
    return dict(row)


def _save_ui_state(data: dict) -> dict:
    _ensure_state_db()
    env = (data.get("env") or "lab").lower()
    if env not in ("lab", "uat", "prod"):
        env = "lab"

    docker_ip = (data.get("docker_ip") or "").strip()
    ssh_user = (data.get("ssh_user") or "autoprovision").strip() or "autoprovision"
    dockhand_domain = (data.get("dockhand_domain") or "").strip()
    kibana_domain = (data.get("kibana_domain") or "").strip()
    updated_at = _utc_now()

    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            UPDATE ui_state
            SET env = ?, docker_ip = ?, ssh_user = ?, dockhand_domain = ?, kibana_domain = ?, updated_at = ?
            WHERE id = 1
            """,
            (env, docker_ip, ssh_user, dockhand_domain, kibana_domain, updated_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "env": env,
        "docker_ip": docker_ip,
        "ssh_user": ssh_user,
        "dockhand_domain": dockhand_domain,
        "kibana_domain": kibana_domain,
        "updated_at": updated_at,
    }


def _read_inventory_defaults():
    """Best-effort parse of last inventory to prefill form.

    Returns (env, docker_ip, ssh_user) or ("lab", "", "autoprovision") if not found.
    """
    env = "lab"
    docker_ip = ""
    ssh_user = "autoprovision"
    if not os.path.exists(INVENTORY_FILE):
        return env, docker_ip, ssh_user
    try:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        # First non-header line under [docker_vm]
        group = None
        for line in lines:
            if line.startswith("[") and line.endswith("]"):
                group = line.strip("[]")
                continue
            if group == "docker_vm" and not line.startswith("["):
                parts = line.split()
                if parts:
                    docker_ip = parts[0]
                for p in parts[1:]:
                    if p.startswith("ansible_user="):
                        ssh_user = p.split("=", 1)[1]
                break
        # Find env group
        for line in lines:
            if line.startswith("[") and line.endswith("]"):
                name = line.strip("[]")
                if name in ("docker_lab", "docker_uat", "docker_prod"):
                    if "lab" in name:
                        env = "lab"
                    elif "uat" in name:
                        env = "uat"
                    elif "prod" in name:
                        env = "prod"
                    break
    except Exception:
        pass
    return env, docker_ip, ssh_user


def _write_inventory(env: str, docker_ip: str, ssh_user: str, ssh_pass: str) -> None:
    group = _env_to_group(env)
    os.makedirs(ANSIBLE_DIR, exist_ok=True)
    with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
        f.write(f"[docker_vm]\n")
        line = f"{docker_ip} ansible_user={ssh_user}"
        if ssh_pass:
            line += f" ansible_password={ssh_pass} ansible_become_password={ssh_pass}"
        line += " ansible_become=true ansible_become_method=sudo\n"
        f.write(line)
        f.write(f"\n[{group}]\n")
        f.write(f"{docker_ip}\n")


async def _run_playbook(playbook_rel: str, log_name: str, extra_vars: dict = None) -> int:
    log_path = os.path.join(BASE_DIR, "data", "logs", log_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = [
        "ansible-playbook",
        "-i", INVENTORY_FILE,
        os.path.join(BASE_DIR, playbook_rel),
    ]
    if extra_vars:
        import json
        cmd += ["--extra-vars", json.dumps(extra_vars)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=BASE_DIR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    with open(log_path, "w", encoding="utf-8") as lf:
        async for chunk in proc.stdout:
            lf.write(chunk.decode("utf-8", errors="replace"))
    await proc.wait()
    return proc.returncode


def _read_log(name: str) -> str:
    p = os.path.join(BASE_DIR, "data", "logs", name)
    if not os.path.exists(p):
        return "No log yet."
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


# ─── routes ───────────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/state/ui")
async def get_ui_state():
    return JSONResponse(_read_ui_state())


@app.post("/state/ui")
async def save_ui_state(request: Request):
    body = await request.json()
    return JSONResponse(_save_ui_state(body))


@app.get("/", response_class=HTMLResponse)
async def index():
    ui_file = os.path.join(BASE_DIR, "app", "ui_preview.html")
    with open(ui_file, "r", encoding="utf-8") as f:
        return f.read()


@app.post("/actions/bootstrap-docker")
async def action_bootstrap_docker(request: Request):
    body = await request.json()
    env      = body.get("env", "lab")
    docker_ip = body.get("docker_ip", "")
    ssh_user  = body.get("ssh_user", "autoprovision")
    ssh_pass  = body.get("ssh_pass", "")
    _save_ui_state(body)
    if not docker_ip:
        return JSONResponse({"error": "docker_ip required"}, status_code=400)
    _write_inventory(env, docker_ip, ssh_user, ssh_pass)
    rc = await _run_playbook("ansible/docker_vm_base.yml", "docker-base.log")
    log = _read_log("docker-base.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/platform-up")
async def action_platform_up(request: Request):
    body = await request.json()
    env      = body.get("env", "lab")
    docker_ip = body.get("docker_ip", "")
    ssh_user  = body.get("ssh_user", "autoprovision")
    ssh_pass  = body.get("ssh_pass", "")
    dockhand_domain = body.get("dockhand_domain", "dockhand.local")
    _save_ui_state(body)
    if not docker_ip:
        return JSONResponse({"error": "docker_ip required"}, status_code=400)
    _write_inventory(env, docker_ip, ssh_user, ssh_pass)
    rc = await _run_playbook(
        "ansible/docker_platform_up.yml",
        "docker-platform.log",
        extra_vars={"dockhand_domain": dockhand_domain},
    )
    log = _read_log("docker-platform.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/elk-up")
async def action_elk_up(request: Request):
    body = await request.json()
    env      = body.get("env", "lab")
    docker_ip = body.get("docker_ip", "")
    ssh_user  = body.get("ssh_user", "autoprovision")
    ssh_pass  = body.get("ssh_pass", "")
    kibana_domain = body.get("kibana_domain", "kibana.local")
    _save_ui_state(body)
    if not docker_ip:
        return JSONResponse({"error": "docker_ip required"}, status_code=400)
    _write_inventory(env, docker_ip, ssh_user, ssh_pass)
    rc = await _run_playbook(
        "ansible/elk_stack.yml",
        "elk.log",
        extra_vars={"kibana_domain": kibana_domain},
    )
    log = _read_log("elk.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/create-talos-cluster")
async def action_create_talos():
    return JSONResponse({"action": "create-talos-cluster", "status": "not_implemented"})


@app.post("/actions/install-k8s-platform")
async def action_k8s_platform():
    return JSONResponse({"action": "install-k8s-platform", "status": "not_implemented"})


@app.post("/actions/deploy-wso2")
async def action_deploy_wso2():
    return JSONResponse({"action": "deploy-wso2", "status": "not_implemented"})


@app.post("/actions/run-migration")
async def action_run_migration():
    return JSONResponse({"action": "run-migration", "status": "not_implemented"})
