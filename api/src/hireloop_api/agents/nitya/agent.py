"""
Nitya — recruiter/HM-facing AI agent.

Architecture:
  Nitya wakes via Postgres LISTEN/NOTIFY on the 'intro_requests' channel (R5).
  It does NOT have a persistent HTTP endpoint — it's a background worker.

  Wake flow:
    1. asyncpg LISTEN on 'intro_requests' channel
    2. NOTIFY payload: {id, candidate_id, job_id, hm_id}
    3. Nitya runs the intro handshake pipeline:
         a. lookup_intro_request   — get full context
         b. enrich_hiring_manager  — Apify waterfall → verified email
         c. Check Gmail token      — abort if candidate has no Gmail connected
         d. draft_intro_email      — LLM generates personalised cold email
         e. send_intro_email       — fire via candidate's Gmail OAuth
         f. update_intro_status    — mark as 'sent'

  State is NOT persisted via LangGraph (Nitya is stateless per intro).
  Error handling: any failure → status = 'failed', error_message logged.

  NEVER uses SendGrid for intro emails (R9 / R16 §2).
  NEVER calls Aarya directly (R5 — DB-only comms).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg
import structlog
from langchain_openai import ChatOpenAI

from hireloop_api.agents.nitya import tools as nitya_tools
from hireloop_api.config import Settings

logger = structlog.get_logger()


# ── System prompt ─────────────────────────────────────────────────────────────

NITYA_SYSTEM_PROMPT = """You are Nitya, Hireschema's AI that helps candidates get warm \
intros to hiring managers.

Your sole job when activated is to:
1. Read the full intro context (candidate profile + job + hiring manager)
2. Check the HM has a verified email (enrich if needed)
3. Draft a warm, personalised intro email from the candidate's POV
4. Send via the candidate's Gmail (never via SendGrid or your own email)

Rules you NEVER break:
- Never send without a verified HM email
- Never send if candidate has no Gmail token connected
- Never impersonate anyone — the email is FROM the candidate, signed by the candidate
- Always write the email as if the candidate wrote it themselves
- Keep emails short: 3-4 paragraphs max
- End every email with a low-pressure call-to-action: a quick 30-min chat
"""


# ── Intro handshake pipeline ──────────────────────────────────────────────────


class NityaIntroHandler:
    """
    Handles a single intro_request through the full pipeline.
    Instantiated once per NOTIFY event.
    """

    def __init__(
        self,
        settings: Settings,
        db: asyncpg.Connection,
    ) -> None:
        self._settings = settings
        self._db = db
        self._llm = ChatOpenAI(
            model=settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.5,
            max_tokens=2048,
            default_headers={
                "HTTP-Referer": "https://hireschema.com",
                "X-Title": "Hireschema - Nitya Recruiter AI",
            },
        )

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Full intro handshake from raw NOTIFY payload.
        Returns a result dict with status and any error details.
        """
        intro_id = str(payload.get("id", ""))
        hm_id = str(payload.get("hm_id", ""))
        # user_id is not in the NOTIFY payload — we fetch it from the intro
        session_id = intro_id  # use intro_id as the Nitya "session" for action logging

        if not intro_id:
            logger.error("nitya_missing_intro_id", payload=payload)
            return {"error": "Missing intro_id in payload"}

        # Nitya only drives the HM cold-email pipeline (enrich → draft → Gmail send).
        # The other intro flows are fully DB-driven and progressed elsewhere:
        #   • candidate_to_recruiter — the recruiter acts from their in-app inbox
        #     (status 'pending'), or the invite email already went out at creation
        #     (status 'invited').
        #   • recruiter_to_candidate — the candidate acts from their inbox.
        # Running the HM pipeline on these would enrich an empty hm_id and wrongly
        # decline a valid request, so Nitya stays out of the way.
        direction = str(payload.get("direction") or "candidate_to_hm")
        if direction != "candidate_to_hm":
            logger.info("nitya_intro_in_app_noop", intro_id=intro_id, direction=direction)
            return {"intro_id": intro_id, "direction": direction, "skipped": "in_app_flow"}

        logger.info("nitya_handling_intro", intro_id=intro_id)

        # ── Step 1: Fetch full context ────────────────────────────────────────
        context = await nitya_tools.lookup_intro_request(
            db=self._db,
            user_id="00000000-0000-0000-0000-000000000000",  # system user_id for logging
            session_id=session_id,
            intro_id=intro_id,
        )

        if "error" in context:
            logger.error("nitya_context_failed", intro_id=intro_id, **context)
            return context

        user_id = context.get("candidate_id", "")
        candidate_id = context.get("candidate_id", "")
        hm_email = context.get("hm_email")
        hm_verified = context.get("email_verified", False)
        enrich_status = context.get("enrich_status", "pending")

        # ── Step 2: Enrich HM if needed ───────────────────────────────────────
        if not hm_email or not hm_verified or enrich_status != "done":
            logger.info("nitya_enriching_hm", hm_id=hm_id)
            await nitya_tools.enrich_hiring_manager(
                db=self._db,
                user_id=user_id,
                session_id=session_id,
                hm_id=hm_id,
                apify_token=self._settings.apify_token,
                neverbounce_api_key=self._settings.neverbounce_api_key,
            )

            # Re-fetch context with fresh email
            context = await nitya_tools.lookup_intro_request(
                db=self._db,
                user_id=user_id,
                session_id=session_id,
                intro_id=intro_id,
            )
            hm_email = context.get("hm_email")
            hm_verified = context.get("email_verified", False)

        if not hm_email or not hm_verified:
            msg = "Could not obtain verified HM email — intro failed (retryable)"
            await nitya_tools.update_intro_status(
                db=self._db,
                user_id=user_id,
                session_id=session_id,
                intro_id=intro_id,
                new_status="failed",
                error_message=msg,
            )
            logger.warning("nitya_no_verified_email", intro_id=intro_id, hm_id=hm_id)
            return {"error": msg, "intro_id": intro_id, "retryable": True}

        # ── Step 3: Draft the intro email (candidate approves + sends via Gmail) ─
        draft = await nitya_tools.draft_intro_email(
            db=self._db,
            user_id=user_id,
            session_id=session_id,
            intro_id=intro_id,
            intro_context=context,
            llm_client=self._llm,
        )

        if "error" in draft:
            await nitya_tools.update_intro_status(
                db=self._db,
                user_id=user_id,
                session_id=session_id,
                intro_id=intro_id,
                new_status="failed",
                error_message=draft["error"],
            )
            return {**draft, "retryable": True}

        from hireloop_api.services.email.gmail_oauth import GmailOAuthService

        gmail_svc = GmailOAuthService(
            google_client_id=self._settings.google_client_id,
            google_client_secret=self._settings.google_client_secret,
            db=self._db,
        )
        has_gmail = await gmail_svc.has_token(candidate_id)
        await gmail_svc.close()

        if not has_gmail:
            logger.info(
                "nitya_draft_ready_awaiting_gmail",
                intro_id=intro_id,
                candidate_id=candidate_id,
            )
            return {
                "intro_id": intro_id,
                "draft_ready": True,
                "gmail_required": True,
                "subject": draft.get("subject"),
                "message": (
                    "Draft ready — connect Google in Profile, then approve send from your inbox."
                ),
            }

        return {
            "intro_id": intro_id,
            "draft_ready": True,
            "subject": draft.get("subject"),
            "message": "Draft ready — review in your inbox and send from your Gmail.",
        }

        # Send is triggered by POST /intros/{id}/approve-send after candidate preview.


