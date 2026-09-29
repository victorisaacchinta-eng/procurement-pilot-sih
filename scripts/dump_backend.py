"""Print the backend's results for every seeded bid and tender (used by parity_test.js)."""
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "dump.db")
from app.data import TENDERS
from app import checks as C, collusion
from app.db import init_db
init_db()
out = {}
for tid, t in TENDERS.items():
    for n, b in t["bidders"].items():
        r = C.run_all_checks(tid, t, n, b)
        s, v, _ = C.score_and_verdict(r)
        out[f"{tid}|{n}"] = {"score": s, "verdict": v, "risk": _["risk_level"], "st": [c["status"] for c in r], "names": [c["name"] for c in r], "reasons": [c["reason"] for c in r]}
    out[f"col|{tid}"] = [[f["signal"], f["severity"]] for f in collusion.screen(tid, t)["findings"]]
print(json.dumps(out))
