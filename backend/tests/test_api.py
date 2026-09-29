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
    assert len(t) == 5 and sum(len(x["bidders"]) for x in t) == 11
    assert all("price" in b and "name" in b for x in t for b in x["bidders"])


def checks_by_name(r):
    return {c["name"]: c for c in r["checks"]}


def test_weights_cover_fifteen_checks_and_sum_to_100():
    from app import checks as C
    assert len(C.CHECKS) == 15 and sum(C.WEIGHTS.values()) == 100
    assert set(C.FAMILY.values()) == set(C.FAMILIES)


def test_clean_bid_scores_100():
    r = evaluate("pipeline-valves", "Petrotech Valve Industries Private Limited")
    assert r["compliance_score"] == 100 and r["verdict"] == "Compliant" and r["risk_level"] == "Low"
    assert len(r["checks"]) == 15
    assert all(c.get("source") and c.get("family") for c in r["checks"])
    assert r["ai_source"] == "deterministic"


def test_name_mismatch_is_corroborated_by_gst_and_pan():
    r = evaluate("pipeline-valves", "Vantage Flow Systems Pvt Ltd")
    st = {k: c["status"] for k, c in checks_by_name(r).items()}
    assert st["Entity name consistency"] == "FLAG" and st["GST registration and returns"] == "FLAG" and st["PAN and income tax"] == "FLAG"
    assert st["OEM authorisation"] == "PASS"
    assert r["compliance_score"] == 89 and r["verdict"] == "Needs review" and r["risk_level"] == "Medium"


def test_hard_fail_caps_score_and_is_critical():
    r = evaluate("refinery-ppe", "Trident Protective Gear & Co")
    c = checks_by_name(r)
    assert c["EMD compliance"]["status"] == "FAIL" and c["Statutory documents"]["status"] == "FAIL"
    assert c["Make in India local content"]["status"] == "FAIL"
    assert "check-digit" in c["GST registration and returns"]["reason"]
    assert "AY 2025-26" in c["PAN and income tax"]["reason"]
    assert r["compliance_score"] <= 45 and r["verdict"] == "Non-compliant" and r["risk_level"] == "Critical"


def test_startup_is_exempt_from_emd():
    r = evaluate("refinery-ppe", "SafeGuard Industrial Wear Pvt Ltd")
    c = checks_by_name(r)
    assert c["EMD compliance"]["status"] == "PASS" and "exempt" in c["EMD compliance"]["reason"]
    assert c["MSE and Startup status"]["status"] == "PASS" and "DPIIT" in c["MSE and Startup status"]["reason"]
    assert r["compliance_score"] == 100


def test_debarred_bidder_without_oem_authorisation():
    r = evaluate("refinery-ppe", "Apex Safety Products Pvt Ltd")
    c = checks_by_name(r)
    assert c["Debarment status"]["status"] == "FAIL" and c["OEM authorisation"]["status"] == "FAIL"
    assert r["risk_level"] == "Critical" and r["compliance_score"] <= 45


def test_new_company_and_missing_esic():
    r = evaluate("tanker-transport", "Swift Tanker Logistics Pvt Ltd")
    c = checks_by_name(r)
    assert c["Shell company indicators"]["status"] == "FLAG" and "days before bidding" in c["Shell company indicators"]["reason"]
    assert c["EPFO and ESIC compliance"]["status"] == "FLAG" and "ESIC" in c["EPFO and ESIC compliance"]["reason"]
    assert c["PAN and income tax"]["status"] == "PASS"   # incorporated after the last assessment year


def test_self_attested_document_is_flagged():
    r = evaluate("tanker-transport", "Ratnagiri Roadlines Pvt Ltd")
    assert checks_by_name(r)["Statutory documents"]["status"] == "FLAG"


def test_epfo_challans_behind_and_gst_returns_missed():
    r = evaluate("depot-security", "Falcon Inspection Technologies")
    c = checks_by_name(r)
    assert c["EPFO and ESIC compliance"]["status"] == "FLAG" and "months behind" in c["EPFO and ESIC compliance"]["reason"]
    assert "4 of the last 6" in c["GST registration and returns"]["reason"]


def test_registries_endpoint():
    assert client.get("/api/registries").status_code == 401
    r = client.get("/api/registries", headers=OFF).json()
    assert len(r["adapters"]) == 10 and all(a["mode"] == "simulated" for a in r["adapters"])


def _sample(name):
    import pathlib
    return (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "samples" / name).read_bytes()


def test_document_extraction_cross_checks_the_bid():
    form = {"tender_id": "pipeline-valves", "bidder_name": "Vantage Flow Systems Pvt Ltd"}
    r = client.post("/api/documents/extract", data=form, headers=OFF,
                    files={"file": ("v.pdf", _sample("vantage-registration-sample.pdf"), "application/pdf")})
    assert r.status_code == 200, r.text
    got = {f["field"]: f["status"] for f in r.json()["fields"]}
    assert got["GSTIN"] == "MATCH" and got["Legal name"] == "MISMATCH"
    r = client.post("/api/documents/extract", data={"tender_id": "refinery-ppe", "bidder_name": "Trident Protective Gear & Co"},
                    headers=OFF, files={"file": ("t.pdf", _sample("trident-registration-sample.pdf"), "application/pdf")})
    assert {f["field"]: f["status"] for f in r.json()["fields"]}["GSTIN"] == "INVALID"


def test_document_extraction_rejects_non_pdf_and_needs_sign_in():
    form = {"tender_id": "pipeline-valves", "bidder_name": "Vantage Flow Systems Pvt Ltd"}
    assert client.post("/api/documents/extract", data=form, files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 401
    assert client.post("/api/documents/extract", data=form, headers=OFF,
                       files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 415


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


def test_reset_is_admin_only_and_logged():
    evaluate("pipeline-valves", "Petrotech Valve Industries Private Limited")
    assert client.post("/api/admin/reset-demo", headers=OFF).status_code == 403
    r = client.post("/api/admin/reset-demo", headers=ADM)
    assert r.status_code == 200 and r.json()["cleared"] >= 1
    assert client.get("/api/audit-log", headers=OFF).json() == []
    access = client.get("/api/audit-log/export", headers=ADM).json()["access_log"]
    assert any(a["action"] == "demo_reset" for a in access)
