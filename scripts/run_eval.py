"""
Measure the checks on a seeded test set and write backend/app/eval_results.json.

The set is built from the three seeded bids that pass every check (one goods
bid, one startup goods bid, one labour services bid). Each test case copies
one of them and plants exactly one defect, so we know which check should
catch it. Clean copies sit right on the thresholds (turnover equal to the
minimum, price exactly 12% off the benchmark, local content at exactly 20%)
to catch off-by-one rules that would flag an honest bid.

The collusion screen gets the same treatment: pairs of bids that are clean,
pairs that sit just outside a threshold, and pairs with one planted link.

What this measures: whether each rule catches the defect it is written for
and leaves a clean bid alone, on synthetic records. Field accuracy needs real
tender outcomes, which we do not have.

    python scripts/run_eval.py           write the results
    python scripts/run_eval.py --check   fail if the results changed (CI)
"""
import copy
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "eval.db")
os.environ.pop("DATABASE_URL", None)
for k in ("LLM_API_KEY", "SARVAM_API_KEY", "CEREBRAS_API_KEY"):
    os.environ.pop(k, None)

from app import checks as C, collusion, documents, registry, rulebook  # noqa: E402
from app.data import DEBARRED, TENDERS  # noqa: E402
from app.db import get_db, init_db  # noqa: E402

OUT = ROOT / "backend" / "app" / "eval_results.json"
BASES = [("pipeline-valves", "Petrotech Valve Industries Private Limited"),
         ("refinery-ppe", "SafeGuard Industrial Wear Pvt Ltd"),
         ("tanker-transport", "Konkan Bulk Carriers Ltd")]
DEBARRED_NAME = next(iter(DEBARRED))


def flip_check_digit(g):
    return g[:-1] + ("A" if g[-1] != "A" else "B")


def pan_of_a_person(b):  # GSTIN rebuilt around a PAN whose holder-type letter says "individual"
    g = b["gstin"][:5] + "P" + b["gstin"][6:14]
    b["gstin"] = g + registry.gstin_check_digit(g)


def adverse_history(t, b, name):
    with get_db() as conn:
        conn.execute("INSERT INTO audit_log (ts, tender_id, bidder_name, checks_json, compliance_score, ai_verdict, ai_reasoning, ai_source, "
                     "evaluated_by, risk_level, officer_decision, decided_by, decided_role, decided_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     ("2026-08-01T10:00:00+05:30", "earlier-tender", name, "[]", 40, "Non-compliant", "", "eval", "eval", "High",
                      "Mark Non-Compliant", "eval", "officer", "2026-08-01T11:00:00+05:30"))


def no_exemption(b):
    b.update(emd=0, claims=[])


def bad_claim(b):
    if "mse" in b.get("claims", []):
        b["udyam"] = "UDYAM-TN-02-0999999"
    else:
        b["dpiit"] = "DIPP99999"


def debarred_renamed(t, b):  # the debarred firm, bidding as "Private Limited" instead of "Pvt Ltd"
    return DEBARRED_NAME.replace("Pvt Ltd", "Private Limited")


def debarred_new_name(t, b):  # a new name, but the GSTIN carries the debarred firm's PAN
    b["gstin"] = "29" + DEBARRED[DEBARRED_NAME]["pan"] + "1ZI"
    return "Apex Protective Solutions"


