"""
Nitya agent tools — recruiter/HM-side deterministic functions.

Tool catalogue:
  - lookup_candidate     : read candidate profile for context
  - lookup_job           : read job details
  - enrich_hiring_manager: trigger HM enrichment waterfall (Apify + NeverBounce)
  - draft_intro_email    : LLM-generated email from candidate POV (shown as preview)
  - send_intro_email     : send via candidate's Gmail OAuth (R9 — NEVER SendGrid)
  - update_intro_status  : update intro_requests.status in DB
  - lookup_intro_request : fetch full intro_request context

Each tool writes to agent_actions (R7 counter pattern).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger()


async def _write_action(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    action_type: str,
    payload: dict,
    result: dict,
    duration_ms: int | None = None,
) -> None:
    """Write agent_action row for Nitya (R7 counter pattern)."""
    await db.execute(
        """
        INSERT INTO public.agent_actions
          (agent, user_id, session_id, action_type, payload, result, duration_ms)
        VALUES ('nitya', $1::uuid, $2::uuid, $3, $4::jsonb, $5::jsonb, $6)
        """,
        user_id,
        session_id,
        action_type,
        json.dumps(payload),
        json.dumps(result),
        duration_ms,
    )


async def lookup_intro_request(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    intro_id: str,
) -> dict[str, Any]:
    """Fetch full intro_request + related candidate + job + HM context."""
    import time

    t0 = time.monotonic()

    row = await db.fetchrow(
        """
        SELECT
            ir.id, ir.status, ir.created_at,
            -- Candidate
            c.id AS candidate_id,
            u.full_name AS candidate_name,
            u.email AS candidate_email,
            c.headline, c.summary, c.current_title, c.current_company,
            c.skills, c.years_experience,
            -- Job
            j.id AS job_id, j.title AS job_title, j.description AS job_desc,
            j.seniority, j.ctc_min, j.ctc_max,
            co.name AS company_name,
            -- Hiring manager
            hm.id AS hm_id, hm.full_name AS hm_name, hm.title AS hm_title,
            hm.email AS hm_email, hm.email_verified,
            hm.linkedin_url AS hm_linkedin,
            hm.enrich_status
        FROM public.intro_requests ir
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users u ON u.id = c.user_id
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        JOIN public.hiring_managers hm ON hm.id = ir.hiring_manager_id
        WHERE ir.id = $1::uuid
        """,
        uuid.UUID(intro_id),
    )

    result = dict(row) if row else {"error": "Intro request not found"}
    if row:
        result["id"] = str(result["id"])
        result["candidate_id"] = str(result["candidate_id"])
        result["job_id"] = str(result["job_id"])
        result["hm_id"] = str(result["hm_id"])
        result["created_at"] = result["created_at"].isoformat()
        result["skills"] = list(result.get("skills") or [])

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        user_id,
        session_id,
        "lookup_intro_request",
        {"intro_id": intro_id},
        {"found": bool(row)},
        duration_ms,
    )
    return result


async def enrich_hiring_manager(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    hm_id: str,
    apify_token: str,
    neverbounce_api_key: str,
) -> dict[str, Any]:
    """Trigger HM enrichment waterfall (Apify + NeverBounce)."""
    import time

    from hireloop_api.services.apify.hm_enricher import HMEnricher

    t0 = time.monotonic()

    # Mark intro as enriching
    await db.execute(
        """
        UPDATE public.intro_requests
        SET status = 'enriching', updated_at = NOW()
        WHERE hiring_manager_id = $1::uuid AND status = 'pending'
        """,
        uuid.UUID(hm_id),
    )

    enricher = HMEnricher(apify_token=apify_token, neverbounce_api_key=neverbounce_api_key, db=db)
    try:
        result = await enricher.enrich(hm_id)
    finally:
        await enricher.close()

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db, user_id, session_id, "enrich_hiring_manager", {"hm_id": hm_id}, result, duration_ms
    )
    return result


async def draft_intro_email(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    intro_id: str,
    intro_context: dict,
    llm_client: Any,
) -> dict[str, Any]:
    """
    Use the LLM to draft a personalised intro email.
    The email is written from the candidate's first-person POV.
    Stored as draft_email on the intro_request row.
    """
    import time

    from langchain_core.messages import HumanMessage, SystemMessage

    t0 = time.monotonic()

    candidate_name = intro_context.get("candidate_name", "The candidate")
    job_title = intro_context.get("job_title", "the role")
    company_name = intro_context.get("company_name", "your company")
    hm_name = intro_context.get("hm_name", "Hiring Manager")
    hm_title = intro_context.get("hm_title", "")
    headline = intro_context.get("headline", "")
    summary = intro_context.get("summary", "")
    skills = intro_context.get("skills", [])
    years_exp = intro_context.get("years_experience", "")

    skills_str = ", ".join(skills[:8]) if skills else "various technologies"

    system = SystemMessage(
        content="""You are Nitya, Hireloop's recruiter AI.
