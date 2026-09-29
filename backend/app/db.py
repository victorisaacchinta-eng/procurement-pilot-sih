"""
SQLite storage: evaluations, officer decisions and an access log.

DPDP-style storage limitation: evaluations older than RETENTION_DAYS are
irreversibly anonymised (bidder identity and free text removed) while the
compliance statistics stay, so audit continuity survives without keeping
personal or commercial identifiers forever.
"""
import os
import json
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "procurement_pilot.db"))
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "180"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                tender_id TEXT NOT NULL,
                bidder_name TEXT NOT NULL,
                checks_json TEXT NOT NULL,
                compliance_score INTEGER NOT NULL,
                ai_verdict TEXT NOT NULL,
                ai_reasoning TEXT NOT NULL,
                ai_source TEXT NOT NULL,
                evaluated_by TEXT,
                officer_decision TEXT,
                override_reason TEXT,
                decided_by TEXT,
                decided_role TEXT,
                decided_at TEXT,
                anonymised INTEGER NOT NULL DEFAULT 0
            )
        """)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
        for col, ddl in [("override_reason", "TEXT"), ("evaluated_by", "TEXT"), ("decided_by", "TEXT"),
                         ("decided_role", "TEXT"), ("decided_at", "TEXT"), ("anonymised", "INTEGER NOT NULL DEFAULT 0")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {ddl}")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT
            )
        """)


def log_access(username: str, role: str, action: str, detail: str = ""):
    with get_db() as conn:
        conn.execute("INSERT INTO access_log (ts, username, role, action, detail) VALUES (?,?,?,?,?)",
                     (now_iso(), username, role, action, detail))


def run_retention(days: int | None = None) -> int:
    """Anonymise evaluations older than `days`. Returns how many rows changed."""
    days = RETENTION_DAYS if days is None else days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    changed = 0
    with get_db() as conn:
        rows = conn.execute("SELECT id, bidder_name, checks_json FROM audit_log WHERE anonymised=0 AND ts < ?", (cutoff,)).fetchall()
        for r in rows:
            token = "anon-" + hashlib.sha256(f"{r['id']}:{r['bidder_name']}".encode()).hexdigest()[:10]
            checks = json.loads(r["checks_json"])
            for c in checks:
                c["reason"] = "[removed under retention policy]"
            conn.execute(
                "UPDATE audit_log SET bidder_name=?, checks_json=?, ai_reasoning=?, override_reason=NULL, anonymised=1 WHERE id=?",
                (token, json.dumps(checks), "[removed under retention policy]", r["id"]),
            )
            changed += 1
    return changed