# id, what is planted, the check that should catch it, applies to (None = all), how to plant it
DEFECTS = [
    ("emd_missing", "No EMD and no exemption", "EMD compliance", None, lambda t, b: no_exemption(b)),
    ("exemption_unverified", "MSE or Startup claim that the registry cannot find", "MSE and Startup status", None, lambda t, b: bad_claim(b)),
    ("turnover_short", "Turnover Rs 1 below the minimum", "Financial turnover", None, lambda t, b: b.update(turnover=t["min_turnover"] - 1)),
    ("document_missing", "A required document missing", "Statutory documents", None,
     lambda t, b: b["documents"].pop(t["required_documents"][-1])),
    ("document_self_attested", "A required document only self-attested", "Statutory documents", None,
     lambda t, b: b["documents"].update({t["required_documents"][-1]: "self-attested"})),
    ("price_low", "Quote 20% under the benchmark", "Price reasonability", None, lambda t, b: b.update(price=round(t["benchmark_price"] * 0.8))),
    ("price_high", "Quote 20% over the benchmark", "Price reasonability", None, lambda t, b: b.update(price=round(t["benchmark_price"] * 1.2))),
    ("local_content_low", "Local content 15%", "Make in India local content", None, lambda t, b: b.update(local_content_pct=15)),
    ("gstin_check_digit", "GSTIN with a wrong check digit", "GST registration and returns", None,
     lambda t, b: b.update(gstin=flip_check_digit(b["gstin"]))),
    ("pan_holder_type", "GSTIN carries an individual's PAN for a company", "PAN and income tax", None, lambda t, b: pan_of_a_person(b)),
    ("name_mismatch", "Documents in another firm's name", "Entity name consistency", None,
     lambda t, b: b.update(document_name="Unrelated Traders and Agencies")),
    ("adverse_media", "Adverse media on record", "Public interest screening", None,
     lambda t, b: b.update(reputational_note="Adverse media on record (test case).")),
    ("new_firm", "Declared one month in business", "Shell company indicators", None,
     lambda t, b: b.update(cin="", incorporated_years_ago=0.08)),
    ("oem_missing", "Reseller with no OEM authorisation", "OEM authorisation", "oem", lambda t, b: b.update(oem={"is_oem": False})),
    ("oem_self_attested", "Reseller with a self-attested OEM letter", "OEM authorisation", "oem",
     lambda t, b: b.update(oem={"is_oem": False, "authorisation": "self-attested"})),
    ("esic_missing", "Labour contract, no ESIC registration", "EPFO and ESIC compliance", "labour", lambda t, b: b.update(esic="")),
    ("labour_unregistered", "Labour contract, no EPFO or ESIC", "EPFO and ESIC compliance", "labour", lambda t, b: b.update(esic="", epfo="")),
]
HISTORY = [("adverse_history", "Marked non-compliant on an earlier tender", "Past performance history", None, lambda t, b: None)]
RENAMES = [  # these plant a different bidding name, so they return it
    ("debarred_exact", "Debarred firm under its listed name", "Debarment status", None, lambda t, b: DEBARRED_NAME),
    ("debarred_renamed", "Debarred firm writing Private Limited for Pvt Ltd", "Debarment status", None, debarred_renamed),
    ("debarred_new_name", "Debarred firm under a new name, same PAN", "Debarment status", None, debarred_new_name),
]
CLEAN = [  # every check should pass on these
    ("as_seeded", "The seeded bid, unchanged", lambda t, b: None),
    ("turnover_at_minimum", "Turnover exactly at the minimum", lambda t, b: b.update(turnover=t["min_turnover"])),
    ("price_12_under", "Quote exactly 12% under the benchmark", lambda t, b: b.update(price=round(t["benchmark_price"] * 0.88))),
    ("price_12_over", "Quote exactly 12% over the benchmark", lambda t, b: b.update(price=round(t["benchmark_price"] * 1.12))),
    ("local_content_20", "Local content exactly 20% (Class-II floor)", lambda t, b: b.update(local_content_pct=20)),
    ("local_content_50", "Local content exactly 50% (Class-I floor)", lambda t, b: b.update(local_content_pct=50)),
    ("name_capitals", "Documents print the name in capitals", lambda t, b: b.update(document_name=b["document_name"].upper())),
]


def run(tid, tender, name, bid):
    t0 = time.perf_counter()
    r = C.run_all_checks(tid, tender, name, bid)
    ms = (time.perf_counter() - t0) * 1000
    return {c["name"]: c for c in r}, C.score_and_verdict(r), ms


def applies(scope, t):
    return scope is None or (scope == "oem" and t["oem_authorisation_required"]) or (scope == "labour" and t["labour_services"])


