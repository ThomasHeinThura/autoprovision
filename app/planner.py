"""Resolves a workload action plus its form values into an executable plan.

A plan is `{inventory: {group: [ips]}, steps: [{playbook, extra_vars, label}]}`.
This module is pure — it validates and computes, it never touches the filesystem
or spawns anything, which is what makes it the highest-value thing to unit test.
Every branch here decides what runs against real infrastructure.
"""

from __future__ import annotations

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERTS_DIR = os.path.join(BASE_DIR, "data", "certs")

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ABS_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")


class PlanError(ValueError):
    """A configuration problem the operator can fix. Surfaced verbatim in the UI."""


# ── validation helpers ───────────────────────────────────────────────────────

def ip_list(raw) -> list[str]:
    items = raw if isinstance(raw, list) else (raw or "").replace(",", " ").split()
    return [i.strip() for i in items if i and i.strip()]


def safe_name(value: str, field: str) -> str:
    v = (value or "").strip()
    if not _NAME_RE.match(v) or ".." in v:
        raise PlanError(f"{field} may contain only letters, digits, '.', '_' and '-'.")
    return v


def safe_abs_path(value: str, field: str) -> str:
    v = (value or "").strip()
    if not _ABS_PATH_RE.match(v) or ".." in v:
        raise PlanError(f"{field} must be an absolute path with no '..' or shell metacharacters.")
    return v


def require(body: dict, key: str, label: str) -> str:
    v = (body.get(key) or "").strip()
    if not v:
        raise PlanError(f"{label} is required.")
    return v


def kubeconfig_for(body: dict, default: str = "uat-cluster") -> str:
    cluster = safe_name(body.get("cluster_name") or default, "Cluster name")
    return os.path.join(BASE_DIR, "data", "k8s", cluster, "kubeconfig")


# ── engine catalogue ─────────────────────────────────────────────────────────
# One table describing every engine, so adding an engine is a data change rather
# than a new branch in six places.

ENGINES = {
    "mssql": {
        "label": "SQL Server", "group": "db_mssql", "port": "1433",
        "data_dir": "/var/opt/mssql/data",
        "single": ("ansible/db/mssql_single.yml", "SQL Server single instance"),
        "cluster": ("ansible/db/mssql_ag.yml", "SQL Server availability group"),
        "bilateral": ("ansible/db/mssql_ag.yml", "SQL Server availability group (2 nodes)"),
        "multiprimary": None,
        "users": ("ansible/db/mssql_wso2_db.yml", "SQL Server logins and schemas"),
        "backup": ("ansible/db/mssql_backup.yml", "SQL Server backups"),
        "clean": ("ansible/db/mssql_ag_clean.yml", "SQL Server availability group teardown"),
        "min_ha_nodes": 2,
    },
    "postgres": {
        "label": "PostgreSQL", "group": "db_postgres", "port": "5432",
        "data_dir": "/var/lib/postgresql/17/main",
        "single": ("ansible/db/postgres_single.yml", "PostgreSQL single instance"),
        "cluster": ("ansible/db/postgres_patroni.yml", "PostgreSQL Patroni cluster"),
        "bilateral": ("ansible/db/postgres_replica.yml", "PostgreSQL streaming replication"),
        "multiprimary": None,
        "users": ("ansible/db/postgres_users.yml", "PostgreSQL roles and databases"),
        "backup": ("ansible/db/postgres_backup.yml", "PostgreSQL backups (pgBackRest)"),
        "clean": ("ansible/db/postgres_clean.yml", "PostgreSQL cluster teardown"),
        "min_ha_nodes": 2,
    },
    "mysql": {
        "label": "MySQL", "group": "db_mysql", "port": "3306",
        "data_dir": "/var/lib/mysql",
        "single": ("ansible/db/mysql_single.yml", "MySQL single instance"),
        "cluster": ("ansible/db/mysql_innodb_cluster.yml", "MySQL InnoDB Cluster"),
        "bilateral": ("ansible/db/mysql_replica.yml", "MySQL semi-synchronous replication"),
        "multiprimary": ("ansible/db/mysql_innodb_cluster.yml", "MySQL multi-primary cluster"),
        "users": ("ansible/db/mysql_users.yml", "MySQL users and databases"),
        "backup": ("ansible/db/mysql_backup.yml", "MySQL backups (XtraBackup)"),
        "clean": ("ansible/db/mysql_clean.yml", "MySQL cluster teardown"),
        "min_ha_nodes": 2,
    },
}

