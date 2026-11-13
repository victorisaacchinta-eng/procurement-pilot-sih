"""Tamper-evident ledger, tender rulebooks, ownership links, OCR, languages and the measured test set."""
import json
import os
import pathlib

os.environ.pop("SARVAM_API_KEY", None)

import pytest  # noqa: E402

from tests.test_api import ADM, APP, OFF, client, evaluate  # noqa: E402  (same app, same database)
from app import documents, ledger, registry, sarvam  # noqa: E402
from app.db import get_db, run_retention  # noqa: E402

SAMPLES = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "samples"


def verify():
    r = client.get("/api/audit-log/verify", headers=OFF)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(autouse=True)
def fresh():
    assert client.post("/api/admin/reset-demo", headers=ADM).status_code == 200
    with get_db() as conn:
        conn.execute("DELETE FROM rulebooks")
        conn.execute("DELETE FROM translations")
    from app import main
    main._tcache.clear()
    yield


# ------------------------------------------------------------------ ledger
def test_every_evaluation_and_decision_is_sealed():
    r = evaluate("tanker-transport", "Ratnagiri Roadlines Pvt Ltd")
    assert len(r["ledger"]["hash"]) == 64
    d = client.post("/api/officer-decision", headers=OFF, json={"tender_id": "tanker-transport",
                    "bidder_name": "Ratnagiri Roadlines Pvt Ltd", "decision": "Request Clarification"}).json()
    assert d["ledger"]["seq"] > r["ledger"]["seq"]
    v = verify()
    assert v["ok"] and v["problems"] == [] and v["records_checked"] == 1
    rows = client.get("/api/audit-log", headers=OFF).json()
    assert rows[0]["ledger"]["hash"] == d["ledger"]["hash"]


def test_editing_a_score_in_the_database_is_caught():
    r = evaluate("refinery-ppe", "Apex Safety Products Pvt Ltd")
    with get_db() as conn:
        conn.execute("UPDATE audit_log SET compliance_score=100, ai_verdict='Compliant' WHERE id=?", (r["evaluation_id"],))
    v = verify()
    assert not v["ok"]
    assert any(f"#{r['evaluation_id']}" in p and "score" in p for p in v["problems"])


def test_editing_a_decision_or_deleting_a_row_is_caught():
    a = evaluate("pipeline-valves", "Vantage Flow Systems Pvt Ltd")
    b = evaluate("pipeline-valves", "Petrotech Valve Industries Private Limited")
    with get_db() as conn:
        conn.execute("UPDATE audit_log SET officer_decision='Qualified', decided_by='officer1' WHERE id=?", (a["evaluation_id"],))
        conn.execute("DELETE FROM audit_log WHERE id=?", (b["evaluation_id"],))
    probs = " ".join(verify()["problems"])
    assert f"#{a['evaluation_id']}" in probs and f"#{b['evaluation_id']}" in probs and "deleted outside the app" in probs


def test_rewriting_the_ledger_itself_breaks_the_chain():
    evaluate("depot-security", "Meridian Guard Solutions Pvt Ltd")
    evaluate("depot-security", "Falcon Inspection Technologies")
    with get_db() as conn:
        first = conn.execute("SELECT id, payload FROM ledger WHERE kind='evaluation' ORDER BY id LIMIT 1").fetchone()
        p = json.loads(first["payload"])
        p["score"] = 100
        conn.execute("UPDATE ledger SET payload=? WHERE id=?", (ledger.canon(p), first["id"]))
    v = verify()
    assert not v["ok"] and any("hash" in x.lower() for x in v["problems"])


def test_retention_keeps_the_chain_intact():
    r = evaluate("tanker-transport", "Konkan Bulk Carriers Ltd")
    with get_db() as conn:
        conn.execute("UPDATE audit_log SET ts='2020-01-01T00:00:00+00:00' WHERE id=?", (r["evaluation_id"],))
    assert run_retention() == 1
    v = verify()
    assert v["ok"], v["problems"]
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM ledger WHERE kind='anonymised'").fetchone()["n"] == 1


def test_reset_starts_a_new_chain_that_names_the_old_head():
    evaluate("pipeline-survey", "Falcon Inspection Technologies")
    with get_db() as conn:
        old = ledger.head(conn)
    r = client.post("/api/admin/reset-demo", headers=ADM).json()
    assert r["previous_head"] == old
    with get_db() as conn:
        rows = ledger.entries(conn)
    assert len(rows) == 1 and rows[0]["kind"] == "reset" and json.loads(rows[0]["payload"])["previous_head"] == old
    assert verify()["ok"]


