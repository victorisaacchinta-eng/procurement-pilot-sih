"""
Storage: evaluations, officer decisions, the hash-chained ledger, tender
rulebooks, a translation cache and an access log.

Two backends behind one small interface:
  DATABASE_URL set   Postgres (Neon in production on Vercel)
  otherwise          SQLite file (local runs and tests)

Preview deployments share the production database URL on Vercel, so a
preview build writes into its own Postgres schema ("preview" by default,
or DB_SCHEMA) and never touches production tables.

DPDP-style storage limitation: evaluations older than RETENTION_DAYS are
irreversibly anonymised (bidder identity and free text removed) while the
compliance statistics stay, so audit continuity survives without keeping
commercial identifiers forever. Each anonymisation is itself written to the
ledger, so the chain still verifies afterwards.
"""
import os
import re
import json
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

DATABASE_URL = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
_default_sqlite = "/tmp/procurement_pilot.db" if os.environ.get("VERCEL") else \
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "procurement_pilot.db")
DB_PATH = os.environ.get("DB_PATH", _default_sqlite)
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "180"))
DB_SCHEMA = (os.environ.get("DB_SCHEMA") or ("preview" if os.environ.get("VERCEL_ENV") == "preview" else "")).strip().lower()
if DB_SCHEMA and not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", DB_SCHEMA):
    raise RuntimeError(f"DB_SCHEMA must be a plain lowercase identifier, got {DB_SCHEMA!r}")

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Conn:
    """Same calls for both backends: execute(sql with ? placeholders), insert() returning the new id."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql: str, params=()):
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(sql.replace("?", "%s"), params)
            return cur
        return self.raw.execute(sql, params)

    def insert(self, sql: str, params=()) -> int:
        if IS_PG:
            cur = self.raw.cursor()
            cur.execute(sql.replace("?", "%s") + " RETURNING id", params)
            return cur.fetchone()["id"]
        return self.raw.execute(sql, params).lastrowid


@contextmanager
def get_db():
    if IS_PG:
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
        if DB_SCHEMA:
            raw.execute(f'SET search_path TO "{DB_SCHEMA}"')
    else:
        raw = sqlite3.connect(DB_PATH)
        raw.row_factory = sqlite3.Row
    try:
        yield _Conn(raw)
        raw.commit()
    finally:
        raw.close()


_AUDIT_COLUMNS = """
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
    anonymised INTEGER NOT NULL DEFAULT 0,
    risk_level TEXT
"""
_ACCESS_COLUMNS = """
    ts TEXT NOT NULL,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
"""
_ADDED_LATER = [("override_reason", "TEXT"), ("evaluated_by", "TEXT"), ("decided_by", "TEXT"),
                ("decided_role", "TEXT"), ("decided_at", "TEXT"), ("anonymised", "INTEGER NOT NULL DEFAULT 0"),
                ("risk_level", "TEXT")]
# Append-only, hash-chained. Each entry's hash covers its content and the previous hash (see ledger.py).
_LEDGER_COLUMNS = """
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    ref_id BIGINT,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL UNIQUE,
    hash TEXT NOT NULL
"""
# Eligibility rules read from a tender document (NIT), applied by a senior approver.
_RULEBOOK_COLUMNS = """
    ts TEXT NOT NULL,
    tender_id TEXT NOT NULL,
    filename TEXT,
    rules_json TEXT NOT NULL,
    extracted_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    applied_by TEXT,
    applied_at TEXT
"""
_TRANSLATION_COLUMNS = """
    text_hash TEXT NOT NULL,
    lang TEXT NOT NULL,
    translated TEXT NOT NULL,
    ts TEXT NOT NULL,
    UNIQUE (text_hash, lang)
"""


def init_db():
    pk = "id BIGSERIAL PRIMARY KEY" if IS_PG else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    if IS_PG and DB_SCHEMA:
        raw = psycopg.connect(DATABASE_URL, connect_timeout=10)
        try:
            raw.execute(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"')
            raw.commit()
        finally:
            raw.close()
    with get_db() as conn:
        conn.execute(f"CREATE TABLE IF NOT EXISTS audit_log ({pk}, {_AUDIT_COLUMNS})")
        conn.execute(f"CREATE TABLE IF NOT EXISTS access_log ({pk}, {_ACCESS_COLUMNS})")
        conn.execute(f"CREATE TABLE IF NOT EXISTS ledger ({pk}, {_LEDGER_COLUMNS})")
        conn.execute(f"CREATE TABLE IF NOT EXISTS rulebooks ({pk}, {_RULEBOOK_COLUMNS})")
        conn.execute(f"CREATE TABLE IF NOT EXISTS translations ({pk}, {_TRANSLATION_COLUMNS})")
        if IS_PG:
            for col, ddl in _ADDED_LATER:
                conn.execute(f"ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS {col} {ddl}")
        else:  # older SQLite files from the first build lack some columns
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()}
            for col, ddl in _ADDED_LATER:
                if col not in cols:
                    conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {ddl}")
    # Records written before the ledger existed are sealed into its first entry.
    from . import ledger
    try:
        with get_db() as conn:
            ledger.ensure_baseline(conn)
    except Exception as e:  # another instance sealed it first (unique prev_hash); nothing to do
        print(f"[ledger] baseline skipped: {type(e).__name__}", flush=True)


def log_access(username: str, role: str, action: str, detail: str = ""):
    with get_db() as conn:
        conn.execute("INSERT INTO access_log (ts, username, role, action, detail) VALUES (?,?,?,?,?)",
                     (now_iso(), username, role, action, detail))


def run_retention(days: int | None = None) -> int:
    """Anonymise evaluations older than `days`. Returns how many rows changed.

    Each anonymisation is written to the ledger in the same transaction, so the
    chain records that the content was removed on purpose and still verifies.
    """
    from . import ledger
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
            ledger.append(conn, "anonymised", r["id"], {"audit_id": r["id"], "retention_days": days})
            changed += 1
    return changed