OBJECT_PROVIDERS = {
    "minio": ("ansible/object/minio.yml", "MinIO", "object_store"),
    "seaweedfs": ("ansible/object/seaweedfs.yml", "SeaweedFS", "object_store"),
}

MONITORING_STACKS = {
    "lgtm": ("ansible/monitoring/lgtm.yml", "LGTM — Loki, Grafana, Tempo, Mimir"),
    "opensearch": ("ansible/monitoring/opensearch.yml", "OpenSearch and Dashboards"),
    "elastic": ("ansible/monitoring/elk_stack.yml", "Elastic Stack"),
}


def engine_of(body: dict) -> tuple[str, dict]:
    key = (body.get("engine") or "mssql").strip()
    if key not in ENGINES:
        raise PlanError(f"Unknown database engine '{key}'.")
    return key, ENGINES[key]


# ── the planner ──────────────────────────────────────────────────────────────

def plan(action: str, body: dict) -> dict:
    fn = _ACTIONS.get(action)
    if not fn:
        raise PlanError(f"Unsupported workload action: {action}")
    return fn(body)


def _step(playbook, label, extra=None, always=False):
    return {"playbook": playbook, "label": label, "extra_vars": extra, "always": always}


# ── platform ─────────────────────────────────────────────────────────────────

def _docker_traefik(body):
    ip = require(body, "docker_ip", "Docker VM IP")
    return {"inventory": {"docker_vm": [ip]}, "steps": [
        _step("ansible/platform/docker_vm_base.yml", "Docker base"),
        _step("ansible/platform/traefik_stack.yml", "Traefik edge proxy"),
    ]}


def _gitlab_platform(body):
    ip = require(body, "docker_ip", "GitLab VM IP")
    return {"inventory": {"docker_vm": [ip]}, "steps": [
        _step("ansible/platform/docker_vm_base.yml", "Docker base"),
        _step("ansible/platform/traefik_stack.yml", "Traefik edge proxy"),
        _step("ansible/platform/docker_platform_up.yml", "PostgreSQL and Dockhand",
              {"dockhand_domain": body.get("dockhand_domain") or "dockhand.example.com"}),
        _step("ansible/platform/gitlab_stack.yml", "GitLab", {
            "gitlab_domain": body.get("gitlab_domain") or "gitlab.example.com",
            "gitlab_registry_domain": body.get("gitlab_registry_domain") or "registry.example.com",
            "gitlab_runner_token": body.get("gitlab_runner_token", ""),
        }),
        _step("ansible/platform/sonarqube_stack.yml", "SonarQube",
              {"sonarqube_domain": body.get("sonarqube_domain") or "sonar.example.com"}),
    ]}


def _sonarqube_up(body):
    ip = require(body, "docker_ip", "GitLab VM IP")
    return {"inventory": {"docker_vm": [ip]}, "steps": [
        _step("ansible/platform/sonarqube_stack.yml", "SonarQube reinstall",
              {"sonarqube_domain": body.get("sonarqube_domain") or "sonar.example.com"}),
    ]}


def _sonarqube_clean(body):
    ip = require(body, "docker_ip", "GitLab VM IP")
    purge = str(body.get("purge_data", "true")).strip().lower() not in ("false", "0", "no", "")
    return {"inventory": {"docker_vm": [ip]}, "steps": [
        _step("ansible/platform/sonarqube_clean.yml", "SonarQube uninstall", {"purge_data": purge}),
    ]}


