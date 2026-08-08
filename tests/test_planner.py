"""Tests for the planner — the code that decides what runs against real infrastructure.

These are the highest-value tests in the repository. A bug here does not throw an
exception, it quietly runs the wrong playbook against the wrong hosts.
"""

import pytest

from app.planner import (
    ENGINES,
    SUPPORTED_ACTIONS,
    PlanError,
    ip_list,
    plan,
    safe_abs_path,
    safe_name,
)
from app.workloads import BY_ID, DESTRUCTIVE, WORKLOADS

# ── registry integrity ───────────────────────────────────────────────────────

def test_every_workload_action_has_a_planner():
    missing = sorted({w.action for w in WORKLOADS} - SUPPORTED_ACTIONS)
    assert missing == [], f"workloads reference actions with no planner: {missing}"


def test_no_workload_depends_on_something_that_does_not_exist():
    dangling = sorted({d for w in WORKLOADS for d in w.requires if d not in BY_ID})
    assert dangling == []


def test_workload_ids_are_unique():
    ids = [w.id for w in WORKLOADS]
    assert len(ids) == len(set(ids))


def test_dependency_graph_is_acyclic():
    seen, stack = set(), set()

    def walk(wid):
        if wid in stack:
            pytest.fail(f"dependency cycle through {wid}")
        if wid in seen:
            return
        stack.add(wid)
        for dep in BY_ID[wid].requires:
            walk(dep)
        stack.discard(wid)
        seen.add(wid)

    for w in WORKLOADS:
        walk(w.id)


def test_destructive_workloads_declare_a_confirmation_field():
    for wid in DESTRUCTIVE:
        wl = BY_ID[wid]
        assert wl.confirm_field, f"{wid} is destructive but names no confirmation field"
        assert any(f.key == wl.confirm_field for f in wl.fields), \
            f"{wid} confirms on '{wl.confirm_field}', which is not one of its fields"


def test_secret_fields_are_never_given_defaults():
    for w in WORKLOADS:
        for f in w.fields:
            if f.type == "password":
                assert f.default == "", f"{w.id}.{f.key} ships a default password"


# ── input validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("10.0.0.1", ["10.0.0.1"]),
    ("10.0.0.1,10.0.0.2", ["10.0.0.1", "10.0.0.2"]),
    ("10.0.0.1\n10.0.0.2\n", ["10.0.0.1", "10.0.0.2"]),
    ("  ", []),
    (None, []),
    (["10.0.0.1"], ["10.0.0.1"]),
])
def test_ip_list_accepts_the_shapes_operators_actually_paste(raw, expected):
    assert ip_list(raw) == expected


@pytest.mark.parametrize("bad", ["../etc", "a/b", "a b", "a;rm -rf /", "", "a$b"])
def test_safe_name_rejects_traversal_and_shell_metacharacters(bad):
    with pytest.raises(PlanError):
        safe_name(bad, "Cluster name")


@pytest.mark.parametrize("bad", ["relative/path", "/var/../etc", "/var/lib;rm", ""])
def test_safe_abs_path_rejects_anything_that_could_escape(bad):
    with pytest.raises(PlanError):
        safe_abs_path(bad, "Data directory")


# ── database engine planning ─────────────────────────────────────────────────

def _db(**over):
    body = {"engine": "mssql", "mode": "single", "node_ips": "10.0.0.1",
            "admin_password": "pw", "cluster_label": "ag1"}
    body.update(over)
    return body


def test_single_node_uses_the_single_playbook():
    p = plan("db-engine-up", _db())
    assert p["steps"][0]["playbook"] == "ansible/db/mssql_single.yml"
    assert p["inventory"] == {"db_mssql": ["10.0.0.1"]}


def test_single_node_rejects_more_than_one_address():
    with pytest.raises(PlanError, match="exactly one"):
        plan("db-engine-up", _db(node_ips="10.0.0.1\n10.0.0.2"))


def test_ha_cluster_needs_three_nodes():
    with pytest.raises(PlanError, match="split brain"):
        plan("db-engine-up", _db(mode="ha", ha_shape="cluster", node_ips="10.0.0.1\n10.0.0.2"))


def test_ha_cluster_rejects_an_even_node_count():
    with pytest.raises(PlanError, match="quorum"):
        plan("db-engine-up",
             _db(mode="ha", ha_shape="cluster", node_ips="1.1.1.1\n1.1.1.2\n1.1.1.3\n1.1.1.4"))


