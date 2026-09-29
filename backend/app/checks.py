"""
The fifteen deterministic compliance checks, the score and the risk level.

Every check is plain Python and returns PASS, FLAG or FAIL with a sentence that
names the actual numbers and the source it was checked against. No model is
involved here, so nothing with a fixed right answer can be hallucinated.

The checks cover all fourteen outcomes SIH26100 asks for, in three families:
  Tender eligibility     EMD (with MSE / Startup exemption), statutory documents
                         (DigiLocker), turnover, price, Make in India local
                         content, OEM authorisation
  Registry verification  GST registration and returns, PAN and income tax,
                         MSE / Startup / NSIC status, EPFO and ESIC
  Integrity and risk     entity name across sources, debarment, public interest,
                         shell company indicators (MCA21), past performance

Scoring
  Weights sum to 100. PASS earns the full weight, FLAG half, FAIL nothing.
  A FAIL on EMD, statutory documents, GST registration or debarment caps the
  score at 45. Any other FAIL caps it at 72.

Verdict and risk level
  Non-compliant  any FAIL, or score below 60     Critical  a capped (45) FAIL
  Needs review   any FLAG                        High      any other FAIL
  Compliant      all PASS                        Medium    any FLAG
                                                 Low       all PASS
"""
from . import registry as R
from .data import ITR_YEARS_REQUIRED
from .db import get_db

FAMILIES = ["Tender eligibility", "Registry verification", "Integrity and risk"]
CHECKS = [  # name, weight, family
    ("EMD compliance", 10, "Tender eligibility"),
    ("Statutory documents", 10, "Tender eligibility"),
    ("Financial turnover", 10, "Tender eligibility"),
    ("Price reasonability", 8, "Tender eligibility"),
    ("Make in India local content", 6, "Tender eligibility"),
    ("OEM authorisation", 6, "Tender eligibility"),
    ("GST registration and returns", 8, "Registry verification"),
    ("PAN and income tax", 7, "Registry verification"),
    ("MSE and Startup status", 6, "Registry verification"),
    ("EPFO and ESIC compliance", 6, "Registry verification"),
    ("Entity name consistency", 7, "Integrity and risk"),
    ("Debarment status", 8, "Integrity and risk"),
    ("Public interest screening", 3, "Integrity and risk"),
    ("Shell company indicators", 3, "Integrity and risk"),
    ("Past performance history", 2, "Integrity and risk"),
]
WEIGHTS = {n: w for n, w, _ in CHECKS}
FAMILY = {n: f for n, _, f in CHECKS}
HARD_CAP_CHECKS = {"EMD compliance", "Statutory documents", "GST registration and returns", "Debarment status"}
ADVERSE_DECISIONS = {"Mark Non-Compliant", "Hold for Review"}
SIM = f" ({R.MODE})"


def rs(n) -> str:
    return f"Rs {n:,.0f}"


def res(name, status, reason, source):
    return {"name": name, "status": status, "reason": reason, "source": source, "family": FAMILY[name]}


def worst(issues):
    """issues: list of (status, text). Returns the worst status and the joined text."""
    order = {"FAIL": 2, "FLAG": 1}
    st = max((s for s, _ in issues), key=lambda s: order[s])
    return st, " ".join(t for _, t in issues)


# ------------------------------------------------------------ Tender eligibility
def check_emd(bidder_name, bidder):
    if bidder["emd"] > 0:
        return res("EMD compliance", "PASS", f"EMD of {rs(bidder['emd'])} recorded against this tender.", "Bid record")
    ok = [c for c in R.verify_claims(bidder_name, bidder) if c["ok"]]
    if ok:
        return res("EMD compliance", "PASS",
                   f"No EMD paid; exempt as a verified {ok[0]['claim']} bidder ({ok[0]['detail']}){SIM}.",
                   "Bid record + " + ("Udyam" if ok[0]["claim"] == "MSE" else "DPIIT" if ok[0]["claim"] == "Startup" else "NSIC"))
    return res("EMD compliance", "FAIL", "No EMD payment on record and no verified MSE, Startup or NSIC exemption.", "Bid record")


