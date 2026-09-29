"""
Registry adapters: one per government source named in SIH26100.

What is real here
  GSTIN structure and check digit (the published algorithm), PAN structure,
  the PAN embedded in a GSTIN, the PAN holder-type code (4th character) and
  the name-initial code (5th character), Udyam and CIN formats.

What is simulated
  The lookups themselves (GSTN, Income Tax, MCA21, Udyam, DPIIT, NSIC, EPFO,
  ESIC, DigiLocker, the debarment list) read the sample registries in data.py.
  Every adapter reports its mode, and every result the officer sees says
  "simulated", so a sample record is never presented as a live one. Wiring a
  live source means replacing one lookup function; the checks do not change.
"""
import difflib
import os
import re
from datetime import date

from . import data as D

GSTIN_RE = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
CIN_RE = re.compile(r"^[LU]\d{5}[A-Z]{2}\d{4}(PTC|PLC|FTC|GOI|NPL|SGC|OPC|GAP|GAT)\d{6}$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

GST_API_KEY = os.environ.get("GST_API_KEY", "").strip()
MODE = "live" if GST_API_KEY else "simulated"
TAG = f" ({MODE})"

# The fourth character of a PAN names the holder type.
PAN_TYPES = {"C": "company", "P": "individual", "H": "HUF", "F": "firm or LLP", "A": "association of persons",
             "T": "trust", "B": "body of individuals", "L": "local authority", "J": "artificial juridical person",
             "G": "government body"}

ADAPTERS = [
    {"id": "gstn", "source": "GSTN", "verifies": "GST registration status, legal name, GSTR-3B return filing", "live": "GSTN through a GST Suvidha Provider"},
    {"id": "itd", "source": "Income Tax Department", "verifies": "PAN holder and income tax return filing", "live": "Income Tax Department PAN and ITR verification"},
    {"id": "mca21", "source": "MCA21", "verifies": "Company name, status and date of incorporation", "live": "MCA21 company master data"},
    {"id": "udyam", "source": "Udyam", "verifies": "MSE registration and category", "live": "Udyam Registration portal"},
    {"id": "dpiit", "source": "Startup India (DPIIT)", "verifies": "Startup recognition and validity", "live": "Startup India recognition records"},
    {"id": "nsic", "source": "NSIC", "verifies": "NSIC single-point registration", "live": "NSIC registration records"},
    {"id": "epfo", "source": "EPFO", "verifies": "Establishment code and monthly challans", "live": "EPFO establishment search"},
    {"id": "esic", "source": "ESIC", "verifies": "Employer code and monthly contributions", "live": "ESIC employer records"},
    {"id": "digilocker", "source": "DigiLocker", "verifies": "Issuer-verified copies of bid documents", "live": "DigiLocker requester API"},
    {"id": "debarment", "source": "GeM / CPPP debarment list", "verifies": "Debarred and banned bidders", "live": "Published GeM and CPPP debarment lists"},
]


def adapters():
    return [dict(a, mode=MODE) for a in ADAPTERS]


# ---------------------------------------------------------------- helpers
def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, (a or "").lower().strip(), (b or "").lower().strip()).ratio()


