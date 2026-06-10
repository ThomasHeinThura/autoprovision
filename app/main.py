from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOB_INVENTORY_DIR = os.path.join(BASE_DIR, "data", "inventory")
STATE_DB = os.path.join(BASE_DIR, "data", "state.db")

app = FastAPI(title="Autoprovision Control Plane", version="0.9.0")
JOBS: dict[str, dict] = {}

# ─── helpers ──────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


# ─── parallel multi-track layer ─────────────────────────────────────────────────
#
# Each track runs as an independent job with its OWN inventory file
# (data/inventory/<job_id>.ini) and its OWN log (data/logs/<job_id>.log) so that
# multiple tracks (2 K8s clusters + 2 ELK + GitLab + MSSQL) run in parallel without
# colliding on a shared inventory or log file.

ALL_TRACKS = [
    # GitLab environment
    "gl_docker", "gl_gitlab",
    # UAT environment (ordered install steps)
    "uat_docker", "uat_elk", "uat_rke2", "uat_rke2_scale", "uat_istio", "uat_argocd",
    "uat_headlamp", "uat_db", "uat_wso2_apim", "uat_wso2_is",
    # Prod environment (ordered install steps)
    "prod_docker", "prod_elk", "prod_rke2", "prod_rke2_scale", "prod_istio", "prod_argocd",
    "prod_headlamp", "prod_db", "prod_wso2_apim", "prod_wso2_is",
    # Certificates (manual cert ops)
    "traefik_cert", "k8s_cert", "k8s_certmanager",
    # Maintenance / backups
    "mssql_clean", "k8s_etcd_backup", "mssql_backup",
]


def _parse_ip_list(raw) -> list[str]:
    """Accept comma / whitespace / newline separated IPs and return a clean list."""
    if isinstance(raw, list):
        items = raw
    else:
        items = (raw or "").replace(",", " ").split()
    return [i.strip() for i in items if i and i.strip()]


_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ABS_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")


def _safe_name(value: str, field: str) -> str:
    """A short identifier (cluster name, AG name, …) that ends up in file paths and shell.
    Reject path separators / traversal / shell metacharacters."""
    v = (value or "").strip()
    if not _NAME_RE.match(v) or ".." in v:
        raise ValueError(f"{field} must contain only letters, digits, '.', '_', '-' (no '/' or '..').")
    return v


def _safe_abs_path(value: str, field: str) -> str:
    """A filesystem path that ends up in a remote shell command. Require an absolute path with
    no traversal or shell metacharacters."""
    v = (value or "").strip()
    if not _ABS_PATH_RE.match(v) or ".." in v:
        raise ValueError(f"{field} must be an absolute path with no '..' or shell metacharacters.")
    return v


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


_SECRET_KEYS = ("ssh_pass", "sa_password", "db_admin_password", "rke2_token", "gitlab_runner_token", "cert_pem", "key_pem")


def _save_target(track: str, data: dict) -> None:
    if track not in ALL_TRACKS:
        return
    _ensure_targets_db()
    # Never persist secrets to disk.
    safe = {k: v for k, v in (data or {}).items() if k not in _SECRET_KEYS}
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


# ─── install status (per step) ──────────────────────────────────────────────────
# Records whether each step of each track has been installed, so a re-run can SKIP
# already-completed steps and only run the failed/not-yet-installed ones.

