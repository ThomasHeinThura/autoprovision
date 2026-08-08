"""Workload registry — the single source of truth for the control plane.

Every workload the console can run is declared here once. The API serves this
registry to the browser, the planner resolves an action to playbooks from it, and
the dependency checker reads its `requires` edges. Nothing about a workload is
declared in two places, so the UI and the backend cannot drift apart — the class
of bug where a card existed in the browser but not in the backend registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from .environments import FULL, EnvSpec
from .environments import load as load_environments

# ── field primitives ─────────────────────────────────────────────────────────

@dataclass
class Field:
    key: str
    label: str
    type: str = "text"            # text | password | textarea | select | number
    default: str = ""
    placeholder: str = ""
    hint: str = ""
    options: list[dict] | None = None   # [{value, label, hint}] for select
    show_if: dict[str, list[str]] | None = None   # {other_key: [values]}
    hosts: bool = False           # value is one or more machine addresses

    def as_dict(self) -> dict:
        d = {
            "key": self.key, "label": self.label, "type": self.type,
            "default": self.default, "placeholder": self.placeholder, "hint": self.hint,
        }
        if self.options:
            d["options"] = self.options
        if self.show_if:
            d["showIf"] = self.show_if
        if self.hosts:
            d["hosts"] = True
        return d


def txt(key, label, default="", placeholder="", hint="", show_if=None, hosts=False):
    return Field(key, label, "text", default, placeholder, hint,
                 show_if=show_if, hosts=hosts)


def secret(key, label, hint="", show_if=None):
    return Field(key, label, "password", hint=hint or "Never written to disk.", show_if=show_if)


def area(key, label, default="", placeholder="", hint="", show_if=None, hosts=False):
    return Field(key, label, "textarea", default, placeholder, hint,
                 show_if=show_if, hosts=hosts)


def sel(key, label, options, default="", hint="", show_if=None):
    return Field(key, label, "select", default or options[0]["value"], hint=hint,
                 options=options, show_if=show_if)


def opt(value, label, hint=""):
    return {"value": value, "label": label, "hint": hint}


# ── workload ─────────────────────────────────────────────────────────────────

@dataclass
class Workload:
    id: str
    env: str
    ordinal: str
    title: str
    summary: str
    action: str
    fields: list[Field] = dc_field(default_factory=list)
    requires: list[str] = dc_field(default_factory=list)
    destructive: bool = False
    confirm_field: str = ""       # field whose value must be retyped to confirm
    always: bool = False          # never skipped as "already done"
    docs: str = ""                # content/<docs>/{requirements,guide,theory}.md

    def as_dict(self) -> dict:
        return {
            "id": self.id, "env": self.env, "ordinal": self.ordinal, "title": self.title,
            "summary": self.summary, "action": self.action,
            "fields": [f.as_dict() for f in self.fields],
            "requires": self.requires, "destructive": self.destructive,
            "confirmField": self.confirm_field, "always": self.always,
            "docs": self.docs or self.action,
        }


@dataclass
class Environment:
    id: str
    group: str
    title: str
    blurb: str
    meta: str = ""


# Environments come from config/environments.yml, so this control plane is not
# tied to any particular topology. Declare as many as you need; the machine count
# follows from how each workload is sized, not from anything fixed here.
ENV_SPECS: list[EnvSpec] = load_environments()

OPERATIONS: list[Environment] = [
    Environment("certs", "Platform operations", "Certificates",
                "TLS for the Kubernetes shared gateway and for every Traefik VM. Paste your own "
                "PEM, or let the internal CA issue and renew automatically.", ""),
    Environment("secrets", "Platform operations", "Secrets",
                "A self-hosted vault so provisioning credentials stop travelling on Ansible "
                "command lines, where they are visible in the process list.", ""),
    Environment("backups", "Platform operations", "Backups & DR",
                "The only thing that protects against corruption, an accidental DELETE, or "
                "ransomware. High availability does not — it replicates the damage faithfully.", ""),
    Environment("danger", "Platform operations", "Danger zone",
                "Workloads that destroy state. Excluded from Run ready workloads, and each "
                "requires you to type its target before it starts.", ""),
]

ENVIRONMENTS: list[Environment] = [
    Environment(spec.id, "Environments", spec.title, spec.blurb, "")
    for spec in ENV_SPECS
] + OPERATIONS


# ── reusable field sets ──────────────────────────────────────────────────────

DB_ENGINES = [
    opt("mssql", "SQL Server", "2025 or 2022. Linux only in this console."),
    opt("postgres", "PostgreSQL", "17. The default choice for new work."),
    opt("mysql", "MySQL", "8.4 LTS."),
]

DB_MODES = [
    opt("single", "Single node", "One VM. No failover."),
    opt("ha", "High availability", "Three or more VMs with automatic failover."),
]

HA_SHAPES = [
    opt("bilateral", "Two-node replication", "A primary and one replica. Manual failover — two "
                                             "nodes cannot arbitrate a split brain."),
    opt("cluster", "Managed cluster", "Three or more nodes with automatic failover."),
    opt("multiprimary", "Multi-primary", "Every node accepts writes. MySQL only."),
]


def db_fields(spec: EnvSpec) -> list[Field]:
    return [
        sel("engine", "Database engine", DB_ENGINES, "mssql",
            "The plan, the requirements and the node count all follow from this."),
        sel("platform", "Operating system", [
            opt("linux", "Linux", "Ubuntu 24.04 LTS."),
            opt("windows", "Windows Server", "Not automated — see the runbook."),
        ], "linux", "SQL Server on Windows is a documented manual path, not a console workload.",
            show_if={"engine": ["mssql"]}),
        sel("mode", "Deploy mode", DB_MODES, "single"),
        sel("ha_shape", "High availability shape", HA_SHAPES, "cluster",
            "Two-node replication has no arbiter. Prefer three nodes.",
            show_if={"mode": ["ha"]}),
        area("node_ips", "Node IPs", "", spec.ips(31, 32, 33),
             "One per line, as many as you need. The first is the initial primary.", hosts=True),
        txt("vip", "Virtual IP", "", spec.ip(40),
            "The address applications connect to. Must be unassigned.",
            show_if={"mode": ["ha"]}),
        txt("cluster_label", "Cluster name", "ag1", "", "Names the availability group or cluster."),
        txt("admin_user", "Provisioning admin", "provisioner",
            hint="Used by Ansible only, then disabled. Never the application's login."),
        secret("admin_password", "Provisioning admin password"),
        txt("data_dir", "Data directory", "", "/var/opt/mssql/data",
            "Put this on its own disk. A full root filesystem takes the whole VM down."),
        txt("port", "Listening port", "", "1433",
            "Restrict to application subnets at the firewall, never the whole LAN."),
        sel("mssql_version", "SQL Server version", [
            opt("2025", "2025", "Requires Ubuntu 24.04."),
            opt("2022", "2022", "Requires Ubuntu 20.04 or 22.04."),
        ], "2025", show_if={"engine": ["mssql"]}),
    ]


def db_user_fields(spec: EnvSpec) -> list[Field]:
    return [
        sel("engine", "Database engine", DB_ENGINES, "mssql"),
        area("node_ips", "Node IPs", "", spec.ips(31, 32, 33),
             "Every node. Logins must exist on all of them, not just the primary.", hosts=True),
        txt("cluster_label", "Cluster name", "ag1"),
        txt("admin_user", "Provisioning admin", "provisioner"),
        secret("admin_password", "Provisioning admin password"),
        area("components", "Components to provision", "apim\nis",
             "apim\nis\nsonarqube",
             "One per line. Each gets its own login and its own database — never a shared account."),
        txt("app_user_prefix", "Login name prefix", "wso2",
            hint="Produces wso2_apim, wso2_is, and so on."),
        secret("app_password", "Runtime login password"),
        txt("login_sid", "Fixed login SID", "",
            "0x57534F3243415242000000000000ABCD",
            "SQL Server only. Identical on every replica, so a failover never orphans the user. "
            "Leave empty to derive one deterministically from the login name."),
        sel("lock_builtins", "Lock built-in superusers", [
            opt("yes", "Yes — disable or rename them", "Recommended."),
            opt("no", "No — leave them enabled", "Only while you still need them."),
        ], "yes"),
    ]


def object_fields(spec: EnvSpec) -> list[Field]:
    return [
        sel("provider", "Provider", [
            opt("minio", "MinIO", "S3-compatible, erasure coded."),
            opt("seaweedfs", "SeaweedFS", "Lower memory, better for very large object counts."),
        ], "minio"),
        sel("mode", "Deploy mode", [
            opt("single", "Standalone", "One node. No redundancy."),
            opt("dist", "Distributed", "2–4 nodes with erasure coding."),
        ], "dist"),
        txt("drives_per_node", "Drives per node", "4", "",
            "Minimum four for erasure coding. Raw disks, not a RAID volume. Every node "
            "must present the same count.", show_if={"mode": ["dist"]}),
        area("node_ips", "Node IPs", "", spec.ips(41, 42, 43, 44),
             "One per line, as many as you need. Every node must present an identical "
             "disk layout.", hosts=True),
        txt("console_domain", "Console domain", "", f"objects-{spec.id}.example.com"),
        txt("admin_user", "Root user", "minioadmin"),
        secret("admin_password", "Root password"),
    ]


def monitoring_fields(spec: EnvSpec) -> list[Field]:
    return [
        sel("stack", "Monitoring stack", [
            opt("lgtm", "LGTM", "Loki, Grafana, Tempo, Mimir. Needs object storage."),
            opt("opensearch", "OpenSearch", "Apache 2.0. Full-text search."),
            opt("elastic", "Elastic Stack", "9.1.4. The path this lab has tested."),
        ], "lgtm", "One stack is installed. The other two are not deployed."),
        sel("placement", "Where it runs", [
            opt("cluster", "In the RKE2 cluster", "No extra VMs. Shares the cluster's fate."),
            opt("vm", "On a Docker VM", "Keeps working when the cluster is what is broken."),
        ], "cluster"),
        sel("mode", "Size", [
            opt("single", "Single node", "No redundancy."),
            opt("ha", "High availability", "Three nodes, odd count for quorum."),
        ], "single"),
        txt("cluster_name", "Cluster (kubeconfig)", f"{spec.id}-cluster", "",
            "Which cluster to install into.", show_if={"placement": ["cluster"]}),
        area("node_ips", "Docker VM IPs", "", spec.ip(50),
             "One per line. An odd count in high availability, so the cluster manager "
             "can hold quorum.", show_if={"placement": ["vm"]}, hosts=True),
        txt("dashboard_domain", "Dashboard domain", "", f"dashboard-{spec.id}.example.com"),
        secret("admin_password", "Admin password"),
        txt("retention_days", "Log retention (days)", "30", "",
            "Shortening this later does not reclaim space already written."),
        txt("object_endpoint", "Object store endpoint", "", f"http://{spec.ip(41)}:9000",
            "Loki, Tempo and Mimir each get their own bucket.",
            show_if={"stack": ["lgtm"]}),
    ]


def rke2_fields(spec: EnvSpec) -> list[Field]:
    return [
        txt("cluster_name", "Cluster name", f"{spec.id}-cluster", "",
            "Names the kubeconfig directory."),
        area("control_plane_ips", "Control plane IPs", "", spec.ips(11, 12, 13),
             "One, three or five — etcd needs an odd count to hold quorum. "
             "The first bootstraps the cluster.", hosts=True),
        area("worker_ips", "Worker IPs", "", spec.ips(21, 22, 23),
             "As many as you need. One per line, or comma separated.", hosts=True),
        txt("registration_address", "Registration address / VIP", "",
            f"rke2-{spec.id}.example.local", "One stable endpoint new nodes join through."),
        txt("rke2_version", "RKE2 version", "v1.36.1+rke2r2"),
        secret("rke2_token", "Cluster join token"),
        txt("rke2_images_local_dir", "Air-gapped image directory", "",
            "/home/bimdevops/rke2-images", "Optional. Leave empty to pull from the internet."),
    ]


def wso2_fields(spec: EnvSpec) -> list[Field]:
    env = spec.id
    return [
        txt("cluster_name", "Cluster (kubeconfig)", f"{env}-cluster"),
        txt("apim_host", "APIM host", f"apim-{env}.example.com"),
        txt("internal_gw_host", "Internal gateway host", f"internal-gw-{env}.example.com"),
        txt("external_gw_host", "External gateway host", f"external-gw-{env}.example.com"),
        txt("is_host", "Identity Server host", f"wso2is-{env}.example.com"),
        txt("mssql_host", "Database host", "", spec.ip(40),
            "The virtual IP in a highly available setup."),
        txt("wso2_db_user", "Database login", "wso2_apim",
            hint="Must match a login created by Database users."),
        secret("wso2_db_password", "Database password"),
        txt("logstash_host", "Log shipper host", "", spec.ip(50), "Optional."),
    ]


# ── the registry ─────────────────────────────────────────────────────────────

def _env_stack(spec: EnvSpec) -> list[Workload]:
    """The complete workload set for one environment.

    Every `full` environment gets the same shape. Machine counts are not fixed
    here — each workload is sized when you configure it, so three environments of
    three machines and three of fifteen are the same amount of code.

    Example addresses come from the environment's subnet, and are placeholders
    only: nothing is deployed from them.
    """
    E = spec.id
    return [
        Workload(f"{E}_docker", E, "1", "Docker + Traefik",
                 "Docker CE, then Traefik owning the shared platform network.",
                 "docker-traefik-up",
                 [txt("docker_ip", "Docker VM IP", "", spec.ip(50), hosts=True)],
                 docs="docker-traefik-up"),
        Workload(f"{E}_object", E, "2", "Object storage",
                 "S3-compatible storage. Backs monitoring, database backups and cluster snapshots.",
                 "object-store-up", object_fields(spec), requires=[f"{E}_docker"],
                 docs="object-store-up"),
        Workload(f"{E}_monitoring", E, "3", "Monitoring",
                 "One stack — logs, metrics and traces for this environment.",
                 "monitoring-up", monitoring_fields(spec), requires=[f"{E}_object"],
                 docs="monitoring-up"),
        Workload(f"{E}_rke2", E, "4", "RKE2 cluster",
                 "Kubernetes with the bundled Canal CNI. Ingress disabled so Istio owns 443.",
                 "rke2-cluster-up", rke2_fields(spec), docs="rke2-cluster-up"),
        Workload(f"{E}_rke2_scale", E, "4b", "Add or scale nodes",
                 "Joins new addresses. Nodes already in the cluster are skipped.",
                 "rke2-scale-up", rke2_fields(spec), requires=[f"{E}_rke2"],
                 always=True, docs="rke2-scale-up"),
        Workload(f"{E}_istio", E, "5", "MetalLB + Istio ambient",
                 "LoadBalancer addresses, then the ambient mesh and one shared gateway.",
                 "k8s-istio-up",
                 [txt("cluster_name", "Cluster (kubeconfig)", f"{E}-cluster"),
                  txt("metallb_ip_range", "MetalLB address range", "",
                      f"{spec.ip(200)}-{spec.ip(220)}",
                      "A contiguous block of unassigned addresses on the node subnet.")],
                 requires=[f"{E}_rke2"], docs="k8s-istio-up"),
        Workload(f"{E}_argocd", E, "6", "ArgoCD",
                 "GitOps delivery, routed over the shared gateway.",
                 "k8s-argocd-up",
                 [txt("cluster_name", "Cluster (kubeconfig)", f"{E}-cluster"),
                  txt("argocd_host", "ArgoCD host", f"argocd-{E}.example.com")],
                 requires=[f"{E}_istio"], docs="k8s-argocd-up"),
        Workload(f"{E}_headlamp", E, "7", "Headlamp",
                 "Cluster dashboard. Skips itself without failing if the chart repo is blocked.",
                 "k8s-headlamp-up",
                 [txt("cluster_name", "Cluster (kubeconfig)", f"{E}-cluster"),
                  txt("headlamp_host", "Headlamp host", f"headlamp-{E}.example.com")],
                 requires=[f"{E}_istio"], docs="k8s-headlamp-up"),
        Workload(f"{E}_db", E, "8", "Database engine",
                 "Install and harden a database engine on your own VMs.",
                 "db-engine-up", db_fields(spec), docs="db-engine-up"),
        Workload(f"{E}_db_users", E, "8b", "Database users",
                 "A provisioning admin, then one least-privilege login per component.",
                 "db-users-up", db_user_fields(spec), requires=[f"{E}_db"],
                 docs="db-users-up"),
        Workload(f"{E}_wso2_apim", E, "9", "WSO2 API Manager",
                 "Control plane and both gateways, rendered with this environment's hostnames.",
                 "k8s-wso2-apim-up", wso2_fields(spec),
                 requires=[f"{E}_istio", f"{E}_db_users"], docs="k8s-wso2-apim-up"),
        Workload(f"{E}_wso2_is", E, "10", "WSO2 Identity Server",
                 "Identity Server for this environment.",
                 "k8s-wso2-is-up", wso2_fields(spec),
                 requires=[f"{E}_istio", f"{E}_db_users"], docs="k8s-wso2-is-up"),
    ]


def _shared_stack(spec: EnvSpec) -> list[Workload]:
    """Only what several environments have in common. Kept deliberately small:
    anything an environment could reasonably own, it owns."""
    E = spec.id
    return [
        Workload(f"{E}_docker", E, "1", "Docker + Traefik",
                 "Docker CE, then Traefik owning the shared platform network.",
                 "docker-traefik-up",
                 [txt("docker_ip", "Docker VM IP", "", spec.ip(10), hosts=True)],
                 docs="docker-traefik-up"),
        Workload(f"{E}_gitlab", E, "2", "Source control + SonarQube",
                 "GitLab CE with its runner and container registry, PostgreSQL, Dockhand, "
                 "SonarQube.",
                 "gitlab-platform-up",
                 [txt("docker_ip", "Docker VM IP", "", spec.ip(10), hosts=True),
                  txt("gitlab_domain", "GitLab domain", "gitlab.example.com"),
                  txt("gitlab_registry_domain", "Registry domain", "registry.example.com"),
                  txt("dockhand_domain", "Dockhand domain", "dockhand.example.com"),
                  txt("sonarqube_domain", "SonarQube domain", "sonar.example.com"),
                  secret("gitlab_runner_token", "Runner token")],
                 requires=[f"{E}_docker"], docs="gitlab-platform-up"),
    ]


def _build_registry() -> list[Workload]:
    """Instantiate every declared environment, then the operational sections.

    Adding an environment to config/environments.yml adds its whole stack here
    with no code change.
    """
    out: list[Workload] = []
    for spec in ENV_SPECS:
        out.extend(_env_stack(spec) if spec.stack == FULL else _shared_stack(spec))
    out.extend(_OPERATIONS_WORKLOADS)
    return out


_OPERATIONS_WORKLOADS: list[Workload] = [
    # ── certificates ──
    Workload("certs_certmanager", "certs", "1", "cert-manager + internal CA",
             "Installs cert-manager and a self-signed root, so certificates renew themselves.",
             "k8s-certmanager-up",
             [txt("cluster_name", "Cluster (kubeconfig)", "uat-cluster")],
             docs="k8s-certmanager-up"),
    Workload("certs_k8s", "certs", "2", "Kubernetes gateway certificate",
             "The TLS secret the shared Istio gateway reads. Paste a PEM, or leave both empty "
             "and cert-manager issues and renews it.",
             "k8s-cert-secret",
             [txt("cluster_name", "Cluster (kubeconfig)", "uat-cluster"),
              txt("namespace", "Namespace", "istio-system",
                  hint="The shared gateway only reads its own namespace."),
              txt("secret_name", "Secret name", "wso2-ingress-cert"),
              txt("cert_dns", "DNS names", "*.example.com",
                  hint="One wildcard covering every host."),
              area("cert_pem", "Certificate PEM", "", "-----BEGIN CERTIFICATE-----",
                   "Leave empty to use cert-manager."),
              area("key_pem", "Private key PEM", "", "-----BEGIN PRIVATE KEY-----",
                   "Leave empty to use cert-manager.")],
             docs="k8s-cert-secret"),
    Workload("certs_traefik", "certs", "3", "Traefik certificate",
             "The default certificate every Traefik router uses. Re-run to rotate.",
             "traefik-cert-apply",
             [area("docker_ips", "Traefik VM IPs", "", "192.168.66.10\n192.168.65.40", hosts=True),
              area("cert_pem", "Certificate PEM", "", "-----BEGIN CERTIFICATE-----"),
              area("key_pem", "Private key PEM", "", "-----BEGIN PRIVATE KEY-----")],
             docs="traefik-cert-apply"),

    # ── secrets ──
    Workload("secrets_vault", "secrets", "1", "Infisical vault",
             "Self-hosted secrets management, so credentials stop travelling on command lines.",
             "vault-up",
             [txt("docker_ip", "Vault VM IP", "", "192.168.66.30", hosts=True),
              txt("vault_domain", "Vault domain", "vault.example.com"),
              secret("admin_password", "Initial admin password"),
              txt("project_slug", "Project slug", "autoprovision")],
             docs="vault-up"),

    # ── backups ──
    Workload("backups_etcd", "backups", "1", "Cluster state snapshots",
             "Daily etcd snapshots on every RKE2 server, plus one immediately.",
             "k8s-etcd-backup",
             [area("control_plane_ips", "RKE2 server IPs", "", "192.168.51.11", hosts=True),
              txt("cluster_name", "Cluster (kubeconfig)", "prod-cluster"),
              txt("snapshot_cron", "Schedule", "0 2 * * *"),
              txt("snapshot_retention", "Snapshots to keep", "14")],
             always=True, docs="k8s-etcd-backup"),
    Workload("backups_db", "backups", "2", "Database backups",
             "Full daily, incremental every 15 minutes, with retention pruning. Primary-aware, "
             "so backups follow a failover.",
             "db-backup-setup",
             [sel("engine", "Database engine", DB_ENGINES, "mssql"),
              area("node_ips", "Database node IPs", "", "192.168.51.31", hosts=True),
              txt("admin_user", "Provisioning admin", "provisioner"),
              secret("admin_password", "Provisioning admin password"),
              txt("backup_dir", "Backup directory", "/var/opt/mssql/backup",
                  hint="Point this at NFS or NAS. A backup on the same disk does not survive the VM."),
              txt("retention_days", "Retention (days)", "7")],
             always=True, docs="db-backup-setup"),
    Workload("backups_object", "backups", "3", "Object store replication",
             "Replicates buckets to a second site. A single cluster in one rack is not "
             "disaster recovery.",
             "object-replicate",
             [txt("source_endpoint", "Source endpoint", "", "http://192.168.51.60:9000"),
              txt("target_endpoint", "Target endpoint", "", "http://dr.example.com:9000"),
              secret("target_access_key", "Target access key"),
              secret("target_secret_key", "Target secret key")],
             always=True, docs="object-replicate"),

    # ── danger zone ──
    Workload("danger_db_clean", "danger", "1", "Reset the database cluster",
             "Removes the cluster manager, the availability group, its endpoint and certificate "
             "on every node. The engine and your databases stay.",
             "db-cluster-clean",
             [sel("engine", "Database engine", DB_ENGINES, "mssql"),
              area("node_ips", "Node IPs", "", "192.168.51.31", hosts=True),
              txt("cluster_label", "Cluster name", "prodag",
                  hint="Type this again below to confirm."),
              txt("vip", "Virtual IP", "", "192.168.51.40",
                  hint="So a stranded address is released."),
              txt("admin_user", "Provisioning admin", "provisioner"),
              secret("admin_password", "Provisioning admin password")],
             destructive=True, confirm_field="cluster_label", docs="db-cluster-clean"),
    Workload("danger_sonarqube_clean", "danger", "2", "Uninstall SonarQube",
             "Removes the container, its volumes and the sonarqube database. GitLab's database "
             "is never touched.",
             "sonarqube-clean",
             [txt("docker_ip", "GitLab VM IP", "", "192.168.66.10",
                  hint="Type this again below to confirm.", hosts=True),
              sel("purge_data", "Purge data", [
                  opt("true", "Yes — wipe volumes and database"),
                  opt("false", "No — keep data, remove the container only")], "true")],
             destructive=True, confirm_field="docker_ip", docs="sonarqube-clean"),
    Workload("danger_sonarqube_up", "danger", "3", "Reinstall SonarQube",
             "Recreates the database if missing and force-recreates just the SonarQube container. "
             "PostgreSQL and GitLab keep running.",
             "sonarqube-up",
             [txt("docker_ip", "GitLab VM IP", "", "192.168.66.10", hosts=True),
              txt("sonarqube_domain", "SonarQube domain", "sonar.example.com")],
             docs="sonarqube-up"),
]

WORKLOADS: list[Workload] = _build_registry()

BY_ID: dict[str, Workload] = {w.id: w for w in WORKLOADS}
ALL_TRACKS: list[str] = [w.id for w in WORKLOADS]      # derived, never hand-maintained
DESTRUCTIVE: set[str] = {w.id for w in WORKLOADS if w.destructive}

# Field keys whose values must never reach the database.
SECRET_KEYS: set[str] = {
    f.key for w in WORKLOADS for f in w.fields if f.type == "password"
} | {"cert_pem", "key_pem"}


def registry_payload() -> dict[str, Any]:
    return {
        "environments": [
            {"id": e.id, "group": e.group, "title": e.title, "blurb": e.blurb, "meta": e.meta}
            for e in ENVIRONMENTS
        ],
        "workloads": [w.as_dict() for w in WORKLOADS],
    }


def defaults_for(workload_id: str) -> dict[str, str]:
    w = BY_ID.get(workload_id)
    return {f.key: f.default for f in w.fields} if w else {}