def eval_checks(timings):
    defects, cases = [], []
    for did, label, target, scope, plant in DEFECTS + HISTORY + RENAMES:
        planted = caught = 0
        misses = []
        for tid, name in BASES:
            t = TENDERS[tid]
            if not applies(scope, t):
                continue
            bid = copy.deepcopy(t["bidders"][name])
            if did == "adverse_history":
                adverse_history(t, bid, name)
            new_name = plant(t, bid)
            bname = new_name if isinstance(new_name, str) else name
            got, (score, verdict, _), ms = run(tid, t, bname, bid)
            if did == "adverse_history":
                with get_db() as conn:
                    conn.execute("DELETE FROM audit_log WHERE tender_id='earlier-tender'")
            timings.append(ms)
            planted += 1
            hit = got[target]["status"] != "PASS"
            caught += hit
            if not hit:
                misses.append(tid)
            cases.append({"case": f"{did}@{tid}", "expect": f"{target} not PASS", "status": got[target]["status"], "score": score})
        defects.append({"id": did, "label": label, "check": target, "planted": planted, "caught": caught, "missed_on": misses})
    clean, false_flags = [], 0
    for cid, label, plant in CLEAN:
        for tid, name in BASES:
            t = TENDERS[tid]
            bid = copy.deepcopy(t["bidders"][name])
            plant(t, bid)
            got, (score, verdict, _), ms = run(tid, t, name, bid)
            timings.append(ms)
            flagged = sorted(n for n, c in got.items() if c["status"] != "PASS")
            false_flags += bool(flagged)
            clean.append({"case": f"{cid}@{tid}", "label": label, "score": score, "flagged": flagged})
    return defects, clean, false_flags


def pair_tender(a_changes, b_changes):
    """Two clean bids on one tender, far apart on every signal, then the planted change."""
    t = copy.deepcopy(TENDERS["tanker-transport"])
    base = t["bidders"]["Konkan Bulk Carriers Ltd"]
    a = dict(copy.deepcopy(base), price=9_300_000, submitted_at="2026-09-07T10:00:00+05:30")
    b = copy.deepcopy(TENDERS["pipeline-valves"]["bidders"]["Petrotech Valve Industries Private Limited"])
    b.update(price=8_900_000, submitted_at="2026-09-07T14:00:00+05:30")
    a.update(a_changes)
    b.update(b_changes(a) if callable(b_changes) else b_changes)
    t["bidders"] = {"Bidder A Pvt Ltd": a, "Bidder B Pvt Ltd": b}
    return t


COLLUSION = [  # id, label, change on B (given A), signal expected or None for a clean pair
    ("clean_pair", "Prices 4% apart, 4 hours apart, nothing shared", {}, None),
    ("price_gap_0_6", "Prices 0.6% apart (threshold 0.5%)", lambda a: {"price": round(a["price"] * 1.006)}, None),
    ("timing_6_min", "Submitted 6 minutes apart (threshold 5)", {"submitted_at": "2026-09-07T10:06:00+05:30"}, None),
    ("price_gap_0_3", "Prices 0.3% apart", lambda a: {"price": round(a["price"] * 1.003)}, "Price clustering"),
    ("timing_2_min", "Submitted 2 minutes apart", {"submitted_at": "2026-09-07T10:02:00+05:30"}, "Submission timing"),
    ("same_address", "Same registered address", lambda a: {"address": a["address"].upper()}, "Shared address"),
    ("shared_director", "One director on both", lambda a: {"directors": [a["directors"][0]]}, "Shared director"),
    ("shared_bank", "Same bank account", lambda a: {"bank": dict(a["bank"])}, "Shared bank account"),
    ("shared_phone", "Same phone number", lambda a: {"contact": {"phone": a["contact"]["phone"], "email": "x@example.in"}}, "Shared contact details"),
    ("shared_email", "Same email, different case", lambda a: {"contact": {"phone": "+91 90000 00000", "email": a["contact"]["email"].upper()}},
     "Shared contact details"),
    ("cover_bid", "One quote 40% over the benchmark", {"price": 13_300_000}, "Possible cover bid"),
]


