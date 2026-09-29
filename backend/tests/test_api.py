import os
import tempfile

# isolated database and no reasoning-layer key for every test run
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
if os.environ.get("TEST_DATABASE_URL"):  # run the same suite against Postgres
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    os.environ.pop("DATABASE_URL", None)
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("CEREBRAS_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import registry  # noqa: E402
from app.db import get_db, run_retention  # noqa: E402

client = TestClient(app)


def token(user, pw):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


OFF = token("officer1", "officer123")
APP = token("approver1", "approver123")
ADM = token("admin1", "admin123")


def evaluate(tid, name, h=OFF):
    r = client.get("/api/evaluate-seed", params={"tender_id": tid, "bidder_name": name}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_health_is_public():
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_rejects_bad_password():
    assert client.post("/api/auth/login", json={"username": "officer1", "password": "nope"}).status_code == 401


def test_api_needs_token():
    assert client.get("/api/tenders").status_code == 401


def test_tenders_shape():
    t = client.get("/api/tenders", headers=OFF).json()
    assert len(t) == 5
    assert all("price" in b and "name" in b for x in t for b in x["bidders"])


def test_clean_bid_scores_100():
    r = evaluate("pipeline-valves", "Petrotech Valve Industries Private Limited")
    assert r["compliance_score"] == 100 and r["verdict"] == "Compliant"
    assert len(r["checks"]) == 10
    assert r["ai_source"] == "deterministic"


def test_name_mismatch_is_corroborated_by_registry():
    r = evaluate("pipeline-valves", "Vantage Flow Systems Pvt Ltd")
    st = {c["name"]: c["status"] for c in r["checks"]}
    assert st["Entity name consistency"] == "FLAG" and st["Registry verification"] == "FLAG"
    assert r["compliance_score"] == 90 and r["verdict"] == "Needs review"


def test_hard_fail_caps_score():
    r = evaluate("refinery-ppe", "Trident Protective Gear & Co")
    st = {c["name"]: c["status"] for c in r["checks"]}
    assert st["EMD compliance"] == "FAIL" and st["Statutory documents"] == "FAIL"
    assert "check-digit" in [c for c in r["checks"] if c["name"] == "Registry verification"][0]["reason"]
    assert r["compliance_score"] <= 45 and r["verdict"] == "Non-compliant"


def test_gstin_checksum():
    assert registry.validate_gstin("33AABCP4821K1ZJ")[0]
    assert not registry.validate_gstin("33AABCP4821K1ZK")[0]


def test_collusion_flags_twin_bids():
    r = client.get("/api/collusion-check", params={"tender_id": "tanker-transport"}, headers=OFF).json()
    sig = {(f["signal"], f["severity"]) for f in r["findings"]}
    assert ("Price clustering", "FLAG") in sig and ("Submission timing", "FLAG") in sig


def test_collusion_clean_tender():
    r = client.get("/api/collusion-check", params={"tender_id": "pipeline-valves"}, headers=OFF).json()
    assert r["findings"] == []


def test_officer_cannot_override():
    evaluate("depot-security", "Meridian Guard Solutions Pvt Ltd")
    r = client.post("/api/officer-decision", headers=OFF,
                    json={"tender_id": "depot-security", "bidder_name": "Meridian Guard Solutions Pvt Ltd", "decision": "Qualified"})
    assert r.status_code == 403


def test_approver_override_needs_reason():
    body = {"tender_id": "depot-security", "bidder_name": "Meridian Guard Solutions Pvt Ltd", "decision": "Qualified"}
    assert client.post("/api/officer-decision", headers=APP, json=body).status_code == 422
    body["override_reason"] = "Labour dispute settled in court on 2 Sep; order copy on file."
    r = client.post("/api/officer-decision", headers=APP, json=body)
    assert r.status_code == 200 and r.json()["decided_by"] == "approver1"


def test_past_performance_builds_up():
    evaluate("depot-security", "Falcon Inspection Technologies")
    client.post("/api/officer-decision", headers=OFF,
                json={"tender_id": "depot-security", "bidder_name": "Falcon Inspection Technologies", "decision": "Mark Non-Compliant"})
    r = evaluate("pipeline-survey", "Falcon Inspection Technologies")
    past = [c for c in r["checks"] if c["name"] == "Past performance history"][0]
    assert past["status"] == "FLAG" and "depot-security" in past["reason"]


def test_export_is_admin_only_and_logged():
    assert client.get("/api/audit-log/export", headers=OFF).status_code == 403
    r = client.get("/api/audit-log/export", headers=ADM).json()
    assert r["exported_by"] == "admin1"
    assert any(a["action"] == "audit_export" for a in r["access_log"])


def test_retention_anonymises_old_rows():
    evaluate("tanker-transport", "Konkan Bulk Carriers Ltd")
    with get_db() as conn:
        conn.execute("UPDATE audit_log SET ts='2020-01-01T00:00:00+00:00' WHERE bidder_name='Konkan Bulk Carriers Ltd'")
    assert run_retention() >= 1
    rows = client.get("/api/audit-log", headers=OFF).json()
    assert not any(r["bidder"] == "Konkan Bulk Carriers Ltd" for r in rows)
    assert any(r["anonymised"] for r in rows)
