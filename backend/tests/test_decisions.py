"""Every officer decision, and every change to one, lands in the access log.

Reuses the client and tokens from test_api, so the isolated test database
and the cleared LLM keys set up there apply here too.
"""
from app.db import get_db

from .test_api import APP, OFF, client, evaluate

TID, BIDDER = "depot-security", "Meridian Guard Solutions Pvt Ltd"
REASON = "Site visit confirmed the licence renewal is already filed with the state."


def _decision_details():
    with get_db() as conn:
        rows = conn.execute("SELECT username, role, detail FROM access_log WHERE action='officer_decision' "
                            "AND detail LIKE ? ORDER BY id", (f"{TID} / {BIDDER}:%",)).fetchall()
    return [(r["username"], r["role"], r["detail"]) for r in rows]


def test_decision_and_change_are_both_logged():
    evaluate(TID, BIDDER)  # fresh row, no decision yet
    before = len(_decision_details())
    r = client.post("/api/officer-decision", headers=APP,
                    json={"tender_id": TID, "bidder_name": BIDDER, "decision": "Qualified", "override_reason": REASON})
    assert r.status_code == 200, r.text
    r = client.post("/api/officer-decision", headers=OFF,
                    json={"tender_id": TID, "bidder_name": BIDDER, "decision": "Mark Non-Compliant"})
    assert r.status_code == 200, r.text

    assert _decision_details()[before:] == [
        ("approver1", "senior_approver", f"{TID} / {BIDDER}: Pending -> Qualified"),
        ("officer1", "officer", f"{TID} / {BIDDER}: Qualified (approver1) -> Mark Non-Compliant"),
    ]


def test_rejected_decision_is_not_logged():
    evaluate(TID, BIDDER)
    before = len(_decision_details())
    r = client.post("/api/officer-decision", headers=OFF,
                    json={"tender_id": TID, "bidder_name": BIDDER, "decision": "Qualified"})
    assert r.status_code == 403
    assert len(_decision_details()) == before
