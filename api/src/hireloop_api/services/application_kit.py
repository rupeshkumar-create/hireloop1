"""
Application kit — save a job + generate apply assets (resume, cover letter, interview prep).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.market_db import fetch_candidate_market
from hireloop_api.markets import job_visible_for_market_sql
from hireloop_api.services.job_present import serialize_job_card
from hireloop_api.services.resume_tailor import generate_tailored_html, save_tailored_resume

logger = structlog.get_logger()

KIT_SYSTEM = """You prepare India job application assets for one candidate and one role.
Return ONLY valid JSON (no markdown fences):
{
  "cover_letter": "2-3 para formal cover letter; India context (LPA if relevant); truthful only",
  "interview_prep": "Markdown with ## Likely questions, ## STAR stories to rehearse,
   ## Role-specific talking points, ## Questions to ask the interviewer"
}
Never invent employers, degrees, or metrics the candidate does not have."""

# Application kits run two LLM jobs (text assets + resume HTML). Use the fast
# fallback model and a lower token cap — quality is fine for structured outputs.
_KIT_LLM_MAX_TOKENS_TEXT = 2048
_KIT_LLM_MAX_TOKENS_RESUME = 2048


def _kit_llm_model(settings: Settings) -> str:
    return settings.openrouter_fallback_model or settings.openrouter_primary_model


def _kit_llm(settings: Settings, *, max_tokens: int, title: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=_kit_llm_model(settings),
        openai_api_key=settings.openrouter_api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.35,
        max_tokens=max_tokens,
        default_headers={
            "HTTP-Referer": "https://app.hireloop.in",
            "X-Title": title,
        },
    )


def _fallback_cover_letter(profile: dict[str, Any], job: dict[str, Any]) -> str:
    name = profile.get("full_name") or "Candidate"
    title = job.get("title") or "the role"
    company = job.get("company_name") or "your company"
    current = profile.get("current_title") or "my current role"
    return (
        f"Dear Hiring Team at {company},\n\n"
        f"I am writing to express my interest in the {title} position. "
        f"In my work as {current}, I have built skills that align with your requirements, "
        f"and I am excited about contributing to {company}.\n\n"
        f"I would welcome the opportunity to discuss how my background can support your team. "
        f"Thank you for your consideration.\n\n"
        f"Best regards,\n{name}"
    )


def _fallback_interview_prep(job: dict[str, Any]) -> str:
    title = job.get("title") or "this role"
    company = job.get("company_name") or "the company"
    skills = job.get("skills_required") or []
    skill_line = ", ".join(skills[:6]) if skills else "the core skills in the JD"
    return (
        f"## Likely questions\n"
        f"- Walk me through your experience relevant to {title}.\n"
        f"- Why {company}, and why this role now?\n"
        f"- Tell me about a project where you used {skill_line}.\n\n"
        f"## STAR stories to rehearse\n"
        f"- One delivery story (Situation → Task → Action → Result).\n"
        f"- One conflict/collaboration story.\n"
        f"- One failure/learning story.\n\n"
        f"## Role-specific talking points\n"
        f"- Mirror vocabulary from the job description honestly.\n"
        f"- Quantify impact in INR/LPA and timelines where possible.\n\n"
        f"## Questions to ask them\n"
        f"- What does success look like in the first 90 days?\n"
        f"- How is this team structured in India?"
    )


async def _generate_text_assets(
    *,
    settings: Settings,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> tuple[str, str]:
    if not settings.openrouter_api_key:
        return _fallback_cover_letter(profile, job), _fallback_interview_prep(job)

    llm = _kit_llm(
        settings,
        max_tokens=_KIT_LLM_MAX_TOKENS_TEXT,
        title="Hireloop - Application Kit",
    )
    prompt = (
        f"Candidate:\n{json.dumps(profile, default=str)[:6000]}\n\n"
        f"Job:\n{json.dumps(job, default=str)[:6000]}"
    )
    try:
        resp = await llm.ainvoke([SystemMessage(content=KIT_SYSTEM), HumanMessage(content=prompt)])
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(raw)
        cover = str(data.get("cover_letter") or "").strip() or _fallback_cover_letter(profile, job)
        prep = str(data.get("interview_prep") or "").strip() or _fallback_interview_prep(job)
        return cover, prep
    except Exception as exc:
        logger.warning("application_kit_llm_failed", error=str(exc))
        return _fallback_cover_letter(profile, job), _fallback_interview_prep(job)


async def _fetch_existing_tailored_resume(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: str,
) -> dict[str, Any] | None:
    existing = await db.fetchrow(
        """
        SELECT id, status FROM public.tailored_resumes
        WHERE candidate_id = $1 AND job_id = $2 AND status = 'ready'
          AND expires_at > NOW()
        """,
        candidate_id,
        job_id,
    )
    if not existing:
        return None
    rid = str(existing["id"])
    return {
        "resume_id": rid,
        "status": "ready",
        "download_path": f"/api/v1/tailored-resumes/tailored/{rid}/download",
    }


async def _generate_tailored_html_only(
    *,
    settings: Settings,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> str:
    llm = _kit_llm(
        settings,
        max_tokens=_KIT_LLM_MAX_TOKENS_RESUME,
        title="Hireloop - Resume Tailor",
    )
    return await generate_tailored_html(
        llm=llm,
        candidate_profile=profile,
        job=job,
        template="modern",
    )


async def _persist_tailored_resume(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job: dict[str, Any],
    html: str,
) -> dict[str, Any]:
    summary = html.split("<p>", 2)[1][:200] if "<p>" in html else ""
    resume_id = await save_tailored_resume(
        db,
        candidate_id=candidate_id,
        job_id=uuid.UUID(str(job["id"])),
        template="modern",
        html_content=html,
        summary_line=summary,
    )
    rid = str(resume_id)
    return {
        "resume_id": rid,
        "status": "ready",
        "download_path": f"/api/v1/tailored-resumes/tailored/{rid}/download",
    }


async def _ensure_tailored_resume(
    db: asyncpg.Connection,
    *,
    settings: Settings,
    candidate_id: uuid.UUID,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    """Sequential resume path (used by callers that don't parallelise LLM work)."""
    existing = await _fetch_existing_tailored_resume(
        db, candidate_id=candidate_id, job_id=str(job["id"])
    )
    if existing:
        return existing

    if not settings.openrouter_api_key:
        return {"resume_id": None, "status": "unavailable", "download_path": None}

    try:
        html = await _generate_tailored_html_only(settings=settings, profile=profile, job=job)
        return await _persist_tailored_resume(db, candidate_id=candidate_id, job=job, html=html)
    except Exception as exc:
        logger.error("application_kit_resume_failed", error=str(exc))
        return {"resume_id": None, "status": "failed", "download_path": None}


async def _ensure_mock_interview(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_title: str,
) -> dict[str, Any]:
    existing = await db.fetchrow(
        """
        SELECT mi.id FROM public.mock_interviews mi
        WHERE mi.candidate_id = $1 AND mi.role_target = $2
          AND mi.status = 'in_progress'
        ORDER BY mi.created_at DESC LIMIT 1
        """,
        candidate_id,
        job_title,
    )
    if existing:
        mid = str(existing["id"])
        return {"mock_interview_id": mid, "path": f"/mock-interview/{mid}"}

    conv_id = uuid.uuid4()
    mock_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.conversations (id, candidate_id, agent, title)
        VALUES ($1, $2, 'aarya', $3)
        """,
        conv_id,
        candidate_id,
        f"Mock: {job_title[:60]}",
    )
    await db.execute(
        """
        INSERT INTO public.mock_interviews (
          id, candidate_id, conversation_id, role_target,
          interview_type, mode, status
        )
        VALUES ($1, $2, $3, $4, 'role_specific', 'chat', 'in_progress')
        """,
        mock_id,
        candidate_id,
        conv_id,
        job_title,
    )
    opening = (
        f"Welcome to your mock interview for {job_title}. "
        "Tell me about yourself and why you're interested in this role."
    )
    await db.execute(
        """
        INSERT INTO public.messages (conversation_id, role, content, content_type)
        VALUES ($1, 'assistant', $2, 'text')
        """,
        conv_id,
        opening,
    )
    mid = str(mock_id)
    return {"mock_interview_id": mid, "path": f"/mock-interview/{mid}"}


async def prepare_application_kit(
    db: asyncpg.Connection,
    user_id: str,
    job_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Save job + generate all apply assets for one role."""
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.skills, c.years_experience, u.full_name, u.email
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )
    if not candidate:
        return {"error": "Candidate not found"}

    market = await fetch_candidate_market(db, candidate["id"])
    vis = job_visible_for_market_sql(market_param="$2")

    job_row = await db.fetchrow(
        f"""
        SELECT j.id, j.title, j.description, j.requirements, j.skills_required,
               j.apply_url, j.location_city, j.ctc_min, j.ctc_max,
               co.name AS company_name, co.logo_url
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE j.id = $1::uuid AND j.is_active = TRUE AND {vis}
          AND j.deleted_at IS NULL
        """,  # noqa: S608
        uuid.UUID(job_id),
        market,
    )
    if not job_row:
        return {"error": "Job not found"}

    candidate_id = candidate["id"]
    await db.execute(
        """
        INSERT INTO public.saved_jobs (candidate_id, job_id)
        VALUES ($1::uuid, $2::uuid)
        ON CONFLICT (candidate_id, job_id) DO NOTHING
        """,
        candidate_id,
        uuid.UUID(job_id),
    )

    profile = dict(candidate)
    profile["id"] = str(profile["id"])
    job = dict(job_row)
    job["id"] = str(job["id"])
    job["skills_required"] = job.get("skills_required") or []

    # DB setup (fast) before parallel LLM work — asyncpg connections are not concurrent-safe.
    existing_resume = await _fetch_existing_tailored_resume(
        db, candidate_id=candidate_id, job_id=str(job["id"])
    )
    mock = await _ensure_mock_interview(
        db, candidate_id=candidate_id, job_title=str(job.get("title") or "Role")
    )

    text_task = asyncio.create_task(
        _generate_text_assets(settings=settings, profile=profile, job=job)
    )
    resume_html_task: asyncio.Task[str] | None = None
    if not existing_resume and settings.openrouter_api_key:
        resume_html_task = asyncio.create_task(
            _generate_tailored_html_only(settings=settings, profile=profile, job=job)
        )

    cover_letter, interview_prep = await text_task

    if existing_resume:
        resume = existing_resume
    elif resume_html_task is not None:
        try:
            html = await resume_html_task
            resume = await _persist_tailored_resume(
                db, candidate_id=candidate_id, job=job, html=html
            )
        except Exception as exc:
            logger.error("application_kit_resume_failed", error=str(exc))
            resume = {"resume_id": None, "status": "failed", "download_path": None}
    else:
        resume = {"resume_id": None, "status": "unavailable", "download_path": None}

    tailored_resume_id = resume.get("resume_id")
    mock_interview_id = mock.get("mock_interview_id")

    kit_row = await db.fetchrow(
        """
        INSERT INTO public.job_application_kits (
          candidate_id, job_id, cover_letter, interview_prep,
          tailored_resume_id, mock_interview_id
        )
        VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, $6::uuid)
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
          cover_letter = EXCLUDED.cover_letter,
          interview_prep = EXCLUDED.interview_prep,
          tailored_resume_id = EXCLUDED.tailored_resume_id,
          mock_interview_id = EXCLUDED.mock_interview_id,
          updated_at = NOW()
        RETURNING id
        """,
        candidate_id,
        uuid.UUID(job_id),
        cover_letter,
        interview_prep,
        uuid.UUID(tailored_resume_id) if tailored_resume_id else None,
        uuid.UUID(mock_interview_id) if mock_interview_id else None,
    )

    card = serialize_job_card(job)
    return {
        "kit_id": str(kit_row["id"]) if kit_row else None,
        "saved": True,
        "job": card,
        "apply_url": job.get("apply_url"),
        "cover_letter": cover_letter,
        "interview_prep": interview_prep,
        "resume": resume,
        "mock_interview": mock,
    }


async def prepare_application_kits(
    db: asyncpg.Connection,
    user_id: str,
    job_ids: list[str],
    settings: Settings,
    *,
    max_jobs: int = 3,
) -> dict[str, Any]:
    """Prepare kits for up to max_jobs roles (sequential — LLM-heavy)."""
    unique_ids = list(dict.fromkeys(job_ids))[:max_jobs]
    kits: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for jid in unique_ids:
        result = await prepare_application_kit(db, user_id, jid, settings)
        if result.get("error"):
            errors.append({"job_id": jid, "error": str(result["error"])})
        else:
            kits.append(result)
    return {
        "count": len(kits),
        "kits": kits,
        "errors": errors,
    }