Draft a warm, personalised cold intro email from the candidate to the hiring manager.
The email must:
- Be 3-4 short paragraphs max
- Sound human and genuine, NOT like a template
- Mention a specific reason why this company/role is interesting
- Reference 2-3 specific skills/experiences that match the role
- End with a clear, low-pressure ask (30-min chat)
- Subject line: concise, compelling, personalised

Return ONLY valid JSON with keys: subject, body_html, body_text
body_html should have basic <p> tags. body_text is plain text.
"""
    )

    human = HumanMessage(
        content=f"""
Draft an intro email with these details:

Candidate: {candidate_name}
Headline: {headline}
Summary: {summary[:400] if summary else "N/A"}
Key skills: {skills_str}
Experience: {years_exp} years

Role: {job_title} at {company_name}
Hiring Manager: {hm_name}{f", {hm_title}" if hm_title else ""}

Make it feel like the candidate wrote it themselves after researching the company.
"""
    )

    result: dict[str, Any] = {}
    try:
        response = await llm_client.ainvoke([system, human])
        raw = response.content.strip()

        # Strip markdown code fence if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        import json as _json

        draft = _json.loads(raw)
        result = {
            "subject": draft.get("subject", f"Intro: {candidate_name} for {job_title}"),
            "body_html": draft.get("body_html", ""),
            "body_text": draft.get("body_text", ""),
        }

        # Save draft to intro_requests
        await db.execute(
            """
            UPDATE public.intro_requests
            SET draft_email = $1, status = 'draft_ready', updated_at = NOW()
            WHERE id = $2::uuid
            """,
            json.dumps(result),
            uuid.UUID(intro_id),
        )

    except Exception as exc:
        logger.error("draft_email_failed", intro_id=intro_id, error=str(exc))
        result = {"error": str(exc)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        user_id,
        session_id,
        "draft_intro_email",
        {"intro_id": intro_id},
        {"drafted": "subject" in result},
        duration_ms,
    )
    return result


async def send_intro_email(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    intro_id: str,
    candidate_id: str,
    hm_email: str,
    hm_name: str,
    subject: str,
    body_html: str,
    body_text: str,
    google_client_id: str,
    google_client_secret: str,
) -> dict[str, Any]:
    """
    Send the drafted intro email via the candidate's Gmail OAuth token (R9).
    Updates intro_request status to 'sent' on success.
    """
    import time

    from hireloop_api.services.email.gmail_oauth import GmailOAuthService

    t0 = time.monotonic()

    svc = GmailOAuthService(
        google_client_id=google_client_id,
        google_client_secret=google_client_secret,
        db=db,
    )
    try:
        success, msg_id_or_error = await svc.send_intro_email(
            candidate_id=candidate_id,
            to_email=hm_email,
            to_name=hm_name,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
        )
    finally:
        await svc.close()

    if success:
        send_info = msg_id_or_error if isinstance(msg_id_or_error, dict) else {}
        await db.execute(
            """
            UPDATE public.intro_requests
            SET status = 'sent', sent_at = NOW(), updated_at = NOW(),
                gmail_message_id = $2, gmail_thread_id = $3, gmail_subject = $4
            WHERE id = $1::uuid
            """,
            uuid.UUID(intro_id),
            send_info.get("id"),
            send_info.get("threadId"),
            subject[:300],
        )
        result: dict[str, Any] = {
            "sent": True,
            "gmail_message_id": send_info.get("id"),
            "intro_status": "sent",
        }
        logger.info("intro_email_sent", intro_id=intro_id, to=hm_email)
        from hireloop_api.config import get_settings
        from hireloop_api.services.notifications import notify_intro_status_email

        await notify_intro_status_email(
            db,
            get_settings(),
            intro_id=intro_id,
            status="sent",
        )
    else:
        await db.execute(
            """
            UPDATE public.intro_requests
            SET error_message = $1, updated_at = NOW()
            WHERE id = $2::uuid
            """,
            str(msg_id_or_error),
            uuid.UUID(intro_id),
        )
        result = {"sent": False, "error": str(msg_id_or_error)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        user_id,
        session_id,
        "send_intro_email",
        {"intro_id": intro_id, "to": hm_email},
        {"sent": success},
        duration_ms,
    )
    return result


async def update_intro_status(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    intro_id: str,
    new_status: str,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Update an intro_request's status field."""
    import time

    t0 = time.monotonic()

    await db.execute(
        """
        UPDATE public.intro_requests
        SET status = $1,
            error_message = COALESCE($2, error_message),
            updated_at = NOW()
        WHERE id = $3::uuid
        """,
        new_status,
        error_message,
        uuid.UUID(intro_id),
    )

    result = {"intro_id": intro_id, "status": new_status}
    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        user_id,
        session_id,
        "update_intro_status",
        {"intro_id": intro_id, "new_status": new_status},
        result,
        duration_ms,
    )
    return result
