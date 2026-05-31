from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
INVENTORY_FILE = os.path.join(ANSIBLE_DIR, "inventory")
STATE_DB = os.path.join(BASE_DIR, "data", "state.db")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
TRAEFIK_CERTS_DIR = os.path.join(BASE_DIR, "docker", "traefik", "certs")
TRAEFIK_CERT_FILE = os.path.join(TRAEFIK_CERTS_DIR, "local-dev-tls.crt")
TRAEFIK_KEY_FILE = os.path.join(TRAEFIK_CERTS_DIR, "local-dev-tls.key")

app = FastAPI(title="Autoprovision Control Plane", version="0.7.0")
JOBS: dict[str, dict] = {}

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
                gitlab_domain TEXT NOT NULL DEFAULT '',
                gitlab_registry_domain TEXT NOT NULL DEFAULT '',
                sonarqube_domain TEXT NOT NULL DEFAULT '',
                talos_cluster_name TEXT NOT NULL DEFAULT '',
                talos_control_plane_ips TEXT NOT NULL DEFAULT '',
                talos_worker_ips TEXT NOT NULL DEFAULT '',
                talos_install_disk TEXT NOT NULL DEFAULT 'sda',
                updated_at TEXT NOT NULL
            )
            """
        )
        # Backward-compatible schema upgrades for existing DBs.
        cols = {
            row[1] for row in conn.execute("PRAGMA table_info(ui_state)").fetchall()
        }
        if "gitlab_domain" not in cols:
            conn.execute("ALTER TABLE ui_state ADD COLUMN gitlab_domain TEXT NOT NULL DEFAULT ''")
        if "gitlab_registry_domain" not in cols:
            conn.execute("ALTER TABLE ui_state ADD COLUMN gitlab_registry_domain TEXT NOT NULL DEFAULT ''")
        if "sonarqube_domain" not in cols:
            conn.execute("ALTER TABLE ui_state ADD COLUMN sonarqube_domain TEXT NOT NULL DEFAULT ''")
        if "talos_cluster_name" not in cols:
            conn.execute("ALTER TABLE ui_state ADD COLUMN talos_cluster_name TEXT NOT NULL DEFAULT ''")
        if "talos_control_plane_ips" not in cols:
            conn.execute("ALTER TABLE ui_state ADD COLUMN talos_control_plane_ips TEXT NOT NULL DEFAULT ''")
        if "talos_worker_ips" not in cols:
            conn.execute("ALTER TABLE ui_state ADD COLUMN talos_worker_ips TEXT NOT NULL DEFAULT ''")
        if "talos_install_disk" not in cols:
            conn.execute("ALTER TABLE ui_state ADD COLUMN talos_install_disk TEXT NOT NULL DEFAULT 'sda'")
        conn.execute(
            """
            INSERT INTO ui_state (
                id, env, docker_ip, ssh_user, dockhand_domain, kibana_domain,
                gitlab_domain, gitlab_registry_domain, sonarqube_domain,
                talos_cluster_name, talos_control_plane_ips, talos_worker_ips, talos_install_disk,
                updated_at
            )
            SELECT 1, 'lab', '', 'autoprovision',
                   'dockhand.example.com', 'kibana.example.com',
                   'gitlab.example.com', 'registry.example.com', 'sonar.example.com',
                   'lab-cluster', '', '', 'sda',
                   ?
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
            """
            SELECT
                env, docker_ip, ssh_user, dockhand_domain, kibana_domain,
                gitlab_domain, gitlab_registry_domain, sonarqube_domain,
                talos_cluster_name, talos_control_plane_ips, talos_worker_ips, talos_install_disk,
                updated_at
            FROM ui_state
            WHERE id = 1
            """
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {
            "env": "lab",
            "docker_ip": "",
            "ssh_user": "autoprovision",
            "dockhand_domain": "dockhand.example.com",
            "kibana_domain": "kibana.example.com",
            "gitlab_domain": "gitlab.example.com",
            "gitlab_registry_domain": "registry.example.com",
            "sonarqube_domain": "sonar.example.com",
            "talos_cluster_name": "lab-cluster",
            "talos_control_plane_ips": "",
            "talos_worker_ips": "",
            "talos_install_disk": "sda",
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
    dockhand_domain = (data.get("dockhand_domain") or "dockhand.example.com").strip()
    kibana_domain = (data.get("kibana_domain") or "kibana.example.com").strip()
    gitlab_domain = (data.get("gitlab_domain") or "gitlab.example.com").strip()
    gitlab_registry_domain = (data.get("gitlab_registry_domain") or "registry.example.com").strip()
    sonarqube_domain = (data.get("sonarqube_domain") or "sonar.example.com").strip()
    talos_cluster_name = (data.get("talos_cluster_name") or "lab-cluster").strip() or "lab-cluster"
    talos_control_plane_ips = (data.get("talos_control_plane_ips") or "").strip()
    talos_worker_ips = (data.get("talos_worker_ips") or "").strip()
    talos_install_disk = (data.get("talos_install_disk") or "sda").strip() or "sda"
    updated_at = _utc_now()

    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            UPDATE ui_state
            SET env = ?, docker_ip = ?, ssh_user = ?, dockhand_domain = ?, kibana_domain = ?,
                gitlab_domain = ?, gitlab_registry_domain = ?, sonarqube_domain = ?,
                talos_cluster_name = ?, talos_control_plane_ips = ?, talos_worker_ips = ?, talos_install_disk = ?,
                updated_at = ?
            WHERE id = 1
            """,
            (
                env,
                docker_ip,
                ssh_user,
                dockhand_domain,
                kibana_domain,
                gitlab_domain,
                gitlab_registry_domain,
                sonarqube_domain,
                talos_cluster_name,
                talos_control_plane_ips,
                talos_worker_ips,
                talos_install_disk,
                updated_at,
            ),
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
        "gitlab_domain": gitlab_domain,
        "gitlab_registry_domain": gitlab_registry_domain,
        "sonarqube_domain": sonarqube_domain,
        "talos_cluster_name": talos_cluster_name,
        "talos_control_plane_ips": talos_control_plane_ips,
        "talos_worker_ips": talos_worker_ips,
        "talos_install_disk": talos_install_disk,
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


async def _run_script(script_rel: str, log_name: str, env_vars: dict = None) -> int:
    log_path = os.path.join(BASE_DIR, "data", "logs", log_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    cmd = ["bash", os.path.join(BASE_DIR, script_rel)]
    run_env = os.environ.copy()
    if env_vars:
        for k, v in env_vars.items():
            run_env[k] = "" if v is None else str(v)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=BASE_DIR,
        env=run_env,
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


def _read_log_tail(name: str, max_chars: int = 60000) -> str:
    content = _read_log(name)
    if len(content) <= max_chars:
        return content
    return content[-max_chars:]


def _action_plan(action: str, body: dict) -> dict:
    if action == "bootstrap-docker":
        return {
            "runner": "playbook",
            "playbook": "ansible/docker_vm_base.yml",
            "log_name": "docker-base.log",
            "extra_vars": None,
        }
    if action == "platform-up":
        return {
            "runner": "playbook",
            "playbook": "ansible/docker_platform_up.yml",
            "log_name": "docker-platform.log",
            "extra_vars": {"dockhand_domain": body.get("dockhand_domain", "dockhand.example.com")},
        }
    if action == "elk-up":
        return {
            "runner": "playbook",
            "playbook": "ansible/elk_stack.yml",
            "log_name": "elk.log",
            "extra_vars": {"kibana_domain": body.get("kibana_domain", "kibana.example.com")},
        }
    if action == "gitlab-up":
        return {
            "runner": "playbook",
            "playbook": "ansible/gitlab_stack.yml",
            "log_name": "gitlab.log",
            "extra_vars": {
                "gitlab_domain": body.get("gitlab_domain", "gitlab.example.com"),
                "gitlab_registry_domain": body.get("gitlab_registry_domain", "registry.example.com"),
                "gitlab_runner_token": body.get("gitlab_runner_token", ""),
            },
        }
    if action == "sonarqube-up":
        return {
            "runner": "playbook",
            "playbook": "ansible/sonarqube_stack.yml",
            "log_name": "sonarqube.log",
            "extra_vars": {"sonarqube_domain": body.get("sonarqube_domain", "sonar.example.com")},
        }
    if action == "create-talos-cluster":
        return {
            "runner": "script",
            "script": "scripts/talos_cluster_create.sh",
            "log_name": "k8s-talos-create.log",
            "extra_vars": {
                "TALOS_CLUSTER_NAME": body.get("talos_cluster_name", "lab-cluster"),
                "TALOS_CONTROL_PLANE_IPS": body.get("talos_control_plane_ips", ""),
                "TALOS_WORKER_IPS": body.get("talos_worker_ips", ""),
                "TALOS_INSTALL_DISK": body.get("talos_install_disk", "sda"),
            },
            "preview": "Create Talos configs, apply control-plane and worker config, bootstrap cluster, fetch kubeconfig, and install Cilium.",
        }
    if action == "add-talos-workers":
        return {
            "runner": "script",
            "script": "scripts/talos_add_workers.sh",
            "log_name": "k8s-talos-workers.log",
            "extra_vars": {
                "TALOS_CLUSTER_NAME": body.get("talos_cluster_name", "lab-cluster"),
                "TALOS_WORKER_IPS": body.get("talos_worker_ips", ""),
            },
            "preview": "Apply Talos worker config to listed worker nodes and verify cluster node list.",
        }
    if action == "install-k8s-platform":
        return {
            "runner": "script",
            "script": "scripts/k8s_platform_install.sh",
            "log_name": "k8s-platform.log",
            "extra_vars": {
                "TALOS_CLUSTER_NAME": body.get("talos_cluster_name", "lab-cluster"),
            },
            "preview": "Install cert-manager, Envoy Gateway, ArgoCD, and Headlamp via Helm.",
        }
    raise ValueError(f"unsupported action: {action}")


def _get_playbook_task_list(playbook_rel: str) -> str:
    cmd = [
        "ansible-playbook",
        "-i",
        INVENTORY_FILE,
        os.path.join(BASE_DIR, playbook_rel),
        "--list-tasks",
    ]
    try:
        p = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, check=False)
    except Exception as e:
        return f"Could not render task list: {e}"
    output = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
    return output.strip() or "No tasks found."


async def _run_action_job(job_id: str, action: str, body: dict):
    try:
        plan = _action_plan(action, body)
        _save_ui_state(body)
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["log_name"] = plan["log_name"]

        if plan.get("runner") == "playbook":
            env = body.get("env", "lab")
            docker_ip = body.get("docker_ip", "")
            ssh_user = body.get("ssh_user", "autoprovision")
            ssh_pass = body.get("ssh_pass", "")
            if not docker_ip:
                raise ValueError("docker_ip required")
            _write_inventory(env, docker_ip, ssh_user, ssh_pass)
            rc = await _run_playbook(plan["playbook"], plan["log_name"], extra_vars=plan["extra_vars"])
        else:
            rc = await _run_script(plan["script"], plan["log_name"], env_vars=plan.get("extra_vars"))

        JOBS[job_id]["rc"] = rc
        JOBS[job_id]["status"] = "completed" if rc == 0 else "failed"
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)


def _ensure_traefik_certs_dir() -> None:
    os.makedirs(TRAEFIK_CERTS_DIR, exist_ok=True)


def _build_san(domains: list[str]) -> str:
    return ",".join(f"DNS:{d}" for d in domains if d)


def _generate_self_signed_cert(domains: list[str]) -> None:
    _ensure_traefik_certs_dir()
    primary = domains[0] if domains else "localhost"
    san = _build_san(domains) or f"DNS:{primary}"
    cmd = [
        "openssl",
        "req",
        "-x509",
        "-nodes",
        "-newkey",
        "rsa:2048",
        "-sha256",
        "-days",
        "365",
        "-subj",
        f"/CN={primary}",
        "-addext",
        f"subjectAltName={san}",
        "-keyout",
        TRAEFIK_KEY_FILE,
        "-out",
        TRAEFIK_CERT_FILE,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _write_provided_cert(cert_pem: str, key_pem: str) -> None:
    _ensure_traefik_certs_dir()
    with open(TRAEFIK_CERT_FILE, "w", encoding="utf-8") as f:
        f.write(cert_pem.strip() + "\n")
    with open(TRAEFIK_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key_pem.strip() + "\n")


@app.post("/tls/configure")
async def configure_tls(request: Request):
    body = await request.json()
    cert_pem = (body.get("cert_pem") or "").strip()
    key_pem = (body.get("key_pem") or "").strip()
    domains = [
        (body.get("dockhand_domain") or "dockhand.example.com").strip(),
        (body.get("kibana_domain") or "kibana.example.com").strip(),
        (body.get("gitlab_domain") or "gitlab.example.com").strip(),
        (body.get("sonarqube_domain") or "sonar.example.com").strip(),
        (body.get("gitlab_registry_domain") or "registry.example.com").strip(),
    ]

    try:
        if cert_pem and key_pem:
            _write_provided_cert(cert_pem, key_pem)
            mode = "provided"
            message = "TLS certificate and key saved for Traefik. Re-run Platform Stack to apply."
        else:
            _generate_self_signed_cert(domains)
            mode = "self-signed"
            message = "Self-signed TLS certificate generated for current domains. Re-run Platform Stack to apply."
    except subprocess.CalledProcessError as e:
        return JSONResponse(
            {
                "error": "openssl_failed",
                "details": e.stderr or e.stdout or str(e),
            },
            status_code=500,
        )
    except FileNotFoundError:
        return JSONResponse(
            {
                "error": "openssl_not_found",
                "details": "OpenSSL is not installed on this machine.",
            },
            status_code=500,
        )

    return JSONResponse(
        {
            "mode": mode,
            "message": message,
            "dns_note": "If you use custom public domains with Let's Encrypt, ensure DNS records point to this Docker VM before requesting ACME certificates.",
        }
    )


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


@app.post("/actions/gitlab-plan")
async def gitlab_plan(request: Request):
    body = await request.json()
    _save_ui_state(body)
    plan_text = _get_playbook_task_list("ansible/gitlab_stack.yml")
    return JSONResponse(
        {
            "plan": plan_text,
            "last_log": _read_log_tail("gitlab.log", 25000),
            "message": "Preview only. Click Deploy GitLab Stack to start deployment.",
        }
    )


@app.post("/actions/preview")
async def action_preview(request: Request):
    body = await request.json()
    action = (body.get("action") or "").strip()
    payload = body.get("payload") or {}

    try:
        plan = _action_plan(action, payload)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    _save_ui_state(payload)
    if plan.get("runner") == "playbook":
        plan_text = _get_playbook_task_list(plan["playbook"])
    else:
        plan_text = plan.get("preview", "Script-based action")
    return JSONResponse(
        {
            "action": action,
            "plan": plan_text,
            "last_log": _read_log_tail(plan["log_name"], 30000),
            "message": "Preview only. Click Deploy to start this action.",
        }
    )


@app.post("/actions/start")
async def start_action(request: Request):
    body = await request.json()
    action = (body.get("action") or "").strip()
    payload = body.get("payload") or {}

    try:
        _action_plan(action, payload)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "action": action,
        "status": "queued",
        "rc": None,
        "error": None,
        "log_name": None,
        "started_at": _utc_now(),
    }
    JOBS[job_id]["task"] = asyncio.create_task(_run_action_job(job_id, action, payload))
    return JSONResponse({"job_id": job_id, "status": "queued"})


@app.get("/actions/job/{job_id}")
async def get_action_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "job_not_found"}, status_code=404)
    log = _read_log_tail(job["log_name"], 60000) if job.get("log_name") else ""
    return JSONResponse(
        {
            "job_id": job_id,
            "action": job.get("action"),
            "status": job.get("status"),
            "rc": job.get("rc"),
            "error": job.get("error"),
            "log": log,
        }
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    ui_file = os.path.join(BASE_DIR, "app", "ui_docker.html")
    with open(ui_file, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/docker", response_class=HTMLResponse)
async def docker_page():
    ui_file = os.path.join(BASE_DIR, "app", "ui_docker.html")
    with open(ui_file, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/k8s", response_class=HTMLResponse)
async def k8s_page():
    ui_file = os.path.join(BASE_DIR, "app", "ui_k8s.html")
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
    dockhand_domain = body.get("dockhand_domain", "dockhand.example.com")
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
    kibana_domain = body.get("kibana_domain", "kibana.example.com")
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


@app.post("/actions/gitlab-up")
async def action_gitlab_up(request: Request):
    body = await request.json()
    env = body.get("env", "lab")
    docker_ip = body.get("docker_ip", "")
    ssh_user = body.get("ssh_user", "autoprovision")
    ssh_pass = body.get("ssh_pass", "")
    gitlab_domain = body.get("gitlab_domain", "gitlab.example.com")
    gitlab_registry_domain = body.get("gitlab_registry_domain", "registry.example.com")
    gitlab_runner_token = body.get("gitlab_runner_token", "")
    _save_ui_state(body)
    if not docker_ip:
        return JSONResponse({"error": "docker_ip required"}, status_code=400)
    _write_inventory(env, docker_ip, ssh_user, ssh_pass)
    rc = await _run_playbook(
        "ansible/gitlab_stack.yml",
        "gitlab.log",
        extra_vars={
            "gitlab_domain": gitlab_domain,
            "gitlab_registry_domain": gitlab_registry_domain,
            "gitlab_runner_token": gitlab_runner_token,
        },
    )
    log = _read_log("gitlab.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/sonarqube-up")
async def action_sonarqube_up(request: Request):
    body = await request.json()
    env = body.get("env", "lab")
    docker_ip = body.get("docker_ip", "")
    ssh_user = body.get("ssh_user", "autoprovision")
    ssh_pass = body.get("ssh_pass", "")
    sonarqube_domain = body.get("sonarqube_domain", "sonar.example.com")
    _save_ui_state(body)
    if not docker_ip:
        return JSONResponse({"error": "docker_ip required"}, status_code=400)
    _write_inventory(env, docker_ip, ssh_user, ssh_pass)
    rc = await _run_playbook(
        "ansible/sonarqube_stack.yml",
        "sonarqube.log",
        extra_vars={"sonarqube_domain": sonarqube_domain},
    )
    log = _read_log("sonarqube.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/create-talos-cluster")
async def action_create_talos(request: Request):
    body = await request.json()
    _save_ui_state(body)
    rc = await _run_script(
        "scripts/talos_cluster_create.sh",
        "k8s-talos-create.log",
        env_vars={
            "TALOS_CLUSTER_NAME": body.get("talos_cluster_name", "lab-cluster"),
            "TALOS_CONTROL_PLANE_IPS": body.get("talos_control_plane_ips", ""),
            "TALOS_WORKER_IPS": body.get("talos_worker_ips", ""),
            "TALOS_INSTALL_DISK": body.get("talos_install_disk", "sda"),
        },
    )
    log = _read_log("k8s-talos-create.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/install-k8s-platform")
async def action_k8s_platform(request: Request):
    body = await request.json()
    _save_ui_state(body)
    rc = await _run_script(
        "scripts/k8s_platform_install.sh",
        "k8s-platform.log",
        env_vars={
            "TALOS_CLUSTER_NAME": body.get("talos_cluster_name", "lab-cluster"),
        },
    )
    log = _read_log("k8s-platform.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/add-talos-workers")
async def action_add_talos_workers(request: Request):
    body = await request.json()
    _save_ui_state(body)
    rc = await _run_script(
        "scripts/talos_add_workers.sh",
        "k8s-talos-workers.log",
        env_vars={
            "TALOS_CLUSTER_NAME": body.get("talos_cluster_name", "lab-cluster"),
            "TALOS_WORKER_IPS": body.get("talos_worker_ips", ""),
        },
    )
    log = _read_log("k8s-talos-workers.log")
    return JSONResponse({"rc": rc, "log": log})


@app.post("/actions/deploy-wso2")
async def action_deploy_wso2():
    return JSONResponse({"action": "deploy-wso2", "status": "not_implemented"})


@app.post("/actions/run-migration")
async def action_run_migration():
    return JSONResponse({"action": "run-migration", "status": "not_implemented"})