# ── object storage ───────────────────────────────────────────────────────────

def _object_store(body):
    provider = (body.get("provider") or "minio").strip()
    if provider not in OBJECT_PROVIDERS:
        raise PlanError(f"Unknown object storage provider '{provider}'.")
    playbook, label, group = OBJECT_PROVIDERS[provider]
    ips = ip_list(body.get("node_ips"))
    mode = (body.get("mode") or "dist").strip()
    drives = int(body.get("drives_per_node") or 4)

    if not ips:
        raise PlanError("At least one node IP is required.")
    if mode == "single" and len(ips) != 1:
        raise PlanError("Standalone mode takes exactly one node. Switch to distributed for more.")
    if mode == "dist":
        if len(ips) < 2:
            raise PlanError("Distributed mode needs at least two nodes.")
        if drives < 4:
            raise PlanError(
                f"Erasure coding needs at least 4 drives per node; {drives} was given. "
                "With fewer, the parity budget cannot survive a node outage plus a drive failure.")
        # MinIO builds erasure sets from the total drive count, and a set must
        # divide evenly across nodes. An indivisible layout is rejected at startup
        # with an error that names neither the node nor the drive count.
        total_drives = len(ips) * drives
        if total_drives % len(ips) != 0:
            raise PlanError(
                f"{len(ips)} nodes × {drives} drives does not divide into even erasure sets.")
        if total_drives < 4:
            raise PlanError(
                f"{total_drives} drives in total is below the minimum erasure set of 4.")

    return {"inventory": {group: ips}, "steps": [
        _step(playbook, f"{label} ({'standalone' if mode == 'single' else f'{len(ips)} nodes'})", {
            "object_mode": mode,
            "drives_per_node": drives,
            "console_domain": body.get("console_domain") or "minio.example.com",
            "object_root_user": body.get("admin_user") or "minioadmin",
            "object_root_password": body.get("admin_password", ""),
        }),
    ]}


def _object_replicate(body):
    src = require(body, "source_endpoint", "Source endpoint")
    return {"inventory": {}, "steps": [
        _step("ansible/object/replicate.yml", "Bucket replication to the second site", {
            "source_endpoint": src,
            "target_endpoint": require(body, "target_endpoint", "Target endpoint"),
            "target_access_key": body.get("target_access_key", ""),
            "target_secret_key": body.get("target_secret_key", ""),
        }, always=True),
    ]}


# ── monitoring ───────────────────────────────────────────────────────────────

def _monitoring(body):
    stack = (body.get("stack") or "lgtm").strip()
    if stack not in MONITORING_STACKS:
        raise PlanError(f"Unknown monitoring stack '{stack}'.")
    playbook, label = MONITORING_STACKS[stack]
    placement = (body.get("placement") or "cluster").strip()
    mode = (body.get("mode") or "single").strip()

    extra = {
        "monitoring_stack": stack,
        "monitoring_mode": mode,
        "dashboard_domain": body.get("dashboard_domain") or "grafana.example.com",
        "admin_password": body.get("admin_password", ""),
        "retention_days": int(body.get("retention_days") or 30),
    }

    if stack == "lgtm":
        endpoint = (body.get("object_endpoint") or "").strip()
        if not endpoint:
            raise PlanError(
                "LGTM stores logs, traces and metrics in object storage. Set the object store "
                "endpoint, or choose OpenSearch or Elastic which use local volumes.")
        extra["object_endpoint"] = endpoint

    if placement == "cluster":
        extra["kubeconfig_path"] = kubeconfig_for(body)
        extra["placement"] = "cluster"
        return {"inventory": {}, "steps": [_step(playbook, f"{label} — in cluster", extra)]}

    ips = ip_list(body.get("node_ips"))
    if not ips:
        raise PlanError("At least one Docker VM IP is required when running on a VM.")
    if mode == "ha" and len(ips) % 2 == 0:
        raise PlanError(
            f"{len(ips)} nodes cannot hold quorum — a cluster manager needs an odd count. "
            "Use three.")
    extra["placement"] = "vm"
    return {"inventory": {"monitoring": ips}, "steps": [
        _step("ansible/platform/docker_vm_base.yml", "Docker base"),
        _step("ansible/platform/traefik_stack.yml", "Traefik edge proxy"),
        _step(playbook, f"{label} — on {len(ips)} VM{'s' if len(ips) > 1 else ''}", extra),
    ]}


