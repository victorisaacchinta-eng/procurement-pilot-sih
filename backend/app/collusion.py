"""
Cross-bid collusion screen.

Compares every pair of bids on one tender:
  price clustering    two quotes within PRICE_GAP_PCT of each other
  submission timing   two bids submitted within TIMING_MINUTES
  shared address      the same registered address
  cover bid           a quote more than COVER_BID_PCT above the benchmark

Close prices alone are normal competition, so a price gap only becomes a FLAG
when it is below the threshold; timing on its own is a WATCH item.
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


def screen(tender_id: str, tender: dict) -> dict:
    bids = tender["bidders"]
    findings = []
    if len(bids) < 2:
        return {"tender_id": tender_id, "bidders_compared": len(bids), "pairs_compared": 0, "findings": [],
                "note": "Only one bid on this tender. Nothing to compare.",
                "thresholds": {"price_gap_pct": PRICE_GAP_PCT, "timing_minutes": TIMING_MINUTES, "cover_bid_pct": COVER_BID_PCT}}
    pairs = 0
    for (na, a), (nb, b) in combinations(bids.items(), 2):
        pairs += 1
        gap = abs(a["price"] - b["price"]) / min(a["price"], b["price"]) * 100
        ta, tb = _ts(a.get("submitted_at")), _ts(b.get("submitted_at"))
        mins = abs((ta - tb).total_seconds()) / 60 if ta and tb else None
        tight = gap < PRICE_GAP_PCT
        close_time = mins is not None and mins <= TIMING_MINUTES
        if tight:
            findings.append({"signal": "Price clustering", "severity": "FLAG", "bidders": [na, nb],
                             "detail": f"{na} and {nb} quoted {gap:.2f}% apart (threshold {PRICE_GAP_PCT}%)."})
        if close_time:
            findings.append({"signal": "Submission timing", "severity": "FLAG" if tight else "WATCH", "bidders": [na, nb],
                             "detail": f"{na} and {nb} submitted {round(mins)} minute(s) apart."})
        if a.get("address") and a.get("address", "").strip().lower() == b.get("address", "").strip().lower():
            findings.append({"signal": "Shared address", "severity": "FLAG", "bidders": [na, nb],
                             "detail": f"{na} and {nb} list the same registered address."})
    for n, b in bids.items():
        over = (b["price"] / tender["benchmark_price"] - 1) * 100
        if over > COVER_BID_PCT:
            findings.append({"signal": "Possible cover bid", "severity": "FLAG", "bidders": [n],
                             "detail": f"{n} quoted {over:.0f}% above the benchmark, which can signal a bid placed only to lose."})
    return {"tender_id": tender_id, "bidders_compared": len(bids), "pairs_compared": pairs, "findings": findings,
            "note": None if findings else "Prices, timing, addresses and benchmark spread look like normal competition.",
            "thresholds": {"price_gap_pct": PRICE_GAP_PCT, "timing_minutes": TIMING_MINUTES, "cover_bid_pct": COVER_BID_PCT}}