def check_documents(bidder, tender):
    docs = bidder.get("documents") or {}
    req = tender["required_documents"]
    missing = [d for d in req if docs.get(d, "missing") == "missing"]
    unverified = [d for d in req if docs.get(d) == "self-attested"]
    if missing:
        return res("Statutory documents", "FAIL", "Missing from the submission: " + ", ".join(missing) + ".", "DigiLocker")
    if unverified:
        return res("Statutory documents", "FLAG",
                   f"Self-attested only, not verifiable at source: {', '.join(unverified)}. "
                   f"{len(req) - len(unverified)} of {len(req)} verified through DigiLocker{SIM}.", "DigiLocker")
    return res("Statutory documents", "PASS", f"All {len(req)} required documents verified at source through DigiLocker{SIM}.", "DigiLocker")


def check_turnover(bidder, tender):
    ok = bidder["turnover"] >= tender["min_turnover"]
    return res("Financial turnover", "PASS" if ok else "FAIL",
               f"Annual turnover {rs(bidder['turnover'])} against a minimum of {rs(tender['min_turnover'])}.", "Bid record")


def check_price(bidder, tender):
    dev = (bidder["price"] - tender["benchmark_price"]) / tender["benchmark_price"] * 100
    if abs(dev) <= 12:
        st, note = "PASS", ""
    elif dev < 0:
        st, note = "FLAG", " Abnormally low quotes need a costing justification."
    else:
        st, note = "FLAG", " Well above the benchmark estimate."
    return res("Price reasonability", st,
               f"Quoted {rs(bidder['price'])}, {dev:+.1f}% against the benchmark of {rs(tender['benchmark_price'])}.{note}", "Tender record")


def check_make_in_india(bidder):
    lc = bidder.get("local_content_pct")
    name = "Make in India local content"
    if lc is None:
        return res(name, "FLAG", "No local content self-certification submitted.", "Bid declaration")
    if lc >= 50:
        return res(name, "PASS", f"Class-I local supplier ({lc}% local content), eligible for purchase preference.", "Bid declaration")
    if lc >= 20:
        return res(name, "PASS", f"Class-II local supplier ({lc}% local content).", "Bid declaration")
    return res(name, "FAIL", f"Non-local supplier ({lc}% local content, below the 20% floor for Class-II).", "Bid declaration")


def check_oem(bidder, tender):
    name = "OEM authorisation"
    if not tender.get("oem_authorisation_required"):
        return res(name, "PASS", f"Not required for this {tender['category'].lower()} tender.", "Tender record")
    oem = bidder.get("oem") or {}
    if oem.get("is_oem"):
        return res(name, "PASS", "Bidder is the original equipment manufacturer (declared).", "Bid declaration")
    auth = oem.get("authorisation", "missing")
    if auth == "verified":
        return res(name, "PASS", f"Bidder is a reseller; OEM authorisation letter verified{SIM}.", "DigiLocker")
    if auth == "self-attested":
        return res(name, "FLAG", "Bidder is a reseller; the OEM authorisation letter is self-attested only.", "Bid declaration")
    return res(name, "FAIL", "Bidder is not the OEM and has no OEM authorisation letter on file.", "Bid declaration")


