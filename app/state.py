"""Persisted state: saved form values and per-step install status.

SQLite, because the jump host should not need a database server to run the thing
that installs database servers.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime

from .workloads import BY_ID, SECRET_KEYS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DB = os.path.join(BASE_DIR, "data", "state.db")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(STATE_DB), exist_ok=True)
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                workload TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS install_status (
                workload TEXT NOT NULL,
                step TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (workload, step))""")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                workload TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                duration_s REAL)""")
        conn.commit()


# ── saved form values ────────────────────────────────────────────────────────

def read_targets() -> dict:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT workload, data FROM targets").fetchall()
    out = {}
    for row in rows:
        try:
            out[row["workload"]] = json.loads(row["data"])
        except (ValueError, TypeError):
            out[row["workload"]] = {}
    return out


def save_target(workload: str, data: dict) -> bool:
    """Persist everything except secrets. Unknown workloads are rejected loudly
    rather than silently discarded — that failure mode hid a real bug for months."""
    if workload not in BY_ID:
        return False
    init_db()
    safe = {k: v for k, v in (data or {}).items()
            if k not in SECRET_KEYS and k not in ("workload", "track", "force", "confirm",
                                                  "ssh_user", "ssh_pass")}
    with _connect() as conn:
        conn.execute("""
            INSERT INTO targets (workload, data, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(workload) DO UPDATE SET data = excluded.data,
                                                updated_at = excluded.updated_at""",
                     (workload, json.dumps(safe), utc_now()))
        conn.commit()
    return True


# ── per-step install status ──────────────────────────────────────────────────

def set_step_status(workload: str, step: str, status: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("""
            INSERT INTO install_status (workload, step, status, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(workload, step) DO UPDATE SET status = excluded.status,
                                                      updated_at = excluded.updated_at""",
                     (workload, step, status, utc_now()))
        conn.commit()


def steps_done(workload: str) -> dict[str, str]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT step, status FROM install_status WHERE workload = ?", (workload,)).fetchall()
    return {r["step"]: r["status"] for r in rows}


def reset_workload(workload: str) -> int:
    init_db()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM install_status WHERE workload = ?", (workload,))
        conn.commit()
        return cur.rowcount


def aggregate(steps: dict[str, str]) -> str:
    if not steps:
        return "idle"
    vals = list(steps.values())
    if any(v == "failed" for v in vals):
        return "failed"
    if all(v == "completed" for v in vals):
        return "completed"
    return "partial"


def status_map() -> dict:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT workload, step, status FROM install_status").fetchall()
        durations = conn.execute("""
            SELECT workload, duration_s, finished_at FROM runs
            WHERE finished_at IS NOT NULL
            GROUP BY workload HAVING MAX(finished_at)""").fetchall()
    by_workload: dict[str, dict] = {}
    for r in rows:
        by_workload.setdefault(r["workload"], {})[r["step"]] = r["status"]
    dur = {r["workload"]: r["duration_s"] for r in durations}
    return {
        w: {"status": aggregate(steps), "steps": steps, "durationSeconds": dur.get(w)}
        for w, steps in by_workload.items()
    }


# ── run history ──────────────────────────────────────────────────────────────

def run_started(run_id: str, workload: str, action: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs (id, workload, action, status, started_at) "
            "VALUES (?, ?, ?, 'running', ?)", (run_id, workload, action, utc_now()))
        conn.commit()


def run_finished(run_id: str, status: str, duration_s: float) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, duration_s = ? WHERE id = ?",
            (status, utc_now(), duration_s, run_id))
        conn.commit()


def recent_runs(limit: int = 40) -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, workload, action, status, started_at, finished_at, duration_s "
            "FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
