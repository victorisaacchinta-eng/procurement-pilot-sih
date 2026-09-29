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
  GET  /api/collusion-check      compare every bid on a tender
  GET  /api/audit-log            every evaluation and decision
  GET  /api/audit-log/export     admin only, and the export itself is logged
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

from . import auth, checks as C, collusion, documents, llm, registry
from .data import TENDERS
from .db import IS_PG, RETENTION_DAYS, get_db, init_db, log_access, now_iso, run_retention

DECISIONS = ("Qualified", "Request Clarification", "Hold for Review", "Mark Non-Compliant")
OVERRIDE_MIN_CHARS = 30
FRONTEND_DIR = Path(os.environ.get("FRONTEND_DIR", Path(__file__).resolve().parents[2] / "frontend"))

app = FastAPI(title="Procurement Pilot", version="2.0.0")
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


def _tender(tender_id: str) -> dict:
    t = TENDERS.get(tender_id)
    if not t:
        raise HTTPException(404, f"Unknown tender: {tender_id}")
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
    for tid, t in TENDERS.items():
        out.append({
            "id": tid, "title": t["title"], "category": t["category"], "authority": t["authority"],
            "authority_full": t["authority_full"], "spec": t["spec"],
            "min_turnover": t["min_turnover"], "benchmark_price": t["benchmark_price"],
            "required_documents": t["required_documents"], "oem_authorisation_required": t["oem_authorisation_required"],
            "labour_services": t["labour_services"],
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
    with get_db() as conn:
        eid = conn.insert(
            "INSERT INTO audit_log (ts, tender_id, bidder_name, checks_json, compliance_score, ai_verdict, ai_reasoning, ai_source, evaluated_by, risk_level) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (now_iso(), tender_id, bidder_name, json.dumps(results), score, verdict, ai["ai_reasoning"], ai["ai_source"], user["username"],
             breakdown["risk_level"]))
    return {"evaluation_id": eid, "tender_id": tender_id, "bidder_name": bidder_name, "checks": results,
            "compliance_score": score, "score_breakdown": breakdown, "verdict": verdict, "risk_level": breakdown["risk_level"],
            "ai_reasoning": ai["ai_reasoning"], "ai_source": ai["ai_source"], "registry_mode": registry.MODE}


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
        conn.execute("UPDATE audit_log SET officer_decision=?, override_reason=?, decided_by=?, decided_role=?, decided_at=? WHERE id=?",
                     (body.decision, reason or None, user["username"], user["role"], now_iso(), row["id"]))
    return {"status": "recorded", "evaluation_id": row["id"], "tender_id": body.tender_id, "bidder_name": body.bidder_name,
            "decision": body.decision, "override_reason": reason or None, "decided_by": user["username"], "ts": now_iso()}


@app.get("/api/collusion-check")
def collusion_check(tender_id: str, user: dict = Depends(auth.current_user)):
    return collusion.screen(tender_id, _tender(tender_id))


def _audit_rows():
    run_retention()
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC").fetchall()
    return [{"id": r["id"], "ts": r["ts"], "tender": r["tender_id"], "bidder": r["bidder_name"], "score": r["compliance_score"],
             "aiVerdict": r["ai_verdict"], "risk": r["risk_level"], "aiSource": r["ai_source"], "evaluatedBy": r["evaluated_by"],
             "officer": r["officer_decision"] or "Pending", "overrideReason": r["override_reason"],
             "by": r["decided_by"], "role": r["decided_role"], "decidedAt": r["decided_at"], "anonymised": bool(r["anonymised"])}
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
    return {"exported_at": now_iso(), "exported_by": user["username"], "retention_days": RETENTION_DAYS,
            "records": rows, "access_log": access}


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
        conn.execute("DELETE FROM audit_log")
    log_access(user["username"], user["role"], "demo_reset", f"{n} evaluations cleared")
    return {"cleared": n}


@app.get("/api/health")
def health():
    return {"status": "ok", "checks": len(C.CHECKS), "registry_adapters": len(registry.ADAPTERS),
            "reasoning_layer": "configured" if llm.configured() else "deterministic only",
            "model": llm.LLM_MODEL if llm.configured() else None, "registry_mode": registry.MODE,
            "retention_days": RETENTION_DAYS, "tenders": len(TENDERS), "database": "postgres" if IS_PG else "sqlite"}


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