# ------------------------------------------------------------ Registry verification
def check_gst(bidder_name, bidder):
    name = "GST registration and returns"
    ok, msg = R.validate_gstin(bidder.get("gstin", ""))
    if not ok:
        return res(name, "FLAG", msg, "GSTN")
    g = bidder["gstin"].upper()
    rec = R.gstn(g)
    if rec is None:
        return res(name, "FLAG", f"GSTIN {g} is valid but not found{SIM}.", "GSTN")
    issues = []
    if rec["status"] != "Active":
        issues.append(("FAIL", f"GST registration is {rec['status'].lower()}."))
    ratio = R.similar(rec["legal_name"], bidder_name)
    if ratio < 0.85:
        issues.append(("FLAG", f"GSTIN legal name is \"{rec['legal_name']}\", not the bidder \"{bidder_name}\" ({round(ratio*100)}% match)."))
    if rec["returns_filed"] < rec["returns_due"]:
        issues.append(("FLAG", f"Filed {rec['returns_filed']} of the last {rec['returns_due']} GSTR-3B returns."))
    if issues:
        st, txt = worst(issues)
        return res(name, st, txt + SIM, "GSTN")
    return res(name, "PASS", f"GSTIN {g} active, legal name matches, {rec['returns_filed']} of {rec['returns_due']} returns filed{SIM}.", "GSTN")


def check_pan(bidder_name, bidder):
    name = "PAN and income tax"
    pan = R.pan_from_gstin(bidder.get("gstin", ""))
    if not R.PAN_RE.match(pan):
        return res(name, "FLAG", "PAN could not be read from the GSTIN.", "Income Tax Department")
    issues = []
    exp = R.expected_pan_type(bidder_name)
    if exp and pan[3] != exp:
        issues.append(("FLAG", f"PAN {pan} is held by a {R.PAN_TYPES.get(pan[3], 'unknown type')}, but the bidder's name indicates a {R.PAN_TYPES[exp]}."))
    if pan[3] != "P" and R.name_initial(bidder_name) and pan[4] != R.name_initial(bidder_name):
        issues.append(("FLAG", f"PAN {pan} name code '{pan[4]}' does not match the bidder's initial '{R.name_initial(bidder_name)}'."))
    rec = R.itd(pan)
    if rec is None:
        issues.append(("FLAG", f"PAN {pan} not found."))
    else:
        if R.similar(rec["name"], bidder_name) < 0.85:
            issues.append(("FLAG", f"PAN {pan} is held by \"{rec['name']}\"."))
        inc = R.incorporation(bidder)
        due = []
        for ay in ITR_YEARS_REQUIRED:   # AY 2025-26 covers the year ending 31 Mar 2025
            fy_end = f"{ay[3:7]}-03-31"
            existed = (inc <= fy_end) if inc else (bidder.get("incorporated_years_ago", 99) >= R.years_between(fy_end, bidder["submitted_at"]))
            if existed:
                due.append(ay)
        missing = [ay for ay in due if ay not in rec["itr_filed"]]
        if missing:
            issues.append(("FLAG", f"No income tax return on record for {', '.join(missing)}."))
        if not due:
            itr_note = "incorporated after the last assessment year, so no return is due yet"
        else:
            itr_note = f"returns filed for {', '.join(due)}"
    if issues:
        st, txt = worst(issues)
        return res(name, st, txt + SIM, "Income Tax Department")
    return res(name, "PASS", f"PAN {pan} ({R.PAN_TYPES.get(pan[3])}) matches the bidder; {itr_note}{SIM}.", "Income Tax Department")


def check_mse(bidder_name, bidder):
    name = "MSE and Startup status"
    claims = R.verify_claims(bidder_name, bidder)
    if not claims:
        return res(name, "PASS", "No MSE, Startup or NSIC benefit claimed; standard terms apply.", "Bid declaration")
    bad = [c for c in claims if not c["ok"]]
    src = " + ".join(sorted({"Udyam" if c["claim"] == "MSE" else "DPIIT" if c["claim"] == "Startup" else "NSIC" for c in claims}))
    if bad:
        return res(name, "FLAG", "Claimed benefit not verified: " + "; ".join(c["detail"] for c in bad) + f"{SIM}.", src)
    return res(name, "PASS", "; ".join(c["detail"] for c in claims) + f"{SIM}.", src)


