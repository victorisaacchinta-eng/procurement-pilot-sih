"""
Procurement Pilot API.

Bid compliance verification for government procurement officers
(SIH26100, Ministry of Petroleum and Natural Gas).

  POST /api/auth/login           sign in, returns a bearer token
  GET  /api/auth/me              who am I
  GET  /api/tenders              open tenders with their bids
  GET  /api/evaluate-seed        run the fifteen checks + reasoning layer on one bid
  GET  /api/registries           the registry adapters and their mode
  POST /api/documents/extract    read a bid PDF, cross-check its identifiers against the bid
  POST /api/officer-decision     record a decision (override rule enforced here)
  GET  /api/collusion-check      compare every bid on a tender, with an ownership graph
  GET  /api/audit-log            every evaluation and decision, with its ledger hash
  GET  /api/audit-log/verify     recompute the hash chain and replay it against the audit log
  GET  /api/audit-log/export     admin only, and the export itself is logged
  POST /api/rulebooks/extract    read the eligibility rules out of a tender document (PDF)
  GET  /api/rulebooks            rulebooks read for a tender
  POST /api/rulebooks/{id}/apply senior approver: the checks use the tender document's rules
  POST /api/tenders/{id}/rulebook/revert   senior approver: back to the tender record
  GET  /api/languages            the 22 scheduled languages of India, plus English
  POST /api/translate            translate interface text and results (Sarvam), cached
  GET  /api/eval                 measured results on the seeded test set (scripts/run_eval.py)
  POST /api/admin/retention      admin only, run the anonymisation job now
  POST /api/admin/reset-demo     admin only, clear evaluations before a demo (logged)
  GET  /api/health               status, no auth

The frontend in ../frontend is served at / by the same process.
"""
import os
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth, checks as C, collusion, documents, ledger, llm, registry, rulebook, sarvam
from .data import TENDERS
from .db import DB_SCHEMA, IS_PG, RETENTION_DAYS, get_db, init_db, log_access, now_iso, run_retention

DECISIONS = ("Qualified", "Request Clarification", "Hold for Review", "Mark Non-Compliant")
OVERRIDE_MIN_CHARS = 30
FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", Path(__file__).resolve().parents[2] / "frontend"))