def eval_collusion():
    out = []
    for cid, label, change, want in COLLUSION:
        t = pair_tender({}, change)
        got = sorted({f["signal"] for f in collusion.screen("eval", t)["findings"]})
        ok = (want in got) if want else not got
        out.append({"case": cid, "label": label, "expect": want or "no signal", "found": got, "ok": ok})
    return out


RULEBOOK_EXPECT = {"min_turnover": 40_000_000, "emd_amount": 180_000, "estimated_value": 9_500_000, "experience_years": 3,
                   "labour_services": True, "bid_end": "28-11-2026", "bid_number": "GEM/2026/B/5512874",
                   "required_documents": ["GST registration certificate", "PAN card", "Audited financial statements", "PESO licence",
                                          "Vehicle registration certificates"]}


def eval_rulebook():
    blob = (ROOT / "frontend" / "samples" / "tanker-transport-tender-sample.pdf").read_bytes()
    rules = {r["key"]: r for r in rulebook.extract_rules(documents.read_document(blob)["pages"])}
    fields = [{"field": k, "expected": v, "read": rules.get(k, {}).get("value"), "page": rules.get(k, {}).get("page"),
               "ok": rules.get(k, {}).get("value") == v} for k, v in RULEBOOK_EXPECT.items()]
    extra = sorted(set(rules) - set(RULEBOOK_EXPECT))
    return {"document": "frontend/samples/tanker-transport-tender-sample.pdf", "fields": fields, "unexpected": extra}


def main(check=False):
    init_db()
    timings = []
    defects, clean, false_flags = eval_checks(timings)
    col = eval_collusion()
    rb = eval_rulebook()
    planted = sum(d["planted"] for d in defects)
    caught = sum(d["caught"] for d in defects)
    col_planted = [c for c in col if c["expect"] != "no signal"]
    col_clean = [c for c in col if c["expect"] == "no signal"]
    result = {
        "about": ("Seeded test set built from the three bids that pass every check. Each case plants one known defect, or sits "
                  "exactly on a threshold where an honest bid must still pass. It measures whether each rule does what it is "
                  "written to do, on synthetic records. Field accuracy needs real tender outcomes, which we do not have yet."),
        "summary": {
            "defects_planted": planted, "defects_caught": caught, "detection_pct": round(caught / planted * 100, 1),
            "clean_cases": len(clean), "clean_flagged": false_flags, "false_flag_pct": round(false_flags / len(clean) * 100, 1),
            "collusion_planted": len(col_planted), "collusion_caught": sum(c["ok"] for c in col_planted),
            "collusion_clean": len(col_clean), "collusion_clean_flagged": sum(not c["ok"] for c in col_clean),
            "rulebook_fields": len(rb["fields"]), "rulebook_read": sum(f["ok"] for f in rb["fields"]),
            "checks_covered": len({d["check"] for d in defects}), "checks_total": len(C.CHECKS),
        },
        "defects": defects, "clean": clean, "collusion": col, "rulebook": rb,
        "not_covered": [n for n, _, _ in C.CHECKS if n not in {d["check"] for d in defects}],
    }
    timing = {"evaluations": len(timings), "median_ms": round(statistics.median(timings), 2),
              "p95_ms": round(sorted(timings)[int(len(timings) * 0.95) - 1], 2), "note": "Rules only, one CPU, no network."}
    if check:
        old = json.loads(OUT.read_text())
        old.pop("timing", None)
        if old != result:
            sys.exit("eval_results.json is out of date. Run python scripts/run_eval.py and commit the result.")
        print("eval results unchanged")
        return
    result["timing"] = timing
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    s = result["summary"]
    print(f"defects caught {s['defects_caught']}/{s['defects_planted']} · clean flagged {s['clean_flagged']}/{s['clean_cases']} · "
          f"collusion {s['collusion_caught']}/{s['collusion_planted']}, clean flagged {s['collusion_clean_flagged']}/{s['collusion_clean']} · "
          f"rulebook {s['rulebook_read']}/{s['rulebook_fields']} · median {timing['median_ms']} ms")


if __name__ == "__main__":
    main("--check" in sys.argv)