# ── kubernetes ───────────────────────────────────────────────────────────────

def _rke2(body, scaling=False):
    cps = ip_list(body.get("control_plane_ips"))
    workers = ip_list(body.get("worker_ips"))
    if not cps:
        raise PlanError("At least one control plane IP is required.")
    if len(cps) % 2 == 0 and len(cps) > 1:
        raise PlanError(
            f"{len(cps)} control planes cannot hold etcd quorum — it needs an odd count. "
            "Use one, three or five.")
    name = safe_name(body.get("cluster_name") or "rke2-cluster", "Cluster name")
    extra = {
        "cluster_name": name,
        "rke2_version": body.get("rke2_version") or "v1.36.1+rke2r2",
        "rke2_token": body.get("rke2_token") or f"{name}-rke2-token",
    }
    if body.get("registration_address"):
        extra["registration_address"] = body["registration_address"]
    if body.get("rke2_images_local_dir"):
        extra["rke2_images_local_dir"] = safe_abs_path(
            body["rke2_images_local_dir"], "Air-gapped image directory")
    return {"inventory": {"rke2_servers": cps, "rke2_agents": workers}, "steps": [
        _step("ansible/k8s/rke2_cluster.yml",
              "Add or scale nodes" if scaling else "RKE2 cluster", extra, always=scaling),
    ]}


def _istio(body):
    common = {"kubeconfig_path": kubeconfig_for(body),
              "tls_secret": body.get("tls_secret") or "wso2-ingress-cert"}
    steps = []
    ip_range = (body.get("metallb_ip_range") or "").strip()
    if ip_range:
        steps.append(_step("ansible/k8s/addons.yml", "MetalLB",
                           {**common, "component": "metallb", "metallb_ip_range": ip_range}))
    steps.append(_step("ansible/k8s/addons.yml", "Istio ambient and the shared gateway", {
        **common, "component": "istio",
        "wso2_certs_dir": os.path.join(BASE_DIR, "WSO2_APIM_KUBE_ISTIO", "certificates"),
    }))
    return {"inventory": {}, "steps": steps}


def _addon(component, label, host_key, host_default):
    def build(body):
        return {"inventory": {}, "steps": [
            _step("ansible/k8s/addons.yml", label, {
                "kubeconfig_path": kubeconfig_for(body),
                "tls_secret": body.get("tls_secret") or "wso2-ingress-cert",
                "component": component,
                host_key: body.get(host_key) or host_default,
            }),
        ]}
    return build


def _certmanager(body):
    return {"inventory": {}, "steps": [
        _step("ansible/k8s/addons.yml", "cert-manager and the internal CA",
              {"kubeconfig_path": kubeconfig_for(body), "component": "certmanager"}),
    ]}


