"""Rejection paths of POST /api/documents/extract.

Reuses the client and officer token from test_api, so the isolated test
database and the cleared LLM keys set up there apply here too.
"""
from app import documents

from .test_api import OFF, client

FORM = {"tender_id": "pipeline-valves", "bidder_name": "Vantage Flow Systems Pvt Ltd"}


def _upload(blob, form=FORM):
    return client.post("/api/documents/extract", data=form, headers=OFF,
                       files={"file": ("bid.pdf", blob, "application/pdf")})


def test_file_over_the_size_limit_is_rejected():
    r = _upload(b"%PDF-1.4\n" + b"0" * documents.MAX_BYTES)
    assert r.status_code == 413
    assert "4 MB" in r.json()["detail"]


def test_unreadable_pdf_is_rejected():
    r = _upload(b"%PDF-1.4\nthis is not a real PDF body")
    assert r.status_code == 422
    assert r.json()["detail"] == "This PDF could not be read."


def test_bidder_not_on_the_tender_is_rejected():
    r = _upload(b"%PDF-1.4", dict(FORM, bidder_name="Nobody Pvt Ltd"))
    assert r.status_code == 404
    assert "has not bid on pipeline-valves" in r.json()["detail"]


def test_unknown_tender_is_rejected():
    r = _upload(b"%PDF-1.4", dict(FORM, tender_id="no-such-tender"))
    assert r.status_code == 404
    assert r.json()["detail"] == "Unknown tender: no-such-tender"