app = FastAPI(title="Procurement Pilot", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
run_retention()


class LoginIn(BaseModel):
    username: str
    password: str


class DecisionIn(BaseModel):
    tender_id: str
    bidder_name: str
    decision: str
    override_reason: str | None = None


class TranslateIn(BaseModel):
    target: str
    texts: list[str]


class ApplyIn(BaseModel):
    values: dict[str, float] | None = None


def _applied_rulebook(tender_id: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM rulebooks WHERE tender_id=? AND status='applied' ORDER BY id DESC LIMIT 1",
                            (tender_id,)).fetchone()


def _tender(tender_id: str) -> dict:
    """The tender as the checks see it: the record, or the record with an applied rulebook."""
    t = TENDERS.get(tender_id)
    if not t:
        raise HTTPException(404, f"Unknown tender: {tender_id}")
    rb = _applied_rulebook(tender_id)
    if rb:
        t = rulebook.effective(t, json.loads(rb["rules_json"])["rules"])
        t["rulebook"] = {"id": rb["id"], "filename": rb["filename"], "applied_by": rb["applied_by"], "applied_at": rb["applied_at"]}
    return t


PUBLIC_BID_FIELDS = ("price", "emd", "turnover", "address", "submitted_at", "gstin", "udyam", "dpiit", "nsic", "cin", "claims",
                     "local_content_pct", "oem", "epfo", "esic", "documents", "document_name")


@app.post("/api/auth/login")
def login(body: LoginIn):
    user = auth.authenticate(body.username.strip(), body.password)
    if not user:
        raise HTTPException(401, "Wrong username or password.")
    log_access(user["username"], user["role"], "login")
    return {"access_token": auth.issue_token(user), "token_type": "bearer", "username": user["username"],
            "role": user["role"], "expires_in": auth.JWT_TTL_SECONDS}


@app.get("/api/auth/me")
def me(user: dict = Depends(auth.current_user)):
    return user


@app.get("/api/tenders")
def tenders(user: dict = Depends(auth.current_user)):
    out = []
    for tid in TENDERS:
        t = _tender(tid)
        out.append({
            "id": tid, "title": t["title"], "category": t["category"], "authority": t["authority"],
            "authority_full": t["authority_full"], "spec": t["spec"],
            "min_turnover": t["min_turnover"], "benchmark_price": t["benchmark_price"],
            "required_documents": t["required_documents"], "oem_authorisation_required": t["oem_authorisation_required"],
            "labour_services": t["labour_services"], "emd_amount": t.get("emd_amount"),
            "rulebook": t.get("rulebook"), "rules_source": t.get("rules_source"),
            "bidders": [dict({"name": n}, **{k: b.get(k) for k in PUBLIC_BID_FIELDS}) for n, b in t["bidders"].items()],
        })
    return out


@app.get("/api/evaluate-seed")
def evaluate_seed(tender_id: str, bidder_name: str, user: dict = Depends(auth.current_user)):
    tender = _tender(tender_id)
    bidder = tender["bidders"].get(bidder_name)
    if not bidder:
        raise HTTPException(404, f"{bidder_name} has not bid on {tender_id}.")
    results = C.run_all_checks(tender_id, tender, bidder_name, bidder)
    score, verdict, breakdown = C.score_and_verdict(results)
    ai = llm.reason(tender, bidder_name, results, score, verdict)
    row = {"ts": now_iso(), "tender_id": tender_id, "bidder_name": bidder_name, "checks_json": json.dumps(results),
           "compliance_score": score, "ai_verdict": verdict, "ai_reasoning": ai["ai_reasoning"], "ai_source": ai["ai_source"],
           "evaluated_by": user["username"], "risk_level": breakdown["risk_level"]}
    with get_db() as conn:
        eid = conn.insert(
            "INSERT INTO audit_log (ts, tender_id, bidder_name, checks_json, compliance_score, ai_verdict, ai_reasoning, ai_source, evaluated_by, risk_level) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(row.values()))
        entry = ledger.append(conn, "evaluation", eid, ledger.evaluation_payload(eid, row))
    return {"evaluation_id": eid, "tender_id": tender_id, "bidder_name": bidder_name, "checks": results,
            "compliance_score": score, "score_breakdown": breakdown, "verdict": verdict, "risk_level": breakdown["risk_level"],
            "ai_reasoning": ai["ai_reasoning"], "ai_source": ai["ai_source"], "registry_mode": registry.MODE,
            "ledger": entry, "rulebook": tender.get("rulebook"), "rules_source": tender.get("rules_source")}


@app.post("/api/officer-decision")
def officer_decision(body: DecisionIn, user: dict = Depends(auth.current_user)):
    if body.decision not in DECISIONS:
        raise HTTPException(400, f"Decision must be one of: {', '.join(DECISIONS)}.")
    _tender(body.tender_id)
    reason = (body.override_reason or "").strip()
    with get_db() as conn:
        row = conn.execute("SELECT id, ai_verdict FROM audit_log WHERE tender_id=? AND bidder_name=? ORDER BY id DESC LIMIT 1",
                           (body.tender_id, body.bidder_name)).fetchone()
        if not row:
            raise HTTPException(404, "No evaluation on record for this bid yet. Evaluate it first.")
        # Override rule: qualifying a bid the system did not mark Compliant is a
        # senior approver's call, and it must be justified in writing.
        if body.decision == "Qualified" and row["ai_verdict"] != "Compliant":
            if user["role"] not in ("senior_approver", "admin"):
                raise HTTPException(403, "Only a senior approver can qualify a bid that was not marked Compliant. Record Hold for Review to send it up.")
            if len(reason) < OVERRIDE_MIN_CHARS:
                raise HTTPException(422, f"Qualifying this bid overrides a {row['ai_verdict']} recommendation. Write at least {OVERRIDE_MIN_CHARS} characters explaining why.")
        ts = now_iso()
        conn.execute("UPDATE audit_log SET officer_decision=?, override_reason=?, decided_by=?, decided_role=?, decided_at=? WHERE id=?",
                     (body.decision, reason or None, user["username"], user["role"], ts, row["id"]))
        entry = ledger.append(conn, "decision", row["id"],
                              ledger.decision_payload(row["id"], body.decision, user["username"], user["role"], reason or None))
    return {"status": "recorded", "evaluation_id": row["id"], "tender_id": body.tender_id, "bidder_name": body.bidder_name,
            "decision": body.decision, "override_reason": reason or None, "decided_by": user["username"], "ts": ts, "ledger": entry}


@app.get("/api/collusion-check")
def collusion_check(tender_id: str, user: dict = Depends(auth.current_user)):
    return collusion.screen(tender_id, _tender(tender_id))


def _audit_rows():
    run_retention()
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC").fetchall()
        sealed = {}
        for e in conn.execute("SELECT id, ref_id, hash FROM ledger WHERE ref_id IS NOT NULL ORDER BY id").fetchall():
            sealed[e["ref_id"]] = {"seq": e["id"], "hash": e["hash"]}
    return [{"id": r["id"], "ts": r["ts"], "tender": r["tender_id"], "bidder": r["bidder_name"], "score": r["compliance_score"],
             "aiVerdict": r["ai_verdict"], "risk": r["risk_level"], "aiSource": r["ai_source"], "evaluatedBy": r["evaluated_by"],
             "officer": r["officer_decision"] or "Pending", "overrideReason": r["override_reason"],
             "by": r["decided_by"], "role": r["decided_role"], "decidedAt": r["decided_at"], "anonymised": bool(r["anonymised"]),
             "ledger": sealed.get(r["id"])}
            for r in rows]


@app.get("/api/registries")
def registries(user: dict = Depends(auth.current_user)):
    return {"mode": registry.MODE, "adapters": registry.adapters()}


@app.post("/api/documents/extract")
async def extract_document(tender_id: str = Form(...), bidder_name: str = Form(...), file: UploadFile = File(...),
                           user: dict = Depends(auth.current_user)):
    tender = _tender(tender_id)
    bidder = tender["bidders"].get(bidder_name)
    if not bidder:
        raise HTTPException(404, f"{bidder_name} has not bid on {tender_id}.")
    blob = await file.read(documents.MAX_BYTES + 1)
    if len(blob) > documents.MAX_BYTES:
        raise HTTPException(413, "The file is larger than 4 MB.")
    if not blob.startswith(b"%PDF"):
        raise HTTPException(415, "Upload a PDF file.")
    try:
        out = documents.extract(blob, bidder_name, bidder)
    except Exception:
        raise HTTPException(422, "This PDF could not be read.")
    log_access(user["username"], user["role"], "document_extract", f"{tender_id} / {bidder_name} / {file.filename}")
    return dict(out, filename=file.filename, tender_id=tender_id, bidder_name=bidder_name)


@app.get("/api/audit-log")
def audit_log(user: dict = Depends(auth.current_user)):
    return _audit_rows()


@app.get("/api/audit-log/export")
def audit_export(user: dict = Depends(auth.require_roles("admin"))):
    rows = _audit_rows()
    log_access(user["username"], user["role"], "audit_export", f"{len(rows)} records")
    with get_db() as conn:
        access = [dict(r) for r in conn.execute("SELECT * FROM access_log ORDER BY id DESC LIMIT 200").fetchall()]
        chain = ledger.entries(conn)
    # The ledger travels with the export, so an auditor can re-check it offline with scripts/verify_ledger.py.
    return {"exported_at": now_iso(), "exported_by": user["username"], "retention_days": RETENTION_DAYS,
            "records": rows, "access_log": access, "ledger": chain, "ledger_head": chain[-1]["hash"] if chain else ledger.GENESIS}


@app.get("/api/audit-log/verify")
def audit_verify(user: dict = Depends(auth.current_user)):
    run_retention()
    with get_db() as conn:
        out = ledger.verify(conn)
    log_access(user["username"], user["role"], "ledger_verify", "intact" if out["ok"] else f"{out['problem_count']} problem(s)")
    return out


@app.post("/api/admin/retention")
def admin_retention(user: dict = Depends(auth.require_roles("admin"))):
    changed = run_retention()
    log_access(user["username"], user["role"], "retention_run", f"{changed} anonymised")
    return {"anonymised": changed, "retention_days": RETENTION_DAYS}


@app.post("/api/admin/reset-demo")
def admin_reset_demo(user: dict = Depends(auth.require_roles("admin"))):
    """Clear evaluations and decisions so a demo starts clean. The reset itself is kept in the access log."""
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]
        old_head = ledger.head(conn)
        conn.execute("DELETE FROM audit_log")
        conn.execute("DELETE FROM ledger")
        # The new chain opens with the old chain's head, so the reset itself is on record.
        ledger.append(conn, "reset", None, {"previous_head": old_head, "cleared": n, "by": user["username"]})
    log_access(user["username"], user["role"], "demo_reset", f"{n} evaluations cleared; previous ledger head {old_head}")
    return {"cleared": n, "previous_head": old_head}


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version, "checks": len(C.CHECKS), "registry_adapters": len(registry.ADAPTERS),
            "reasoning_layer": "configured" if llm.configured() else "deterministic only",
            "model": llm.LLM_MODEL if llm.configured() else None, "registry_mode": registry.MODE,
            "sarvam": {"translate": sarvam.TRANSLATE_MODEL if sarvam.configured() else None,
                       "ocr": documents.OCR_ENGINE if sarvam.configured() else None, "languages": len(sarvam.LANGUAGES) - 1},
            "retention_days": RETENTION_DAYS, "tenders": len(TENDERS), "database": "postgres" if IS_PG else "sqlite",
            "schema": DB_SCHEMA or None}


