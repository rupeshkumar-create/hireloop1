# Hireschema system bible presentation — design

**Date:** 2026-07-15  
**Status:** Approved · Implemented  
**Audience:** Boss / leadership — read for a clear picture of the whole product  
**Format goals:** Full system bible · minimal text · large diagrams · dual deliverable

## Goals

1. One unified deck that explains **the whole app**: product, candidate side, recruiter side, agents, backend, and how parts connect.
2. Visual-first: large diagrams, short labels, few bullets (style **C** from briefing).
3. Dual delivery:
   - **A)** Self-contained HTML slide deck (browser preview + print-to-PDF CSS)
   - **B)** Markdown twin with Mermaid diagrams (Pandoc-friendly PDF source)
4. Accurate to the codebase and to the already-approved vendor corrections in `2026-07-13-leadership-decks-v2-design.md`.
5. Distinct from the three v2 decks (business / candidate / recruiter): this is the **single system bible** that ties all three together.

## Non-goals

- Replacing `docs/presentations/v2/` (keep those as role-focused decks)
- Interactive product demo / live API calls
- Deep algorithm whitepaper beyond one match-scoring diagram
- Inventing roadmap commitments beyond what PHASE_TRACKER / readiness docs state

## Vendor truth (slides)

| Use | Vendor |
|-----|--------|
| Auth / DB / Realtime / Storage | Supabase (Postgres 15, pgvector, RLS) |
| Marketing + SPA hosting | Vercel (Next.js 15) |
| API | FastAPI on Railway (AWS ECS ap-south-1 target) |
| Edge / WAF | Cloudflare planned; not claimed as live |
| LLM + embeddings gateway | OpenRouter — primary `anthropic/claude-sonnet-4.6`, fast `google/gemini-2.5-flash`, embeddings `openai/text-embedding-3-small` (1536-d, HNSW, cosine) |
| Agents | LangGraph single-threaded master loop |
| Voice STT / TTS | Deepgram Nova-3 / Aura |
| Job scrape | Apify (Google Jobs actor path per v2 truth) |
| JD / page extract | Firecrawl |
| Resume parse | In-app parser (Affinda not on active slide stack) |
| Transactional email | **Resend** |
| Cold HM intro email | Candidate **Gmail OAuth** only (never transactional provider) |
| Client state | Zustand; chat also SSE |

Do **not** put MSG91, SendGrid, or NeverBounce on slides unless tagged “planned / not active,” and prefer omitting them for boss clarity (aligned with v2 decks).

## Deliverables

| File | Purpose |
|------|---------|
| `docs/presentations/system-bible/index.html` | Full HTML deck (keyboard nav, print CSS) |
| `docs/presentations/system-bible/styles.css` | Diagram-first, light corporate look |
| `docs/presentations/system-bible/deck.js` | Slide nav, print helper |
| `docs/presentations/system-bible/README.md` | How to open, export PDF (browser print), Pandoc note |
| `docs/presentations/system-bible/Hireschema-System-Bible.md` | Markdown + Mermaid twin for Pandoc |
| Optional | `Hireschema-System-Bible.pdf` if local headless Chrome / Pandoc available |

## Visual direction

- Light background, Hireschema brand as hero signal on title slide
- Large connected diagrams (monorepo, E2E architecture, intro handshake, agent loops)
- Minimal bullets (≈3–5 short lines max per slide; diagrams carry the story)
- Avoid: purple neon AI aesthetic, dense wall-of-text, card grids in hero slides
- Print: `@media print` / landscape slide pages so browser “Save as PDF” works

## Slide outline (16)

1. **Title** — Hireschema: system bible  
2. **Product at a glance** — India marketplace; candidate + recruiter; Aarya + Nitya  
3. **Monorepo map** — `web` / `app` / `api` / `supabase`  
4. **Tech stack layers** — one layered diagram (UI → API → Agents → Data → Vendors)  
5. **End-to-end architecture** — how surfaces connect to API, agents, DB, vendors  
6. **Candidate journey** — signup → profile → match → intro / apply (flow diagram)  
7. **Recruiter journey** — brief → publish → consented search → pipeline (flow diagram)  
8. **Aarya** — purpose, master loop, tool inventory (diagram + short tool list)  
9. **Nitya** — purpose, LISTEN/NOTIFY wake, intro pipeline tools  
10. **How agents connect** — DB-only intro handshake (hero diagram; no agent RPC)  
11. **Matching & embeddings** — vectors → scores → feed; weight summary  
12. **Voice = chat** — Deepgram STT → same Aarya path → TTS  
13. **Key data model** — core tables as a relationship sketch  
14. **Compliance & hard rules** — DPDP, Gmail-only cold mail, India lock, consent default-off  
15. **Build status** — scaffolded vs key-gated vs deferred (candid)  
16. **Takeaways** — what to remember in 5 lines

## Content rules

- Separate candidate vs recruiter clearly (slides 6–7 and agents 8–9).
- Stress **R5**: Aarya and Nitya never call each other; `intro_requests` + Postgres notify + `approve-send` is the bridge.
- Name real tools: Aarya (`profile_read`, `job_search`, `get_match_score`, `request_intro`, …); Nitya (`lookup_intro_request`, `enrich_hiring_manager`, `draft_intro_email`, `send_intro_email`, `update_intro_status`).
- Match scoring weights (for diagram labels): skills 0.40 · profile emb 0.30 · experience 0.15 · location 0.10 · CTC 0.05.
- India-only rules called out once (market `IN`, INR/LPA, job visibility).
- Status slide stays honest: code largely present; E2E depends on live keys; payments deferred.

## Preview / companion

- Serve `docs/presentations/system-bible/` locally and open in browser companion for visual QA of diagrams before finalizing PDF export instructions.

## Acceptance criteria

- [ ] Boss can answer: what the product is, who uses which side, what stack we use  
- [ ] Boss can explain how Aarya and Nitya differ and how they connect via DB  
- [ ] HTML opens offline (relative CSS/JS) and Print → PDF produces readable landscape slides  
- [ ] Markdown opens with Mermaid rendering (or Pandoc) and mirrors the same 16 sections  
- [ ] Vendor truth matches this spec (Resend / Gmail / OpenRouter / Apify / Firecrawl / Deepgram / Supabase / Vercel)

## Implementation note (after approval)

Build HTML + CSS diagrams first; mirror into Markdown Mermaid; verify in browser; document PDF export steps in README. Commit only when requested.