def _ensure_status_db() -> None:
    os.makedirs(os.path.dirname(STATE_DB), exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS install_status (
                track TEXT NOT NULL,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (track, step)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _set_step_status(track: str, step: str, status: str) -> None:
    _ensure_status_db()
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.execute(
            """
            INSERT INTO install_status (track, step, status, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(track, step) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
            """,
            (track, step, status, _utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def _reset_track_status(track: str) -> int:
    """Clear all recorded step statuses for a track so the next run re-installs everything.
    Used when a step was marked 'completed' but the result is actually broken (e.g. an RKE2
    cluster that returned rc=0 before the node-Ready gate existed). Returns rows deleted."""
    _ensure_status_db()
    conn = sqlite3.connect(STATE_DB)
    try:
        cur = conn.execute("DELETE FROM install_status WHERE track = ?", (track,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _get_steps_done(track: str) -> dict:
    """Return {step_label: status} for a track."""
    _ensure_status_db()
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT step, status FROM install_status WHERE track = ?", (track,)
        ).fetchall()
    finally:
        conn.close()
    return {r["step"]: r["status"] for r in rows}


def _aggregate_status(steps: dict) -> str:
    """Roll per-step statuses up to a single track status for the UI badge."""
    if not steps:
        return "idle"
    vals = list(steps.values())
    if any(v == "failed" for v in vals):
        return "failed"
    if all(v == "completed" for v in vals):
        return "completed"
    return "partial"


def _status_map() -> dict:
    """Per-track {status, steps} for every track that has recorded steps."""
    _ensure_status_db()
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT track, step, status FROM install_status").fetchall()
    finally:
        conn.close()
    by_track: dict = {}
    for r in rows:
        by_track.setdefault(r["track"], {})[r["step"]] = r["status"]
    return {t: {"status": _aggregate_status(steps), "steps": steps} for t, steps in by_track.items()}


# ─── certificate staging (PEM → files on the jump host, never persisted to DB) ──
CERTS_DIR = os.path.join(BASE_DIR, "data", "certs")


def _stage_cert(track: str, cert_pem: str, key_pem: str) -> tuple[str, str]:
    if not (cert_pem or "").strip() or not (key_pem or "").strip():
        raise ValueError("both certificate (PEM) and private key (PEM) are required")
    d = os.path.join(CERTS_DIR, track)
    os.makedirs(d, exist_ok=True)
    crt = os.path.join(d, "tls.crt")
    key = os.path.join(d, "tls.key")
    with open(crt, "w", encoding="utf-8") as f:
        f.write(cert_pem.strip() + "\n")
    with open(key, "w", encoding="utf-8") as f:
        f.write(key_pem.strip() + "\n")
    os.chmod(key, 0o600)
    return crt, key


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
    os.chmod(path, 0o600)  # holds ansible_password — owner-only
    return path


def _track_plan(action: str, body: dict) -> dict:
    """Return {inventory: {group: [ips]}, steps: [{playbook, extra_vars, label}]} for a track."""
    if action in ("rke2-cluster-up", "rke2-scale-up"):
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
        # Scale = same idempotent playbook (already-joined nodes skip install via `creates`;
        # only new IPs join). `always` so install-status never skips a scale re-run.
        scaling = action == "rke2-scale-up"
        return {
            "inventory": {"rke2_servers": cp, "rke2_agents": workers},
            "steps": [{
                "playbook": "ansible/rke2_cluster.yml",
                "extra_vars": extra,
                "label": "RKE2 add/scale nodes" if scaling else "RKE2 cluster",
                "always": scaling,
            }],
        }

    if action == "mssql-single-up":
        ip = (body.get("mssql_ip") or "").strip()
        if not ip:
            raise ValueError("mssql_ip is required")
        # Native install only (apt package on the Ubuntu VM). Defaults to SQL Server 2025 on
        # Ubuntu 24.04 (supported); 2022 needs Ubuntu 20.04/22.04. Ubuntu 26.04 is unsupported.
        single_extra = {"sa_password": body.get("sa_password", ""), "mssql_pid": body.get("mssql_pid") or "Developer"}
        if body.get("mssql_version"):
            single_extra["mssql_version"] = body.get("mssql_version")
        if body.get("ubuntu_release"):
            single_extra["ubuntu_release"] = body.get("ubuntu_release")
        return {
            "inventory": {"mssql": [ip]},
            "steps": [{
                "playbook": "ansible/mssql_single.yml",
                "extra_vars": single_extra,
                "label": "MSSQL single instance (native)",
            }],
        }

    if action == "mssql-ag-up":
        ips = _parse_ip_list(body.get("mssql_ips"))
        if len(ips) < 2:
            raise ValueError("at least two MSSQL AG node IPs are required (first is primary)")
        # Native HA AG only (Pacemaker, CLUSTER_TYPE=EXTERNAL): optional virtual IP (listener).
        # Defaults to SQL Server 2025 on Ubuntu 24.04; override via mssql_version/ubuntu_release.
        ag_extra = {
            "sa_password": body.get("sa_password", ""),
            "ag_name": body.get("ag_name") or "ag1",
            "mssql_pid": body.get("mssql_pid") or "Enterprise",
        }
        # Optional named sysadmin: sa still installs + creates this login on every node, then the
        # AG/cert/endpoint SQL runs as it. Both must be set to take effect; else everything uses sa.
        if (body.get("db_admin_user") or "").strip() and (body.get("db_admin_password") or "").strip():
            ag_extra["db_admin_user"] = body.get("db_admin_user").strip()
            ag_extra["db_admin_password"] = body.get("db_admin_password")
        if body.get("listener_ip"):
            ag_extra["listener_ip"] = body.get("listener_ip")
        if body.get("enable_fencing"):
            ag_extra["enable_fencing"] = body.get("enable_fencing")
        if body.get("mssql_version"):
            ag_extra["mssql_version"] = body.get("mssql_version")
        if body.get("ubuntu_release"):
            ag_extra["ubuntu_release"] = body.get("ubuntu_release")
        return {
            "inventory": {"mssql_ag": ips},
            "steps": [{
                "playbook": "ansible/mssql_ag.yml",
                "extra_vars": ag_extra,
                "label": "MSSQL HA AG (native + Pacemaker)",
            }],
        }

    if action == "mssql-ag-clean":
        ips = _parse_ip_list(body.get("mssql_ips"))
        if len(ips) < 2:
            raise ValueError("at least two MSSQL AG node IPs are required")
        clean_extra = {"sa_password": body.get("sa_password", ""), "ag_name": body.get("ag_name") or "ag1"}
        if body.get("listener_ip"):
            clean_extra["listener_ip"] = body.get("listener_ip")
        return {
            "inventory": {"mssql_ag": ips},
            "steps": [{
                "playbook": "ansible/mssql_ag_clean.yml",
                "extra_vars": clean_extra,
                "label": "MSSQL AG cleanup / reset (then re-run MSSQL HA AG)",
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

    if action == "traefik-cert-apply":
        ips = _parse_ip_list(body.get("docker_ips"))
        if not ips:
            raise ValueError("at least one Traefik VM IP is required")
        crt = os.path.join(CERTS_DIR, "traefik_cert", "tls.crt")
        key = os.path.join(CERTS_DIR, "traefik_cert", "tls.key")
        return {
            "inventory": {"docker_vm": ips},
            "needs_cert": True,
            "steps": [{
                "playbook": "ansible/traefik_cert.yml",
                "extra_vars": {"cert_src": crt, "key_src": key},
                "label": "Apply/Update Traefik default certificate",
            }],
        }

    if action == "k8s-cert-secret":
        cluster = (body.get("cluster_name") or "uat-cluster").strip()
        namespace = (body.get("namespace") or "istio-system").strip()
        secret = (body.get("secret_name") or "wso2-ingress-cert").strip()
        kubeconfig = os.path.join(BASE_DIR, "data", "k8s", cluster, "kubeconfig")
        cert_pem = (body.get("cert_pem") or "").strip()
        key_pem = (body.get("key_pem") or "").strip()
        base_vars = {"kubeconfig_path": kubeconfig, "namespace": namespace, "secret_name": secret}
        if cert_pem and key_pem:
            # PEM provided → stage it to jump-host files and create the secret (idempotent rotate).
            base_vars["cert_src"] = os.path.join(CERTS_DIR, "k8s_cert", "tls.crt")
            base_vars["key_src"] = os.path.join(CERTS_DIR, "k8s_cert", "tls.key")
            return {
                "inventory": {},  # runs on localhost (kubectl against the cluster kubeconfig)
                "needs_cert": True,
                "steps": [{
                    "playbook": "ansible/k8s_cert.yml",
                    "extra_vars": base_vars,
                    "label": f"TLS secret {secret} in {namespace} ({cluster}) [provided cert]",
                }],
            }
        # No PEM → cert-manager issues + auto-renews the secret from the internal CA (ca-issuer).
        # Requires the 'cert-manager (internal CA)' workload to have run on this cluster first.
        base_vars["use_certmanager"] = True
        base_vars["cert_dns"] = (body.get("cert_dns") or "*.example.com").strip()
        return {
            "inventory": {},
            "steps": [{
                "playbook": "ansible/k8s_cert.yml",
                "extra_vars": base_vars,
                "label": f"TLS secret {secret} in {namespace} ({cluster}) [cert-manager]",
            }],
        }

    if action == "k8s-certmanager-up":
        cluster = (body.get("cluster_name") or "uat-cluster").strip()
        kubeconfig = os.path.join(BASE_DIR, "data", "k8s", cluster, "kubeconfig")
        return {
            "inventory": {},
            "steps": [{
                "playbook": "ansible/k8s_addons.yml",
                "extra_vars": {"kubeconfig_path": kubeconfig, "component": "certmanager"},
                "label": f"cert-manager + internal CA ({cluster})",
            }],
        }

    # ── In-cluster IAC: Istio / ArgoCD / Headlamp / WSO2 (run on localhost vs the cluster) ──
    if action in ("k8s-istio-up", "k8s-argocd-up", "k8s-headlamp-up", "k8s-wso2-apim-up", "k8s-wso2-is-up"):
        cluster = (body.get("cluster_name") or "uat-cluster").strip()
        kubeconfig = os.path.join(BASE_DIR, "data", "k8s", cluster, "kubeconfig")
        tls_secret = body.get("tls_secret") or "wso2-ingress-cert"
        wso2_src = os.path.join(BASE_DIR, "WSO2_APIM_KUBE_ISTIO")
        common = {"kubeconfig_path": kubeconfig, "tls_secret": tls_secret}

        if action == "k8s-istio-up":
            steps = []
            ip_range = (body.get("metallb_ip_range") or "").strip()
            if ip_range:
                steps.append({"playbook": "ansible/k8s_addons.yml", "label": "MetalLB (LoadBalancer IPs)",
                              "extra_vars": {**common, "component": "metallb", "metallb_ip_range": ip_range}})
            steps.append({"playbook": "ansible/k8s_addons.yml", "label": "Istio (+HTTPS ingress)",
                          "extra_vars": {**common, "component": "istio",
                                         "wso2_certs_dir": os.path.join(wso2_src, "certificates")}})
            return {"inventory": {}, "steps": steps}

        if action == "k8s-argocd-up":
            return {"inventory": {}, "steps": [{
                "playbook": "ansible/k8s_addons.yml", "label": "ArgoCD (HTTPS via Istio)",
                "extra_vars": {**common, "component": "argocd",
                               "argocd_host": body.get("argocd_host") or "argocd.example.com"},
            }]}

        if action == "k8s-headlamp-up":
            return {"inventory": {}, "steps": [{
                "playbook": "ansible/k8s_addons.yml", "label": "Headlamp (skipped if repo blocked)",
                "extra_vars": {**common, "component": "headlamp",
                               "headlamp_host": body.get("headlamp_host") or "headlamp.example.com"},
            }]}

        # WSO2 APIM / IS — render the repo with env values and apply
        wso2_vars = {
            **common,
            "wso2_src": wso2_src,
            "render_dir": os.path.join(BASE_DIR, "data", "wso2-render", cluster),
            "apim_host": body.get("apim_host") or "apim.example.com",
            "internal_gw_host": body.get("internal_gw_host") or "internal-gw.example.com",
            "external_gw_host": body.get("external_gw_host") or "external-gw.example.com",
            "is_host": body.get("is_host") or "wso2is.example.com",
            "mssql_host": body.get("mssql_host") or "",
            # Optional: docker ELK VM IP/host running Logstash on :5044 (gateway filebeat target).
            "logstash_host": body.get("logstash_host") or "",
        }
        if action == "k8s-wso2-apim-up":
            if not wso2_vars["mssql_host"]:
                raise ValueError("mssql_host (SQL Server IP/hostname) is required for WSO2 APIM")
            return {"inventory": {}, "steps": [{
                "playbook": "ansible/k8s_wso2.yml", "label": "WSO2 API Manager (CP + gateways)",
                "extra_vars": {**wso2_vars, "component": "apim"},
            }]}
        if action == "k8s-wso2-is-up":
            if not wso2_vars["mssql_host"]:
                raise ValueError("mssql_host (SQL Server IP/hostname) is required for WSO2 IS")
            return {"inventory": {}, "steps": [{
                "playbook": "ansible/k8s_wso2.yml", "label": "WSO2 Identity Server",
                "extra_vars": {**wso2_vars, "component": "is"},
            }]}

    # ── Backups (production-grade): RKE2 etcd snapshots + MSSQL FULL/LOG backups ──
    if action == "k8s-etcd-backup":
        cp = _parse_ip_list(body.get("control_plane_ips"))
        if not cp:
            raise ValueError("at least one RKE2 server (control plane) IP is required")
        # cluster_name lands in a fetch dest path on the jump host — reject traversal.
        extra = {"cluster_name": _safe_name(body.get("cluster_name") or "rke2-cluster", "cluster_name")}
        if body.get("snapshot_cron"):
            extra["snapshot_cron"] = body.get("snapshot_cron")
        if body.get("snapshot_retention"):
            extra["snapshot_retention"] = body.get("snapshot_retention")
        if body.get("fetch_to_jumphost"):
            extra["fetch_to_jumphost"] = body.get("fetch_to_jumphost")
        return {
            "inventory": {"rke2_servers": cp},
            "steps": [{
                "playbook": "ansible/k8s_etcd_backup.yml",
                "extra_vars": extra,
                "label": "RKE2 etcd snapshots (scheduled + on-demand)",
                "always": True,  # a backup must run every time, never be skipped as 'done'
            }],
        }

    if action == "mssql-backup-setup":
        ips = _parse_ip_list(body.get("mssql_ips"))
        if not ips:
            raise ValueError("at least one MSSQL node IP is required")
        if not body.get("sa_password"):
            raise ValueError("sa_password is required")
        extra = {"sa_password": body.get("sa_password")}
        if (body.get("db_admin_user") or "").strip() and (body.get("db_admin_password") or "").strip():
            extra["db_admin_user"] = body.get("db_admin_user").strip()
            extra["db_admin_password"] = body.get("db_admin_password")
        if body.get("backup_dir"):
            # backup_dir is interpolated into a shell script on the MSSQL host — validate strictly.
            extra["backup_dir"] = _safe_abs_path(body.get("backup_dir"), "backup_dir")
        if body.get("retention_days"):
            # Numeric only — it reaches `find -mtime +N` on the host.
            extra["retention_days"] = int(body.get("retention_days"))
        return {
            "inventory": {"mssql_backup": ips},
            "steps": [{
                "playbook": "ansible/mssql_backup.yml",
                "extra_vars": extra,
                "label": "MSSQL scheduled backups (FULL daily + LOG 15min)",
                "always": True,  # a backup must run every time, never be skipped as 'done'
            }],
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


def _log_append(log_path: str, text: str) -> None:
    with open(log_path, "a", encoding="utf-8") as lf:
        lf.write(text)


async def _run_track_job(job_id: str, action: str, body: dict):
    track = JOBS[job_id].get("track") or (body.get("track") or "")
    force = bool(body.get("force"))
    log_name = _track_log_name(track, job_id)
    JOBS[job_id]["log_name"] = log_name
    log_path = os.path.join(BASE_DIR, "data", "logs", log_name)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    # Truncate the per-track log and write a run header; every step appends from here.
    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(f"===== run {action}{'  [FORCE: re-run all steps]' if force else ''} =====\n"
                 f"Already-completed steps are skipped unless Force is set.\n")
    try:
        plan = _track_plan(action, body)
        JOBS[job_id]["status"] = "running"
        ssh_user = body.get("ssh_user", "autoprovision")
        ssh_pass = body.get("ssh_pass", "")
        inv_path = _write_job_inventory(job_id, plan["inventory"], ssh_user, ssh_pass)
        JOBS[job_id]["inventory"] = inv_path

        # Stage certificate PEMs to jump-host files for cert actions (never saved to DB).
        if plan.get("needs_cert"):
            _stage_cert(track, body.get("cert_pem", ""), body.get("key_pem", ""))

        done = _get_steps_done(track)  # {label: status} from previous runs
        rc = 0
        for step in plan["steps"]:
            label = step["label"]
            # `always` steps (e.g. scale/add-nodes) re-run every time so new IPs get joined.
            if not force and not step.get("always") and done.get(label) == "completed":
                _log_append(log_path, f"\n✓ SKIP — '{label}' already installed (use Force to re-run).\n")
                JOBS[job_id]["step"] = f"skipped: {label}"
                continue
            JOBS[job_id]["step"] = label
            _log_append(log_path, f"\n▶ RUN — '{label}'\n")
            rc = await _run_playbook_step(
                step["playbook"], inv_path, log_path,
                extra_vars=step.get("extra_vars"), append=True,
            )
            _set_step_status(track, label, "completed" if rc == 0 else "failed")
            if rc != 0:
                break

        JOBS[job_id]["rc"] = rc
        JOBS[job_id]["status"] = "completed" if rc == 0 else "failed"
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)
        _log_append(log_path, f"\nError: {e}\n")


# ─── routes ───────────────────────────────────────────────────────────────────

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


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


@app.get("/tracks/status")
async def tracks_status():
    """Persisted per-track install status (and per-step) so the dashboard reflects what is
    already installed across restarts. Re-running a track skips completed steps unless Force."""
    return JSONResponse(_status_map())


@app.post("/tracks/reset")
async def tracks_reset(request: Request):
    """Clear a track's recorded install status so the next run re-installs every step.
    Use this when a step is marked 'completed' but is actually broken."""
    body = await request.json()
    track = body.get("track", "")
    if track not in ALL_TRACKS:
        return JSONResponse({"error": "unknown track"}, status_code=400)
    n = _reset_track_status(track)
    return JSONResponse({"track": track, "cleared": n})


@app.get("/", response_class=HTMLResponse)
async def index():
    ui_file = os.path.join(BASE_DIR, "app", "ui_parallel.html")
    with open(ui_file, "r", encoding="utf-8") as f:
        return f.read()


