"""
Sarvam AI, India's own model stack, for everything language and vision.

  translate()   sarvam-translate:v1, all 22 scheduled languages of India
  parse_pdf()   Sarvam Vision through the Document AI parse job: OCR for
                scanned bid and tender documents, page by page
  (reasoning)   sarvam-105b through llm.py, already in production

Key: SARVAM_API_KEY, or LLM_API_KEY when the reasoning layer already points
at api.sarvam.ai, so one key covers all three.

Identifiers never leave the server in the clear for translation: GSTIN, PAN,
CIN, Udyam, DPIIT, EPFO and ESIC numbers and GeM bid numbers are swapped for
placeholders before the call and put back after it. If a placeholder does not
come back intact, the original English line is returned instead, because a
wrong identifier is worse than an untranslated sentence.
"""
import gzip
import hashlib
import io
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

BASE_URL = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai").rstrip("/")
TRANSLATE_MODEL = "sarvam-translate:v1"
CHUNK = 1900          # the model takes 2,000 characters per request
OCR_MAX_PAGES = 10    # Document AI limit per PDF
OCR_TIMEOUT = float(os.environ.get("SARVAM_OCR_TIMEOUT", "90"))
RESULT_FORMATS = ("json", "html", "md")
UA = "procurement-pilot/3.0"

# The 22 languages of the Eighth Schedule, plus English. Codes are Sarvam's (Odia is od-IN).
LANGUAGES = [
    ("en-IN", "English", "English", "Latin"),
    ("as-IN", "Assamese", "অসমীয়া", "Bengali"),
    ("bn-IN", "Bengali", "বাংলা", "Bengali"),
    ("brx-IN", "Bodo", "बड़ो", "Devanagari"),
    ("doi-IN", "Dogri", "डोगरी", "Devanagari"),
    ("gu-IN", "Gujarati", "ગુજરાતી", "Gujarati"),
    ("hi-IN", "Hindi", "हिन्दी", "Devanagari"),
    ("kn-IN", "Kannada", "ಕನ್ನಡ", "Kannada"),
    ("ks-IN", "Kashmiri", "کٲشُر", "Arabic"),
    ("kok-IN", "Konkani", "कोंकणी", "Devanagari"),
    ("mai-IN", "Maithili", "मैथिली", "Devanagari"),
    ("ml-IN", "Malayalam", "മലയാളം", "Malayalam"),
    ("mni-IN", "Manipuri", "মৈতৈলোন্", "Bengali"),
    ("mr-IN", "Marathi", "मराठी", "Devanagari"),
    ("ne-IN", "Nepali", "नेपाली", "Devanagari"),
    ("od-IN", "Odia", "ଓଡ଼ିଆ", "Oriya"),
    ("pa-IN", "Punjabi", "ਪੰਜਾਬੀ", "Gurmukhi"),
    ("sa-IN", "Sanskrit", "संस्कृतम्", "Devanagari"),
    ("sat-IN", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ", "Ol Chiki"),
    ("sd-IN", "Sindhi", "سنڌي", "Arabic"),
    ("ta-IN", "Tamil", "தமிழ்", "Tamil"),
    ("te-IN", "Telugu", "తెలుగు", "Telugu"),
    ("ur-IN", "Urdu", "اردو", "Arabic"),
]
CODES = {c for c, *_ in LANGUAGES}
RTL = {"ks-IN", "sd-IN", "ur-IN"}

_ID = re.compile(
    r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]"      # GSTIN
    r"|[A-Z]{3}[ABCFGHJLPT][A-Z]\d{4}[A-Z]"              # PAN
    r"|[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}"               # CIN
    r"|UDYAM-[A-Z]{2}-\d{2}-\d{7}"                        # Udyam
    r"|DIPP\d{3,7}"                                       # DPIIT
    r"|[A-Z]{5}\d{10}"                                    # EPFO establishment code
    r"|\d{17}"                                            # ESIC employer code
    r"|GEM/\d{4}/B/\d+"                                   # GeM bid number
    r"|[A-Z]{4}0[A-Z0-9]{6})\b")                          # IFSC


