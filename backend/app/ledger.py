"""
Tamper-evident ledger for the audit trail.

Every evaluation, officer decision, anonymisation and rulebook change is
appended to the `ledger` table as one entry. Each entry stores the SHA-256 of
its own content plus the hash of the entry before it, so the entries form a
chain: editing, deleting or reordering any past entry breaks every hash after
it. `prev_hash` is UNIQUE, so two writers can never fork the chain.

The ledger stores digests of bidder identity and free text, never the text
itself. That keeps the DPDP retention job honest: when an old evaluation is
anonymised, the audit row loses its identifiers, the ledger records that the
anonymisation happened, and the chain still verifies.

verify() walks the chain, recomputes every hash, then replays the entries
against the audit_log table. A score, verdict, decision or record changed
directly in the database (outside the app) is reported with the record id.

Records written before the ledger existed are sealed into one "baseline"
entry the first time the app starts with this code.
"""
import hashlib
import json

from .db import IS_PG, now_iso

GENESIS = "0" * 64
KINDS = ("baseline", "evaluation", "decision", "anonymised", "rulebook_applied", "rulebook_reverted", "reset")


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(*parts) -> str:
    return hashlib.sha256(canon(list(parts)).encode()).hexdigest()


def entry_hash(ts: str, kind: str, ref_id, payload_json: str, prev_hash: str) -> str:
    return sha(ts, kind, ref_id, payload_json, prev_hash)


def content_digest(bidder_name, checks_json, ai_reasoning) -> str:
    return sha(bidder_name or "", checks_json or "", ai_reasoning or "")


def row_state(r) -> dict:
    """The fields of one audit_log row that the ledger vouches for."""
    anonymised = bool(r["anonymised"])
    return {
        "tender_id": r["tender_id"], "score": int(r["compliance_score"]), "verdict": r["ai_verdict"], "risk": r["risk_level"],
        "content": None if anonymised else content_digest(r["bidder_name"], r["checks_json"], r["ai_reasoning"]),
        "decision": r["officer_decision"], "decided_by": r["decided_by"],
        "reason": None if anonymised else sha(r["override_reason"] or ""),
        "anonymised": anonymised,
    }


def head(conn) -> str:
    row = conn.execute("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()
    return row["hash"] if row else GENESIS


def append(conn, kind: str, ref_id, payload: dict) -> dict:
    """Append one entry inside the caller's transaction. Returns {seq, hash}."""
    if kind not in KINDS:
        raise ValueError(f"unknown ledger kind {kind}")
    if IS_PG:  # one writer at a time; released at commit
        conn.execute("LOCK TABLE ledger IN SHARE ROW EXCLUSIVE MODE")
    prev = head(conn)
    ts = now_iso()
    body = canon(payload)
    h = entry_hash(ts, kind, ref_id, body, prev)
    seq = conn.insert("INSERT INTO ledger (ts, kind, ref_id, payload, prev_hash, hash) VALUES (?,?,?,?,?,?)",
                      (ts, kind, ref_id, body, prev, h))
    return {"seq": seq, "hash": h}


def ensure_baseline(conn):
    """Seal records that predate the ledger into its first entry (runs once)."""
    if conn.execute("SELECT id FROM ledger LIMIT 1").fetchone():
        return None
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    if not rows:
        return None
    return append(conn, "baseline", None, {"records": {str(r["id"]): row_state(r) for r in rows}})


def evaluation_payload(audit_id: int, row: dict) -> dict:
    return {"audit_id": audit_id, "tender_id": row["tender_id"], "score": int(row["compliance_score"]),
            "verdict": row["ai_verdict"], "risk": row["risk_level"], "evaluated_by": row.get("evaluated_by"),
            "content": content_digest(row["bidder_name"], row["checks_json"], row["ai_reasoning"])}


def decision_payload(audit_id: int, decision: str, decided_by: str, role: str, reason: str | None) -> dict:
    return {"audit_id": audit_id, "decision": decision, "decided_by": decided_by, "role": role, "reason": sha(reason or "")}


def entries(conn) -> list:
    return [dict(r) for r in conn.execute("SELECT id, ts, kind, ref_id, payload, prev_hash, hash FROM ledger ORDER BY id").fetchall()]


def verify_chain(rows: list) -> tuple[list, str]:
    """Recompute every hash. Works on database rows or on an exported list. Returns (problems, head)."""
    problems, prev = [], GENESIS
    for i, e in enumerate(rows):
        if e["prev_hash"] != prev:
            problems.append(f"Entry {e['id']} does not follow entry {rows[i - 1]['id'] if i else 'zero'}: "
                            "an entry was removed, inserted or reordered.")
        if entry_hash(e["ts"], e["kind"], e["ref_id"], e["payload"], e["prev_hash"]) != e["hash"]:
            problems.append(f"Entry {e['id']} ({e['kind']}) was altered after it was written: its hash no longer matches its content.")
        prev = e["hash"]
    return problems, prev


def _expected_state(rows: list) -> dict:
    state = {}
    for e in rows:
        p = json.loads(e["payload"])
        if e["kind"] == "baseline":
            for k, v in p.get("records", {}).items():
                state[int(k)] = dict(v)
        elif e["kind"] == "evaluation":
            state[p["audit_id"]] = {"tender_id": p["tender_id"], "score": p["score"], "verdict": p["verdict"], "risk": p["risk"],
                                    "content": p["content"], "decision": None, "decided_by": None, "reason": sha(""), "anonymised": False}
        elif e["kind"] == "decision" and p["audit_id"] in state:
            state[p["audit_id"]].update(decision=p["decision"], decided_by=p["decided_by"], reason=p["reason"])
        elif e["kind"] == "anonymised" and p["audit_id"] in state:
            state[p["audit_id"]].update(content=None, reason=None, anonymised=True)
    return state


LABELS = {"tender_id": "tender", "score": "score", "verdict": "recommendation", "risk": "risk level",
          "decision": "officer decision", "decided_by": "decided by"}


def verify(conn) -> dict:
    rows = entries(conn)
    problems, last = verify_chain(rows)
    expected = _expected_state(rows)
    audit = {r["id"]: r for r in conn.execute("SELECT * FROM audit_log").fetchall()}
    for aid, r in sorted(audit.items()):
        want = expected.get(aid)
        if want is None:
            problems.append(f"Record #{aid} is not on the ledger: it was added outside the app.")
            continue
        got = row_state(r)
        for k, label in LABELS.items():
            if want.get(k) != got.get(k):
                problems.append(f"Record #{aid}: {label} reads \"{got.get(k)}\" but the ledger recorded \"{want.get(k)}\".")
        if got["anonymised"] and not want.get("anonymised"):
            problems.append(f"Record #{aid} was anonymised outside the retention job.")
        elif not got["anonymised"]:
            if want.get("content") and want["content"] != got["content"]:
                problems.append(f"Record #{aid}: the bidder name, check results or reasoning were edited after the evaluation.")
            if want.get("reason") is not None and want["reason"] != got["reason"]:
                problems.append(f"Record #{aid}: the written override reason was edited after the decision.")
    for aid in sorted(set(expected) - set(audit)):
        problems.append(f"Record #{aid} is on the ledger but missing from the audit log: it was deleted outside the app.")
    return {"ok": not problems, "entries": len(rows), "records_checked": len(audit), "head": last,
            "problems": problems[:25], "problem_count": len(problems), "checked_at": now_iso()}
