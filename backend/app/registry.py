"""
GSTIN and Udyam verification.

Format and checksum validation are real (the published GSTIN check-digit
algorithm). The legal-name lookup runs against a simulated registry until a
GST data provider key is set, and every result says which mode it ran in, so a
simulated match is never presented as a live one.
"""
import os
import re
import difflib

from .data import SIMULATED_GST_REGISTRY

GSTIN_RE = re.compile(r"^[0-3][0-9][A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-\d{2}-\d{7}$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

GST_API_KEY = os.environ.get("GST_API_KEY", "").strip()
MODE = "live" if GST_API_KEY else "simulated"


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


def _lookup_legal_name(gstin: str):
    if MODE == "live":
        # One HTTP call to a GST data provider goes here. Left unimplemented on
        # purpose: a misconfigured live mode should fail loudly, never fake a match.
        raise NotImplementedError("Live GST lookup is not wired yet. Unset GST_API_KEY to run simulated.")
    return SIMULATED_GST_REGISTRY.get(gstin)


def verify(bidder_name: str, bidder: dict) -> dict:
    ok, msg = validate_gstin(bidder.get("gstin", ""))
    tag = f" ({MODE} registry)"
    if not ok:
        return {"status": "FLAG", "reason": msg + tag, "mode": MODE}
    legal = _lookup_legal_name(bidder["gstin"].upper())
    if legal is None:
        return {"status": "FLAG", "reason": f"GSTIN {bidder['gstin']} is valid but not found in the registry." + tag, "mode": MODE}
    ratio = difflib.SequenceMatcher(None, legal.lower(), bidder_name.lower()).ratio()
    if ratio >= 0.85:
        extra = ""
        if bidder.get("cert") in ("msme", "udyam") and bidder.get("udyam") and not validate_udyam(bidder["udyam"]):
            return {"status": "FLAG", "reason": f"GSTIN matches, but Udyam number {bidder['udyam']} is malformed." + tag, "mode": MODE}
        if bidder.get("udyam"):
            extra = f" Udyam {bidder['udyam']} format valid."
        return {"status": "PASS", "reason": f"GSTIN legal name \"{legal}\" matches the bidder.{extra}" + tag, "mode": MODE}
    return {"status": "FLAG",
            "reason": f"GSTIN legal name is \"{legal}\", which does not match the bidder \"{bidder_name}\" ({round(ratio*100)}% match)." + tag,
            "mode": MODE}