def test_export_carries_the_ledger():
    evaluate("pipeline-survey", "Falcon Inspection Technologies")
    r = client.get("/api/audit-log/export", headers=ADM).json()
    assert r["ledger"] and r["ledger_head"] == r["ledger"][-1]["hash"]
    problems, head = ledger.verify_chain(r["ledger"])
    assert problems == [] and head == r["ledger_head"]


# ------------------------------------------------------------------ rulebook
def extract_rulebook(h=OFF):
    return client.post("/api/rulebooks/extract", data={"tender_id": "tanker-transport"}, headers=h,
                       files={"file": ("nit.pdf", (SAMPLES / "tanker-transport-tender-sample.pdf").read_bytes(), "application/pdf")})


def test_rulebook_is_read_from_the_tender_document_with_pages():
    r = extract_rulebook()
    assert r.status_code == 200, r.text
    rb = r.json()
    rules = {x["key"]: x for x in rb["rules"]}
    assert rules["min_turnover"]["value"] == 40_000_000 and rules["min_turnover"]["page"] == 1
    assert "Rs 4 Crore" in rules["min_turnover"]["line"]
    assert rules["emd_amount"]["value"] == 180_000 and rules["labour_services"]["page"] == 2
    assert {c["key"]: c["status"] for c in rb["comparison"]}["min_turnover"] == "differs"
    assert rb["status"] == "draft" and rb["method"] == "text layer"


def test_only_a_senior_approver_applies_a_rulebook_and_it_changes_the_result():
    rid = extract_rulebook().json()["id"]
    before = {c["name"]: c for c in evaluate("tanker-transport", "Ratnagiri Roadlines Pvt Ltd")["checks"]}
    assert before["Financial turnover"]["status"] == "PASS"
    assert client.post(f"/api/rulebooks/{rid}/apply", headers=OFF).status_code == 403
    r = client.post(f"/api/rulebooks/{rid}/apply", headers=APP)
    assert r.status_code == 200 and r.json()["tender"]["min_turnover"] == 40_000_000
    after = evaluate("tanker-transport", "Ratnagiri Roadlines Pvt Ltd")
    turnover = {c["name"]: c for c in after["checks"]}["Financial turnover"]
    assert turnover["status"] == "FAIL" and "page 1" in turnover["reason"] and after["rulebook"]["id"] == rid
    assert {c["name"]: c for c in evaluate("tanker-transport", "Swift Tanker Logistics Pvt Ltd")["checks"]}["Financial turnover"]["status"] == "PASS"
    with get_db() as conn:
        kinds = [e["kind"] for e in ledger.entries(conn)]
    assert "rulebook_applied" in kinds
    assert client.post("/api/tenders/tanker-transport/rulebook/revert", headers=APP).status_code == 200
    back = {c["name"]: c for c in evaluate("tanker-transport", "Ratnagiri Roadlines Pvt Ltd")["checks"]}
    assert back["Financial turnover"]["status"] == "PASS"
    assert client.post("/api/tenders/tanker-transport/rulebook/revert", headers=APP).status_code == 409
    assert verify()["ok"]


def test_approver_can_correct_a_misread_value_before_applying():
    rid = extract_rulebook().json()["id"]
    r = client.post(f"/api/rulebooks/{rid}/apply", headers=APP, json={"values": {"min_turnover": 35_000_000}})
    assert r.status_code == 200 and r.json()["edited"] == ["min_turnover"] and r.json()["tender"]["min_turnover"] == 35_000_000
    assert client.post(f"/api/rulebooks/{rid}/apply", headers=APP, json={"values": {"labour_services": 0}}).status_code == 422
    client.post("/api/tenders/tanker-transport/rulebook/revert", headers=APP)


def test_rulebook_rejects_non_pdf_and_unknown_tender():
    assert client.post("/api/rulebooks/extract", data={"tender_id": "tanker-transport"}, headers=OFF,
                       files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 415
    assert client.post("/api/rulebooks/extract", data={"tender_id": "nope"}, headers=OFF,
                       files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}).status_code == 404


def test_rulebook_wording_variants():
    from app import rulebook
    pages = [(1, "OEM Authorization Certificate: Not required\nMSE Exemption for Years of Experience and Turnover : Yes\n"
                 "Earnest Money Deposit (EMD) of Rs. 2,50,000/- shall be paid\n"
                 "Minimum average annual turnover of Rs 12.5 crore during last 3 financial years")]
    rules = {r["key"]: r["value"] for r in rulebook.extract_rules(pages)}
    assert rules == {"emd_amount": 250_000, "min_turnover": 125_000_000, "mse_exemption": True}