def gstin_check_digit(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def validate_gstin(gstin: str) -> tuple[bool, str]:
    g = (gstin or "").strip().upper()
    if not g:
        return False, "No GSTIN supplied."
    if not GSTIN_RE.match(g):
        return False, f"GSTIN {g} does not follow the 15-character GSTIN format."
    if gstin_check_digit(g[:14]) != g[14]:
        return False, f"GSTIN {g} fails the check-digit test, so it cannot be a valid registration."
    return True, "GSTIN format and check digit are valid."


def validate_udyam(udyam: str) -> bool:
    return bool(UDYAM_RE.match((udyam or "").strip().upper()))


def pan_from_gstin(gstin: str) -> str:
    g = (gstin or "").strip().upper()
    return g[2:12] if len(g) == 15 else ""


def expected_pan_type(name: str):
    n = (name or "").lower()
    if re.search(r"\b(pvt\.?|private)\s+(ltd\.?|limited)\b|\b(ltd\.?|limited)$", n):
        return "C"
    if re.search(r"&\s*co\.?$|\bllp$|\bpartners$", n):
        return "F"
    return None


def name_initial(name: str) -> str:
    words = [w for w in re.split(r"\s+", (name or "").strip()) if w]
    if words and words[0].lower() == "the" and len(words) > 1:
        words = words[1:]
    return words[0][0].upper() if words else ""


def months_behind(last_yyyy_mm: str, submitted_at: str) -> int:
    y, m = (int(x) for x in last_yyyy_mm.split("-"))
    sy, sm = int(submitted_at[:4]), int(submitted_at[5:7])
    return (sy - y) * 12 + (sm - m)


def years_between(start_iso: str, end_iso: str) -> float:
    a = date.fromisoformat(start_iso[:10]); b = date.fromisoformat(end_iso[:10])
    return (b - a).days / 365.25


def days_between(start_iso: str, end_iso: str) -> int:
    return (date.fromisoformat(end_iso[:10]) - date.fromisoformat(start_iso[:10])).days


# ---------------------------------------------------------------- lookups (one per adapter)
def _live_guard(source):
    if MODE == "live":
        # A live call goes here. Unimplemented on purpose: a misconfigured live
        # mode must fail loudly, never fake a match.
        raise NotImplementedError(f"Live {source} lookup is not wired yet. Unset GST_API_KEY to run simulated.")


def gstn(gstin):
    _live_guard("GSTN"); return D.SIMULATED_GST_REGISTRY.get(gstin)


def itd(pan):
    _live_guard("Income Tax"); return D.SIMULATED_ITD_REGISTRY.get(pan)


def mca21(cin):
    _live_guard("MCA21"); return D.SIMULATED_MCA21.get(cin) if cin else None


def udyam(num):
    _live_guard("Udyam"); return D.SIMULATED_UDYAM.get((num or "").upper())


def dpiit(num):
    _live_guard("DPIIT"); return D.SIMULATED_DPIIT.get((num or "").upper())


def nsic(num):
    _live_guard("NSIC"); return D.SIMULATED_NSIC.get((num or "").upper())


def epfo(code):
    _live_guard("EPFO"); return D.SIMULATED_EPFO.get(code) if code else None


def esic(code):
    _live_guard("ESIC"); return D.SIMULATED_ESIC.get(code) if code else None


def debarment(name):
    _live_guard("debarment list"); return D.DEBARRED.get(name)


def incorporation(bidder):
    """Incorporation date from MCA21 for companies; firms fall back to the declared age."""
    rec = mca21(bidder.get("cin"))
    return rec["incorporated"] if rec else None


# ---------------------------------------------------------------- MSE / Startup / NSIC claims
def verify_claims(bidder_name, bidder):
    """Each claimed benefit, verified at source. Returns a list of {claim, ok, detail}."""
    out = []
    for claim in bidder.get("claims") or []:
        if claim == "mse":
            num = bidder.get("udyam", "")
            rec = udyam(num) if validate_udyam(num) else None
            if not validate_udyam(num):
                out.append({"claim": "MSE", "ok": False, "detail": f"Udyam number {num or '(none)'} is not in the Udyam format"})
            elif not rec:
                out.append({"claim": "MSE", "ok": False, "detail": f"Udyam {num} not found"})
            elif similar(rec["name"], bidder_name) < 0.85:
                out.append({"claim": "MSE", "ok": False, "detail": f"Udyam {num} is registered to {rec['name']}"})
            else:
                out.append({"claim": "MSE", "ok": True, "detail": f"Udyam {num} verified, {rec['category']} enterprise"})
        elif claim == "startup":
            num = bidder.get("dpiit", "")
            rec = dpiit(num)
            if not rec:
                out.append({"claim": "Startup", "ok": False, "detail": f"DPIIT recognition {num or '(none)'} not found"})
            elif similar(rec["name"], bidder_name) < 0.85:
                out.append({"claim": "Startup", "ok": False, "detail": f"DPIIT {num} is recognised for {rec['name']}"})
            elif rec["valid_until"] < bidder["submitted_at"][:10]:
                out.append({"claim": "Startup", "ok": False, "detail": f"DPIIT {num} recognition expired on {rec['valid_until']}"})
            else:
                out.append({"claim": "Startup", "ok": True, "detail": f"DPIIT {num} recognised startup, valid to {rec['valid_until']}"})
        elif claim == "nsic":
            num = bidder.get("nsic", "")
            rec = nsic(num)
            ok = bool(rec) and similar(rec["name"], bidder_name) >= 0.85
            out.append({"claim": "NSIC", "ok": ok, "detail": f"NSIC {num} {'verified' if ok else 'not verified'}"})
    return out