def check_epfo_esic(bidder_name, bidder, tender):
    name = "EPFO and ESIC compliance"
    labour = tender.get("labour_services")
    recs = {"EPFO": (bidder.get("epfo"), R.epfo(bidder.get("epfo"))), "ESIC": (bidder.get("esic"), R.esic(bidder.get("esic")))}
    if not labour:
        on = [k for k, (_, r) in recs.items() if r]
        return res(name, "PASS", "Not mandatory for a goods supply" + (f"; {' and '.join(on)} registration on record{SIM}." if on else "; no registration on record."),
                   "EPFO + ESIC")
    issues = []
    if not any(r for _, r in recs.values()):
        return res(name, "FAIL", "Labour services tender, but no EPFO or ESIC registration found" + SIM + ".", "EPFO + ESIC")
    for k, (code, r) in recs.items():
        if not r:
            issues.append(("FLAG", f"No {k} registration found for a labour services contract."))
            continue
        lag = R.months_behind(r["last_challan"], bidder["submitted_at"])
        if lag > 1:
            issues.append(("FLAG", f"{k} {code}: last challan {r['last_challan']}, {lag} months behind."))
    if issues:
        st, txt = worst(issues)
        return res(name, st, txt + SIM, "EPFO + ESIC")
    return res(name, "PASS", f"EPFO and ESIC registered, challans current to {recs['EPFO'][1]['last_challan']}{SIM}.", "EPFO + ESIC")


# ------------------------------------------------------------ Integrity and risk
def check_entity_name(bidder_name, bidder):
    name = "Entity name consistency"
    doc = bidder.get("document_name", bidder_name)
    mca = R.mca21(bidder.get("cin"))
    issues = []
    r = R.similar(doc, bidder_name)
    if r < 0.85:
        issues.append(("FLAG", f"Documents read \"{doc}\" against a bidding entity of \"{bidder_name}\", only a {round(r*100)}% match."))
    if mca and R.similar(mca["name"], bidder_name) < 0.85:
        issues.append(("FLAG", f"MCA21 lists CIN {bidder['cin']} as \"{mca['name']}\"{SIM}."))
    if issues:
        st, txt = worst(issues)
        return res(name, st, txt, "Documents + MCA21")
    src = " and MCA21" if mca else ""
    return res(name, "PASS", f"Bid, documents{src} carry the same name.", "Documents + MCA21" if mca else "Documents")


def check_debarment(bidder_name):
    rec = R.debarment(bidder_name)
    if rec:
        return res("Debarment status", "FAIL", f"On the debarment list until {rec['until']}: {rec['reason']}{SIM}.", "GeM / CPPP list")
    return res("Debarment status", "PASS", f"Not on the GeM / CPPP debarment list{SIM}.", "GeM / CPPP list")


def check_public_interest(bidder):
    note = bidder.get("reputational_note") or ""
    if note:
        return res("Public interest screening", "FLAG", note, "Adverse media record")
    return res("Public interest screening", "PASS", "No adverse public-interest record on file.", "Adverse media record")


def check_shell(bidder_name, bidder, tender_bidders):
    name = "Shell company indicators"
    mca = R.mca21(bidder.get("cin"))
    addr = (bidder.get("address") or "").strip().lower()
    shared = [n for n, b in tender_bidders.items() if n != bidder_name and addr and (b.get("address") or "").strip().lower() == addr]
    issues = []
    if mca:
        days = R.days_between(mca["incorporated"], bidder["submitted_at"])
        age_txt = f"incorporated {mca['incorporated']} (MCA21, {R.MODE})"
        if mca["status"] != "Active":
            issues.append(("FLAG", f"MCA21 status is {mca['status']}."))
        if days < 91:
            issues.append(("FLAG", f"Incorporated only {days} days before bidding (MCA21, {R.MODE}). Recommend enhanced scrutiny before award."))
    else:
        age = bidder.get("incorporated_years_ago", 99)
        age_txt = f"declared {age:g} years in business (not an MCA-registered company)"
        if age < 0.25:
            issues.append(("FLAG", f"Declared only {max(1, round(age*12))} month(s) in business."))
    if shared:
        issues.append(("FLAG", f"Registered address matches {', '.join(shared)} on this same tender."))
    if issues:
        st, txt = worst(issues)
        return res(name, st, txt, "MCA21 + tender")
    return res(name, "PASS", f"{age_txt[0].upper() + age_txt[1:]}; no address overlap with other bidders on this tender.", "MCA21 + tender")