def _wso2(component, label):
    def build(body):
        vars_ = {
            "kubeconfig_path": kubeconfig_for(body),
            "tls_secret": body.get("tls_secret") or "wso2-ingress-cert",
            "wso2_src": os.path.join(BASE_DIR, "WSO2_APIM_KUBE_ISTIO"),
            "render_dir": os.path.join(BASE_DIR, "data", "wso2-render",
                                       safe_name(body.get("cluster_name") or "uat-cluster",
                                                 "Cluster name")),
            "apim_host": body.get("apim_host") or "apim.example.com",
            "internal_gw_host": body.get("internal_gw_host") or "internal-gw.example.com",
            "external_gw_host": body.get("external_gw_host") or "external-gw.example.com",
            "is_host": body.get("is_host") or "wso2is.example.com",
            "mssql_host": require(body, "mssql_host", "Database host"),
            "wso2_db_user": (body.get("wso2_db_user") or "wso2_apim").strip(),
            "wso2_db_password": body.get("wso2_db_password") or "",
            "logstash_host": body.get("logstash_host") or "",
            "component": component,
        }
        return {"inventory": {}, "steps": [_step("ansible/k8s/wso2.yml", label, vars_)]}
    return build


def _etcd_backup(body):
    cps = ip_list(body.get("control_plane_ips"))
    if not cps:
        raise PlanError("At least one RKE2 server IP is required.")
    extra = {"cluster_name": safe_name(body.get("cluster_name") or "rke2-cluster", "Cluster name")}
    for k in ("snapshot_cron", "snapshot_retention", "fetch_to_jumphost"):
        if body.get(k):
            extra[k] = body[k]
    return {"inventory": {"rke2_servers": cps}, "steps": [
        _step("ansible/k8s/etcd_backup.yml", "etcd snapshots", extra, always=True),
    ]}


# ── databases ────────────────────────────────────────────────────────────────

def _db_engine(body):
    key, eng = engine_of(body)
    mode = (body.get("mode") or "single").strip()
    shape = (body.get("ha_shape") or "cluster").strip()
    ips = ip_list(body.get("node_ips"))

    if key == "mssql" and (body.get("platform") or "linux").strip() == "windows":
        raise PlanError(
            "SQL Server on Windows Server is not automated by this console. It needs a Windows "
            "failover cluster and a domain, which is a different toolchain. Follow "
            "docs/mssql/windows-ad-ag.md, or choose Linux.")

    if not ips:
        raise PlanError("At least one node IP is required.")

    if mode == "single":
        if len(ips) != 1:
            raise PlanError("Single node takes exactly one IP. Switch to high availability for more.")
        playbook, label = eng["single"]
    else:
        target = eng.get(shape)
        if not target:
            raise PlanError(
                f"{eng['label']} does not support the '{shape}' shape. "
                f"Multi-primary is a MySQL-only topology.")
        playbook, label = target
        if shape == "bilateral" and len(ips) != 2:
            raise PlanError("Two-node replication takes exactly two nodes.")
        if shape in ("cluster", "multiprimary"):
            if len(ips) < 3:
                raise PlanError(
                    f"A managed cluster needs at least three nodes; {len(ips)} was given. "
                    "Two nodes cannot arbitrate a split brain — both sides believe they are "
                    "primary and the data diverges.")
            if len(ips) % 2 == 0:
                raise PlanError(
                    f"{len(ips)} nodes cannot hold quorum. Use an odd count — three or five.")

    extra = {
        "db_engine": key,
        "db_mode": mode,
        "ha_shape": shape if mode == "ha" else "",
        "cluster_label": safe_name(body.get("cluster_label") or "ag1", "Cluster name"),
        "db_admin_user": (body.get("admin_user") or "provisioner").strip(),
        "db_admin_password": body.get("admin_password", ""),
        "db_port": body.get("port") or eng["port"],
        "db_data_dir": safe_abs_path(body.get("data_dir") or eng["data_dir"], "Data directory"),
    }
    if body.get("vip"):
        extra["listener_ip"] = body["vip"]
    if key == "mssql":
        extra["mssql_version"] = body.get("mssql_version") or "2025"
        # The existing playbooks still read sa_password; keep them working unchanged.
        extra["sa_password"] = body.get("admin_password", "")
        extra["ag_name"] = extra["cluster_label"]

    return {"inventory": {eng["group"]: ips}, "steps": [
        _step(playbook, label, extra),
        _step("ansible/db/harden.yml", "Harden and lock built-in accounts",
              {"db_engine": key, "db_port": extra["db_port"]}),
    ]}


