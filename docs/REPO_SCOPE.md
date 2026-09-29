# Repo scope

**This repository is the SIH26100 build of Procurement Pilot, and only that.**
Prepared 29 September 2026 for Team Ace Azael.

## Target

| | |
|---|---|
| Target repo | `victorisaacchinta-eng/procurement-pilot-sih` (new, public) |
| Purpose | The link that goes on the SIH portal and on slide 6 of the national deck |
| Problem statement | SIH26100, Ministry of Petroleum and Natural Gas, theme Smart Automation |
| Deploy target | One Render web service from `render.yaml` (API at `/api`, frontend at `/`) |

## Not in scope, not touched

| Repo or folder | Status |
|---|---|
| `victorisaacchinta-eng/procurement-pilot` | Left exactly as it is. It is the LaunchPad X build (hotel mess kitchen procurement agent, TypeScript), last pushed 25 Aug 2026. Nothing from this build is pushed there. |
| ForgeProof | A friend's separate SIH project. Nothing from it is here. |
| `Downloads/proc /server.py` ("Dynamic Edition") | A separate stdlib-only clone built from a brief. Not used, except that its score-cap idea (45 / 72) was adopted and is credited here. |

### Why a new repo instead of the old one

1. An evaluator who opens `procurement-pilot` today lands on a hotel procurement agent. That contradicts a submission about bid compliance for PSU tenders.
2. A branch would not fix it: GitHub shows the default branch first, and changing the default branch would bury the LaunchPad X record that the win is tied to.
3. A clean history makes the repo easy to review: backend, frontend, tests and deploy file, nothing else.

Both repos can point at each other in their READMEs if you want the lineage visible.

## Where this code came from

| Part | Source |
|---|---|
| Backend base | `Downloads/procurement-pilot-final 3/main.py` (FastAPI, 9 checks, dated 9 Sep 2026). The check logic, the seeded tenders and the override rule come from it. |
| Added in this build | 10th check (registry verification with real GSTIN check digits), weighted scoring with caps, collusion screen, JWT sign-in with three roles, server-side override rule by role, DPDP-style retention job, logged admin export, provider-agnostic reasoning layer, tests, CI, Render blueprint. |
| Rebuilt, not recovered | Auth, collusion, registry and retention were first written in the 11 Sep chat, but that code was never saved to the Mac. They were written again here and are covered by tests. |
| Frontend | New. Swiss poster layout in saffron, white, India green and Chakra navy, with the CRT sign-in, particle gimbal while the agent works, and stamped decisions. |

### Changes to behaviour you should know about

- **Scoring changed.** The old code gave FAIL the same half credit as FLAG. Now FAIL earns nothing and certain FAILs cap the score. Trident drops from a middling score to 45.
- **Statutory documents** now reads an explicit `documents_missing` list per bid instead of inferring from EMD and certificates.
- **Decision names** are `Qualified`, `Request Clarification`, `Hold for Review`, `Mark Non-Compliant`, matching the past-performance check.
- **A third tanker bid** (Ratnagiri Roadlines) was added to the sample data so the collusion screen has a real hit to show.
- **Trident's turnover** was set below the tender minimum and its GSTIN given a bad check digit so one bid demonstrates hard failures.

## What is real and what is simulated

| Real | Simulated or seeded |
|---|---|
| All ten checks and the scoring | Tenders, bids and addresses |
| GSTIN format and check-digit validation | GSTIN legal-name registry |
| Collusion screen maths | Debarment list |
| JWT sign-in, roles, override rule | Demo accounts |
| Retention and logged export | Reasoning layer runs only if `LLM_API_KEY` is set |

## Things deliberately left out

- **National Emblem of India.** Not used anywhere. The State Emblem of India (Prohibition of Improper Use) Act, 2005 bars using the emblem in any way that suggests the work relates to the Government without authorisation. A student prototype carrying it would read as an official system, which is also the opposite of what a jury wants to see.
- **PSU and GeM logos.** Removed from the old build's assets. Showing CPCL, ONGC, BPCL or GeM logos implies a partnership that does not exist yet.
- **SIH logo.** Not included; add it only if the SIH guidelines allow participants to use it on their own sites.
- **Model vendor name in the UI.** The reasoning layer shows the model name only, and the provider is configuration.

## Before pushing

- [ ] Confirm the repo name and that it should be public
- [ ] Decide on a licence (none is included, which means all rights reserved)
- [ ] Deploy on Render and put the live URL in this README and on slide 6
- [ ] Open the live URL in a private window, sign in as each demo account, run the demo path in the README
- [ ] Confirm the demo video and deck match this build (score numbers, decision names, 10 checks)