# ------------------------------------------------------------------ ownership links and debarment
def test_collusion_finds_shared_directors_contacts_and_bank_accounts():
    r = client.get("/api/collusion-check", params={"tender_id": "tanker-transport"}, headers=OFF).json()
    sig = {f["signal"] for f in r["findings"]}
    assert {"Shared director", "Shared contact details"} <= sig
    edge = [e for e in r["graph"]["edges"] if {e["a"], e["b"]} == {"Swift Tanker Logistics Pvt Ltd", "Ratnagiri Roadlines Pvt Ltd"}][0]
    assert {"price", "timing", "director", "contact"} <= set(edge["links"])
    r = client.get("/api/collusion-check", params={"tender_id": "refinery-ppe"}, headers=OFF).json()
    assert [f["signal"] for f in r["findings"]] == ["Shared bank account"]
    assert len(r["graph"]["nodes"]) == 3


def test_debarment_survives_a_renamed_or_new_name_bid():
    assert registry.debarment("Apex Safety Products Private Limited")["matched_by"] == "name"
    assert registry.debarment("Apex Protective Solutions", "AAKCA7741E")["matched_by"] == "PAN"
    assert registry.debarment("Apex Safety Solutions Pvt Ltd") is None


# ------------------------------------------------------------------ OCR (Sarvam Vision), mocked
SCANNED = (SAMPLES / "ratnagiri-registration-scanned-sample.pdf").read_bytes()


def test_scanned_pdf_without_a_key_says_what_is_needed():
    r = client.post("/api/documents/extract", data={"tender_id": "tanker-transport", "bidder_name": "Ratnagiri Roadlines Pvt Ltd"},
                    headers=OFF, files={"file": ("scan.pdf", SCANNED, "application/pdf")})
    assert r.status_code == 200 and r.json()["fields"] == [] and "Sarvam" in r.json()["summary"]


def test_scanned_pdf_is_read_by_ocr(monkeypatch):
    calls = {}

    def fake_parse(blob, language="en-IN", sleep=None):
        calls["bytes"] = len(blob)
        return [(1, "Legal Name of Business: Ratnagiri Roadlines Pvt Ltd\nGSTIN: 27AAHCR6652N1ZP\nCIN: U60231MH2023PTC166520")]
    monkeypatch.setattr(sarvam, "configured", lambda: True)
    monkeypatch.setattr(sarvam, "parse_pdf", fake_parse)
    r = client.post("/api/documents/extract", data={"tender_id": "tanker-transport", "bidder_name": "Ratnagiri Roadlines Pvt Ltd"},
                    headers=OFF, files={"file": ("scan.pdf", SCANNED, "application/pdf")}).json()
    assert calls["bytes"] > 0 and r["method"].startswith("OCR")
    got = {f["field"]: f for f in r["fields"]}
    assert got["GSTIN"]["status"] == "MATCH" and got["GSTIN"]["page"] == 1 and "27AAHCR6652N1ZP" in got["GSTIN"]["snippet"]
    assert got["Legal name"]["status"] == "MATCH" and "Sarvam Vision" in r["summary"]


def test_text_pdfs_never_go_to_ocr(monkeypatch):
    monkeypatch.setattr(sarvam, "configured", lambda: True)
    monkeypatch.setattr(sarvam, "parse_pdf", lambda *a, **k: pytest.fail("OCR called for a text PDF"))
    doc = documents.read_document((SAMPLES / "petrotech-registration-sample.pdf").read_bytes())
    assert doc["method"] == "text layer"


# ------------------------------------------------------------------ languages (Sarvam), mocked
def test_twenty_two_scheduled_languages_plus_english():
    r = client.get("/api/languages").json()
    codes = {x["code"] for x in r["languages"]}
    assert len(codes) == 23 and {"sat-IN", "mni-IN", "brx-IN", "doi-IN", "ks-IN", "kok-IN", "mai-IN", "sa-IN", "sd-IN"} <= codes
    assert r["configured"] is False
    assert all(x["native"] for x in r["languages"])


def test_translate_needs_a_key_and_a_known_language():
    body = {"target": "hi-IN", "texts": ["Financial turnover"]}
    assert client.post("/api/translate", json=body).status_code == 401
    assert client.post("/api/translate", json=body, headers=OFF).status_code == 503
    assert client.post("/api/translate", json={"target": "xx-IN", "texts": ["a"]}, headers=OFF).status_code == 422


