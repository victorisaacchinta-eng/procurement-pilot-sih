# Procurement Pilot

Bid compliance checking for government procurement officers. Built by **Team Ace Azael** (ACE Engineering College, Hyderabad) for **Smart India Hackathon 2026, problem statement SIH26100** (Ministry of Petroleum and Natural Gas).

Every bid runs through ten fixed checks written in plain code. A reasoning layer reads those results through one tool call and explains every flag in plain language. A named officer records the decision, and overruling a flagged bid needs a senior approver and a written reason. Everything lands in an audit log.

> Student prototype. Not an official government system and not affiliated with or endorsed by any ministry or PSU. All tenders, bids, GSTINs and Udyam numbers in this repo are sample data.

## What it does

| | |
|---|---|
| **Ten deterministic checks** | EMD, statutory documents, financial turnover, price reasonability, entity name consistency, registry verification, debarment, public interest screening, shell company indicators, past performance. Each returns PASS, FLAG or FAIL with a sentence naming the real numbers. |
| **Weighted score** | Weights sum to 100. PASS earns the full weight, FLAG half, FAIL nothing. A FAIL on EMD, documents or debarment caps the score at 45; any other FAIL caps it at 72. The UI shows exactly where points were lost. |
| **Registry verification** | Real GSTIN structure and check-digit validation. Legal-name match runs against a simulated registry and every result says `simulated`. |
| **Collusion screen** | Compares every pair of bids on a tender: price clustering under 0.5%, submissions within 5 minutes, shared registered address, cover bids over 25% above the benchmark. |
| **Reasoning layer** | One real tool-calling step over any OpenAI-compatible API. The model cannot set the score or verdict. No key, a timeout or an error falls back to a deterministic summary and says so. |
| **Roles** | `officer`, `senior_approver`, `admin` with JWT sign-in. The override rule is enforced by the server: an officer gets 403, an approver needs 30+ characters of reason (422 otherwise). |
| **DPDP-style retention** | Evaluations older than `RETENTION_DAYS` (180) are irreversibly anonymised while scores stay. Viewing the log needs sign-in; exporting it is admin only and every export is logged. |

## Run it locally

You need Python 3.11 or newer.

```bash
git clone https://github.com/victorisaacchinta-eng/procurement-pilot-sih.git
cd procurement-pilot-sih/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Expected output ends with `Uvicorn running on http://127.0.0.1:8000`. Open that address. The landing page loads; press **Open workstation** and tap a demo account.

| Account | Password | Role |
|---|---|---|
| officer1 | officer123 | Officer |
| approver1 | approver123 | Senior approver |
| admin1 | admin123 | Admin |

These are demo credentials. Override them with `DEMO_USERS` and set `JWT_SECRET` before any real use.

To turn on the reasoning layer, copy `.env.example` to `backend/.env` and set `LLM_API_KEY`. Without it every check still runs and the recommendation is a deterministic summary.

## Demo path

1. **Pipeline valves → Petrotech.** All ten pass, 100/100, Compliant.
2. **Pipeline valves → Vantage.** Documents and the GSTIN legal name both say "Vantage Flow Solutions Ltd". Two independent checks flag it. 90, Needs review.
3. **Refinery PPE → Trident.** No EMD, BIS licence copy missing, turnover short, GSTIN fails the check digit. Capped at 45, Non-compliant.
4. **Tanker transport → Screen for collusion.** Swift and Ratnagiri quoted 0.38% apart and submitted 2 minutes apart. Two FLAGs.
5. **Depot security → Meridian → Qualified** as `officer1`: refused, told to use Hold for Review. Sign in as `approver1`: the written override box opens.
6. **Depot security → Falcon → Mark Non-Compliant**, then evaluate **Pipeline survey → Falcon**: past performance now flags the earlier decision.
7. **Audit log** as `admin1` → **Export log**. The export shows up in the access log inside the export.

## Deploy (Render, one service)

The repo includes `render.yaml`. In Render: **New → Blueprint**, pick this repo, then set `LLM_API_KEY` if you want the reasoning layer. `JWT_SECRET` is generated for you. The same service serves the API at `/api` and the frontend at `/`.

Free Render instances sleep when idle and their disk resets on redeploy, so the audit log starts fresh after a deploy. The frontend handles a sleeping backend: it pings `/api/health` on load, and if the API still does not answer it runs a built-in demo engine on the same sample data and labels it "Demo engine".

**Split deploy (optional):** host `frontend/` on any static host and set `window.PP_API` at the top of `frontend/index.html` to the API origin, plus `CORS_ORIGINS` on the backend.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q                      # 15 API tests
cd .. && python scripts/dump_backend.py > /tmp/b.json && node scripts/parity_test.js /tmp/b.json
```

The second command runs the frontend's offline engine against the backend's own results for every sample bid. CI runs both on every push.

If you change anything in `backend/app/data.py`, `checks.py` or `collusion.py`, run `python scripts/sync_seed.py` so the frontend's copy of the data stays identical.

## Layout

```
backend/
  app/main.py        routes, override rule, static mount
  app/checks.py      the ten checks, weights, caps, verdict
  app/registry.py    GSTIN / Udyam validation, simulated registry
  app/collusion.py   pairwise collusion screen
  app/llm.py         tool-calling reasoning layer, provider-agnostic
  app/auth.py        JWT sign-in, roles
  app/db.py          SQLite, access log, retention job
  app/data.py        sample tenders and bids
  tests/test_api.py
frontend/
  index.html         landing page and officer workstation, one file
  team-logo.png
scripts/             seed sync, parity test
docs/REPO_SCOPE.md   what this repo is and is not
render.yaml
```

## API

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/login` | anyone |
| GET | `/api/auth/me` | signed in |
| GET | `/api/tenders` | signed in |
| GET | `/api/evaluate-seed?tender_id=&bidder_name=` | signed in |
| POST | `/api/officer-decision` | signed in (qualifying a flagged bid: senior approver or admin) |
| GET | `/api/collusion-check?tender_id=` | signed in |
| GET | `/api/audit-log` | signed in |
| GET | `/api/audit-log/export` | admin |
| POST | `/api/admin/retention` | admin |
| GET | `/api/health` | anyone |

## Known limits

- Tenders and bids are seeded; there is no document upload or PDF parsing in this build.
- GSTIN legal-name lookup is simulated. Structure and check-digit validation are real.
- The debarment list is a seeded placeholder, not a live GeM or CPPP lookup.
- SQLite is fine for the prototype; a real deployment needs a managed database and backups.
- The reasoning layer's provider is configuration. For government data, point `LLM_BASE_URL` at an Indian or self-hosted model.

## Team

Team Ace Azael, ACE Engineering College, Hyderabad.