def test_ha_cluster_accepts_three_nodes():
    p = plan("db-engine-up",
             _db(mode="ha", ha_shape="cluster", node_ips="1.1.1.1\n1.1.1.2\n1.1.1.3"))
    assert p["steps"][0]["playbook"] == "ansible/db/mssql_ag.yml"


def test_bilateral_takes_exactly_two_nodes():
    with pytest.raises(PlanError, match="exactly two"):
        plan("db-engine-up", _db(mode="ha", ha_shape="bilateral", node_ips="1.1.1.1"))


def test_multi_primary_is_rejected_for_engines_that_cannot_do_it():
    for engine in ("mssql", "postgres"):
        with pytest.raises(PlanError, match="MySQL-only"):
            plan("db-engine-up", _db(engine=engine, mode="ha", ha_shape="multiprimary",
                                     node_ips="1.1.1.1\n1.1.1.2\n1.1.1.3"))


def test_multi_primary_is_allowed_for_mysql():
    p = plan("db-engine-up", _db(engine="mysql", mode="ha", ha_shape="multiprimary",
                                 node_ips="1.1.1.1\n1.1.1.2\n1.1.1.3",
                                 data_dir="/var/lib/mysql"))
    assert "mysql" in p["steps"][0]["playbook"]


def test_sql_server_on_windows_stops_with_a_pointer_to_the_runbook():
    with pytest.raises(PlanError, match="windows-ad-ag.md"):
        plan("db-engine-up", _db(platform="windows"))


def test_windows_is_only_rejected_for_sql_server():
    # The field is not shown for other engines; a stale value must not block them.
    p = plan("db-engine-up", _db(engine="postgres", platform="windows",
                                 data_dir="/var/lib/postgresql/17/main"))
    assert "postgres" in p["steps"][0]["playbook"]


def test_every_engine_plans_a_hardening_step():
    for engine, spec in ENGINES.items():
        p = plan("db-engine-up", _db(engine=engine, data_dir=spec["data_dir"]))
        assert p["steps"][-1]["playbook"] == "ansible/db/harden.yml", \
            f"{engine} does not harden after install"


def test_database_password_never_lands_in_the_inventory_groups():
    p = plan("db-engine-up", _db(admin_password="hunter2"))
    assert "hunter2" not in str(p["inventory"])


# ── database users ───────────────────────────────────────────────────────────

def _users(**over):
    body = {"engine": "mssql", "node_ips": "10.0.0.1", "components": "apim\nis",
            "app_password": "pw", "admin_password": "adm"}
    body.update(over)
    return body


def test_users_requires_at_least_one_component():
    with pytest.raises(PlanError, match="at least one component"):
        plan("db-users-up", _users(components="  "))


def test_users_requires_a_runtime_password():
    with pytest.raises(PlanError, match="password is required"):
        plan("db-users-up", _users(app_password=""))


def test_locking_builtins_adds_a_second_step():
    on = plan("db-users-up", _users(lock_builtins="yes"))
    off = plan("db-users-up", _users(lock_builtins="no"))
    assert len(on["steps"]) == len(off["steps"]) + 1
    assert on["steps"][-1]["playbook"] == "ansible/db/lock_builtins.yml"


def test_components_reach_the_playbook_as_a_list():
    p = plan("db-users-up", _users(components="apim, is , sonarqube"))
    assert p["steps"][0]["extra_vars"]["components"] == ["apim", "is", "sonarqube"]


# ── object storage ───────────────────────────────────────────────────────────

def _obj(**over):
    body = {"provider": "minio", "mode": "dist", "nodes": "4",
            "node_ips": "1.1.1.1\n1.1.1.2\n1.1.1.3\n1.1.1.4", "drives_per_node": "4"}
    body.update(over)
    return body


def test_distributed_object_storage_needs_four_drives_per_node():
    with pytest.raises(PlanError, match="parity budget"):
        plan("object-store-up", _obj(drives_per_node="2"))


def test_distributed_object_storage_needs_at_least_two_nodes():
    with pytest.raises(PlanError, match="at least two"):
        plan("object-store-up", _obj(node_ips="1.1.1.1"))


def test_standalone_object_storage_takes_one_node():
    p = plan("object-store-up", _obj(mode="single", node_ips="1.1.1.1"))
    assert p["inventory"] == {"object_store": ["1.1.1.1"]}


