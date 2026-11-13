"""
Tender rulebook: read the eligibility rules from the tender document itself.

The fifteen checks are only as good as the tender values they compare
against. Those values are usually keyed in by hand, and one dropped zero in
"minimum turnover" can qualify a bidder the tender would have rejected. Here
the officer uploads the tender document (the GeM bid document or NIT), the
rules are read out of it page by page, and every value carries the page and
line it came from.

  Rules first    regular expressions for the fields GeM bid documents and
                 NITs actually print: EMD amount, minimum average annual
                 turnover, estimated bid value, years of experience, MSE and
                 Startup exemptions, Make in India, OEM authorisation, labour
                 clauses, required documents, bid end date and bid number
  Sarvam second  if the reasoning layer is configured, sarvam-105b lists any
                 other eligibility condition it sees. Those come back as
                 suggestions for the officer to check against the page; they
                 are never applied on their own

Applying a rulebook to a tender is a senior approver's call and goes on the
ledger. Applied rules change what the checks compare against; they never
loosen a requirement that is already on record (documents and flags are
added, not removed).
"""
import json
import re

from . import llm

LAKH, CRORE = 100_000, 10_000_000
_AMT = r"(?:Rs\.?|INR|₹)?\s*([\d][\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr\.?|l\b)?"
YESNO = r"[^\n:]{0,60}?[:\s]+\b(yes|no|applicable|not\s+applicable|allowed|not\s+allowed)\b"
NEGATED = re.compile(r"\bnot\s+(?:required|applicable|mandatory)\b|:\s*no\b", re.I)

AMOUNT_RULES = [
    ("min_turnover", "Minimum average annual turnover",
     re.compile(r"(?:minimum\s+)?(?:average\s+)?annual\s+turnover(?:\s+of\s+the\s+bidder)?(?:\s*\((?:for\s+)?(?:last\s+)?\d+\s+(?:financial\s+)?years?\))?"
                r"[^\d₹]{0,80}?" + _AMT, re.I)),
    ("emd_amount", "EMD amount",
     re.compile(r"(?:EMD\s+amount|earnest\s+money\s+deposit(?:\s*\(EMD\))?(?:\s+of)?)[^\d₹]{0,40}?" + _AMT, re.I)),
    ("estimated_value", "Estimated bid value",
     re.compile(r"estimated\s+(?:bid\s+|tender\s+|contract\s+)?(?:value|cost)[^\d₹]{0,40}?" + _AMT, re.I)),
]
EXPERIENCE = re.compile(r"(?:years?\s+of\s+past\s+experience\s+required[^\d]{0,60}?(\d{1,2})\s*years?"
                        r"|(?:minimum\s+(?:of\s+)?)?(\d{1,2})\s*years?\s+(?:of\s+)?(?:past\s+|relevant\s+|similar\s+)?(?:experience|operations?|in\s+business))", re.I)
YESNO_RULES = [  # the value printed after the label decides it
    ("mse_exemption", "MSE exemption allowed", re.compile(r"MSE\s+(?:exemption|purchase\s+preference)" + YESNO, re.I)),
    ("startup_exemption", "Startup exemption allowed", re.compile(r"start-?up\s+exemption" + YESNO, re.I)),
    ("mii", "Make in India preference applies", re.compile(r"MII\s+(?:compliance|purchase\s+preference)" + YESNO, re.I)),
]
FLAG_RULES = [  # the clause being there decides it, unless the line says it does not apply
    ("mii", "Make in India preference applies", re.compile(r"preference\s+to\s+make\s+in\s+india|class[- ]i\s+local\s+supplier", re.I)),
    ("oem_authorisation_required", "OEM authorisation required", re.compile(r"OEM\s+authori[sz]ation", re.I)),
    ("labour_services", "Labour law compliance (EPFO, ESIC)", re.compile(r"\b(?:EPF|EPFO|ESI|ESIC|minimum\s+wages|manpower\s+outsourcing)\b", re.I)),
]
BID_END = re.compile(r"(?:bid\s+end\s+date(?:/time)?|last\s+date\s+(?:and\s+time\s+)?(?:of|for)\s+(?:bid\s+)?submission)[^\d]{0,20}(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})", re.I)
BID_NO = re.compile(r"GEM/\d{4}/B/\d+", re.I)
DOCUMENTS = [  # name as the checks use it, then what tender documents print
    ("GST registration certificate", r"GST\s+(?:registration\s+)?certificate|GSTIN\s+certificate"),
    ("PAN card", r"\bPAN\s+card\b|copy\s+of\s+PAN"),
    ("Audited financial statements", r"audited\s+(?:financial\s+statements|balance\s+sheets?|accounts)"),
    ("API 6D licence", r"API\s*6D\s+(?:licen[cs]e|monogram|certificate)"),
    ("API 607 fire-test report", r"API\s*607"),
    ("BIS licence copy", r"BIS\s+licen[cs]e"),
    ("PESO licence", r"PESO\s+(?:licen[cs]e|approval)"),
    ("Vehicle registration certificates", r"(?:vehicle\s+)?registration\s+certificates?\s+\(?RC|vehicle\s+registration\s+certificates?"),
    ("PSARA licence copy", r"PSARA\s+licen[cs]e"),
    ("NDT accreditation certificate", r"NDT\s+accreditation"),
    ("ISO 9001 certificate", r"ISO\s*9001"),
    ("OEM authorisation letter", r"OEM\s+authori[sz]ation\s+(?:letter|certificate)"),
    ("Experience certificates", r"experience\s+(?:certificates?|criteria)|work\s+orders?\s+(?:and|&)\s+completion"),
]