# ── LISTEN/NOTIFY worker ──────────────────────────────────────────────────────


class NityaWorker:
    """
    Long-running background worker that LISTENs on the Postgres 'intro_requests'
    channel and dispatches each intro to NityaIntroHandler.

    Start this as a separate asyncio task in the FastAPI lifespan or as a
    standalone process (recommended for production).
    """

    def __init__(self, settings: Settings, db_dsn: str) -> None:
        self._settings = settings
        self._db_dsn = db_dsn
        self._running = False
        # Hold references to in-flight handler tasks so they aren't garbage-
        # collected mid-flight (a fire-and-forget task with no reference can be
        # cancelled by the GC before it finishes — dropping the intro silently).
        self._inflight: set[asyncio.Task] = set()

    async def start(self) -> None:
        """Connect to Postgres and start listening for intro_requests notifications."""
        self._running = True
        logger.info("nitya_worker_starting")

        while self._running:
            try:
                conn = await asyncpg.connect(self._db_dsn, statement_cache_size=0)
                try:
                    await conn.add_listener("intro_requests", self._on_notify)
                    logger.info("nitya_worker_listening")

                    # Keep connection alive with periodic pings
                    while self._running:
                        await asyncio.sleep(30)
                        await conn.execute("SELECT 1")  # keepalive

                finally:
                    await conn.remove_listener("intro_requests", self._on_notify)
                    await conn.close()

            except Exception as exc:
                logger.error("nitya_worker_error", error=str(exc))
                if self._running:
                    await asyncio.sleep(5)  # retry after 5s on connection failure

    def stop(self) -> None:
        self._running = False

    def _on_notify(
        self,
        conn: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Callback invoked by asyncpg when a NOTIFY arrives."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.error("nitya_invalid_notify_payload", raw=payload)
            return

        logger.info("nitya_intro_received", intro_id=data.get("id"))
        task = asyncio.create_task(self._handle_async(data))
        self._inflight.add(task)
        task.add_done_callback(self._inflight.discard)

    async def _handle_async(self, payload: dict) -> None:
        """Spawn a fresh DB connection and handle the intro in a dedicated task."""
        try:
            conn = await asyncpg.connect(self._db_dsn, statement_cache_size=0)
            try:
                intro_id = str(payload.get("id") or "")
                claimed = await conn.fetchval(
                    "SELECT pg_try_advisory_lock(hashtext($1))",
                    intro_id,
                )
                if not claimed:
                    logger.info("nitya_intro_already_claimed", intro_id=intro_id)
                    return
                handler = NityaIntroHandler(settings=self._settings, db=conn)
                result = await handler.handle(payload)
                logger.info("nitya_intro_handled", **result)
            finally:
                await conn.close()
        except Exception as exc:
            logger.error("nitya_handler_unhandled_error", error=str(exc), payload=payload)