def _db_users(body):
    key, eng = engine_of(body)
    ips = ip_list(body.get("node_ips"))
    if not ips:
        raise PlanError("At least one node IP is required. Logins must exist on every node.")
    components = [c.strip() for c in (body.get("components") or "").replace(",", "\n").split("\n")
                  if c.strip()]
    if not components:
        raise PlanError("List at least one component. Each gets its own login and database.")
    if not (body.get("app_password") or "").strip():
        raise PlanError("A runtime login password is required.")

    playbook, label = eng["users"]
    extra = {
        "db_engine": key,
        "cluster_label": safe_name(body.get("cluster_label") or "ag1", "Cluster name"),
        "db_admin_user": (body.get("admin_user") or "provisioner").strip(),
        "db_admin_password": body.get("admin_password", ""),
        "components": components,
        "app_user_prefix": safe_name(body.get("app_user_prefix") or "wso2", "Login name prefix"),
        "app_password": body.get("app_password"),
        "lock_builtins": (body.get("lock_builtins") or "yes") == "yes",
    }
    if key == "mssql":
        extra["sa_password"] = body.get("admin_password", "")
        extra["ag_name"] = extra["cluster_label"]
        extra["wso2_db_user"] = f"{extra['app_user_prefix']}_apim"
        extra["wso2_db_password"] = body.get("app_password")
        if (body.get("login_sid") or "").strip():
            extra["wso2_db_sid"] = body["login_sid"].strip()

    steps = [_step(playbook, label, extra)]
    if extra["lock_builtins"]:
        steps.append(_step("ansible/db/lock_builtins.yml",
                           "Disable built-in superuser accounts",
                           {"db_engine": key, "db_admin_user": extra["db_admin_user"],
                            "db_admin_password": extra["db_admin_password"]}))
    return {"inventory": {eng["group"]: ips}, "steps": steps}


def _db_backup(body):
    key, eng = engine_of(body)
    ips = ip_list(body.get("node_ips"))
    if not ips:
        raise PlanError("At least one database node IP is required.")
    playbook, label = eng["backup"]
    extra = {
        "db_engine": key,
        "db_admin_user": (body.get("admin_user") or "provisioner").strip(),
        "db_admin_password": body.get("admin_password", ""),
        "backup_dir": safe_abs_path(body.get("backup_dir") or "/var/backups/db", "Backup directory"),
        "retention_days": int(body.get("retention_days") or 7),
    }
    if key == "mssql":
        extra["sa_password"] = body.get("admin_password", "")
    return {"inventory": {"db_backup": ips}, "steps": [
        _step(playbook, label, extra, always=True),
    ]}


def _db_clean(body):
    key, eng = engine_of(body)
    ips = ip_list(body.get("node_ips"))
    if len(ips) < 2:
        raise PlanError("A cluster teardown needs the full node list — at least two.")
    playbook, label = eng["clean"]
    extra = {
        "db_engine": key,
        "cluster_label": safe_name(body.get("cluster_label") or "ag1", "Cluster name"),
        "db_admin_user": (body.get("admin_user") or "provisioner").strip(),
        "db_admin_password": body.get("admin_password", ""),
    }
    if body.get("vip"):
        extra["listener_ip"] = body["vip"]
    if key == "mssql":
        extra["sa_password"] = body.get("admin_password", "")
        extra["ag_name"] = extra["cluster_label"]
    return {"inventory": {eng["group"]: ips}, "steps": [
        _step(playbook, label, extra, always=True),
    ]}


# ── certificates and secrets ─────────────────────────────────────────────────

