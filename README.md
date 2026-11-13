<p align="center">
  <img src="assets/readme/hero.svg" alt="Procurement Pilot: fifteen checks on every bid, before anyone signs." width="100%">
</p>

<p align="center">
  <a href="https://procurement-pilot-sih.vercel.app"><img alt="Live" src="https://img.shields.io/badge/live-procurement--pilot--sih.vercel.app-FF9933?style=flat-square&labelColor=111010&logo=vercel&logoColor=FBF8F2"></a>
  <a href="https://youtu.be/D4A3Fv-sczU"><img alt="Demo video" src="https://img.shields.io/badge/demo-4%3A52-C8102E?style=flat-square&labelColor=111010&logo=youtube&logoColor=FBF8F2"></a>
  <img alt="SIH 2026 SIH26100" src="https://img.shields.io/badge/SIH%202026-SIH26100-138808?style=flat-square&labelColor=111010">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-FBF8F2?style=flat-square&labelColor=111010&logo=python&logoColor=FBF8F2">
  <img alt="FastAPI" src="https://img.shields.io/badge/api-FastAPI-FBF8F2?style=flat-square&labelColor=111010&logo=fastapi&logoColor=FBF8F2">
  <img alt="Postgres on Neon" src="https://img.shields.io/badge/db-Postgres%20(Neon)-FBF8F2?style=flat-square&labelColor=111010&logo=postgresql&logoColor=FBF8F2">
  <a href="https://github.com/victorisaacchinta-eng/procurement-pilot-sih/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/victorisaacchinta-eng/procurement-pilot-sih/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="50 API tests" src="https://img.shields.io/badge/tests-50%20API%20%2B%20parity%20%2B%20eval-138808?style=flat-square&labelColor=111010">
  <img alt="Sarvam" src="https://img.shields.io/badge/Sarvam-reasoning%20%C2%B7%20OCR%20%C2%B7%2022%20languages-FF9933?style=flat-square&labelColor=111010">
  <img alt="MIT licence" src="https://img.shields.io/badge/licence-MIT-FF9933?style=flat-square&labelColor=111010">
</p>

<h3 align="center">Registry-verified bid compliance for government procurement.<br>Code decides. AI explains. A named officer signs.</h3>

<p align="center"><a href="https://procurement-pilot-sih.vercel.app"><b>procurement-pilot-sih.vercel.app</b></a> &nbsp;·&nbsp; <a href="https://youtu.be/D4A3Fv-sczU"><b>watch the 4:52 demo</b></a></p>

<p align="center">
  <a href="#-see-it">See it</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#-the-score">The score</a> ·
  <a href="#-the-fifteen-checks">Checks</a> ·
  <a href="#-all-fourteen-sih26100-outcomes">Coverage</a> ·
  <a href="#-measured-on-a-seeded-test-set">Measured</a> ·
  <a href="#-quick-start">Quick start</a> ·
  <a href="#-the-3-minute-demo">Demo</a>
</p>

<img src="assets/readme/divider.svg" width="100%" alt="">

A procurement officer checking a GeM bid today opens portal after portal: GST, income tax, MCA21, Udyam, EPFO,
the debarment list, then the bid documents themselves. It is slow, and two officers can reach two different answers
on the same bid. Procurement Pilot runs **fifteen fixed checks** on every bid against **ten registry sources**,
scores it out of 100 with a risk level, explains every flag in plain language, and leaves the decision, and the
signature, to a named officer. Built by **Team Ace Azael** (ACE Engineering College, Hyderabad) for
**Smart India Hackathon 2026**, problem statement **SIH26100** from the Ministry of Petroleum and Natural Gas.

> [!NOTE]
> Student prototype. Not an official government system and not affiliated with or endorsed by any ministry or PSU.
> All tenders, bids, registry records, GSTINs, PANs, CINs and Udyam numbers here are **sample data**, and every
> registry lookup is labelled **simulated** in the app.