def api_key() -> str:
    explicit = (os.environ.get("SARVAM_API_KEY") or "").strip()
    if explicit:
        return explicit
    if "sarvam.ai" in (os.environ.get("LLM_BASE_URL") or ""):
        return (os.environ.get("LLM_API_KEY") or "").strip()
    return ""


def configured() -> bool:
    return bool(api_key())


def languages() -> list:
    return [{"code": c, "name": n, "native": nat, "script": s, "rtl": c in RTL} for c, n, nat, s in LANGUAGES]


class SarvamError(Exception):
    pass


def _request(method: str, path: str, *, body: bytes | None = None, content_type: str | None = None, timeout: float = 30,
             retries: int = 2, raw: bool = False):
    headers = {"api-subscription-key": api_key(), "User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            if raw:
                return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
            return json.loads(_body(data) or "{}")
    except urllib.error.HTTPError as e:
        if e.code in (429, 502, 503) and retries > 0:  # rate limited or briefly unavailable: wait and try again
            time.sleep(1.5 * (3 - retries))
            return _request(method, path, body=body, content_type=content_type, timeout=timeout, retries=retries - 1, raw=raw)
        detail = ""
        try:
            j = json.loads(_body(e.read()) or "{}")
            err = j.get("error") if isinstance(j.get("error"), dict) else j
            detail = str(err.get("message") or err.get("detail") or "")[:200]
        except (ValueError, OSError, AttributeError):
            pass
        raise SarvamError(f"Sarvam returned HTTP {e.code}" + (f": {detail}" if detail else "")) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SarvamError(f"Sarvam did not answer ({type(e).__name__})") from None


def _body(raw: bytes) -> str:
    """Response bytes to text. Large replies (parse results) arrive gzip-compressed; urllib does not undo that."""
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SarvamError(f"Sarvam sent a reply that is not text (it starts {raw[:6].hex()})") from None


# ------------------------------------------------------------------ translation
def protect(text: str) -> tuple[str, list]:
    found = []

    def sub(m):
        found.append(m.group(0))
        return f"[{len(found)}]"
    return _ID.sub(sub, text), found


def restore(text: str, found: list) -> str | None:
    for i, v in enumerate(found, 1):
        token = f"[{i}]"
        if token not in text:
            return None
        text = text.replace(token, v, 1)
    return text


def _chunks(text: str) -> list:
    if len(text) <= CHUNK:
        return [text]
    parts, cur = [], ""
    for piece in re.split(r"(?<=[.!?\n])\s+", text):
        while len(piece) > CHUNK:
            parts.append(piece[:CHUNK]); piece = piece[CHUNK:]
        if len(cur) + len(piece) + 1 > CHUNK:
            parts.append(cur); cur = piece
        else:
            cur = (cur + " " + piece).strip()
    if cur:
        parts.append(cur)
    return parts


def _translate_raw(text: str, target: str) -> str:
    out = []
    for part in _chunks(text):
        j = _request("POST", "/translate", body=json.dumps({
            "input": part, "source_language_code": "en-IN", "target_language_code": target,
            "model": TRANSLATE_MODEL, "numerals_format": "international"}).encode(), content_type="application/json")
        out.append(j.get("translated_text") or "")
    return " ".join(out).strip()


def translate(text: str, target: str) -> str:
    """One string, English to `target`. Identifiers are protected (see module docstring)."""
    if target not in CODES:
        raise ValueError(f"Unsupported language {target}")
    if target == "en-IN" or not re.search(r"[A-Za-z]{2}", text or ""):
        return text
    safe, found = protect(text)
    done = restore(_translate_raw(safe, target), found)
    return text if done is None or not done.strip() else done


NUM_LINE = re.compile(r"\s*(\d{1,3})\s*[.)\u0964]\s*(.*)$")


def _numbered(group: list, target: str) -> list | None:
    """Several short lines in one call, sent as a numbered list. Numbered lists survive translation far better
    than bare line breaks. Returns None if the numbering does not come back intact."""
    safe, founds = zip(*(protect(t) for t in group))
    out = _translate_raw("\n".join(f"{i}. {line}" for i, line in enumerate(safe, 1)), target)
    got = {}
    for line in out.split("\n"):
        m = NUM_LINE.match(line)
        if m:
            got[int(m.group(1))] = m.group(2).strip()
    if sorted(got) != list(range(1, len(group) + 1)):
        return None
    back = [restore(got[i], f) for i, f in enumerate(founds, 1)]
    return [b if b and b.strip() else t for b, t in zip(back, group)]


def translate_many(texts: list, target: str, cache_get=None, cache_put=None, workers: int = 6, budget: float = 45.0) -> dict:
    """Translate a list, using an optional cache. Short lines go together as a numbered list; a list whose
    numbering does not survive is halved and retried, down to single lines. Anything still waiting when
    the time budget runs out comes back in English and is counted as failed, so the caller can retry it."""
    deadline = time.monotonic() + budget
    results, todo = {}, []
    unique = list(dict.fromkeys(texts))
    for t in unique:
        hit = cache_get(t) if cache_get else None
        if hit is not None:
            results[t] = hit
        else:
            todo.append(t)
    groups, cur, size = [], [], 0
    for t in todo:
        if "\n" in t or len(t) > 300:
            groups.append([t]); continue
        if (size + len(t) + 6 > 1400 or len(cur) >= 20) and cur:
            groups.append(cur); cur, size = [], 0
        cur.append(t); size += len(t) + 6
    if cur:
        groups.append(cur)
    failed = []

    def solve(group):
        if time.monotonic() > deadline:
            raise SarvamError("out of time")
        if len(group) == 1:
            return [translate(group[0], target)]
        done = _numbered(group, target)
        if done is not None:
            return done
        if len(group) <= 3:
            return [translate(t, target) for t in group]
        half = len(group) // 2
        return solve(group[:half]) + solve(group[half:])

    def run(group):
        try:
            return group, solve(group)
        except SarvamError:
            failed.extend(group)
            return group, list(group)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for group, out in ex.map(run, groups):
            for src, tr in zip(group, out):
                results[src] = tr
                if cache_put and src not in failed:
                    cache_put(src, tr)
    return {"results": results, "translated": len(todo) - len(failed), "cached": len(unique) - len(todo), "failed": len(failed)}


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ------------------------------------------------------------------ OCR (Sarvam Vision, Document AI)
def _multipart(fields: dict, file_field: str, filename: str, blob: bytes, mime: str) -> tuple[bytes, str]:
    boundary = "pp-" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + blob + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _strip_markup(content: str) -> str:
    """Parse output (HTML or Markdown) to plain lines. Block ends become line breaks, so a label and its
    value stay on the lines the page printed them on."""
    text = re.sub(r"(?i)<br\s*/?>|</(?:p|div|h[1-6]|li|tr|table|section|header|footer|caption)>", "\n", content or "")
    text = re.sub(r"(?i)</t[dh]>", " \t ", text)             # table cells stay on their row
    text = re.sub(r"<[^>]+>", " ", text)                      # any other tag
    text = re.sub(r"[*_#`>|]+", " ", html.unescape(text))     # Markdown emphasis, headings, tables
    return "\n".join(x for x in (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()) if x)


def parse_pdf(blob: bytes, language: str = "en-IN", sleep=time.sleep) -> list:
    """OCR a PDF with Sarvam Vision. Returns [(page_number, text), ...]. Raises SarvamError."""
    if not configured():
        raise SarvamError("No Sarvam API key is configured")
    body, ctype = _multipart({"language": language}, "file", "document.pdf", blob, "application/pdf")
    job = _request("POST", "/doc-ai/v1/job/parse", body=body, content_type=ctype, timeout=60)
    job_id = job.get("job_id")
    if not job_id:
        raise SarvamError("Sarvam did not return a job id")
    deadline, wait, status = time.monotonic() + OCR_TIMEOUT, 1.0, job.get("status")
    while status not in ("completed", "partially_completed", "failed", "rejected"):
        if time.monotonic() > deadline:
            raise SarvamError("OCR took longer than expected; try again in a minute")
        sleep(wait)
        wait = min(wait * 1.5, 5)
        status = _request("GET", f"/doc-ai/v1/job/{job_id}/status").get("status")
    if status in ("failed", "rejected"):
        raise SarvamError(f"Sarvam could not read this document (job {status})")
    res = None
    for fmt in RESULT_FORMATS:  # the results endpoint refuses a format the job did not produce
        try:
            data = _request("GET", f"/doc-ai/v1/job/{job_id}/results?format={fmt}", timeout=60, raw=True)
        except SarvamError as e:
            if "cannot serve" not in str(e) or fmt == RESULT_FORMATS[-1]:
                raise
            continue
        res = _from_zip(data) if data[:4] == b"PK\x03\x04" else json.loads(_body(data) or "{}")
        break
    pages = _pages_of(res or {})
    if not any(t for _, t in pages):
        print(f"[sarvam] parse results had no text; shape: {_shape(res)}", flush=True)
        raise SarvamError("Sarvam returned no text for this document")
    return sorted(pages)


def _from_zip(data: bytes) -> dict:
    """Some result formats come back as a ZIP archive: a JSON result, or one HTML / Markdown file per page or per document."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        print(f"[sarvam] results archive: {names[:20]}", flush=True)
        for n in names:
            if n.lower().endswith(".json"):
                try:
                    j = json.loads(_body(z.read(n)))
                except (ValueError, SarvamError):
                    continue
                if isinstance(j, dict) and (j.get("documents") or j.get("pages")):
                    return j
        texts = sorted(n for n in names if n.lower().endswith((".html", ".htm", ".md", ".txt")))
        pages = []
        for i, n in enumerate(texts, 1):
            content = _body(z.read(n))
            split = re.split(r"(?i)<[^>]+data-page(?:-number)?=[\"']?(\d+)[^>]*>", content)
            if len(texts) == 1 and len(split) > 2:  # one file, pages marked inside it
                pages += [{"page_number": int(split[k]), "content": split[k + 1]} for k in range(1, len(split) - 1, 2)]
                continue
            num = re.findall(r"(\d+)", n.rsplit("/", 1)[-1])
            pages.append({"page_number": int(num[-1]) if num and len(texts) > 1 else i, "content": content})
        return {"documents": [{"pages": pages}]}


def _text_of(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in ("content", "html", "markdown", "md", "text"):
            if isinstance(x.get(k), str):
                return x[k]
        if isinstance(x.get("blocks"), list):  # JSON results: blocks of text
            return "\n".join(_text_of(b) for b in x["blocks"])
    if isinstance(x, list):
        return "\n".join(_text_of(b) for b in x)
    return ""


def _pages_of(res: dict) -> list:
    """Pages from a parse result: documents[].pages[] with page_number and content, read defensively."""
    docs = res.get("documents")
    if not isinstance(docs, list):
        docs = [res]
    pages = []
    for doc in docs:
        plist = doc.get("pages") if isinstance(doc, dict) else None
        if not isinstance(plist, list):
            plist = [doc]
        for i, p in enumerate(plist, 1):
            num = p.get("page_number") if isinstance(p, dict) else None
            pages.append((int(num or i), _strip_markup(_text_of(p))))
    return pages


def _shape(x, depth=0):
    if depth > 3:
        return "..."
    if isinstance(x, dict):
        return {k: _shape(v, depth + 1) for k, v in list(x.items())[:12]}
    if isinstance(x, list):
        return [_shape(x[0], depth + 1), f"len {len(x)}"] if x else []
    return type(x).__name__
