"""Every machine this control plane is managing, derived from what you configured.

At three machines you keep the topology in your head. At fifty you do not, and
the question that matters becomes "which machines am I actually managing, and what
does each one do?" Nothing else in the system can answer that: the inventory files
are per-run, and Ansible has no memory between them.

This reads the saved configuration, collects every field marked as carrying a
machine address, and reports one row per host. It is not a discovery scan — it
reflects intent, not reality. A machine you configured but never provisioned still
appears, which is usually exactly what you want to see.
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict

from . import state
from .workloads import BY_ID, ENV_SPECS, WORKLOADS

# Which field key implies which Ansible role. Anything unlisted falls back to the
# workload's own title, which is a worse label but never a wrong one.
ROLE_BY_FIELD = {
    "control_plane_ips": "Kubernetes control plane",
    "worker_ips": "Kubernetes worker",
    "node_ips": None,           # depends on the workload — resolved below
    "docker_ip": "Docker host",
    "docker_ips": "Docker host",
}

ROLE_BY_ACTION = {
    "db-engine-up": "Database",
    "db-users-up": "Database",
    "db-backup-setup": "Database",
    "db-cluster-clean": "Database",
    "object-store-up": "Object storage",
    "monitoring-up": "Monitoring",
    "vault-up": "Vault",
    "gitlab-platform-up": "Source control",
    "docker-traefik-up": "Docker host",
    "traefik-cert-apply": "Docker host",
    "k8s-etcd-backup": "Kubernetes control plane",
}


def _split(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").replace(",", " ").split() if p.strip()]


def _networks(hosts) -> list[str]:
    """The /24s these addresses actually sit on, most-populated first.

    Reported rather than the configured subnet, because the config's subnet only
    seeds form placeholders and diverges the moment someone types a real address.
    """
    counts: dict[str, int] = defaultdict(int)
    for host in hosts:
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            continue          # a hostname, not an address
        if addr.version == 4:
            counts[str(ipaddress.ip_network(f"{addr}/24", strict=False))] += 1
    return [net for net, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _sort_key(host: str):
    """Sort addresses numerically, hostnames alphabetically, addresses first."""
    try:
        return (0, int(ipaddress.ip_address(host)), "")
    except ValueError:
        return (1, 0, host.lower())


def survey() -> dict:
    targets = state.read_targets()
    status = state.status_map()

    hosts: dict[str, dict] = defaultdict(
        lambda: {"roles": set(), "environments": set(), "workloads": []})

    for wl in WORKLOADS:
        saved = targets.get(wl.id) or {}
        if not saved:
            continue
        for f in wl.fields:
            if not f.hosts:
                continue
            for host in _split(saved.get(f.key, "")):
                entry = hosts[host]
                role = ROLE_BY_FIELD.get(f.key) or ROLE_BY_ACTION.get(wl.action) or wl.title
                entry["roles"].add(role)
                entry["environments"].add(wl.env)
                entry["workloads"].append({
                    "id": wl.id,
                    "ordinal": wl.ordinal,
                    "title": wl.title,
                    "status": status.get(wl.id, {}).get("status", "idle"),
                })

    rows = [
        {
            "host": host,
            "roles": sorted(v["roles"]),
            "environments": sorted(v["environments"]),
            "workloads": v["workloads"],
            # A machine carrying several unrelated roles is worth noticing. It is
            # legitimate in a lab and a bad idea in production.
            "shared": len(v["roles"]) > 1,
        }
        for host, v in sorted(hosts.items(), key=lambda kv: _sort_key(kv[0]))
    ]

    by_env: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for env in row["environments"]:
            by_env[env].add(row["host"])

    return {
        "hosts": rows,
        "totalHosts": len(rows),
        "environments": [
            {
                "id": spec.id,
                "title": spec.title,
                "hostCount": len(by_env.get(spec.id, ())),
                # The networks actually in use, not the placeholder subnet from the
                # config — showing 192.168.66.0/24 next to machines on 10.20.x is
                # worse than showing nothing.
                "networks": _networks(by_env.get(spec.id, ())),
            }
            for spec in ENV_SPECS
        ],
        "operations": [
            {"id": env, "hostCount": len(by_env.get(env, ()))}
            for env in ("certs", "secrets", "backups", "danger")
            if by_env.get(env)
        ],
        "sharedHosts": [r["host"] for r in rows if r["shared"]],
        "unconfigured": [
            {"id": w.id, "env": w.env, "ordinal": w.ordinal, "title": w.title}
            for w in WORKLOADS
            if any(f.hosts for f in w.fields) and not (targets.get(w.id) or {})
        ],
    }


def as_inventory() -> str:
    """The whole estate as one Ansible inventory, for use outside the console.

    Credentials are deliberately absent — this is for `--list-hosts`, ad-hoc
    commands and documentation, not for a run. Real runs get a per-run inventory
    that the console writes and chmods 0600.
    """
    targets = state.read_targets()
    groups: dict[str, set[str]] = defaultdict(set)

    for wl in WORKLOADS:
        saved = targets.get(wl.id) or {}
        if not saved:
            continue
        for f in wl.fields:
            if not f.hosts:
                continue
            for host in _split(saved.get(f.key, "")):
                groups[wl.env].add(host)
                role = (ROLE_BY_FIELD.get(f.key) or ROLE_BY_ACTION.get(wl.action) or "other")
                groups[role.lower().replace(" ", "_")].add(host)

    lines = [
        "# Generated by Autoprovision — every configured machine, by environment and role.",
        "# No credentials: real runs use a per-run inventory written at 0600.",
        "",
    ]
    for group in sorted(groups):
        lines.append(f"[{group}]")
        lines.extend(sorted(groups[group], key=_sort_key))
        lines.append("")
    return "\n".join(lines)


def unknown_environments() -> list[str]:
    """Saved state referring to environments that no longer exist in the config.

    Renaming or removing an environment orphans its recorded install status. That
    is recoverable, but it should be visible rather than silently ignored.
    """
    known = {spec.id for spec in ENV_SPECS} | {"certs", "secrets", "backups", "danger"}
    saved = set(state.read_targets()) | set(state.status_map())
    return sorted({
        wid.split("_", 1)[0] for wid in saved
        if wid not in BY_ID and wid.split("_", 1)[0] not in known
    })
