# Procurement Pilot

Bid compliance checking for government procurement officers. Built by **Team Ace Azael** (ACE Engineering College, Hyderabad) for **Smart India Hackathon 2026, problem statement SIH26100** (Ministry of Petroleum and Natural Gas).

Every bid runs through ten fixed checks written in plain code. A reasoning layer reads those results through one tool call and explains every flag in plain language. A named officer records the decision, and overruling a flagged bid needs a senior approver and a written reason. Everything lands in an audit log.

**Live:** https://procurement-pilot-sih.vercel.app (sign in with a demo account below)

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

Before a recording or a review window, sign in as `admin1`, open **Audit log** and press **Reset demo data** twice to start from a clean log.

## Deploy (Vercel + Neon, free)

The production setup is one Vercel project: FastAPI runs as a Vercel Function and `frontend/` is served from the CDN. `pyproject.toml` tells Vercel where the app is (`backend.app.main:app`).

1. Import this repo into Vercel. No build settings are needed.
2. In the project, open **Storage → Create → Neon** and connect it. This adds `DATABASE_URL`, and the app switches from SQLite to Postgres automatically.
3. In **Settings → Environment Variables**, set `JWT_SECRET` to a long random string. Every function instance must share it, or sign-ins will randomly fail.
4. Optional: turn on the reasoning layer with Sarvam's `sarvam-105b`: `LLM_BASE_URL=https://api.sarvam.ai/v1`, `LLM_MODEL=sarvam-105b`, `LLM_REASONING_EFFORT=low`, `LLM_API_KEY=<your Sarvam key>`. Any other OpenAI-compatible provider works the same way.
5. Redeploy. `GET /api/health` should report `"database": "postgres"`.

Vercel functions do not sleep for minutes the way free always-on hosts do. Neon's free compute idles after 5 minutes and wakes on the next query.

**Alternative: Render.** `render.yaml` deploys the same app as one long-running service (`New → Blueprint`). On the free plan it sleeps after 15 minutes idle and loses its SQLite file, so set `DATABASE_URL` there too if you use it.

If the API is unreachable for any reason, the frontend falls back to a built-in demo engine on the same sample data and labels it "Demo engine".

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q                      # 15 API tests on SQLite
TEST_DATABASE_URL=postgresql://... python -m pytest -q   # same suite on Postgres
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
  app/db.py          Postgres (DATABASE_URL) or SQLite, access log, retention job
  app/data.py        sample tenders and bids
  tests/test_api.py
frontend/
  index.html         landing page and officer workstation, one file
  team-logo.png
scripts/             seed sync, parity test
docs/REPO_SCOPE.md   what this repo is and is not
pyproject.toml       Vercel entrypoint
render.yaml          Render alternative
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
| POST | `/api/admin/reset-demo` | admin (clears evaluations before a demo; logged) |
| GET | `/api/health` | anyone |

## Known limits

- Tenders and bids are seeded; there is no document upload or PDF parsing in this build.
- GSTIN legal-name lookup is simulated. Structure and check-digit validation are real.
- The debarment list is a seeded placeholder, not a live GeM or CPPP lookup.
- Production runs on a free Neon Postgres; a real deployment needs a paid tier with backups and point-in-time restore.
- The reasoning layer's provider is configuration. The live build uses Sarvam's `sarvam-105b`, an Indian model; a self-hosted model works the same way.

## Team

Team Ace Azael, ACE Engineering College, Hyderabad.