## ◆ See it

<p align="center">
  <a href="https://youtu.be/D4A3Fv-sczU"><img src="assets/readme/video.jpg" width="100%" alt="Watch the Procurement Pilot demo on YouTube (4:52)"></a>
  <br><sub>The full walkthrough on YouTube, 4:52.</sub>
</p>

<p align="center">
  <img src="assets/readme/walkthrough.gif" width="100%" alt="The live workstation: Petrotech scores 100, Vantage 89 with the document check finding a legal-name mismatch, Trident 45 and stamped non-compliant, a senior approver's written override, the collusion screen and the audit log.">
  <br><sub>Real screens from the live build: 100, 89, the document check, 45 and the stamp, a written override, the collusion screen and the audit log.</sub>
</p>

## ◆ How it works

<p align="center">
  <img src="assets/readme/flow.svg" width="100%" alt="How a bid moves: bid in, ten registries, fifteen checks, score and risk, reasoning, officer, audit log.">
</p>

<table>
<tr>
<td width="33%" valign="top">

**Checks in plain code**<br>
<sub>Fifteen deterministic checks. Each returns PASS, FLAG or FAIL with a sentence naming the real numbers and the source it checked. Same bid, same answer, every time.</sub>

</td>
<td width="33%" valign="top">

**One adapter per registry**<br>
<sub>GSTN, Income Tax, MCA21, Udyam, DPIIT, NSIC, EPFO, ESIC, DigiLocker and the GeM / CPPP debarment list. Going live means replacing one lookup function; the checks do not change.</sub>

</td>
<td width="33%" valign="top">

**It reads the documents**<br>
<sub>Upload a bid PDF: it pulls the GSTIN, PAN, Udyam, CIN, DPIIT number and legal name, cross-checks each against the bid and shows the page and line it came from. Scanned PDFs go to Sarvam Vision for OCR.</sub>

</td>
</tr>
<tr>
<td valign="top">

