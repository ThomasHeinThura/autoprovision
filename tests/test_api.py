"""API tests, focused on the guarantees that must hold even against a direct call.

The browser is not a security boundary. If bulk run excludes destructive workloads
only in JavaScript, the guarantee is decorative.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """A client with state redirected to a throwaway database."""
    tmp = tempfile.mkdtemp()
    from app import state
    monkeypatch.setattr(state, "STATE_DB", os.path.join(tmp, "state.db"))
    from app.main import app
    return TestClient(app)


# ── registry ─────────────────────────────────────────────────────────────────

def test_registry_lists_environments_and_workloads(client):
    r = client.get("/api/registry")
    assert r.status_code == 200
    body = r.json()
    assert {e["id"] for e in body["environments"]} >= {"shared", "uat", "prod", "danger"}
    assert len(body["workloads"]) > 30


def test_registry_never_ships_a_default_secret(client):
    for w in client.get("/api/registry").json()["workloads"]:
        for f in w["fields"]:
            if f["type"] == "password":
                assert f["default"] == ""


def test_uat_and_production_are_separate_environments_with_their_own_stacks(client):
    workloads = client.get("/api/registry").json()["workloads"]
    uat = {w["title"] for w in workloads if w["env"] == "uat"}
    prod = {w["title"] for w in workloads if w["env"] == "prod"}
    assert uat == prod, "the two environments should offer the same capabilities"
    for needed in ("Object storage", "Monitoring", "Database engine"):
        assert needed in uat, f"UAT is missing its own {needed}"
        assert needed in prod, f"Production is missing its own {needed}"


def test_shared_holds_only_what_both_environments_share(client):
    workloads = client.get("/api/registry").json()["workloads"]
    shared = {w["title"] for w in workloads if w["env"] == "shared"}
    assert shared == {"Docker + Traefik", "Source control + SonarQube"}


# ── destructive protection ───────────────────────────────────────────────────

def test_destructive_run_is_refused_without_confirmation(client):
    r = client.post("/api/run", json={
        "workload": "danger_db_clean",
        "values": {"engine": "mssql", "node_ips": "1.1.1.1\n1.1.1.2", "cluster_label": "prodag"},
    })
    assert r.status_code == 400
    assert "prodag" in r.json()["error"]


def test_destructive_run_is_refused_with_the_wrong_confirmation(client):
    r = client.post("/api/run", json={
        "workload": "danger_db_clean",
        "values": {"engine": "mssql", "node_ips": "1.1.1.1\n1.1.1.2", "cluster_label": "prodag"},
        "confirm": "uatag",          # a real cluster name, just not this one
    })
    assert r.status_code == 400
    assert "destroys state" in r.json()["error"]


def test_confirmation_tolerates_surrounding_whitespace(client):
    """Operators paste. Whitespace should not be the thing that stops a deliberate
    teardown, but the value itself must still match exactly."""
    r = client.post("/api/run", json={
        "workload": "danger_db_clean",
        "values": {"engine": "mssql", "node_ips": "1.1.1.1\n1.1.1.2", "cluster_label": "prodag",
                   "admin_password": "pw"},
        "confirm": "  prodag  ",
    })
    assert r.status_code == 200


def test_confirmation_cannot_be_satisfied_by_an_empty_target(client):
    r = client.post("/api/run", json={
        "workload": "danger_db_clean",
        "values": {"engine": "mssql", "node_ips": "1.1.1.1\n1.1.1.2", "cluster_label": ""},
        "confirm": "",
    })
    assert r.status_code == 400


# ── bulk run ─────────────────────────────────────────────────────────────────

def test_bulk_run_never_starts_a_destructive_workload(client):
    """The regression that motivated this: filling the availability-group teardown
    card and clicking Run All used to tear down the cluster with no confirmation."""
    r = client.post("/api/run-ready", json={"values": {
        "danger_db_clean": {"engine": "mssql", "node_ips": "1.1.1.1\n1.1.1.2",
                            "cluster_label": "prodag", "admin_password": "pw"},
        "danger_sonarqube_clean": {"docker_ip": "10.0.0.9", "purge_data": "true"},
    }})
    assert r.status_code == 200
    body = r.json()
    started = {s["workload"] for s in body["started"]}
    assert "danger_db_clean" not in started
    assert "danger_sonarqube_clean" not in started
    assert set(body["excludedDestructive"]) == {"danger_db_clean", "danger_sonarqube_clean"}


def test_bulk_run_skips_workloads_whose_dependencies_have_not_completed(client):
    r = client.post("/api/run-ready", json={"values": {
        "uat_wso2_apim": {"cluster_name": "uat-cluster", "mssql_host": "10.0.0.31",
                          "wso2_db_user": "wso2_apim"},
    }})
    started = {s["workload"] for s in r.json()["started"]}
    assert "uat_wso2_apim" not in started, "WSO2 started before Istio and the database users"


# ── unknown workloads are rejected, not silently discarded ───────────────────

@pytest.mark.parametrize("endpoint,payload", [
    ("/api/run", {"workload": "does_not_exist", "values": {}}),
    ("/api/reset", {"workload": "does_not_exist"}),
    ("/api/targets", {"workload": "does_not_exist", "values": {}}),
])
def test_unknown_workload_is_rejected_loudly(client, endpoint, payload):
    r = client.post(endpoint, json=payload)
    assert r.status_code == 400
    assert "Unknown workload" in r.json()["error"]


def test_every_registered_workload_can_be_saved_and_reset(client):
    """The bug this replaces: two workloads existed in the UI but not the backend
    registry, so their settings were silently dropped and reset returned 400."""
    for w in client.get("/api/registry").json()["workloads"]:
        assert client.post("/api/targets",
                           json={"workload": w["id"], "values": {"probe": "1"}}).status_code == 200
        assert client.post("/api/reset", json={"workload": w["id"]}).status_code == 200
        assert client.get(f"/api/log/{w['id']}").status_code == 200


# ── secrets ──────────────────────────────────────────────────────────────────

def test_saved_values_never_include_a_secret(client):
    client.post("/api/targets", json={"workload": "uat_db", "values": {
        "engine": "mssql", "node_ips": "10.0.0.1", "admin_password": "hunter2",
    }})
    saved = client.get("/api/state").json()["targets"]["uat_db"]
    assert "admin_password" not in saved
    assert "hunter2" not in str(saved)


def test_ssh_credentials_are_never_persisted(client):
    client.post("/api/targets", json={"workload": "uat_db", "values": {
        "engine": "mssql", "ssh_user": "root", "ssh_pass": "toor",
    }})
    saved = client.get("/api/state").json()["targets"]["uat_db"]
    assert "ssh_pass" not in saved and "toor" not in str(saved)


# ── preview ──────────────────────────────────────────────────────────────────

def test_preview_reports_a_playbook_that_has_not_been_written(client):
    r = client.post("/api/preview", json={"workload": "uat_db", "values": {
        "engine": "postgres", "mode": "single", "node_ips": "10.0.0.1",
        "data_dir": "/var/lib/postgresql/17/main",
    }})
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert all("exists" in s for s in steps)


def test_preview_answers_200_for_an_incomplete_configuration(client):
    """Preview is called on every keystroke. "You have not finished typing" is a
    legitimate answer to a well-formed request, not a protocol error — and a 4xx
    per keystroke makes the browser console and error monitoring useless."""
    r = client.post("/api/preview", json={"workload": "uat_db", "values": {
        "engine": "mssql", "mode": "ha", "ha_shape": "cluster", "node_ips": "10.0.0.1",
    }})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert "split brain" in body["error"]
    assert body["steps"] == []


def test_preview_still_rejects_an_unknown_workload(client):
    r = client.post("/api/preview", json={"workload": "nope", "values": {}})
    assert r.status_code == 400


def test_a_valid_preview_reports_itself_as_valid(client):
    r = client.post("/api/preview", json={"workload": "uat_db", "values": {
        "engine": "mssql", "mode": "single", "node_ips": "10.0.0.1",
        "data_dir": "/var/opt/mssql/data",
    }})
    assert r.json()["valid"] is True
    assert len(r.json()["steps"]) == 2


# ── readiness ────────────────────────────────────────────────────────────────

def test_readiness_names_what_a_workload_is_waiting_on(client):
    readiness = client.get("/api/state").json()["readiness"]
    blocked = readiness["uat_istio"]["blockedBy"]
    assert readiness["uat_istio"]["ready"] is False
    assert any(b["title"] == "RKE2 cluster" for b in blocked)


def test_workloads_with_no_dependencies_start_ready(client):
    readiness = client.get("/api/state").json()["readiness"]
    assert readiness["shared_docker"]["ready"] is True


# ── content ──────────────────────────────────────────────────────────────────

def test_missing_content_explains_how_to_add_it_rather_than_404ing(client):
    r = client.get("/api/content/not-a-real-workload/theory")
    assert r.status_code == 200
    assert "content/not-a-real-workload/theory.md" in r.text


@pytest.mark.parametrize("slug", ["..", "../../etc", "..%2f..%2fetc", ".ssh", "/etc/passwd"])
def test_content_path_cannot_escape_the_content_directory(client, slug):
    r = client.get(f"/api/content/{slug}/theory")
    assert "root:" not in r.text and "BEGIN PRIVATE KEY" not in r.text


def test_an_api_typo_returns_a_json_error_not_the_console_html(client):
    r = client.get("/api/registryy")
    assert r.status_code == 404
    assert r.json()["error"].startswith("No such endpoint")


def test_only_known_pages_are_served(client):
    assert "has been written" in client.get("/api/content/db-engine-up/passwd").text


# ── build freshness ──────────────────────────────────────────────────────────

def test_committed_console_build_is_not_older_than_its_source():
    """app/dist/ is committed, so it can silently go stale — you edit the console,
    forget to rebuild, and then spend an hour debugging a fix that is not running.
    This caught exactly that during development."""
    import os
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    dist = root / "app" / "dist" / "index.html"
    src = root / "console" / "src"

    assert dist.exists(), "app/dist/ is missing — run: cd console && npm run build"

    built = dist.stat().st_mtime
    newest = max((p.stat().st_mtime for p in src.rglob("*") if p.is_file()), default=0)
    newest_name = max(
        (p for p in src.rglob("*") if p.is_file()),
        key=lambda p: p.stat().st_mtime, default=None,
    )
    assert built >= newest, (
        f"app/dist/ is older than {os.path.relpath(newest_name, root)}. "
        "Run: cd console && npm run build — and commit the result."
    )
