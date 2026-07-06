"""
Embedding service — generates 1536-dim vectors via OpenAI-compatible API.

Uses OpenRouter's text-embedding-3-small endpoint (same API contract as OpenAI).
All embeddings are stored in Postgres and indexed with pgvector HNSW for
cosine similarity search.

Embedding targets:
  candidates   → candidate_embeddings (profile_embedding, skills_embedding, resume_embedding)
  jobs         → job_embeddings       (jd_embedding, title_embedding, skills_embedding)

Called by:
  - ResumeParserService.apply_to_profile() → embed candidate after profile update
  - JobIngester.ingest()                   → embed all newly inserted/updated jobs
  - Nightly pg_cron re-embedding job       → keep vectors fresh
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import httpx
import structlog

logger = structlog.get_logger()

_EMBEDDING_MODEL = "openai/text-embedding-3-small"  # via OpenRouter
_EMBEDDING_DIM = 1536
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_BATCH_SIZE = 20  # max texts per API call (rate-limit headroom)
_MAX_CHARS = 8_000  # truncate at 8k chars (~2k tokens) before embedding


def _truncate(text: str | None, max_chars: int = _MAX_CHARS) -> str:
    """Truncate text to avoid exceeding embedding model context window."""
    if not text:
        return ""
    return text[:max_chars]


def _format_vector(vector: list[float]) -> str:
    """Return a pgvector literal accepted by asyncpg for `$n::vector` params."""
    return "[" + ",".join(str(float(v)) for v in vector) + "]"


class EmbeddingService:
    """
    Generates text embeddings and upserts them into Postgres.

    Usage:
        svc = EmbeddingService(openrouter_api_key, db)
        await svc.embed_candidate(candidate_id)
        await svc.embed_job(job_id)
    """

    def __init__(self, api_key: str, db: asyncpg.Connection) -> None:
        self._api_key = api_key
        self._db = db
        self._http = httpx.AsyncClient(
            base_url=_OPENROUTER_BASE,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://hireloop.in",
                "X-Title": "Hireloop Embeddings",
            },
            timeout=60.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    # ── Core embedding call ───────────────────────────────────────────────────

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Call the embedding API for a batch of texts.
        Returns a list of float vectors in the same order as input.
        Raises httpx.HTTPStatusError on API failure.
        """
        if not texts:
            return []

        # Truncate each text to stay within token limits
        safe_texts = [_truncate(t) or " " for t in texts]  # never send empty string

        response = await self._http.post(
            "/embeddings",
            json={"model": _EMBEDDING_MODEL, "input": safe_texts},
        )
        response.raise_for_status()
        data = response.json()

        # API returns items sorted by index
        items: list[dict[str, Any]] = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    async def _embed_single(self, text: str) -> list[float]:
        """Embed a single text string. Returns empty list on error."""
        try:
            results = await self._embed_texts([text])
            return results[0] if results else []
        except Exception as exc:
            logger.warning("embed_single_failed", error=str(exc))
            return []

    # ── Candidate embedding ───────────────────────────────────────────────────

    async def embed_candidate(self, candidate_id: str) -> bool:
        """
        Read the candidate's profile from DB, generate 3 embeddings,
        and upsert into candidate_embeddings.
        Returns True on success.
        """
        row = await self._db.fetchrow(
            """
            SELECT
                c.id,
                u.full_name,
                c.headline,
                c.summary,
                c.current_title,
                c.current_company,
                c.location_city,
                c.location_state,
                c.years_experience,
                c.expected_ctc_min,
                c.expected_ctc_max,
                c.skills,
                r.raw_text   AS resume_text
            FROM public.candidates c
            JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
            LEFT JOIN public.resumes r
                ON r.candidate_id = c.id
                AND r.is_primary = TRUE
            WHERE c.id = $1::uuid AND c.deleted_at IS NULL
            """,
            candidate_id,
        )

        if not row:
            logger.warning("embed_candidate_not_found", candidate_id=candidate_id)
            return False

        # Build text representations for each embedding type
        skills_list: list[str] = list(row["skills"] or [])

        location_parts = [row["location_city"], row["location_state"], "India"]
        location_text = ", ".join([p for p in location_parts if p])

        profile_text = " | ".join(
            filter(
                None,
                [
                    row["headline"] or None,
                    (
                        " @ ".join([p for p in [row["current_title"], row["current_company"]] if p])
                        if (row["current_title"] or row["current_company"])
                        else None
                    ),
                    row["summary"] or None,
                    f"Experience: {row['years_experience']} years"
                    if row["years_experience"]
                    else None,
                    f"Location: {location_text}" if location_text else None,
                    (
                        f"Expected CTC: {row['expected_ctc_min']}-{row['expected_ctc_max']} INR"
                        if (row["expected_ctc_min"] or row["expected_ctc_max"])
                        else None
                    ),
                ],
            )
        )
        skills_text = " ".join(skills_list)
        resume_text = row["resume_text"] or ""

        try:
            # Batch all three embeddings in parallel
            profile_emb, skills_emb, resume_emb = await asyncio.gather(
                self._embed_single(profile_text or "candidate profile"),
                self._embed_single(skills_text or "general skills"),
                self._embed_single(resume_text or profile_text or "resume"),
            )

            if not profile_emb:
                logger.warning("embed_candidate_empty_result", candidate_id=candidate_id)
                return False

            await self._db.execute(
                """
                INSERT INTO public.candidate_embeddings
                    (
                        candidate_id,
                        profile_embedding,
                        skills_embedding,
                        resume_embedding,
                        updated_at
                    )
                VALUES ($1::uuid, $2::vector, $3::vector, $4::vector, NOW())
                ON CONFLICT (candidate_id) DO UPDATE SET
                    profile_embedding = EXCLUDED.profile_embedding,
                    skills_embedding  = EXCLUDED.skills_embedding,
                    resume_embedding  = EXCLUDED.resume_embedding,
                    updated_at        = NOW()
                """,
                candidate_id,
                _format_vector(profile_emb),
                _format_vector(skills_emb or profile_emb),  # fallback to profile if no skills
                _format_vector(resume_emb or profile_emb),
            )

            logger.info("embed_candidate_done", candidate_id=candidate_id)
            return True

        except Exception as exc:
            logger.error("embed_candidate_failed", candidate_id=candidate_id, error=str(exc))
            return False

    # ── Job embedding ─────────────────────────────────────────────────────────

    async def embed_job(self, job_id: str) -> bool:
        """
        Read a single job from DB, generate 3 embeddings,
        and upsert into job_embeddings.
        Returns True on success. Never raises — every failure path returns False
        with a logged reason, so a batch can't silently drop jobs.
        """
        try:
            row = await self._db.fetchrow(
                """
                SELECT id, title, description, requirements, skills_required
                FROM public.jobs
                WHERE id = $1::uuid
                  AND is_active = TRUE
                  AND deleted_at IS NULL
                """,
                job_id,
            )

            if not row:
                logger.warning("embed_job_not_found", job_id=job_id)
                return False

            skills_list: list[str] = list(row["skills_required"] or [])
            jd_text = " ".join(filter(None, [row["description"], row["requirements"]]))
            skills_text = " ".join(skills_list)

            jd_emb, title_emb, skills_emb = await asyncio.gather(
                self._embed_single(jd_text or row["title"]),
                self._embed_single(row["title"]),
                self._embed_single(skills_text or row["title"]),
            )

            if not jd_emb:
                logger.warning("embed_job_empty_result", job_id=job_id)
                return False

            await self._db.execute(
                """
                INSERT INTO public.job_embeddings
                    (job_id, jd_embedding, title_embedding, skills_embedding, updated_at)
                VALUES ($1::uuid, $2::vector, $3::vector, $4::vector, NOW())
                ON CONFLICT (job_id) DO UPDATE SET
                    jd_embedding     = EXCLUDED.jd_embedding,
                    title_embedding  = EXCLUDED.title_embedding,
                    skills_embedding = EXCLUDED.skills_embedding,
                    updated_at       = NOW()
                """,
                job_id,
                _format_vector(jd_emb),
                _format_vector(title_emb or jd_emb),
                _format_vector(skills_emb or jd_emb),
            )

            logger.info("embed_job_done", job_id=job_id)
            return True

        except Exception as exc:
            logger.error("embed_job_failed", job_id=job_id, error=str(exc))
            return False

    # ── Batch helpers ─────────────────────────────────────────────────────────

    async def embed_jobs_batch(self, job_ids: list[str]) -> dict[str, bool]:
        """
        Embed multiple jobs, one at a time. Returns {job_id: success_bool}.

        NOTE: these calls are deliberately sequential. ``embed_job`` issues DB
        reads/writes on this service's single asyncpg connection, and a connection
        cannot run concurrent queries — gathering them used to make ~all-but-a-few
        fail with "another operation is in progress", which (because the failure
        surfaced from a query outside ``embed_job``'s try) was swallowed silently
        and left most jobs un-embedded. Per-job HTTP latency is hidden by the three
        concurrent ``_embed_single`` calls inside each ``embed_job``.
        """
        results: dict[str, bool] = {}
        for jid in job_ids:
            results[jid] = await self.embed_job(jid)
        return results

    async def embed_all_pending_jobs(self) -> tuple[int, int]:
        """
        Embed all active jobs that don't yet have embeddings.
        Returns (embedded_count, failed_count).
        """
        rows = await self._db.fetch(
            """
            SELECT j.id FROM public.jobs j
            LEFT JOIN public.job_embeddings je ON je.job_id = j.id
            WHERE j.is_active = TRUE
              AND j.deleted_at IS NULL
              AND je.job_id IS NULL
            ORDER BY j.scraped_at DESC
            LIMIT 500
            """
        )

        if not rows:
            return 0, 0

        job_ids = [str(r["id"]) for r in rows]
        results = await self.embed_jobs_batch(job_ids)

        success = sum(1 for v in results.values() if v)
        failed = len(results) - success
        logger.info("embed_pending_jobs_done", success=success, failed=failed)
        return success, failed

    async def embed_all_pending_candidates(self) -> tuple[int, int]:
        """
        Embed all candidates who have a resume but no embeddings yet.
        Returns (embedded_count, failed_count).
        """
        rows = await self._db.fetch(
            """
            SELECT c.id FROM public.candidates c
            LEFT JOIN public.candidate_embeddings ce ON ce.candidate_id = c.id
            WHERE c.deleted_at IS NULL
              AND ce.candidate_id IS NULL
            ORDER BY c.updated_at DESC
            LIMIT 200
            """
        )

        if not rows:
            return 0, 0

        success = failed = 0
        for r in rows:
            ok = await self.embed_candidate(str(r["id"]))
            if ok:
                success += 1
            else:
                failed += 1

        logger.info("embed_pending_candidates_done", success=success, failed=failed)
        return success, failed