**AI that explains, never approves**<br>
<sub>A reasoning layer (Sarvam's <code>sarvam-105b</code>) writes the explanation. It cannot set the score or the verdict, PAN and GSTIN are masked before anything reaches it, and without a key the app falls back to a deterministic summary and says so.</sub>

</td>
<td valign="top">

**Collusion across bids**<br>
<sub>Every pair of bids on a tender is compared: prices within 0.5%, submissions within 5 minutes, shared addresses, a shared director (by DIN), bank account or phone number, and cover bids more than 25% above the benchmark. A graph shows who is tied to whom.</sub>

</td>
<td valign="top">

**A human signs, on the record**<br>
<sub>Officer, senior approver and admin roles are enforced by the server. Passing a flagged bid needs a senior approver and a written reason of 30+ characters. Every decision lands in the audit log, and prints as a signed report.</sub>

</td>
</tr>
<tr>
<td valign="top">

**Rules from the tender itself**<br>
<sub>Upload the GeM bid document or NIT and the minimum turnover, EMD, estimated value, experience, exemptions, labour clauses and required documents are read page by page. A senior approver checks them, corrects any misread value and applies them to the tender.</sub>

</td>
<td valign="top">

**A ledger that shows tampering**<br>
<sub>Every evaluation, decision, anonymisation and rulebook change is sealed in a SHA-256 hash chain. <b>Verify</b> recomputes the chain and replays it against the audit log, so a score edited straight in the database is named on screen.</sub>

</td>
<td valign="top">

**Twenty-two languages**<br>
<sub>The workstation runs in English and all 22 scheduled languages of India through Sarvam Translate. GSTINs, PANs and other identifiers are held back from translation, and anything that does not come back intact stays in English.</sub>

</td>
</tr>
</table>

## ◆ The score

<p align="center">
  <img src="assets/readme/score.svg" width="100%" alt="How the score works: weights add to 100; PASS earns full weight, FLAG half, FAIL zero; risk is Low, Medium, High or Critical, with caps at 72 and 45.">
</p>

The weights add up to 100. A FAIL on EMD, statutory documents, GST registration or debarment caps the score at
**45** and makes the risk **Critical**; any other FAIL caps it at **72** (**High**); any FLAG makes it **Medium**;
all PASS is **Low**. The workstation shows a *Why not 100* line with every point lost and why.

## ◆ The fifteen checks

| Family | Check | Weight | Checked against |
|---|---|---:|---|
| **Tender eligibility** | EMD compliance 🔻 | 10 | Bid record, Udyam / DPIIT / NSIC for exemptions |
|  | Statutory documents 🔻 | 10 | DigiLocker |
|  | Financial turnover | 10 | Bid record; the tender document when a rulebook is applied |
|  | Price reasonability | 8 | Tender benchmark |
|  | Make in India local content | 6 | Bid declaration (Class-I 50%+, Class-II 20%+) |
|  | OEM authorisation | 6 | Bid declaration |
| **Registry verification** | GST registration and returns 🔻 | 8 | GSTN, plus the real GSTIN check digit |
|  | PAN and income tax | 7 | Income Tax Department, PAN read from the GSTIN |
|  | MSE and Startup status | 6 | Udyam, DPIIT, NSIC |
|  | EPFO and ESIC compliance | 6 | EPFO, ESIC |
| **Integrity and risk** | Entity name consistency | 7 | Bid, documents, GSTN, PAN holder, MCA21 |
|  | Debarment status 🔻 | 8 | GeM / CPPP debarment list, by name and by the PAN behind the GSTIN |
|  | Public interest screening | 3 | Adverse media record |
|  | Shell company indicators | 3 | MCA21 incorporation date, shared addresses |
|  | Past performance history | 2 | This platform's own audit log |

🔻 a FAIL here caps the score at 45. Rules that need no lookup are real: the GSTIN check digit, the PAN inside the
GSTIN with its holder-type and name codes, the Make in India class thresholds, EMD exemptions for verified MSE,
Startup and NSIC bidders, a one-month grace on EPFO / ESIC challans, and incorporation under 91 days as a shell signal.

## ◆ All fourteen SIH26100 outcomes

| # | Asked for | Where it lives |
|---|---|---|
| 1 | Integrate with government portals | `registry.py` adapters (sample data) and the Registries view |
| 2 | Udyam / MSME | MSE and Startup status; EMD exemption |
| 3 | GST registration and returns | GST registration and returns |
| 4 | PAN and income tax | PAN and income tax |
| 5 | Make in India / local content | Make in India local content |
| 6 | EPFO / ESIC | EPFO and ESIC compliance |
| 7 | Startup India, NSIC, OEM authorisation | MSE and Startup status; OEM authorisation |
| 8 | DigiLocker / document verification | Statutory documents; document reader with page citations; OCR through Sarvam Vision |
| 9 | Blacklisting / debarment | Debarment status, matched by name and by PAN |
| 10 | Other statutory and tender-specific | Tender rulebook read from the NIT; EMD, turnover, price; spec gaps named by the reasoning layer |
| 11 | AI for missing or inconsistent information | Entity name across bid, documents, GSTN, PAN, MCA21; ownership links between bidders; reasoning layer |
| 12 | Compliance score and risk level | Score, why-not-100, Low / Medium / High / Critical |
| 13 | AI recommendation | Reasoning layer (Sarvam `sarvam-105b`), in 22 languages |
| 14 | Auditable record | Hash-chained ledger with Verify, audit log, access log, printable report |

## ◆ Measured on a seeded test set

`scripts/run_eval.py` builds a test set from the three seeded bids that pass every check. Each case plants one
known defect, so we know which check should catch it, or sits exactly on a threshold where an honest bid must still
pass. CI fails if the results change.

| What | Result |
|---|---|
| Planted defects caught, across all 15 checks | **57 / 57** |
| Honest bids flagged, including bids on a threshold (turnover equal to the minimum, price exactly 12% off, local content at 20% and 50%) | **0 / 21** |
| Collusion links found (price, timing, address, director, bank, phone, email, cover bid) | **8 / 8**, with 0 of 3 clean pairs flagged |
| Rules read correctly from the sample tender document | **8 / 8** |

The set includes the ways a debarred firm gets back in: the listed name written as "Private Limited" instead of
"Pvt Ltd", and a new name over the same PAN. The first build of the debarment check matched exact names only and
let both through; it now matches both. This is a regression harness on synthetic records.
Field accuracy needs real tender outcomes, which we do not have. Every case is listed in the workstation
under **Measured** and in [`backend/app/eval_results.json`](backend/app/eval_results.json).

<img src="assets/readme/divider.svg" width="100%" alt="">

## ◆ Quick start

You need Python 3.11 or newer.

```bash
git clone https://github.com/victorisaacchinta-eng/procurement-pilot-sih.git
cd procurement-pilot-sih/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

It ends with `Uvicorn running on http://127.0.0.1:8000`. Open that address, press **Open workstation** and tap a
demo account.

| Account | Password | Role |
|---|---|---|
| `officer1` | `officer123` | Officer |
| `approver1` | `approver123` | Senior approver |
| `admin1` | `admin123` | Admin |

These are demo credentials. Override them with `DEMO_USERS` and set `JWT_SECRET` before any real use.

<details>
<summary><b>Turn on the reasoning layer</b></summary>

<br>

Copy `.env.example` to `backend/.env` and set `LLM_API_KEY`. For Sarvam: `LLM_BASE_URL=https://api.sarvam.ai/v1`,
`LLM_MODEL=sarvam-105b`, `LLM_REASONING_EFFORT=none`. Any OpenAI-compatible provider works the same way. Without a
key every check still runs and the recommendation is a deterministic summary.

OCR (Sarvam Vision) and the 22 languages (Sarvam Translate) use the same Sarvam key. When `LLM_BASE_URL` points at
Sarvam they pick up `LLM_API_KEY`; with another reasoning provider, set `SARVAM_API_KEY`. Without it, text PDFs are
still read, scanned PDFs say what is needed, and the workstation stays in English.

</details>

## ◆ The 3-minute demo

| Do | You see |
|---|---|
| **Pipeline valves → Petrotech** | Every check passes: **100, Compliant, risk Low** |
| **Pipeline valves → Vantage** | GSTN, the PAN holder and the documents all say "Vantage Flow Solutions Ltd": **89, Needs review**. Press **Vantage** under Document check and the PDF reader finds the same mismatch |
| **Refinery PPE → SafeGuard** | No EMD paid, but a verified DPIIT startup, so the exemption holds: **100** |
| **Refinery PPE → Trident** | No EMD, BIS licence missing, turnover short, 15% local content, a GSTIN that fails its check digit: **45, Critical** |
| **Refinery PPE → Apex** | On the debarment list and not the OEM: **45, Critical** |
| **Tanker transport → Screen for collusion** | Swift and Ratnagiri quoted 0.38% apart, 2 minutes apart, share a director (DIN 08812345) and a phone number. Swift itself: incorporated 55 days before bidding, no ESIC |
| **Tanker transport → sample tender document**, as `approver1` | The record says Rs 40 lakh minimum turnover, page 1 of the document says Rs 4 crore. **Apply** it and Ratnagiri drops from **95** to **72, Non-compliant**, with the page cited in the check |
| **Ratnagiri → Document check → Ratnagiri (scanned)** | An image-only PDF read by Sarvam Vision; every identifier matches, with page and line |
| **Refinery PPE → Screen for collusion** | Trident and the debarred Apex pay from the same bank account |
| **Depot security → Meridian → Qualified** | Refused for `officer1`. As `approver1`, the written-override box opens |
| **Registries**, then **Audit log** as `admin1` | Every source and its mode; every decision with name, time and ledger seal; **Verify chain**; **Export log** |
| **Language**, top bar | தமிழ், हिन्दी, اردو and the rest of the 22; **Print report** follows the language on screen |

Before a recording or a review window, sign in as `admin1`, open **Audit log** and press **Reset demo data** twice.

## ◆ Tests

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q                      # 50 API tests on SQLite (Sarvam calls are mocked)
TEST_DATABASE_URL=postgresql://... python -m pytest -q   # same suite on Postgres
cd .. && python scripts/dump_backend.py > /tmp/b.json && node scripts/parity_test.js /tmp/b.json
python scripts/run_eval.py --check       # the measured results above are still true
```

The parity test runs the frontend's offline engine against the backend's own results for every sample bid. CI runs all of it on every push.

If you change anything in `backend/app/data.py`, `checks.py` or `collusion.py`, run `python scripts/run_eval.py` and `python scripts/sync_seed.py` so the measured results and the frontend's copy of the data stay identical.

<details>
<summary><b>Deploy (Vercel + Neon, free)</b></summary>

<br>

The production setup is one Vercel project: FastAPI runs as a Vercel Function and `frontend/` is served from the CDN. `pyproject.toml` tells Vercel where the app is (`backend.app.main:app`).

1. Import this repo into Vercel. No build settings are needed.
2. In the project, open **Storage → Create → Neon** and connect it. This adds `DATABASE_URL`, and the app switches from SQLite to Postgres automatically.
3. In **Settings → Environment Variables**, set `JWT_SECRET` to a long random string. Every function instance must share it, or sign-ins will randomly fail.
4. Optional: turn on the reasoning layer with Sarvam's `sarvam-105b`: `LLM_BASE_URL=https://api.sarvam.ai/v1`, `LLM_MODEL=sarvam-105b`, `LLM_REASONING_EFFORT=none` (switches off hidden reasoning, which keeps answers fast), `LLM_API_KEY=<your Sarvam key>`. Any other OpenAI-compatible provider works the same way.
5. Redeploy. `GET /api/health` should report `"database": "postgres"`, and `sarvam.translate` once the Sarvam key is in.

Preview deployments use their own Postgres schema (`preview`) inside the same database, so testing a branch never touches production records.

Vercel functions do not sleep for minutes the way free always-on hosts do. Neon's free compute idles after 5 minutes and wakes on the next query.

**Alternative: Render.** `render.yaml` deploys the same app as one long-running service (`New → Blueprint`). On the free plan it sleeps after 15 minutes idle and loses its SQLite file, so set `DATABASE_URL` there too if you use it.

If the API is unreachable for any reason, the frontend falls back to a built-in demo engine on the same sample data and labels it "Demo engine".

</details>

<details>
<summary><b>API</b></summary>

<br>

| Method | Path | Who |
|---|---|---|
| POST | `/api/auth/login` | anyone |
| GET | `/api/auth/me` | signed in |
| GET | `/api/tenders` | signed in |
| GET | `/api/evaluate-seed?tender_id=&bidder_name=` | signed in |
| GET | `/api/registries` | signed in |
| POST | `/api/documents/extract` (multipart: tender_id, bidder_name, file) | signed in (logged) |
| POST | `/api/officer-decision` | signed in (qualifying a flagged bid: senior approver or admin) |
| GET | `/api/collusion-check?tender_id=` | signed in |
| GET | `/api/audit-log` | signed in |
| GET | `/api/audit-log/verify` | signed in (logged) |
| GET | `/api/audit-log/export` | admin (carries the ledger) |
| POST | `/api/rulebooks/extract` (multipart: tender_id, file) | signed in (logged) |
| GET | `/api/rulebooks?tender_id=` | signed in |
| POST | `/api/rulebooks/{id}/apply` | senior approver or admin (sealed in the ledger) |
| POST | `/api/tenders/{id}/rulebook/revert` | senior approver or admin (sealed in the ledger) |
| GET | `/api/languages` | anyone |
| POST | `/api/translate` | signed in |
| GET | `/api/eval` | signed in |
| POST | `/api/admin/retention` | admin |
| POST | `/api/admin/reset-demo` | admin (clears evaluations before a demo; logged) |
| GET | `/api/health` | anyone |

</details>

<details>
<summary><b>Repository layout</b></summary>

<br>

```
backend/
  app/main.py        routes, override rule, static mount
  app/checks.py      the fifteen checks, weights, caps, verdict, risk level
  app/registry.py    one adapter per registry; GSTIN / PAN rules
  app/documents.py   PDF reader, page citations, OCR fallback, identifier cross-check
  app/rulebook.py    eligibility rules read from the tender document
  app/ledger.py      SHA-256 hash chain, verify and replay
  app/sarvam.py      Sarvam Translate (22 languages) and Sarvam Vision (OCR)
  app/collusion.py   pairwise collusion screen and ownership graph
  app/llm.py         reasoning layer, provider-agnostic
  app/auth.py        JWT sign-in, roles
  app/db.py          Postgres (DATABASE_URL) or SQLite, access log, retention job
  app/data.py        sample tenders, bids and simulated registries
  app/eval_results.json  measured results, written by scripts/run_eval.py
  tests/test_api.py, tests/test_finale.py
frontend/
  index.html         landing page and officer workstation, one file
  team-logo.png
  samples/           sample bid PDFs (one scanned) and a sample tender document
scripts/             seed sync, parity test, measured test set, sample PDFs
assets/readme/       README artwork (SVG, GIF)
docs/REPO_SCOPE.md   what this repo is and is not
pyproject.toml       Vercel entrypoint
render.yaml          Render alternative
```

</details>

## ◆ Honest limits

- Tenders and bids are seeded. The document reader cross-checks a PDF against a seeded bid; it does not create new bids.
- Every registry lookup (GSTN, Income Tax, MCA21, Udyam, DPIIT, NSIC, EPFO, ESIC, DigiLocker, debarment) reads sample records and says so. GSTIN check digit and PAN structure rules are real. Live access needs government onboarding (API Setu, a GST Suvidha Provider).
- OCR and translation call Sarvam and need its key. Translation covers the interface and the results; the tender document and the bid stay authoritative in their own language. Urdu, Kashmiri and Sindhi set text direction per paragraph; the layout itself is not mirrored.
- The ledger shows tampering; it cannot prevent it. Someone with full database access could rewrite the whole chain consistently. The head hash is shown on Verify and carried in every export, so a copy kept outside the system exposes that too; publishing the head daily is the next step.
- The rulebook reader is tuned to GeM bid document wording. An unusual NIT may need the approver's correction before applying, which the apply step allows.
- Production runs on a free Neon Postgres; a real deployment needs a paid tier with backups and point-in-time restore.
- The reasoning layer's provider is configuration. The live build uses Sarvam's `sarvam-105b`, an Indian model; a self-hosted model works the same way.

## ◆ Roadmap

- Publish the ledger head daily outside the system
- Live GSTN and Udyam lookups through API Setu and a GST Suvidha Provider
- One pilot with a CPSE procurement team

## ◆ Licence

MIT, see [`LICENSE`](LICENSE). Third-party packages keep their own licences.

<img src="assets/readme/divider.svg" width="100%" alt="">

<p align="center"><sub>Built by <b>Team Ace Azael</b>, ACE Engineering College, Hyderabad · Smart India Hackathon 2026 · SIH26100.<br>Repository by <a href="https://github.com/victorisaacchinta-eng">Chintha Victor Isaac</a>.</sub></p>
