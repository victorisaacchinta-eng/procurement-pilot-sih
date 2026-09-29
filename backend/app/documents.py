"""
Document verification: read a bid document (PDF) and cross-check the
identifiers in it against the bid on record.

Real: text extraction from the PDF's text layer (pypdf) and pattern matching for
GSTIN, PAN, Udyam, CIN, DPIIT numbers and the legal name, followed by the same
GSTIN check-digit rule the checks use. Scanned PDFs have no text layer; they
need OCR, which is planned (see docs/REPO_SCOPE.md), and the result says so.
Nothing here changes the score. It is evidence for the officer.
"""
import io
import re

from . import registry as R

MAX_BYTES = 4 * 1024 * 1024
PATTERNS = {
    "GSTIN": re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"),
    "PAN": re.compile(r"\b[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]\b"),
    "Udyam": re.compile(r"\bUDYAM-[A-Z]{2}-\d{2}-\d{7}\b"),
    "CIN": re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b"),
    "DPIIT": re.compile(r"\bDIPP\d{3,7}\b"),
}
NAME_RE = re.compile(r"(?:Legal Name(?: of (?:Business|the Company))?|Name of (?:Enterprise|Company|Entity))\s*[:\-]\s*(.+)", re.I)


def read_pdf_text(blob: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return "\n".join((p.extract_text() or "") for p in reader.pages), len(reader.pages)


def extract(blob: bytes, bidder_name: str, bidder: dict) -> dict:
    text, pages = read_pdf_text(blob)
    flat = re.sub(r"[ \t]+", " ", text)
    if len(flat.strip()) < 20:
        return {"pages": pages, "text_layer": False, "fields": [], "summary":
                "No text layer found. This looks like a scanned document; reading it needs OCR, which is planned. "
                "Nothing was verified from this file."}
    found = {}
    for k, rx in PATTERNS.items():
        vals = []
        for m in rx.findall(flat.upper()):
            if m not in vals:
                vals.append(m)
        found[k] = vals
    # A PAN inside a GSTIN is not a separate PAN.
    found["PAN"] = [p for p in found["PAN"] if not any(p in g for g in found["GSTIN"])] or [R.pan_from_gstin(g) for g in found["GSTIN"][:1]]
    nm = NAME_RE.search(flat)
    doc_name = nm.group(1).strip().split("\n")[0].strip() if nm else ""

    rows = []
    bid_gstin = (bidder.get("gstin") or "").upper()
    for g in found["GSTIN"][:3]:
        ok, msg = R.validate_gstin(g)
        if not ok:
            rows.append({"field": "GSTIN", "found": g, "on_bid": bid_gstin, "status": "INVALID", "note": msg})
        else:
            rows.append({"field": "GSTIN", "found": g, "on_bid": bid_gstin, "status": "MATCH" if g == bid_gstin else "MISMATCH",
                         "note": "Check digit valid." + ("" if g == bid_gstin else " Differs from the GSTIN on the bid.")})
    bid_pan = R.pan_from_gstin(bid_gstin)
    for p in found["PAN"][:2]:
        rows.append({"field": "PAN", "found": p, "on_bid": bid_pan, "status": "MATCH" if p == bid_pan else "MISMATCH",
                     "note": f"Holder type: {R.PAN_TYPES.get(p[3], 'unknown')}."})
    for key, bid_key in (("Udyam", "udyam"), ("CIN", "cin"), ("DPIIT", "dpiit")):
        want = (bidder.get(bid_key) or "").upper()
        for v in found[key][:2]:
            rows.append({"field": key, "found": v, "on_bid": want or "(none)", "status": "MATCH" if v == want else "MISMATCH", "note": ""})
    if doc_name:
        r = R.similar(doc_name, bidder_name)
        rows.append({"field": "Legal name", "found": doc_name, "on_bid": bidder_name, "status": "MATCH" if r >= 0.85 else "MISMATCH",
                     "note": f"{round(r*100)}% textual match."})
    bad = [x for x in rows if x["status"] != "MATCH"]
    if not rows:
        summary = "Text was read, but no GSTIN, PAN, Udyam, CIN, DPIIT number or legal name was found."
    elif bad:
        summary = f"{len(bad)} of {len(rows)} identifiers in this document do not match the bid: " + ", ".join(f"{x['field']} ({x['status'].lower()})" for x in bad) + "."
    else:
        summary = f"All {len(rows)} identifiers found in this document match the bid."
    return {"pages": pages, "text_layer": True, "chars": len(flat), "fields": rows, "summary": summary}
