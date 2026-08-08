"""Environment configuration, loaded from config/environments.yml.

Environments are data, not code. This control plane is not built for one
customer's topology — you declare however many environments you need, size each
workload for the machines you actually have, and the registry follows.

The file is optional: without it the defaults below apply, so a fresh checkout
still starts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "environments.yml")

FULL = "full"
SHARED = "shared"


@dataclass(frozen=True)
class EnvSpec:
    id: str
    title: str
    stack: str = FULL
    subnet: str = "192.168.10"
    blurb: str = ""

    def ip(self, host: int) -> str:
        return f"{self.subnet}.{host}"

    def ips(self, *hosts: int) -> str:
        return "\n".join(self.ip(h) for h in hosts)


# Used when config/environments.yml is absent or unreadable.
DEFAULTS: list[EnvSpec] = [
    EnvSpec("shared", "Shared services", SHARED, "192.168.66",
            "Only what several environments genuinely share: source control, the container "
            "registry, and code quality."),
    EnvSpec("uat", "UAT", FULL, "192.168.65",
            "A complete, self-contained environment for testing."),
    EnvSpec("prod", "Production", FULL, "192.168.51",
            "A complete, self-contained environment with no runtime dependency on any other."),
]


class ConfigError(Exception):
    """The environment file exists but cannot be used. Surfaced at startup rather
    than producing a half-built registry nobody can explain."""


def _validate(raw: list[dict]) -> list[EnvSpec]:
    specs: list[EnvSpec] = []
    seen: set[str] = set()
    reserved = {"certs", "secrets", "backups", "danger", "handbook", "topology", "api"}

    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"environments[{i}] is not a mapping")
        env_id = str(entry.get("id", "")).strip()
        if not env_id:
            raise ConfigError(f"environments[{i}] has no id")
        if not env_id.replace("-", "").replace("_", "").isalnum():
            raise ConfigError(
                f"environment id '{env_id}' may contain only letters, digits, '-' and '_' — "
                "it becomes part of workload ids and URLs")
        if env_id in seen:
            raise ConfigError(f"environment id '{env_id}' is declared twice")
        if env_id in reserved:
            raise ConfigError(
                f"environment id '{env_id}' is reserved by the console. Choose another.")
        seen.add(env_id)

        stack = str(entry.get("stack", FULL)).strip() or FULL
        if stack not in (FULL, SHARED):
            raise ConfigError(
                f"environment '{env_id}' has stack '{stack}'; expected '{FULL}' or '{SHARED}'")

        specs.append(EnvSpec(
            id=env_id,
            title=str(entry.get("title") or env_id).strip(),
            stack=stack,
            subnet=str(entry.get("subnet") or "192.168.10").strip(),
            blurb=" ".join(str(entry.get("blurb") or "").split()),
        ))

    if not specs:
        raise ConfigError("no environments declared")
    return specs


def load() -> list[EnvSpec]:
    if not os.path.isfile(CONFIG_PATH):
        return list(DEFAULTS)
    try:
        import yaml
    except ImportError:
        # Ansible depends on PyYAML, so any host that can run a playbook has it.
        # A jump host without it is a broken install, not a supported setup — but
        # falling back beats refusing to start.
        return list(DEFAULTS)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}

    raw = doc.get("environments")
    if raw is None:
        return list(DEFAULTS)
    if not isinstance(raw, list):
        raise ConfigError("'environments' must be a list")
    return _validate(raw)