def to_rupees(num: str, unit: str | None) -> int:
    n = float(num.replace(",", ""))
    u = (unit or "").lower().rstrip(".")
    if u.startswith(("crore", "cr")):
        n *= CRORE
    elif u.startswith(("lakh", "lac")) or u == "l":
        n *= LAKH
    return int(round(n))


def fmt_rupees(n: int) -> str:
    if n >= CRORE:
        return f"Rs {n / CRORE:g} crore"
    if n >= LAKH:
        return f"Rs {n / LAKH:g} lakh"
    return f"Rs {n:,}"


def _line_of(text: str, start: int, end: int | None = None) -> str:
    """The printed line(s) a match sits on. A label and its value often extract as two lines."""
    end = start if end is None else end
    while end > start and text[end - 1].isspace():  # a match can swallow the line break after the value
        end -= 1
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", end)
    chunk = text[a:b if b >= 0 else None]
    return " / ".join(p for p in (re.sub(r"\s+", " ", x).strip() for x in chunk.split("\n")) if p)[:180]


def _first(pages, rx):
    for pno, text in pages:
        m = rx.search(text or "")
        if m:
            return m, pno, _line_of(text, m.start(), m.end())
    return None


def extract_rules(pages: list) -> list:
    rules = []
    for key, label, rx in AMOUNT_RULES:
        done = False
        for pno, text in pages:
            for m in rx.finditer(text or ""):
                value = to_rupees(m.group(1), m.group(2))
                if value >= 1000:  # anything smaller is a year count or a clause number, not money
                    rules.append({"key": key, "label": label, "value": value, "display": fmt_rupees(value), "page": pno,
                                  "line": _line_of(text, m.start(), m.end()), "method": "rule"})
                    done = True
                    break
            if done:
                break
    hit = _first(pages, EXPERIENCE)
    if hit:
        m, pno, line = hit
        years = int(m.group(1) or m.group(2))
        rules.append({"key": "experience_years", "label": "Years of experience required", "value": years,
                      "display": f"{years} year{'s' if years != 1 else ''}", "page": pno, "line": line, "method": "rule"})
    seen = set()
    for key, label, rx in YESNO_RULES:
        hit = _first(pages, rx)
        if hit:
            m, pno, line = hit
            seen.add(key)
            if m.group(1).lower() in ("yes", "applicable", "allowed"):
                rules.append({"key": key, "label": label, "value": True, "display": "Yes", "page": pno, "line": line, "method": "rule"})
    for key, label, rx in FLAG_RULES:
        if key in seen:
            continue
        for pno, text in pages:
            m = next((m for m in rx.finditer(text or "") if not NEGATED.search(_line_of(text, m.start()))), None)
            if m:
                rules.append({"key": key, "label": label, "value": True, "display": "Yes", "page": pno, "line": _line_of(text, m.start()), "method": "rule"})
                break
    docs = []
    for name, pattern in DOCUMENTS:
        rx = re.compile(pattern, re.I)
        for pno, text in pages:
            m = next((m for m in rx.finditer(text or "") if not NEGATED.search(_line_of(text, m.start(), m.end()))), None)
            if m:
                docs.append({"name": name, "page": pno, "line": _line_of(text, m.start(), m.end())})
                break
    if docs:
        rules.append({"key": "required_documents", "label": "Documents required", "value": [d["name"] for d in docs],
                      "display": ", ".join(d["name"] for d in docs), "page": docs[0]["page"], "line": docs[0]["line"],
                      "method": "rule", "items": docs})
    for key, label, rx in (("bid_end", "Bid end date", BID_END), ("bid_number", "GeM bid number", BID_NO)):
        hit = _first(pages, rx)
        if hit:
            m, pno, line = hit
            v = m.group(1) if m.groups() else m.group(0).upper()
            rules.append({"key": key, "label": label, "value": v, "display": v, "page": pno, "line": line, "method": "rule", "info": True})
    return rules


