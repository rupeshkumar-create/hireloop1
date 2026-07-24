# Hireschema — System Bible (full pack)

Merged from **01-business**, **02-candidate**, and **03-recruiter** leadership decks.  
HTML twin: `index.html` · PDF: `Hireschema-System-Bible.pdf`

---

## Business

### Not a job board with a chatbot
- **Aarya** (candidate): profile · chat/voice · Google Jobs ingest · scored matches · Request Intro  
- **Nitya** (recruiter): JD · publish · score candidates · Gmail OAuth intros  
- Shared Supabase graph · intros via `intro_requests` · **no agent RPC**

### Why it exists
| Candidate | Recruiter |
|-----------|-----------|
| Less apply-spam; scored live ingest; intro from *their* Gmail | JD in minutes; same matcher shortlist; warm intros |

MVP focus: India (`market=IN`, INR/LPA). Opt-in discovery default OFF.

### Surfaces
`web/` marketing · `app/` SPA (+ `/r/{slug}`) · `api/` FastAPI/LangGraph · `supabase/` Postgres/pgvector

### Stack (live)
Next.js 15 · Supabase Auth (LinkedIn) · FastAPI + LangGraph · OpenRouter (claude-sonnet-4.6 / gemini-2.5-flash / embedding-3-small) · Deepgram · Apify Google Jobs (`johnvc/Google-Jobs-Scraper`) · Firecrawl · Resend (txn) · Gmail OAuth (cold).  
*Not on slides: Affinda, SendGrid, MSG91.*

### Master loop
Think → Tool → Execute → Write `agent_actions`

---

## Candidate · Aarya

### Journey
LinkedIn → Onboard (CV/prefs) → Chat → Matches → Intro (Gmail→HM)

### SPA
`/onboarding` · `/chat` · `/jobs`/`matches` · `/profile` · client `api.ts` only · Realtime `agent_actions`

### Profile signals
LinkedIn → users/candidates · Resume → Storage/parser · Chat prefs · `candidate_embeddings` (profile/skills/resume, 1536-d)

### Job ingest
**Source:** Apify Google Jobs only.  
**Triggers:** cron, `aarya_auto_ingest`, `POST /matches/find-new`, `career_path_ingest`  
**Pipeline:** Scrape → upsert `jobs` → embed `job_embeddings` → score `match_scores`  
**Dedup:** `apify_job_id` → fingerprint → `apply_url` · query skip 24h · bucket freshness 12h · Find new = unseen impressions only  
Embeddings run in **background workers**, not inside JobIngester.

### Match math (`MatchingEngine._assemble_score`)
```
overall = Σ (w_i × dim_i) / Σ w_included
then × role_fit × domain_fit × title_penalty × seniority_gap

w: skills 0.40 · profile 0.30 · experience 0.15 · location 0.10 · ctc 0.05
```
- **Skills:** `0.85×coverage + 0.15×jaccard` + embedding lift α=0.40 (lift only)  
- **Profile:** title affinity + profile↔JD cosine lift α=0.50  
- **Location:** remote/city/state bands  
- **Floors:** persist ≥0.35 · feed ≥0.38  
- **RRF (k=60)** orders feed/search lists — does **not** redefine overall_score

### Request Intro (R5)
Aarya INSERT `intro_requests` → NOTIFY → Nitya draft → candidate approve-send → Gmail. No HTTP between agents.

### Voice
Mic → Nova-3 → same Aarya → Aura TTS. Same chat surface.

---

## Recruiter · Nitya

### Journey
Signup → JD (form/URL) → Publish `/r/{slug}` → Search → Intro

### JD
Manual form · URL import (Firecrawl + Ashby/Greenhouse + JSON-LD)

### Graph search — no separate ranker
```
ensure_role_scoring_job (jobs.source='recruiter')
→ MatchingEngine.score_job(limit=500)
→ ORDER BY overall_score DESC
→ role_pipeline (stage=search)
```
Visibility: `share_with_recruiters` and not private.  
Same weights/dims/gates as candidate Matches. Per-criterion LLM scoring **not live**.

### Nitya intros
LISTEN `intro_requests` · enrich (Apify) · draft · Gmail OAuth send · update status

---

## Status · roadmap

### Risks
Match/Find-new reliability · chat find-jobs polish · need Apify + embed workers + Gmail OAuth · recruiter empty if graph empty

### Next 2 weeks
Stabilize ingest→embed→score · impression hygiene · chat↔Matches parity · Gmail intro E2E · embed-after-role-sync

### Post-MVP
15–20 min Aarya Deepgram screening call → richer profile **and** apply-time screening card for recruiters (after MVP stable)

---

## Takeaways
1. Two agents, one Postgres graph  
2. Jobs from Apify Google Jobs → embed → score  
3. One MatchingEngine for candidate feed + recruiter pipeline  
4. Cold email = Gmail + approve-send; Resend = transactional  
5. Screening call = post-MVP  
