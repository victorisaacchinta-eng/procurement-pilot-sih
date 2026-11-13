"""
Document verification: read a bid document (PDF) and cross-check the
identifiers in it against the bid on record.

Reading, in this order:
  text layer     pypdf, page by page (digitally generated PDFs)
  OCR            scanned PDFs have no text layer; they go to Sarvam Vision
                 (Document AI parse job), which reads 22 Indian languages and
                 English. Needs a Sarvam key; without one the result says so.

Every value found carries the page it was found on and the line around it,
so the officer can open the document at that page and see it for themselves.
The GSTIN check-digit rule is the same one the checks use. Nothing here
changes the score. It is evidence for the officer.
"""
import io
import re

from . import registry as R
from . import sarvam

MAX_BYTES = 4 * 1024 * 1024
PATTERNS = {
    "GSTIN": re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"),
    "PAN": re.compile(r"\b[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]\b"),
    "Udyam": re.compile(r"\bUDYAM-[A-Z]{2}-\d{2}-\d{7}\b"),
    "CIN": re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b"),
    "DPIIT": re.compile(r"\bDIPP\d{3,7}\b"),
}
NAME_RE = re.compile(r"(?:Legal Name(?: of (?:Business|the Company))?|Name of (?:Enterprise|Company|Entity))\s*[:\-]\s*(.+)", re.I)
OCR_ENGINE = "Sarvam Vision (Document AI)"


def read_pdf_pages(blob: bytes) -> list:
    """[(page_number, text)] from the PDF's text layer."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(blob))
    return [(i, p.extract_text() or "") for i, p in enumerate(reader.pages, 1)]


def first_pages(blob: bytes, n: int) -> bytes:
    from pypdf import PdfReader, PdfWriter
    reader, writer = PdfReader(io.BytesIO(blob)), PdfWriter()
    for p in reader.pages[:n]:
        writer.add_page(p)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def read_document(blob: bytes) -> dict:
    """Pages of text plus how they were read. Never raises for a scanned file; says what happened instead."""
    pages = read_pdf_pages(blob)
    chars = sum(len(re.sub(r"\s+", "", t)) for _, t in pages)
    if chars >= 20:
        return {"pages": pages, "page_count": len(pages), "method": "text layer", "note": None}
    if not sarvam.configured():
        return {"pages": [], "page_count": len(pages), "method": None,
                "note": "No text layer found. This looks like a scanned document. Reading it needs OCR through Sarvam Vision, "
                        "which needs the Sarvam API key on the server. Nothing was verified from this file."}
    note = None
    src = blob
    if len(pages) > sarvam.OCR_MAX_PAGES:
        src = first_pages(blob, sarvam.OCR_MAX_PAGES)
        note = f"Only the first {sarvam.OCR_MAX_PAGES} of {len(pages)} pages were read by OCR."
    try:
        ocr = sarvam.parse_pdf(src)
    except Exception as e:  # never let an OCR surprise take the whole check down
        if not isinstance(e, sarvam.SarvamError):
            print(f"[documents] OCR failed: {type(e).__name__}: {e}", flush=True)
            e = f"an unexpected {type(e).__name__} reading Sarvam's reply"
        return {"pages": [], "page_count": len(pages), "method": None,
                "note": f"This is a scanned document and OCR did not complete: {e}. Nothing was verified from this file."}
    return {"pages": ocr, "page_count": len(pages), "method": f"OCR, {OCR_ENGINE}", "note": note}


def snippet(line: str, value: str, width: int = 90) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    if len(line) <= width:
        return line
    i = max(0, line.upper().find(value.upper()) - width // 3)
    return ("…" if i else "") + line[i:i + width].strip() + "…"


def find_all(pages: list, rx: re.Pattern, upper: bool = True) -> list:
    """Every distinct match with the first page and line it appears on: [(value, page, line)]."""
    seen, out = set(), []
    for pno, text in pages:
        for line in (text or "").splitlines():
            hay = line.upper() if upper else line
            for m in rx.finditer(hay):
                v = m.group(0)
                if v not in seen:
                    seen.add(v)
                    out.append((v, pno, line))
    return out


def extract(blob: bytes, bidder_name: str, bidder: dict) -> dict:
    doc = read_document(blob)
    pages = doc["pages"]
    base = {"pages": doc["page_count"], "method": doc["method"], "text_layer": doc["method"] == "text layer"}
    if not pages:
        return dict(base, fields=[], summary=doc["note"])
    found = {k: find_all(pages, rx) for k, rx in PATTERNS.items()}
    gstins = [v for v, *_ in found["GSTIN"]]
    # A PAN inside a GSTIN is not a separate PAN.
    pans = [x for x in found["PAN"] if not any(x[0] in g for g in gstins)]
    if not pans and found["GSTIN"]:
        g, pno, line = found["GSTIN"][0]
        pans = [(R.pan_from_gstin(g), pno, line)]
    name_hit = None
    for pno, text in pages:
        m = NAME_RE.search(text or "")
        if m:
            name_hit = (m.group(1).strip().split("\n")[0].strip(), pno, m.group(0).split("\n")[0])
            break

    def row(field, value, on_bid, status, note, pno, line):
        return {"field": field, "found": value, "on_bid": on_bid, "status": status, "note": note, "page": pno, "snippet": snippet(line, value)}

    rows = []
    bid_gstin = (bidder.get("gstin") or "").upper()
    for g, pno, line in found["GSTIN"][:3]:
        ok, msg = R.validate_gstin(g)
        if not ok:
            rows.append(row("GSTIN", g, bid_gstin, "INVALID", msg, pno, line))
        else:
            rows.append(row("GSTIN", g, bid_gstin, "MATCH" if g == bid_gstin else "MISMATCH",
                            "Check digit valid." + ("" if g == bid_gstin else " Differs from the GSTIN on the bid."), pno, line))
    bid_pan = R.pan_from_gstin(bid_gstin)
    for p, pno, line in pans[:2]:
        rows.append(row("PAN", p, bid_pan, "MATCH" if p == bid_pan else "MISMATCH", f"Holder type: {R.PAN_TYPES.get(p[3], 'unknown')}.", pno, line))
    for key, bid_key in (("Udyam", "udyam"), ("CIN", "cin"), ("DPIIT", "dpiit")):
        want = (bidder.get(bid_key) or "").upper()
        for v, pno, line in found[key][:2]:
            rows.append(row(key, v, want or "(none)", "MATCH" if v == want else "MISMATCH", "", pno, line))
    if name_hit:
        r = R.similar(name_hit[0], bidder_name)
        rows.append(row("Legal name", name_hit[0], bidder_name, "MATCH" if r >= 0.85 else "MISMATCH", f"{round(r*100)}% textual match.",
                        name_hit[1], name_hit[2]))
    bad = [x for x in rows if x["status"] != "MATCH"]
    if not rows:
        summary = "Text was read, but no GSTIN, PAN, Udyam, CIN, DPIIT number or legal name was found."
    elif bad:
        summary = f"{len(bad)} of {len(rows)} identifiers in this document do not match the bid: " + ", ".join(f"{x['field']} ({x['status'].lower()})" for x in bad) + "."
    else:
        summary = f"All {len(rows)} identifiers found in this document match the bid."
    if doc["method"] and doc["method"].startswith("OCR"):
        summary += f" Read from a scanned image by {OCR_ENGINE}."
    if doc["note"]:
        summary += " " + doc["note"]
    chars = sum(len(t or "") for _, t in pages)
    return dict(base, chars=chars, fields=rows, summary=summary)
