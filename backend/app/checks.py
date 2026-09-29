"""
The ten deterministic compliance checks and the scoring rule.

Every check is plain Python and returns PASS, FLAG or FAIL with a sentence that
names the actual numbers. No model is involved here, so nothing with a fixed
right answer can be hallucinated.

Scoring
  Each check carries a weight (they sum to 100).
  PASS earns the full weight, FLAG half, FAIL nothing.
  A FAIL on EMD, statutory documents or debarment caps the score at 45.
  Any other FAIL caps it at 72.
  So a bid cannot look healthy while failing something that matters.

Verdict
  Non-compliant  any FAIL, or score below 60
  Needs review   any FLAG
  Compliant      all ten PASS
"""
import difflib

from . import registry
from .data import DEBARRED
from .db import get_db

WEIGHTS = {
    "EMD compliance": 15,
    "Statutory documents": 15,
    "Financial turnover": 15,
    "Price reasonability": 10,
    "Entity name consistency": 10,
    "Registry verification": 10,
    "Debarment status": 10,
    "Public interest screening": 5,
    "Shell company indicators": 5,
    "Past performance history": 5,
}
HARD_CAP_CHECKS = {"EMD compliance", "Statutory documents", "Debarment status"}
ADVERSE_DECISIONS = {"Mark Non-Compliant", "Hold for Review"}


def rs(n) -> str:
    return f"Rs {n:,.0f}"


def check_emd(bidder):
    ok = bidder["emd"] > 0
    return {"name": "EMD compliance", "status": "PASS" if ok else "FAIL",
            "reason": f"EMD of {rs(bidder['emd'])} recorded against this tender." if ok
            else "No EMD payment on record and no exemption claimed."}


def check_documents(bidder):
    missing = bidder.get("documents_missing") or []
    if not missing:
        return {"name": "Statutory documents", "status": "PASS", "reason": "All mandatory statutory documents present."}
    return {"name": "Statutory documents", "status": "FAIL", "reason": "Missing from the submission: " + ", ".join(missing) + "."}


def check_turnover(bidder, tender):
    ok = bidder["turnover"] >= tender["min_turnover"]
    return {"name": "Financial turnover", "status": "PASS" if ok else "FAIL",
            "reason": f"Annual turnover {rs(bidder['turnover'])} against a minimum of {rs(tender['min_turnover'])}."}


def check_price(bidder, tender):
    dev = (bidder["price"] - tender["benchmark_price"]) / tender["benchmark_price"] * 100
    if abs(dev) <= 12:
        st, note = "PASS", ""
    elif dev < 0:
        st, note = "FLAG", " Abnormally low quotes need a costing justification."
    else:
        st, note = "FLAG", " Well above the benchmark estimate."
    return {"name": "Price reasonability", "status": st,
            "reason": f"Quoted {rs(bidder['price'])}, {dev:+.1f}% against the benchmark of {rs(tender['benchmark_price'])}.{note}"}


def check_entity_name(bidder_name, bidder):
    doc = bidder.get("document_name", bidder_name)
    ratio = difflib.SequenceMatcher(None, bidder_name.lower().strip(), doc.lower().strip()).ratio()
    if doc.strip().lower() == bidder_name.strip().lower():
        return {"name": "Entity name consistency", "status": "PASS", "reason": "Documents are in the exact name of the bidding entity."}
    if ratio >= 0.85:
        return {"name": "Entity name consistency", "status": "PASS",
                "reason": f"Document name is a {round(ratio*100)}% textual match to the bidding entity, within tolerance."}
    return {"name": "Entity name consistency", "status": "FLAG",
            "reason": f"Documents read \"{doc}\" against a bidding entity of \"{bidder_name}\", only a {round(ratio*100)}% match."}


def check_registry(bidder_name, bidder):
    r = registry.verify(bidder_name, bidder)
    return {"name": "Registry verification", "status": r["status"], "reason": r["reason"], "mode": r["mode"]}


def check_debarment(bidder_name):
    if bidder_name in DEBARRED:
        return {"name": "Debarment status", "status": "FAIL", "reason": "Bidder is on the debarment list."}
    return {"name": "Debarment status", "status": "PASS",
            "reason": "Not on the seeded debarment list (prototype list, not a live GeM lookup)."}