# ------------------------------------------------------------------ tender rulebooks
def _rulebook_out(r) -> dict:
    data = json.loads(r["rules_json"])
    return {"id": r["id"], "tender_id": r["tender_id"], "filename": r["filename"], "ts": r["ts"], "extracted_by": r["extracted_by"],
            "status": r["status"], "applied_by": r["applied_by"], "applied_at": r["applied_at"], **data}


@app.post("/api/rulebooks/extract")
async def rulebook_extract(tender_id: str = Form(...), file: UploadFile = File(...), user: dict = Depends(auth.current_user)):
    record = TENDERS.get(tender_id)
    if not record:
        raise HTTPException(404, f"Unknown tender: {tender_id}")
    blob = await file.read(documents.MAX_BYTES + 1)
    if len(blob) > documents.MAX_BYTES:
        raise HTTPException(413, "The file is larger than 4 MB.")
    if not blob.startswith(b"%PDF"):
        raise HTTPException(415, "Upload the tender document as a PDF.")
    try:
        doc = documents.read_document(blob)
    except Exception:
        raise HTTPException(422, "This PDF could not be read.")
    if not doc["pages"]:
        raise HTTPException(422, doc["note"] or "No text could be read from this PDF.")
    rules = rulebook.extract_rules(doc["pages"])
    data = {"rules": rules, "suggestions": rulebook.suggest(doc["pages"], rules), "comparison": rulebook.compare(rules, record),
            "pages": doc["page_count"], "method": doc["method"], "note": doc["note"]}
    with get_db() as conn:
        rid = conn.insert("INSERT INTO rulebooks (ts, tender_id, filename, rules_json, extracted_by, status) VALUES (?,?,?,?,?,?)",
                          (now_iso(), tender_id, file.filename, json.dumps(data), user["username"], "draft"))
        r = conn.execute("SELECT * FROM rulebooks WHERE id=?", (rid,)).fetchone()
    log_access(user["username"], user["role"], "rulebook_extract", f"{tender_id} / {file.filename} / {len(rules)} rules")
    return _rulebook_out(r)


