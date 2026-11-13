"""
Cross-bid collusion screen.

Compares every pair of bids on one tender:
  price clustering    two quotes within PRICE_GAP_PCT of each other
  submission timing   two bids submitted within TIMING_MINUTES
  shared address      the same registered address
  shared director     a director (by DIN, from MCA21) sits on both bidders
  shared bank account the same bank account (IFSC and account) on both bids
  shared contact      the same phone number or email on both bids
  cover bid           a quote more than COVER_BID_PCT above the benchmark

Close prices alone are normal competition, so a price gap only becomes a FLAG
when it is below the threshold; timing on its own is a WATCH item. Ownership
links (director, bank, contact) are the strongest signals: firms that are
meant to compete should not share a director or a bank account.

The screen also returns a graph (bidders as nodes, shared links as edges) so
the officer can see at a glance who is tied to whom. A link is a reason to
look closer, not proof of collusion.
"""
from datetime import datetime
from itertools import combinations

PRICE_GAP_PCT = 0.5
TIMING_MINUTES = 5
COVER_BID_PCT = 25


def _ts(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _dins(b):
    return {d["din"]: d["name"] for d in (b.get("directors") or []) if d.get("din")}


def _bank(b):
    k = b.get("bank") or {}
    return f"{k.get('ifsc', '').upper()}:{k.get('account_last4', '')}" if k.get("ifsc") and k.get("account_last4") else None


def _contacts(b):
    c = b.get("contact") or {}
    out = {}
    if c.get("phone"):
        out["phone " + c["phone"]] = c["phone"]
    if c.get("email"):
        out["email " + c["email"].lower()] = c["email"].lower()
    return out


def screen(tender_id: str, tender: dict) -> dict:
    bids = tender["bidders"]
    findings = []
    th = {"price_gap_pct": PRICE_GAP_PCT, "timing_minutes": TIMING_MINUTES, "cover_bid_pct": COVER_BID_PCT}
    nodes = [{"id": n} for n in bids]
    if len(bids) < 2:
        return {"tender_id": tender_id, "bidders_compared": len(bids), "pairs_compared": 0, "findings": [],
                "note": "Only one bid on this tender. Nothing to compare.", "thresholds": th, "graph": {"nodes": nodes, "edges": []}}
    pairs, edges = 0, []
    for (na, a), (nb, b) in combinations(bids.items(), 2):
        pairs += 1
        links = []
        gap = abs(a["price"] - b["price"]) / min(a["price"], b["price"]) * 100
        ta, tb = _ts(a.get("submitted_at")), _ts(b.get("submitted_at"))
        mins = abs((ta - tb).total_seconds()) / 60 if ta and tb else None
        tight = gap < PRICE_GAP_PCT
        close_time = mins is not None and mins <= TIMING_MINUTES
        if tight:
            findings.append({"signal": "Price clustering", "severity": "FLAG", "bidders": [na, nb],
                             "detail": f"{na} and {nb} quoted {gap:.2f}% apart (threshold {PRICE_GAP_PCT}%)."})
            links.append("price")
        if close_time:
            findings.append({"signal": "Submission timing", "severity": "FLAG" if tight else "WATCH", "bidders": [na, nb],
                             "detail": f"{na} and {nb} submitted {round(mins)} minute(s) apart."})
            links.append("timing")
        if a.get("address") and a.get("address", "").strip().lower() == b.get("address", "").strip().lower():
            findings.append({"signal": "Shared address", "severity": "FLAG", "bidders": [na, nb],
                             "detail": f"{na} and {nb} list the same registered address."})
            links.append("address")
        common = sorted(set(_dins(a)) & set(_dins(b)))
        if common:
            who = "; ".join(f"{_dins(a)[d]} (DIN {d})" for d in common)
            findings.append({"signal": "Shared director", "severity": "FLAG", "bidders": [na, nb],
                             "detail": f"{who} is a director of both {na} and {nb} (MCA21)."})
            links.append("director")
        if _bank(a) and _bank(a) == _bank(b):
            k = a["bank"]
            findings.append({"signal": "Shared bank account", "severity": "FLAG", "bidders": [na, nb],
                             "detail": f"{na} and {nb} name the same bank account (IFSC {k['ifsc'].upper()}, account ending {k['account_last4']})."})
            links.append("bank")
        ca, cb = _contacts(a), _contacts(b)
        shared = [ca[k] for k in sorted(set(ca) & set(cb))]
        if shared:
            findings.append({"signal": "Shared contact details", "severity": "FLAG", "bidders": [na, nb],
                             "detail": f"{na} and {nb} give the same " + " and ".join(
                                 ("phone number " if "@" not in s else "email ") + s for s in shared) + "."})
            links.append("contact")
        if links:
            edges.append({"a": na, "b": nb, "links": links})
    for n, b in bids.items():
        over = (b["price"] / tender["benchmark_price"] - 1) * 100
        if over > COVER_BID_PCT:
            findings.append({"signal": "Possible cover bid", "severity": "FLAG", "bidders": [n],
                             "detail": f"{n} quoted {over:.0f}% above the benchmark, which can signal a bid placed only to lose."})
    return {"tender_id": tender_id, "bidders_compared": len(bids), "pairs_compared": pairs, "findings": findings,
            "note": None if findings else "Prices, timing, addresses, ownership, bank accounts, contacts and benchmark spread look like normal competition.",
            "thresholds": th, "graph": {"nodes": nodes, "edges": edges}}