def check_public_interest(bidder):
    note = bidder.get("reputational_note") or ""
    if note:
        return {"name": "Public interest screening", "status": "FLAG", "reason": note}
    return {"name": "Public interest screening", "status": "PASS", "reason": "No adverse public-interest record on file."}


def check_shell(bidder, tender_bidders):
    age = bidder.get("incorporated_years_ago", 99)
    addr = (bidder.get("address") or "").strip().lower()
    young = age < 0.25
    shared = [n for n, b in tender_bidders.items() if b is not bidder and addr and (b.get("address") or "").strip().lower() == addr]
    if young and shared:
        return {"name": "Shell company indicators", "status": "FLAG",
                "reason": f"Incorporated about {round(age*365)} days ago and shares a registered address with {', '.join(shared)}."}
    if young:
        return {"name": "Shell company indicators", "status": "FLAG",
                "reason": f"Incorporated only about {max(1, round(age*12))} month(s) before this tender. Recommend enhanced scrutiny before award."}
    if shared:
        return {"name": "Shell company indicators", "status": "FLAG",
                "reason": f"Registered address matches {', '.join(shared)} on this same tender."}
    return {"name": "Shell company indicators", "status": "PASS",
            "reason": f"Incorporated {age:g} years ago; no address overlap with other bidders on this tender."}


def check_past_performance(bidder_name, tender_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT tender_id, officer_decision FROM audit_log WHERE bidder_name=? AND officer_decision IS NOT NULL AND tender_id != ?",
            (bidder_name, tender_id)).fetchall()
    adverse = [r for r in rows if r["officer_decision"] in ADVERSE_DECISIONS]
    if adverse:
        hit = ", ".join(sorted({r["tender_id"] for r in adverse}))
        return {"name": "Past performance history", "status": "FLAG",
                "reason": f"{len(adverse)} earlier adverse officer decision(s) on this platform, on {hit}."}
    if rows:
        return {"name": "Past performance history", "status": "PASS",
                "reason": f"{len(rows)} earlier decision(s) on this platform, none adverse."}
    return {"name": "Past performance history", "status": "PASS", "reason": "No earlier decisions for this bidder on this platform yet."}


def run_all_checks(tender_id, tender, bidder_name, bidder):
    checks = [
        check_emd(bidder),
        check_documents(bidder),
        check_turnover(bidder, tender),
        check_price(bidder, tender),
        check_entity_name(bidder_name, bidder),
        check_registry(bidder_name, bidder),
        check_debarment(bidder_name),
        check_public_interest(bidder),
        check_shell(bidder, tender["bidders"]),
        check_past_performance(bidder_name, tender_id),
    ]
    for c in checks:
        w = WEIGHTS[c["name"]]
        earned = w if c["status"] == "PASS" else w / 2 if c["status"] == "FLAG" else 0
        c["weight"] = w
        c["points"] = earned
    return checks


def score_and_verdict(checks):
    raw = sum(c["points"] for c in checks)
    fails = [c for c in checks if c["status"] == "FAIL"]
    flags = [c for c in checks if c["status"] == "FLAG"]
    cap = None
    if any(c["name"] in HARD_CAP_CHECKS for c in fails):
        cap = 45
    elif fails:
        cap = 72
    value = min(raw, cap) if cap is not None else raw
    score = int(value + 0.5)  # half-up, same as the frontend's Math.round
    if fails or score < 60:
        verdict = "Non-compliant"
    elif flags:
        verdict = "Needs review"
    else:
        verdict = "Compliant"
    breakdown = {
        "raw": raw,
        "cap": cap,
        "cap_reason": (f"A FAIL on {', '.join(c['name'] for c in fails if c['name'] in HARD_CAP_CHECKS)} caps the score at 45."
                       if cap == 45 else "A failed check caps the score at 72." if cap == 72 else None),
        "lost": [{"name": c["name"], "status": c["status"], "points_lost": c["weight"] - c["points"]} for c in checks if c["status"] != "PASS"],
    }
    return score, verdict, breakdown