def _traefik_cert(body):
    ips = ip_list(body.get("docker_ips"))
    if not ips:
        raise PlanError("At least one Traefik VM IP is required.")
    return {"inventory": {"docker_vm": ips}, "needs_cert": True, "steps": [
        _step("ansible/certs/traefik_cert.yml", "Traefik default certificate", {
            "cert_src": os.path.join(CERTS_DIR, "certs_traefik", "tls.crt"),
            "key_src": os.path.join(CERTS_DIR, "certs_traefik", "tls.key"),
        }, always=True),
    ]}


def _k8s_cert(body):
    namespace = safe_name(body.get("namespace") or "istio-system", "Namespace")
    secret_name = safe_name(body.get("secret_name") or "wso2-ingress-cert", "Secret name")
    base = {"kubeconfig_path": kubeconfig_for(body), "namespace": namespace,
            "secret_name": secret_name}
    cert_pem = (body.get("cert_pem") or "").strip()
    key_pem = (body.get("key_pem") or "").strip()

    if bool(cert_pem) != bool(key_pem):
        raise PlanError("Provide both the certificate and the private key, or neither. "
                        "Leaving both empty hands the job to cert-manager.")
    if cert_pem:
        base["cert_src"] = os.path.join(CERTS_DIR, "certs_k8s", "tls.crt")
        base["key_src"] = os.path.join(CERTS_DIR, "certs_k8s", "tls.key")
        return {"inventory": {}, "needs_cert": True, "steps": [
            _step("ansible/certs/k8s_cert.yml",
                  f"TLS secret {secret_name} in {namespace} (provided)", base, always=True),
        ]}
    base["use_certmanager"] = True
    base["cert_dns"] = body.get("cert_dns") or "*.example.com"
    return {"inventory": {}, "steps": [
        _step("ansible/certs/k8s_cert.yml",
              f"TLS secret {secret_name} in {namespace} (cert-manager)", base, always=True),
    ]}


def _vault(body):
    ip = require(body, "docker_ip", "Vault VM IP")
    return {"inventory": {"docker_vm": [ip]}, "steps": [
        _step("ansible/platform/docker_vm_base.yml", "Docker base"),
        _step("ansible/platform/traefik_stack.yml", "Traefik edge proxy"),
        _step("ansible/platform/infisical.yml", "Infisical vault", {
            "vault_domain": body.get("vault_domain") or "vault.example.com",
            "vault_admin_password": body.get("admin_password", ""),
            "project_slug": safe_name(body.get("project_slug") or "autoprovision", "Project slug"),
        }),
    ]}


_ACTIONS = {
    "docker-traefik-up": _docker_traefik,
    "gitlab-platform-up": _gitlab_platform,
    "sonarqube-up": _sonarqube_up,
    "sonarqube-clean": _sonarqube_clean,
    "object-store-up": _object_store,
    "object-replicate": _object_replicate,
    "monitoring-up": _monitoring,
    "rke2-cluster-up": lambda b: _rke2(b, scaling=False),
    "rke2-scale-up": lambda b: _rke2(b, scaling=True),
    "k8s-istio-up": _istio,
    "k8s-argocd-up": _addon("argocd", "ArgoCD", "argocd_host", "argocd.example.com"),
    "k8s-headlamp-up": _addon("headlamp", "Headlamp", "headlamp_host", "headlamp.example.com"),
    "k8s-certmanager-up": _certmanager,
    "k8s-cert-secret": _k8s_cert,
    "traefik-cert-apply": _traefik_cert,
    "k8s-wso2-apim-up": _wso2("apim", "WSO2 API Manager"),
    "k8s-wso2-is-up": _wso2("is", "WSO2 Identity Server"),
    "k8s-etcd-backup": _etcd_backup,
    "db-engine-up": _db_engine,
    "db-users-up": _db_users,
    "db-backup-setup": _db_backup,
    "db-cluster-clean": _db_clean,
    "vault-up": _vault,
}

SUPPORTED_ACTIONS = frozenset(_ACTIONS)
