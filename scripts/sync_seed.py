"""
Copy the backend's seed data and rules into frontend/index.html.

The frontend carries an offline demo engine (used only when the API does not
answer). This script keeps its data identical to the backend's, so the two
cannot drift. Run it after editing anything in backend/app/data.py,
checks.py, collusion.py, auth.py or main.py:

    python scripts/sync_seed.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "seed.db"))
os.environ.pop("DEMO_USERS", None)

from app import data as D  # noqa: E402
from app.data import TENDERS  # noqa: E402
from app.checks import CHECKS, FAMILIES, HARD_CAP_CHECKS, ADVERSE_DECISIONS  # noqa: E402
from app import collusion, registry  # noqa: E402
from app.auth import _DEFAULT_USERS  # noqa: E402
from app.main import DECISIONS, OVERRIDE_MIN_CHARS  # noqa: E402

seed = {
    "tenders": [
        {"id": tid, **{k: t[k] for k in ("title", "category", "authority", "authority_full", "spec", "min_turnover", "benchmark_price",
                                          "required_documents", "oem_authorisation_required", "labour_services")},
         "bidders": [{"name": n, **b} for n, b in t["bidders"].items()]}
        for tid, t in TENDERS.items()
    ],
    "mode": registry.MODE,
    "adapters": registry.ADAPTERS,
    "registries": {"gst": D.SIMULATED_GST_REGISTRY, "itd": D.SIMULATED_ITD_REGISTRY, "mca21": D.SIMULATED_MCA21,
                   "udyam": D.SIMULATED_UDYAM, "dpiit": D.SIMULATED_DPIIT, "nsic": D.SIMULATED_NSIC,
                   "epfo": D.SIMULATED_EPFO, "esic": D.SIMULATED_ESIC, "debarred": D.DEBARRED},
    "itr_years_required": D.ITR_YEARS_REQUIRED,
    "checks": [{"name": n, "weight": w, "family": f} for n, w, f in CHECKS],
    "families": FAMILIES,
    "hard_cap_checks": sorted(HARD_CAP_CHECKS),
    "adverse_decisions": sorted(ADVERSE_DECISIONS),
    "decisions": list(DECISIONS),
    "override_min_chars": OVERRIDE_MIN_CHARS,
    "collusion": {"price_gap_pct": collusion.PRICE_GAP_PCT, "timing_minutes": collusion.TIMING_MINUTES, "cover_bid_pct": collusion.COVER_BID_PCT},
    "demo_users": {u: {"password": p, "role": r} for u, p, r in (e.split(":") for e in _DEFAULT_USERS.split(","))},
}

payload = json.dumps(seed, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
index = ROOT / "frontend" / "index.html"
html = index.read_text(encoding="utf-8")
pattern = re.compile(r'(<script type="application/json" id="pp-seed">)(.*?)(</script>)', re.S)
if not pattern.search(html):
    sys.exit("pp-seed script tag not found in frontend/index.html")
html = pattern.sub(lambda m: m.group(1) + payload + m.group(3), html, count=1)
index.write_text(html, encoding="utf-8")
print(f"seed synced: {len(seed['tenders'])} tenders, {sum(len(t['bidders']) for t in seed['tenders'])} bids")
