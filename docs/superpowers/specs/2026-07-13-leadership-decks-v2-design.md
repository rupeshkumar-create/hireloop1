# Hireschema leadership decks v2 — design

**Date:** 2026-07-13  
**Status:** Approved (user)  
**Deliverable:** Three downloadable HTML decks + zip

## Goals

1. Keep **three decks** (business, candidate, recruiter) — sharper and denser than v1.
2. Full-stack depth: product story **and** real architecture (routes, tables, services).
3. Specific to Hireschema — not generic “AI recruiting” copy.
4. Each deck ends with **Status & risks** (candid) + **Next 2 weeks** (roadmap).
5. **Exclude** MSG91, SendGrid, NeverBounce from all slides (not in active use). Transactional email = **Resend**; cold intros = **Gmail OAuth**.
6. Decks 02 & 03 must explain **match scoring, job ingest, graph/candidate search** in detail: where data comes from, how it is calculated, how it flows.
7. Downloadable: `docs/presentations/v2/` + `Hireschema-decks-v2.zip` (self-contained offline).

## Non-goals

- Interactive animated product tour
- Replacing v1 files (keep as reference under `docs/presentations/`)
- Live localhost companion for delivery

## Vendor truth (slides)

| Use | Vendor |
|-----|--------|
| Auth / DB / Realtime / Storage | Supabase |
| Web hosting | Vercel |
| API | Railway / AWS ECS path |
| Edge | Vercel (Cloudflare planned, not live) |
| LLM + embeddings gateway | OpenRouter (`text-embedding-3-small`, 1536-d) |
| Voice | Deepgram |
| Job scrape | Apify — **Google Jobs** actor `johnvc/Google-Jobs-Scraper` |
| JD URL import | Firecrawl + HTML/JSON-LD |
| Transactional email | **Resend** |
| Cold HM email | Candidate **Gmail OAuth** |

Do **not** mention MSG91, SendGrid, or NeverBounce.

## Algorithm truth (decks 02 & 03)

### Job ingest

1. Trigger: cron / admin ingest / Aarya auto-ingest / Find new (`force_refresh`).
2. Apify Google Jobs scrape → normalize → upsert `jobs` (dedupe: `apify_job_id`, fingerprint, `apply_url`).
3. Dedupe window 24h per query/location unless force refresh; bucket freshness 12h for candidate ingest.
4. Embeddings **after** ingest via background workers → `job_embeddings` / `candidate_embeddings`.
5. Impressions in `candidate_job_impressions`; Find new = unseen only.

### Match scoring (`MatchingEngine` / `matching.py`)

Weights (renorm if dim missing):

- Skills **0.40** · Profile emb path **0.30** · Experience **0.15** · Location **0.10** · CTC **0.05**

Skills lexical: `0.85 * coverage + 0.15 * jaccard`, then semantic lift from embeddings.  
Gates: role-fit, domain-fit multiplier, generic-title penalty, seniority gap.  
Persist floor ~0.35 (path-aligned lower); feed floor ~0.38.  
Written to `match_scores` (`overall_score`, dim scores, `bias_audit`, explanation fields).  
**RRF (k=60)** used for feed/search **ranking fusion**, not for computing `overall_score`.

### Recruiter “graph” search

No separate graph engine. Role mirrored to a `jobs` row (`source='recruiter'`) → same `MatchingEngine.score_job` → order by `overall_score` → `role_pipeline`.

## Deck outlines

### 01 Business (~11 slides)
Title → What/why → Two agents → Surfaces → System map → Stack (corrected vendors) → Agent loop → Compliance → Status & risks → Next 2 weeks → Close

### 02 Candidate (~12–14 slides)
Title → Journey → SPA → Profile/embeddings → Aarya tools → **Ingest deep-dive** → **Scoring deep-dive** (weights + gates + RRF) → Intro handshake → Realtime → Status & risks (match/chat) → Next 2 weeks → Close

### 03 Recruiter (~12–14 slides)
Title → Journey → SPA → JD create/import → Publish → **Search deep-dive** (mirror job + same scorer) → **Scoring recap** tied to pipeline → Nitya + Gmail → Enrichment (Apify only, no NeverBounce) → Status & risks → Next 2 weeks → Close

## Status & risks content (seed)

- Code S01–S21 largely written; E2E with real keys incomplete
- Job match feed / chat “find jobs” still need product polish and reliability work
- Apify / Gmail OAuth / Resend env-dependent
- Payments deferred; S22 infra deploy incomplete in tracker

## Post-MVP: Aarya screening call (user-requested)

**Gate:** After job ingest/match is stable and candidate + recruiter MVP works.

**Flow:** Candidate schedules 15–20 min Deepgram voice call with Aarya → extract experience, career path, prefs → write profile/embeddings.

**Dual purpose:**
1. Candidate — richer profile → better relevant matches
2. Recruiter — on apply, backend screens call insights + JD → screening result in pipeline UI

**Slide placement:** Deck 01 roadmap · Deck 02 candidate call deep-dive · Deck 03 recruiter screening results. Not in “Next 2 weeks.”

## Delivery

- Files: `index.html`, `01-business.html`, `02-candidate.html`, `03-recruiter.html`, `shared.css`, `shared.js`
- Zip: `Hireschema-decks-v2.zip`
- Nav: keyboard + print-to-PDF CSS
