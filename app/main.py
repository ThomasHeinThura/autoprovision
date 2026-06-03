from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import json
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANSIBLE_DIR = os.path.join(BASE_DIR, "ansible")
INVENTORY_FILE = os.path.join(ANSIBLE_DIR, "inventory")
JOB_INVENTORY_DIR = os.path.join(BASE_DIR, "data", "inventory")
STATE_DB = os.path.join(BASE_DIR, "data", "state.db")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
TRAEFIK_CERTS_DIR = os.path.join(BASE_DIR, "docker", "traefik", "certs")
TRAEFIK_CERT_FILE = os.path.join(TRAEFIK_CERTS_DIR, "local-dev-tls.crt")
TRAEFIK_KEY_FILE = os.path.join(TRAEFIK_CERTS_DIR, "local-dev-tls.key")

app = FastAPI(title="Autoprovision Control Plane", version="0.8.0")
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
    if action == "traefik-up":
        return {
            "runner": "playbook",
            "playbook": "ansible/traefik_stack.yml",
            "log_name": "traefik.log",
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


# ─── parallel multi-track layer ─────────────────────────────────────────────────
#
# Each track runs as an independent job with its OWN inventory file
# (data/inventory/<job_id>.ini) and its OWN log (data/logs/<job_id>.log) so that
# multiple tracks (2 K8s clusters + 2 ELK + GitLab + MSSQL) run in parallel without
# colliding on a shared inventory or log file.

ALL_TRACKS = [
    "docker_traefik", "dockhand", "gitlab",
    "elk_uat", "elk_prod",
    "rke2_uat", "rke2_prod",
    "mssql_uat", "mssql_prod",
]


def _parse_ip_list(raw) -> list[str]:
    """Accept comma / whitespace / newline separated IPs and return a clean list."""
    if isinstance(raw, list):
        items = raw
    else:
        items = (raw or "").replace(",", " ").split()
    return [i.strip() for i in items if i and i.strip()]


def _ensure_targets_db() -> None:
    os.makedirs(os.path.dirname(STATE_DB), exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS targets (
                track TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _read_targets() -> dict:
    _ensure_targets_db()
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT track, data FROM targets").fetchall()
    finally:
        conn.close()
    out = {}
    for row in rows:
        try:
            out[row["track"]] = json.loads(row["data"])
        except Exception:
            out[row["track"]] = {}
    return out


def _save_target(track: str, data: dict) -> None:
    if track not in ALL_TRACKS:
        return
    _ensure_targets_db()
    # Never persist secrets to disk.
    safe = {k: v for k, v in (data or {}).items() if k not in ("ssh_pass", "sa_password", "rke2_token", "gitlab_runner_token")}
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            INSERT INTO targets (track, data, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(track) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at
            """,
            (track, json.dumps(safe), _utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def _write_job_inventory(job_id: str, groups: dict[str, list[str]], ssh_user: str, ssh_pass: str) -> str:
    """Write a per-job inventory file and return its path.

    `groups` maps an Ansible group name to its list of host IPs. SSH credentials are
    applied per host so the file is fully self-contained for this one job.
    """
    os.makedirs(JOB_INVENTORY_DIR, exist_ok=True)
    path = os.path.join(JOB_INVENTORY_DIR, f"{job_id}.ini")
    user = ssh_user or "autoprovision"
    with open(path, "w", encoding="utf-8") as f:
        for group, hosts in groups.items():
            f.write(f"[{group}]\n")
            for host in hosts:
                line = f"{host} ansible_user={user}"
                if ssh_pass:
                    line += f" ansible_password={ssh_pass} ansible_become_password={ssh_pass}"
                line += " ansible_become=true ansible_become_method=sudo\n"
                f.write(line)
            f.write("\n")
    return path


def _track_plan(action: str, body: dict) -> dict:
    """Return {inventory: {group: [ips]}, steps: [{playbook, extra_vars, label}]} for a track."""
    if action == "rke2-cluster-up":
        cp = _parse_ip_list(body.get("control_plane_ips"))
        workers = _parse_ip_list(body.get("worker_ips"))
        if not cp:
            raise ValueError("at least one control plane IP is required")
        extra = {
            "cluster_name": body.get("cluster_name") or "rke2-cluster",
            "rke2_version": body.get("rke2_version") or "v1.36.1+rke2r2",
            "rke2_token": body.get("rke2_token") or ((body.get("cluster_name") or "rke2-cluster") + "-rke2-token"),
        }
        if body.get("registration_address"):
            extra["registration_address"] = body.get("registration_address")
        if body.get("rke2_images_local_dir"):
            extra["rke2_images_local_dir"] = body.get("rke2_images_local_dir")
        return {
            "inventory": {"rke2_servers": cp, "rke2_agents": workers},
            "steps": [{"playbook": "ansible/rke2_cluster.yml", "extra_vars": extra, "label": "RKE2 cluster"}],
        }

    if action == "mssql-single-up":
        ip = (body.get("mssql_ip") or "").strip()
        if not ip:
            raise ValueError("mssql_ip is required")
        return {
            "inventory": {"mssql": [ip]},
            "steps": [{
                "playbook": "ansible/mssql_single.yml",
                "extra_vars": {"sa_password": body.get("sa_password", ""), "mssql_pid": body.get("mssql_pid") or "Developer"},
                "label": "MSSQL single instance",
            }],
        }

    if action == "mssql-ag-up":
        ips = _parse_ip_list(body.get("mssql_ips"))
        if len(ips) < 2:
            raise ValueError("at least two MSSQL AG node IPs are required (first is primary)")
        return {
            "inventory": {"mssql_ag": ips},
            "steps": [{
                "playbook": "ansible/mssql_ag.yml",
                "extra_vars": {
                    "sa_password": body.get("sa_password", ""),
                    "ag_name": body.get("ag_name") or "ag1",
                    "mssql_pid": body.get("mssql_pid") or "Developer",
                },
                "label": "MSSQL Always On AG",
            }],
        }

    if action == "docker-traefik-up":
        ip = (body.get("docker_ip") or "").strip()
        if not ip:
            raise ValueError("docker_ip is required")
        return {
            "inventory": {"docker_vm": [ip]},
            "steps": [
                {"playbook": "ansible/docker_vm_base.yml", "extra_vars": None, "label": "Docker base (Docker CE + repo)"},
                {"playbook": "ansible/traefik_stack.yml", "extra_vars": None, "label": "Traefik edge proxy (owns platform network)"},
            ],
        }

    if action == "dockhand-up":
        ip = (body.get("docker_ip") or "").strip()
        if not ip:
            raise ValueError("docker_ip is required")
        return {
            "inventory": {"docker_vm": [ip]},
            "steps": [
                {"playbook": "ansible/docker_vm_base.yml", "extra_vars": None, "label": "Docker base"},
                {"playbook": "ansible/traefik_stack.yml", "extra_vars": None, "label": "Traefik edge proxy"},
                {"playbook": "ansible/docker_platform_up.yml",
                 "extra_vars": {"dockhand_domain": body.get("dockhand_domain") or "dockhand.example.com"},
                 "label": "Dockhand + PostgreSQL"},
            ],
        }

    if action == "elk-stack-up":
        ip = (body.get("docker_ip") or "").strip()
        if not ip:
            raise ValueError("docker_ip (ELK VM IP) is required")
        return {
            "inventory": {"docker_vm": [ip]},
            "steps": [
                {"playbook": "ansible/docker_vm_base.yml", "extra_vars": None, "label": "Docker base"},
                {"playbook": "ansible/traefik_stack.yml", "extra_vars": None, "label": "Traefik edge proxy"},
                {"playbook": "ansible/elk_stack.yml",
                 "extra_vars": {"kibana_domain": body.get("kibana_domain") or "kibana.example.com"},
                 "label": "ELK stack (Kibana via Traefik)"},
            ],
        }

    if action == "gitlab-platform-up":
        ip = (body.get("docker_ip") or "").strip()
        if not ip:
            raise ValueError("docker_ip (GitLab VM IP) is required")
        return {
            "inventory": {"docker_vm": [ip]},
            "steps": [
                {"playbook": "ansible/docker_vm_base.yml", "extra_vars": None, "label": "Docker base"},
                {"playbook": "ansible/traefik_stack.yml", "extra_vars": None, "label": "Traefik edge proxy"},
                {"playbook": "ansible/docker_platform_up.yml",
                 "extra_vars": {"dockhand_domain": body.get("dockhand_domain") or "dockhand.example.com"},
                 "label": "Platform (PostgreSQL + Dockhand)"},
                {"playbook": "ansible/gitlab_stack.yml",
                 "extra_vars": {
                     "gitlab_domain": body.get("gitlab_domain") or "gitlab.example.com",
                     "gitlab_registry_domain": body.get("gitlab_registry_domain") or "registry.example.com",
                     "gitlab_runner_token": body.get("gitlab_runner_token", ""),
                 },
                 "label": "GitLab"},
                {"playbook": "ansible/sonarqube_stack.yml",
                 "extra_vars": {"sonarqube_domain": body.get("sonarqube_domain") or "sonar.example.com"},
                 "label": "SonarQube"},
            ],
        }

    raise ValueError(f"unsupported track action: {action}")


async def _run_playbook_step(playbook_rel: str, inventory_path: str, log_path: str,
                             extra_vars: dict = None, append: bool = False) -> int:
    cmd = ["ansible-playbook", "-i", inventory_path, os.path.join(BASE_DIR, playbook_rel)]
    if extra_vars:
        cmd += ["--extra-vars", json.dumps(extra_vars)]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=BASE_DIR,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    mode = "a" if append else "w"
    with open(log_path, mode, encoding="utf-8") as lf:
        lf.write(f"\n===== ansible-playbook {playbook_rel} =====\n")
        lf.flush()
        async for chunk in proc.stdout:
            lf.write(chunk.decode("utf-8", errors="replace"))
            lf.flush()
    await proc.wait()
    return proc.returncode


def _track_log_name(track: str, job_id: str) -> str:
    """Stable per-track log file so each tab keeps showing its previous run's log."""
    safe = track if track in ALL_TRACKS else job_id
    return f"track-{safe}.log"


async def _run_track_job(job_id: str, action: str, body: dict):
    track = JOBS[job_id].get("track") or (body.get("track") or "")
    log_name = _track_log_name(track, job_id)
    JOBS[job_id]["log_name"] = log_name
    log_path = os.path.join(BASE_DIR, "data", "logs", log_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    try:
        plan = _track_plan(action, body)
        JOBS[job_id]["status"] = "running"
        ssh_user = body.get("ssh_user", "autoprovision")
        ssh_pass = body.get("ssh_pass", "")
        inv_path = _write_job_inventory(job_id, plan["inventory"], ssh_user, ssh_pass)
        JOBS[job_id]["inventory"] = inv_path

        rc = 0
        for idx, step in enumerate(plan["steps"]):
            JOBS[job_id]["step"] = step["label"]
            rc = await _run_playbook_step(
                step["playbook"], inv_path, log_path,
                extra_vars=step.get("extra_vars"), append=(idx > 0),
            )
            if rc != 0:
                break

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


# ─── parallel track endpoints ───────────────────────────────────────────────────

@app.get("/state/targets")
async def get_targets():
    return JSONResponse(_read_targets())


@app.post("/state/targets")
async def save_target(request: Request):
    body = await request.json()
    track = (body.get("track") or "").strip()
    data = body.get("data") or {}
    _save_target(track, data)
    return JSONResponse({"track": track, "saved": track in ALL_TRACKS})


@app.post("/tracks/preview")
async def track_preview(request: Request):
    body = await request.json()
    action = (body.get("action") or "").strip()
    payload = body.get("payload") or {}
    try:
        plan = _track_plan(action, payload)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    steps_text = "\n".join(
        f"  {i+1}. {s['label']}  ->  {s['playbook']}" for i, s in enumerate(plan["steps"])
    )
    inv_text = "\n".join(
        f"  [{g}] {', '.join(h)}" for g, h in plan["inventory"].items()
    )
    return JSONResponse(
        {
            "action": action,
            "plan": f"Inventory:\n{inv_text}\n\nSteps:\n{steps_text}",
            "message": "Preview only. Click Run to start this track.",
        }
    )


@app.post("/tracks/start")
async def track_start(request: Request):
    body = await request.json()
    action = (body.get("action") or "").strip()
    payload = body.get("payload") or {}
    track = (payload.get("track") or "").strip()
    try:
        _track_plan(action, payload)  # validate inputs before queueing
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if track:
        _save_target(track, payload)

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "action": action,
        "track": track,
        "status": "queued",
        "rc": None,
        "error": None,
        "step": None,
        "started_at": _utc_now(),
    }
    JOBS[job_id]["task"] = asyncio.create_task(_run_track_job(job_id, action, payload))
    return JSONResponse({"job_id": job_id, "status": "queued", "track": track})


@app.get("/tracks/job/{job_id}")
async def track_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return JSONResponse({"error": "job_not_found"}, status_code=404)
    log_name = job.get("log_name") or _track_log_name(job.get("track") or "", job_id)
    log = _read_log_tail(log_name, 200000)
    return JSONResponse(
        {
            "job_id": job_id,
            "action": job.get("action"),
            "track": job.get("track"),
            "status": job.get("status"),
            "step": job.get("step"),
            "rc": job.get("rc"),
            "error": job.get("error"),
            "log": log,
        }
    )


@app.get("/tracks/log/{track}")
async def track_log(track: str):
    """Return the last (previous or live) log for a track, so a tab shows prior output on open."""
    if track not in ALL_TRACKS:
        return JSONResponse({"error": "unknown track"}, status_code=400)
    return JSONResponse({"track": track, "log": _read_log_tail(f"track-{track}.log", 200000)})


@app.get("/", response_class=HTMLResponse)
async def index():
    ui_file = os.path.join(BASE_DIR, "app", "ui_parallel.html")
    with open(ui_file, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/docker", response_class=HTMLResponse)
async def docker_page():
    ui_file = os.path.join(BASE_DIR, "app", "ui_docker.html")
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


@app.post("/actions/deploy-wso2")
async def action_deploy_wso2():
    return JSONResponse({"action": "deploy-wso2", "status": "not_implemented"})


@app.post("/actions/run-migration")
async def action_run_migration():
    return JSONResponse({"action": "run-migration", "status": "not_implemented"})