def check_past_performance(bidder_name, tender_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT tender_id, officer_decision FROM audit_log WHERE bidder_name=? AND officer_decision IS NOT NULL AND tender_id != ?",
            (bidder_name, tender_id)).fetchall()
    adverse = [r for r in rows if r["officer_decision"] in ADVERSE_DECISIONS]
    name = "Past performance history"
    if adverse:
        hit = ", ".join(sorted({r["tender_id"] for r in adverse}))
        return res(name, "FLAG", f"{len(adverse)} earlier adverse officer decision(s) on this platform, on {hit}.", "Platform audit log")
    if rows:
        return res(name, "PASS", f"{len(rows)} earlier decision(s) on this platform, none adverse.", "Platform audit log")
    return res(name, "PASS", "No earlier decisions for this bidder on this platform yet.", "Platform audit log")


def run_all_checks(tender_id, tender, bidder_name, bidder):
    checks = [
        check_emd(bidder_name, bidder),
        check_documents(bidder, tender),
        check_turnover(bidder, tender),
        check_price(bidder, tender),
        check_make_in_india(bidder),
        check_oem(bidder, tender),
        check_gst(bidder_name, bidder),
        check_pan(bidder_name, bidder),
        check_mse(bidder_name, bidder),
        check_epfo_esic(bidder_name, bidder, tender),
        check_entity_name(bidder_name, bidder),
        check_debarment(bidder_name),
        check_public_interest(bidder),
        check_shell(bidder_name, bidder, tender["bidders"]),
        check_past_performance(bidder_name, tender_id),
    ]
    for c in checks:
        w = WEIGHTS[c["name"]]
        c["weight"] = w
        c["points"] = w if c["status"] == "PASS" else w / 2 if c["status"] == "FLAG" else 0
    return checks


def score_and_verdict(checks):
    raw = sum(c["points"] for c in checks)
    fails = [c for c in checks if c["status"] == "FAIL"]
    flags = [c for c in checks if c["status"] == "FLAG"]
    hard = [c["name"] for c in fails if c["name"] in HARD_CAP_CHECKS]
    cap = 45 if hard else 72 if fails else None
    value = min(raw, cap) if cap is not None else raw
    score = int(value + 0.5)  # half-up, same as the frontend's Math.round
    if fails or score < 60:
        verdict = "Non-compliant"
    elif flags:
        verdict = "Needs review"
    else:
        verdict = "Compliant"
    risk = "Critical" if hard else "High" if fails else "Medium" if flags else "Low"
    breakdown = {
        "raw": raw,
        "cap": cap,
        "cap_reason": (f"A FAIL on {', '.join(hard)} caps the score at 45." if cap == 45
                       else "A failed check caps the score at 72." if cap == 72 else None),
        "lost": [{"name": c["name"], "status": c["status"], "points_lost": c["weight"] - c["points"]} for c in checks if c["status"] != "PASS"],
        "risk_level": risk,
        "families": {f: {"pass": sum(1 for c in checks if c["family"] == f and c["status"] == "PASS"),
                         "total": sum(1 for c in checks if c["family"] == f)} for f in FAMILIES},
    }
    return score, verdict, breakdown


def risk_level(breakdown):
    return breakdown["risk_level"]