async def embed_pending_and_score_candidate(
    db: asyncpg.Connection,
    settings: Any,
    candidate_id: str,
    *,
    limit: int = 500,
) -> tuple[int, int]:
    """
    Embed active jobs missing vectors, then score the candidate against them.

    Ingested Apify/Fantastic jobs are unusable for ranking until embedded — this
    is the bridge between scrape and a populated match feed.
    Returns (jobs_embedded, pairs_scored).
    """
    from hireloop_api.services.matching import MatchingEngine

    svc = EmbeddingService(api_key=settings.openrouter_api_key, db=db)
    try:
        embedded, _failed = await svc.embed_all_pending_jobs()
    finally:
        await svc.close()

    engine = MatchingEngine(db)
    scored = await engine.score_candidate(candidate_id, limit=limit)
    return embedded, scored


async def run_job_embedding(settings: Any, job_id: str) -> None:
    """
    Fire-and-forget (re)embedding of a single job on its own pooled connection.
    Used after a recruiter publishes a role into the jobs feed so it can rank in
    the candidate match feed. Never raises.
    """
    from hireloop_api.deps import get_db_pool

    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as db:
            svc = EmbeddingService(settings.openrouter_api_key, db)
            try:
                await svc.embed_job(job_id)
            finally:
                await svc.close()
    except Exception as exc:  # background task — never propagate
        logger.warning("job_embedding_bg_failed", job_id=job_id, error=str(exc))