@app.get("/api/rulebooks")
def rulebooks(tender_id: str, user: dict = Depends(auth.current_user)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM rulebooks WHERE tender_id=? ORDER BY id DESC LIMIT 10", (tender_id,)).fetchall()
    return [_rulebook_out(r) for r in rows]


@app.post("/api/rulebooks/{rulebook_id}/apply")
def rulebook_apply(rulebook_id: int, body: ApplyIn | None = None, user: dict = Depends(auth.require_roles("senior_approver", "admin"))):
    with get_db() as conn:
        r = conn.execute("SELECT * FROM rulebooks WHERE id=?", (rulebook_id,)).fetchone()
        if not r:
            raise HTTPException(404, "No such rulebook.")
        data = json.loads(r["rules_json"])
        edited = []
        for key, value in ((body.values or {}) if body else {}).items():
            if key not in rulebook.EDITABLE:
                raise HTTPException(422, f"{key} cannot be edited here.")
            if not (0 < value < 1e12):
                raise HTTPException(422, f"{key} must be a positive number.")
            for rule in data["rules"]:
                if rule["key"] == key and rule["value"] != int(value):
                    rule.update(value=int(value), method="rule, corrected by " + user["username"],
                                display=(f"{int(value)} years" if key == "experience_years" else rulebook.fmt_rupees(int(value))))
                    edited.append(key)
        data["comparison"] = rulebook.compare(data["rules"], TENDERS[r["tender_id"]])
        ts = now_iso()
        conn.execute("UPDATE rulebooks SET status='superseded' WHERE tender_id=? AND status='applied'", (r["tender_id"],))
        conn.execute("UPDATE rulebooks SET status='applied', applied_by=?, applied_at=?, rules_json=? WHERE id=?",
                     (user["username"], ts, json.dumps(data), rulebook_id))
        entry = ledger.append(conn, "rulebook_applied", None, {"rulebook_id": rulebook_id, "tender_id": r["tender_id"],
                                                                "rules": ledger.sha(data["rules"]), "applied_by": user["username"], "edited": edited})
    log_access(user["username"], user["role"], "rulebook_apply", f"{r['tender_id']} / rulebook {rulebook_id}")
    return {"status": "applied", "rulebook_id": rulebook_id, "tender_id": r["tender_id"], "edited": edited, "ledger": entry,
            "tender": {k: v for k, v in _tender(r["tender_id"]).items() if k != "bidders"}}


@app.post("/api/tenders/{tender_id}/rulebook/revert")
def rulebook_revert(tender_id: str, user: dict = Depends(auth.require_roles("senior_approver", "admin"))):
    if tender_id not in TENDERS:
        raise HTTPException(404, f"Unknown tender: {tender_id}")
    with get_db() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM rulebooks WHERE tender_id=? AND status='applied'", (tender_id,)).fetchone()["n"]
        if not n:
            raise HTTPException(409, "No rulebook is applied to this tender.")
        conn.execute("UPDATE rulebooks SET status='reverted' WHERE tender_id=? AND status='applied'", (tender_id,))
        entry = ledger.append(conn, "rulebook_reverted", None, {"tender_id": tender_id, "by": user["username"]})
    log_access(user["username"], user["role"], "rulebook_revert", tender_id)
    return {"status": "reverted", "tender_id": tender_id, "ledger": entry}


# ------------------------------------------------------------------ languages (Sarvam)
_tcache: dict = {}


def _cache_get(lang):
    def get(text):
        key = (sarvam.text_hash(text), lang)
        if key in _tcache:
            return _tcache[key]
        with get_db() as conn:
            r = conn.execute("SELECT translated FROM translations WHERE text_hash=? AND lang=?", key).fetchone()
        if r:
            _tcache[key] = r["translated"]
            return r["translated"]
        return None
    return get


def _cache_put(lang):
    def put(text, translated):
        key = (sarvam.text_hash(text), lang)
        _tcache[key] = translated
        try:
            with get_db() as conn:
                conn.execute("INSERT INTO translations (text_hash, lang, translated, ts) VALUES (?,?,?,?)", (*key, translated, now_iso()))
        except Exception:  # another request cached it first
            pass
    return put


@app.get("/api/languages")
def languages():
    return {"configured": sarvam.configured(), "model": sarvam.TRANSLATE_MODEL, "languages": sarvam.languages()}


@app.post("/api/translate")
def translate(body: TranslateIn, user: dict = Depends(auth.current_user)):
    if body.target not in sarvam.CODES:
        raise HTTPException(422, f"Unsupported language: {body.target}")
    texts = [t for t in body.texts if isinstance(t, str)][:200]
    if any(len(t) > 6000 for t in texts):
        raise HTTPException(413, "One of the texts is longer than 6,000 characters.")
    if body.target == "en-IN":
        return {"target": body.target, "translations": texts, "engine": None, "translated": 0, "cached": 0, "failed": 0}
    if not sarvam.configured():
        raise HTTPException(503, "Translation needs the Sarvam API key on the server.")
    out = sarvam.translate_many(texts, body.target, _cache_get(body.target), _cache_put(body.target))
    if out["failed"] and not out["translated"] and not out["cached"]:
        raise HTTPException(502, "Sarvam did not answer. The interface stays in English for now.")
    return {"target": body.target, "translations": [out["results"].get(t, t) for t in texts], "engine": sarvam.TRANSLATE_MODEL,
            "translated": out["translated"], "cached": out["cached"], "failed": out["failed"]}


# ------------------------------------------------------------------ measured results
EVAL_PATH = Path(__file__).resolve().parent / "eval_results.json"


@app.get("/api/eval")
def eval_results(user: dict = Depends(auth.current_user)):
    if not EVAL_PATH.exists():
        raise HTTPException(404, "No measured results yet. Run scripts/run_eval.py.")
    return json.loads(EVAL_PATH.read_text())


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