SUGGEST_PROMPT = (
    "You read Indian government tender documents. You are given the text of one tender document, page by page, and the "
    "eligibility rules already read from it by code. List up to six OTHER eligibility or qualification conditions a "
    "procurement officer must verify (for example certifications, licences, fleet size, staff qualifications, past "
    "orders). Return only a JSON array, each item {\"condition\": short sentence, \"page\": page number}. If there are "
    "none, return []. Use only what the text says. No markdown."
)


def suggest(pages: list, rules: list) -> list:
    """Sarvam's read of conditions the rules did not cover. Advisory; never applied automatically."""
    if not llm.configured():
        return []
    text = "\n".join(f"[page {p}]\n{llm.mask_ids(t)[:3000]}" for p, t in pages[:6])[:9000]
    known = ", ".join(r["label"] for r in rules) or "none"
    try:
        resp = llm._post({"model": llm.LLM_MODEL, "max_tokens": 1500, "messages": [
            {"role": "system", "content": SUGGEST_PROMPT},
            {"role": "user", "content": f"Rules already read: {known}\n\nTender document:\n{text}"}]})
        content = llm._clean(resp["choices"][0]["message"].get("content") or "")
        m = re.search(r"\[.*\]", content, re.S)
        items = json.loads(m.group(0)) if m else []
    except Exception as e:  # advisory only; the rules above stand on their own
        print(f"[rulebook] suggestion pass skipped: {type(e).__name__}", flush=True)
        return []
    out = []
    for it in items[:6]:
        if isinstance(it, dict) and str(it.get("condition") or "").strip():
            page = it.get("page")
            out.append({"condition": str(it["condition"]).strip()[:240], "page": page if isinstance(page, int) else None,
                        "method": f"suggested by {llm.LLM_MODEL}"})
    return out


COMPARE = {"min_turnover": "min_turnover", "estimated_value": "benchmark_price", "oem_authorisation_required": "oem_authorisation_required",
           "labour_services": "labour_services"}


def compare(rules: list, tender: dict) -> list:
    """Each rule next to what the tender record says."""
    out = []
    for r in rules:
        if r.get("info"):
            continue
        rec = None
        if r["key"] in COMPARE:
            rec = tender.get(COMPARE[r["key"]])
        elif r["key"] == "required_documents":
            rec = tender.get("required_documents") or []
        elif r["key"] == "emd_amount":
            rec = tender.get("emd_amount")
        if r["key"] == "required_documents":
            new = [d for d in r["value"] if d not in rec]
            status = "adds" if new else "same"
            note = ("Not on record: " + ", ".join(new)) if new else "All on record."
        elif rec is None:
            status, note = "new", "Not on the tender record."
        elif rec == r["value"]:
            status, note = "same", "Matches the tender record."
        else:
            status = "differs"
            note = f"Tender record says {fmt_rupees(rec) if isinstance(rec, int) and not isinstance(rec, bool) else rec}."
        out.append({"key": r["key"], "status": status, "note": note})
    return out


EDITABLE = {"min_turnover", "emd_amount", "estimated_value", "experience_years"}


def effective(tender: dict, rules: list) -> dict:
    """The tender as the checks should see it once a rulebook is applied."""
    t = dict(tender)
    by = {r["key"]: r for r in rules}
    if "min_turnover" in by:
        t["min_turnover"] = int(by["min_turnover"]["value"])
    if "estimated_value" in by:
        t["benchmark_price"] = int(by["estimated_value"]["value"])
    if "emd_amount" in by:
        t["emd_amount"] = int(by["emd_amount"]["value"])
    if by.get("oem_authorisation_required"):
        t["oem_authorisation_required"] = True
    if by.get("labour_services"):
        t["labour_services"] = True
    if "required_documents" in by:
        t["required_documents"] = list(dict.fromkeys(list(tender["required_documents"]) + list(by["required_documents"]["value"])))
    extras = []
    if "experience_years" in by:
        extras.append(f"The tender document asks for {by['experience_years']['display']} of experience (page {by['experience_years']['page']}).")
    if extras:
        t["spec"] = tender["spec"] + " " + " ".join(extras)
    t["rules_source"] = {r["key"]: {"page": r["page"], "display": r["display"]} for r in rules if not r.get("info")}
    return t