def test_translate_keeps_identifiers_and_caches(monkeypatch):
    sent = []

    def fake_raw(text, target):
        sent.append(text)
        return "\n".join(f"<{target}> {line}" for line in text.split("\n"))
    monkeypatch.setattr(sarvam, "configured", lambda: True)
    monkeypatch.setattr(sarvam, "_translate_raw", fake_raw)
    texts = ["GSTIN 27AAHCR6652N1ZP is valid", "Financial turnover", "Financial turnover"]
    r = client.post("/api/translate", json={"target": "ta-IN", "texts": texts}, headers=OFF).json()
    assert r["translations"][0] == "<ta-IN> GSTIN 27AAHCR6652N1ZP is valid"
    assert "27AAHCR6652N1ZP" not in "".join(sent)  # the identifier never went to the model
    assert r["translations"][1] == r["translations"][2] and r["translated"] == 2
    again = client.post("/api/translate", json={"target": "ta-IN", "texts": texts[:2]}, headers=OFF).json()
    assert again["cached"] == 2 and again["translated"] == 0


def test_translation_that_drops_an_identifier_falls_back_to_english(monkeypatch):
    monkeypatch.setattr(sarvam, "configured", lambda: True)
    monkeypatch.setattr(sarvam, "_translate_raw", lambda text, target: "translated without the placeholder")
    assert sarvam.translate("PAN AAHCR6652N on record", "hi-IN") == "PAN AAHCR6652N on record"


# ------------------------------------------------------------------ measured results and health
def test_eval_results_are_served():
    r = client.get("/api/eval", headers=OFF).json()
    s = r["summary"]
    assert s["defects_caught"] == s["defects_planted"] > 50 and s["clean_flagged"] == 0
    assert s["checks_covered"] == s["checks_total"] == 15 and r["not_covered"] == []


def test_health_reports_sarvam():
    h = client.get("/api/health").json()
    assert h["version"] == "3.0.0" and h["sarvam"]["languages"] == 22 and h["sarvam"]["translate"] is None


def _zip(files):
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_ocr_asks_for_the_format_the_job_produced(monkeypatch):
    calls = []

    def fake_request(method, path, **kw):
        calls.append(path)
        if path.endswith("/parse"):
            return {"job_id": "j1", "status": "accepted"}
        if path.endswith("/status"):
            return {"status": "completed"}
        if "format=html" in path:  # parse results arrive as a ZIP of HTML pages
            return _zip({"output/page_1.html": "<p>Legal Name of Business: X Ltd<br>GSTIN: 27AAHCR6652N1ZP</p>",
                         "output/page_2.html": "<p>CIN: U60231MH2023PTC166520</p>"})
        raise sarvam.SarvamError("Sarvam returned HTTP 400: job produced html, cannot serve json")
    monkeypatch.setattr(sarvam, "configured", lambda: True)
    monkeypatch.setattr(sarvam, "_request", fake_request)
    pages = sarvam.parse_pdf(b"%PDF-1.4", sleep=lambda s: None)
    assert pages == [(1, "Legal Name of Business: X Ltd\nGSTIN: 27AAHCR6652N1ZP"), (2, "CIN: U60231MH2023PTC166520")]
    assert calls[-1].endswith("format=html")


def test_ocr_reads_a_zip_with_a_json_result_or_one_html_file():
    j = {"documents": [{"pages": [{"page_number": 1, "content": "GSTIN: 27AAHCR6652N1ZP"}]}]}
    assert sarvam._from_zip(_zip({"result.json": json.dumps(j), "page_1.html": "<p>x</p>"})) == j
    one = sarvam._from_zip(_zip({"document.html": '<div data-page="1"><p>A</p></div><div data-page="2"><p>B</p></div>'}))
    assert [(p["page_number"], sarvam._strip_markup(p["content"])) for p in one["documents"][0]["pages"]] == [(1, "A"), (2, "B")]


def test_model_suggestions_that_restate_read_rules_are_dropped(monkeypatch):
    from app import llm, rulebook
    said = [{"condition": "Bidders must submit GST registration certificate, PAN card, audited balance sheets, PESO licence and vehicle "
                          "registration certificates.", "page": 1},
            {"condition": "The bidder shall deploy a fleet of at least 8 tank trucks fitted with GPS.", "page": 2},
            {"condition": "The service provider shall comply with EPF and ESIC for all drivers.", "page": 2}]
    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "_post", lambda payload: {"choices": [{"message": {"content": json.dumps(said)}}]})
    doc = documents.read_document((SAMPLES / "tanker-transport-tender-sample.pdf").read_bytes())
    rules = rulebook.extract_rules(doc["pages"])
    got = rulebook.suggest(doc["pages"], rules)
    assert [g["condition"] for g in got] == [said[1]["condition"]] and got[0]["page"] == 2


def test_sarvam_replies_that_arrive_gzipped_are_read():
    import gzip as gz
    assert sarvam._body(gz.compress('{"a": "ठीक"}'.encode())) == '{"a": "ठीक"}'
    assert sarvam._body('{"a": 1}'.encode()) == '{"a": 1}'