def test_object_storage_caps_at_four_nodes():
    with pytest.raises(PlanError, match="up to four"):
        plan("object-store-up", _obj(node_ips="\n".join(f"1.1.1.{i}" for i in range(1, 6))))


# ── monitoring ───────────────────────────────────────────────────────────────

def test_lgtm_refuses_to_run_without_object_storage():
    with pytest.raises(PlanError, match="object storage"):
        plan("monitoring-up", {"stack": "lgtm", "placement": "cluster", "object_endpoint": ""})


def test_lgtm_plans_once_an_endpoint_is_given():
    p = plan("monitoring-up", {"stack": "lgtm", "placement": "cluster",
                               "object_endpoint": "http://10.0.0.60:9000",
                               "cluster_name": "uat-cluster"})
    assert p["steps"][0]["playbook"] == "ansible/monitoring/lgtm.yml"
    assert p["inventory"] == {}


def test_elastic_needs_no_object_storage():
    p = plan("monitoring-up", {"stack": "elastic", "placement": "cluster",
                               "cluster_name": "uat-cluster"})
    assert p["steps"][0]["playbook"] == "ansible/monitoring/elk_stack.yml"


def test_monitoring_on_vms_rejects_an_even_node_count_in_ha():
    with pytest.raises(PlanError, match="quorum"):
        plan("monitoring-up", {"stack": "opensearch", "placement": "vm", "mode": "ha",
                               "node_ips": "1.1.1.1\n1.1.1.2"})


def test_monitoring_on_a_vm_installs_docker_first():
    p = plan("monitoring-up", {"stack": "opensearch", "placement": "vm", "mode": "single",
                               "node_ips": "1.1.1.1"})
    assert p["steps"][0]["playbook"] == "ansible/platform/docker_vm_base.yml"


# ── kubernetes ───────────────────────────────────────────────────────────────

def test_rke2_rejects_an_even_control_plane_count():
    with pytest.raises(PlanError, match="etcd quorum"):
        plan("rke2-cluster-up", {"control_plane_ips": "1.1.1.1\n1.1.1.2", "cluster_name": "c"})


def test_rke2_allows_a_single_control_plane():
    p = plan("rke2-cluster-up", {"control_plane_ips": "1.1.1.1", "cluster_name": "uat-cluster"})
    assert p["inventory"]["rke2_servers"] == ["1.1.1.1"]


def test_scaling_always_reruns():
    p = plan("rke2-scale-up", {"control_plane_ips": "1.1.1.1", "cluster_name": "uat-cluster"})
    assert p["steps"][0]["always"] is True


def test_cluster_name_cannot_escape_the_kubeconfig_directory():
    with pytest.raises(PlanError):
        plan("k8s-argocd-up", {"cluster_name": "../../etc"})


# ── certificates ─────────────────────────────────────────────────────────────

def test_certificate_requires_both_halves_or_neither():
    with pytest.raises(PlanError, match="both"):
        plan("k8s-cert-secret", {"cert_pem": "-----BEGIN CERTIFICATE-----", "key_pem": ""})


def test_empty_certificate_hands_the_job_to_cert_manager():
    p = plan("k8s-cert-secret", {"cluster_name": "uat-cluster"})
    assert p["steps"][0]["extra_vars"]["use_certmanager"] is True
    assert not p.get("needs_cert")


def test_provided_certificate_is_staged():
    p = plan("k8s-cert-secret", {"cluster_name": "uat-cluster",
                                 "cert_pem": "cert", "key_pem": "key"})
    assert p["needs_cert"] is True


# ── backups ──────────────────────────────────────────────────────────────────

def test_backups_always_run_and_are_never_skipped():
    p = plan("db-backup-setup", {"engine": "mssql", "node_ips": "1.1.1.1",
                                 "admin_password": "pw", "backup_dir": "/var/backups/db"})
    assert p["steps"][0]["always"] is True


def test_backup_directory_must_be_an_absolute_path():
    with pytest.raises(PlanError):
        plan("db-backup-setup", {"engine": "mssql", "node_ips": "1.1.1.1",
                                 "backup_dir": "backups; rm -rf /"})


def test_etcd_snapshots_always_run():
    p = plan("k8s-etcd-backup", {"control_plane_ips": "1.1.1.1", "cluster_name": "prod-cluster"})
    assert p["steps"][0]["always"] is True


# ── every action produces a well-formed plan ─────────────────────────────────

def test_unknown_action_is_rejected():
    with pytest.raises(PlanError, match="Unsupported"):
        plan("definitely-not-a-real-action", {})
