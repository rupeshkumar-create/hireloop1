# Backend Improvement Plan — 50 items (Jun 12, 2026)

Prioritized, grounded in the current code. 🔥 = biggest demo-visible impact.
Status: API = FastAPI/asyncpg, 2-tier parser, lexical+RRF matching, LangGraph agents.

---

## A. Latency — onboarding & first feed (the "slow AI" you're seeing)

1. 🔥 **Parallelize onboarding enrichment.** LinkedIn fetch → CI generation → career path → scoring run sequentially after signup. Run LinkedIn enrich + résumé parse concurrently (`asyncio.gather`), then one CI pass.
2. 🔥 **Defer Career Intelligence to background.** Don't block the dashboard on the 24-layer CI generation; render profile immediately, stream CI in via the panel's existing cache/poll.
3. 🔥 **Single-flight guard for first scoring.** `score_candidate` can be triggered by signup AND first feed load; add a per-candidate in-flight lock so it runs once.
4. **Batch embeddings.** `EmbeddingService` embeds one text per call; OpenRouter supports batching — embed candidate + all chunks in one request.
5. **Cache LinkDAPI responses** (24h, keyed by URL) — repeated onboarding retries currently re-fetch.
6. **Move `recompute_matches` heavy loop to chunked tasks** with progress rows so the admin panel can show "scored 120/200".
7. **Add `EXPLAIN ANALYZE` pass + composite index** on `match_scores(candidate_id, overall_score DESC)` (feed sort) and `jobs(country_code, is_active, expires_at)`.
8. **HTTP/2 + connection reuse for OpenRouter** — one shared `httpx.AsyncClient` per process instead of per-call clients (chat already does; parser/CI don't).
9. **Profile P95s**: add timing middleware emitting per-route histograms to the observability endpoint so slowness is measured, not guessed.

## B. Voice latency (Aarya call)

10. 🔥 **Stream TTS sentence-by-sentence.** Today the full LLM reply is generated, then spoken. Pipe the SSE token stream into incremental TTS per sentence — cuts perceived latency from ~8s to ~1.5s.
11. 🔥 **Use the fast model unconditionally in voice mode** (complexity router already exists — force-fast for voice turns).
12. **Pre-warm the voice pipeline** when the call screen mounts (open WS, prime STT, fetch profile context) instead of on first utterance.
13. **Shorter voice system prompt.** The full Aarya prompt + turn context is large; voice needs a trimmed variant (target <1.5k tokens).
14. **Barge-in:** stop TTS playback as soon as STT detects speech (currently the candidate waits out the answer).
15. **Cache the candidate context block per call session** instead of rebuilding per turn.

## C. Résumé parser (make it stronger)

16. 🔥 **Layout-aware extraction**: integrate `pdfplumber` word-position data to reconstruct columns — two-column CVs currently interleave lines, confusing the LLM tier.
17. **OCR fallback** (`pytesseract`/RapidOCR) for scanned/image PDFs — today these parse as empty.
18. **DOCX styles → structure**: use heading styles in `python-docx` to segment sections instead of regex on text.
19. **Confidence scores per field** in `ParsedResume`; only auto-apply ≥0.7, queue the rest as Aarya confirm-questions (feeds the no-repeat-questions goal).
20. **Multi-pass LLM parse**: pass 1 segment (sections), pass 2 extract per-section with focused schemas — fewer hallucinated fields than one mega-prompt.
21. **Skills canonicalization table** (`skill_aliases`): map "ReactJS/React.js/react" → `react` at parse time; today aliases dilute skill-overlap matching.
22. **Date normalization + tenure math**: parse "Jan 2021 – present" to real dates; compute `years_experience` from work history instead of trusting the stated number.
23. **Language detection + Hinglish handling** for regional CVs.
24. **Parser eval harness**: 20 fixture résumés (anonymized) + golden JSON; CI fails if extraction F1 drops — makes "stronger" measurable.
25. **Store parser version + raw text hash** on `resumes` so re-parse only runs when the parser improves.

## D. Job finding / ingestion

26. 🔥 **Multi-source beyond Apify**: add free/cheap feeds (company career-site JSON, Greenhouse/Lever public boards APIs, Google Jobs schema crawl) so the feed isn't hostage to one paid actor.
27. **Freshness decay**: score boost for jobs <72h, penalty after 14d; expire-sweep cron to flip `is_active=false`.
28. **Dead-link checker**: nightly HEAD request on `apply_url`; demote/expire 404s (huge trust win).
29. **Ingest dedup v2**: simhash/minhash on title+description (the current dedup is field-equality based; reposts slip through).
30. **JD enrichment at ingest**: one LLM pass to extract `skills_required`, seniority, CTC band, remote flag where the source lacks them — match quality is capped by JD structure today.
31. **Per-career-path scrape budgets** + spend ledger so auto-ingest can't burn the Apify plan.
32. **Recruiter-posted jobs parity**: same enrichment + embedding path as scraped jobs (today they skip some normalization).

## E. Matching & ranking

33. 🔥 **Learned re-ranker from behavior**: log impressions/clicks/saves/intro-requests per (candidate, job) into `match_feedback`; train a simple logistic/LambdaMART re-ranker weekly. Data capture should start NOW.
34. **Skill-graph similarity**: relate skills ("FastAPI"~"Django"~"Python backend") via an embedding-based skill graph instead of exact lexical overlap — biggest quality jump for sparse CVs.
35. **Title normalization service** shared by parser, ingest, and matcher (one canonical title taxonomy; today three heuristics disagree).
36. **Two-sided CTC modeling**: infer missing job CTC bands from title+city+company-size priors instead of treating unknown as neutral.
37. **Negative preferences**: let Aarya record "not interested in X" (company/industry/title) and hard-filter — repeated bad matches erode trust fastest.
38. **Explainable score breakdown endpoint** (`/matches/{id}/why`) returning per-component contributions for the UI and for debugging relevance complaints.
39. **Diversity guarantee in feed**: cap max 2 jobs per company on the first screen (MMR helps but doesn't guarantee).
40. **Cold-start pack**: for brand-new candidates with thin profiles, blend popularity (saves/intro-rates) until personal signal exists.

## F. Resume generation / application kit

41. **Template system for tailored PDFs**: 2–3 ATS-safe layouts with a selector; today one hardcoded layout.
42. **Fact-guard on generation**: validate generated résumé bullet claims against parsed source data; flag/refuse invented employers, dates, metrics (truthfulness guarantee).
43. **JD-keyword coverage report** with each tailored résumé ("covers 14/18 JD keywords") — demo-friendly and useful.
44. **Async kit generation with progress events** (SSE) instead of poll loops in the UI.

## G. Agents (Aarya/Nitya) & memory

45. **Tool-call streaming events to UI** — surface "Searching jobs… → Scoring → Drafting" steps live (uses existing `agent_actions`), which *feels* faster even at equal latency.
46. **Memory summarization budget**: cap `aarya_state.change_log` and re-summarize memory when >200 words (currently unbounded growth except log slice).
47. **Nitya retry/poison-queue**: failed intro-processing tasks currently log and drop; add `retry_count` + dead-letter status so no intro silently dies.

## H. Infra, reliability & safety

48. **Per-user rate limits** on LLM-spending endpoints (chat, generate, tailor): e.g. 30 chat turns/hr — protects demo from cost blowups and abuse (slowapi or Postgres token bucket).
49. **Backpressure + queue for background jobs**: replace ad-hoc `BackgroundTasks` with a Postgres job table + worker loop (visibility, retries, graceful deploys); arq/RQ-style without new infra.
50. **Nightly pg_dump retention + restore runbook** — you've reset the DB twice; before real candidates arrive, automated backups and a tested restore path are non-negotiable.

---

## Suggested sequencing
- **Before demo (cheap, visible):** #2 #3 #10 #11 #45 (perceived speed) + #28 (no dead links in the demo feed).
- **Week 1 after:** #1 #16 #21 #26 #33-data-capture #48.
- **Month 1:** #20 #24 #34 #35 #41 #42 #49 #50.
