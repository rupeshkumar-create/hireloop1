"""
Application kit — save a job + generate apply assets (resume, cover letter, interview prep).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings
from hireloop_api.market_db import fetch_candidate_market
from hireloop_api.markets import (
    MARKET_LABELS,
    currency_for_market,
    job_visible_for_market_sql,
    normalize_market,
)
from hireloop_api.services.ai_context import compose_candidate_prompt
from hireloop_api.services.application_dossier import build_dossier_snapshot
from hireloop_api.services.ats_resume_check import run_ats_check
from hireloop_api.services.job_present import serialize_job_card
from hireloop_api.services.kit_reviewer import review_and_revise_kit_text
from hireloop_api.services.outcome_learning import build_kit_aware_interview_prep
from hireloop_api.services.resume_tailor import (
    generate_tailored_html,
    resume_summary_line,
    save_tailored_resume,
)
from hireloop_api.services.resume_trimmer import trim_resume_html_for_job
from hireloop_api.services.tailored_resume_profile import load_tailored_resume_profile

logger = structlog.get_logger()

ProgressCallback = Callable[[int, str, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class PreparedApplicationKit:
    id: uuid.UUID
    candidate_id: uuid.UUID
    job_id: uuid.UUID
    cover_letter: str
    interview_prep: str
    resume_id: uuid.UUID
    resume_html: str | None
    resume_summary: str | None
    mock_interview_id: uuid.UUID
    conversation_id: uuid.UUID | None
    job_title: str
    ats_report: dict[str, Any] | None
    dossier: dict[str, Any]
    reviewer_notes: str | None


KIT_SYSTEM_BASE = """You prepare job application assets for one candidate and one role.
Return ONLY valid JSON (no markdown fences):
{
  "cover_letter": "2-3 para formal cover letter; use the candidate's home market context; truthful only",
  "interview_prep": "Markdown with ## Likely questions, ## STAR stories to rehearse,
   ## Role-specific talking points, ## Questions to ask the interviewer"
}
Never invent employers, degrees, dates, titles, or metrics the candidate does not have."""


def _kit_system_prompt(market: str) -> str:
    m = normalize_market(market)
    label = MARKET_LABELS.get(m, m)
    currency = currency_for_market(m)
    if m == "IN":
        comp_hint = "Use INR/LPA and India notice-period norms when relevant."
    else:
        comp_hint = f"Use {currency} annual salary framing for {label}; avoid India-only LPA unless the role is IN-based."
    return f"{KIT_SYSTEM_BASE}\nCandidate home market: {label} ({m}). {comp_hint}"


# Application kits run two LLM jobs (text assets + resume HTML). Use the fast
# fallback model and a lower token cap — quality is fine for structured outputs.
_KIT_LLM_MAX_TOKENS_TEXT = 2048
_KIT_LLM_MAX_TOKENS_RESUME = 2048
_PLACEHOLDER_VALUES = {"", "null", "none", "undefined", "n/a", "na", "-", "—"}
_INTERVIEW_PREP_REQUIRED_SECTIONS = (
    "## Likely questions",
    "## STAR stories to rehearse",
    "## Role-specific talking points",
    "## Questions to ask them",
)


def _normalize_profile_enrichment(value: object) -> dict[str, Any]:
    """Decode asyncpg JSONB values and accept only a top-level JSON object."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


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
            "HTTP-Referer": "https://hireschema.com",
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


def _fallback_interview_prep(job: dict[str, Any], *, market: str = "IN") -> str:
    title = job.get("title") or "this role"
    company = job.get("company_name") or "the company"
    skills = job.get("skills_required") or []
    skill_line = ", ".join(skills[:6]) if skills else "the core skills in the JD"
    m = normalize_market(market)
    currency = currency_for_market(m)
    comp_line = (
        "- Quantify impact in INR/LPA and timelines where possible.\n"
        if m == "IN"
        else f"- Quantify impact in {currency} and timelines where possible.\n"
    )
    location_line = (
        "- How is this team structured locally?"
        if m != "IN"
        else "- How is this team structured in India?"
    )
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
        f"{comp_line}\n"
        f"## Questions to ask them\n"
        f"- What does success look like in the first 90 days?\n"
        f"{location_line}"
    )


def _clean_generated_text(value: Any) -> str:
    """Remove placeholder-only lines from LLM text assets."""
    if not isinstance(value, str):
        return ""
    cleaned: list[str] = []
    for raw_line in value.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if line.lower() in _PLACEHOLDER_VALUES:
            continue
        if line.startswith("-") and line.lstrip("- ").strip().lower() in _PLACEHOLDER_VALUES:
            continue
        cleaned.append(raw_line.rstrip())
    return "\n".join(cleaned).strip()


def _is_useful_cover_letter(text: str) -> bool:
    plain = text.strip()
    if plain.lower() in _PLACEHOLDER_VALUES:
        return False
    return len(plain.split()) >= 40 and any(
        marker in plain.lower() for marker in ("dear ", "hiring", "interest")
    )


def _normalize_interview_prep(text: str, *, fallback: str) -> str:
    cleaned = _clean_generated_text(text)
    if not cleaned:
        return fallback
    missing = [section for section in _INTERVIEW_PREP_REQUIRED_SECTIONS if section not in cleaned]
    if not missing:
        return cleaned

    fallback_sections = _split_markdown_sections(fallback)
    parts = [cleaned]
    for heading in missing:
        section = fallback_sections.get(heading)
        if section:
            parts.append(section)
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _split_markdown_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line.strip()
            sections[current] = [line.rstrip()]
        elif current is not None:
            sections[current].append(line.rstrip())
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def normalize_application_text_assets(
    *,
    cover_letter: Any,
    interview_prep: Any,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> tuple[str, str]:
    """Validate and repair LLM-generated application-kit text before persistence."""
    fallback_cover = _fallback_cover_letter(profile, job)
    market = normalize_market(str(profile.get("market") or "IN"))
    fallback_prep = _fallback_interview_prep(job, market=market)
    cover = _clean_generated_text(cover_letter)
    if not _is_useful_cover_letter(cover):
        cover = fallback_cover
    prep = _normalize_interview_prep(str(interview_prep or ""), fallback=fallback_prep)
    return cover, prep


async def _generate_text_assets(
    *,
    settings: Settings,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> tuple[str, str]:
    if not settings.openrouter_api_key:
        market = normalize_market(str(profile.get("market") or "IN"))
        return _fallback_cover_letter(profile, job), _fallback_interview_prep(job, market=market)

    market = normalize_market(str(profile.get("market") or "IN"))

    llm = _kit_llm(
        settings,
        max_tokens=_KIT_LLM_MAX_TOKENS_TEXT,
        title="Hireschema - Application Kit",
    )
    prompt = compose_candidate_prompt(
        profile,
        task="application_kit",
        task_prompt=f"Job:\n{json.dumps(job, default=str)[:6000]}",
    )
    try:
        resp = await llm.ainvoke(
            [SystemMessage(content=_kit_system_prompt(market)), HumanMessage(content=prompt)]
        )
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(raw)
        return normalize_application_text_assets(
            cover_letter=data.get("cover_letter") if isinstance(data, dict) else None,
            interview_prep=data.get("interview_prep") if isinstance(data, dict) else None,
            profile=profile,
            job=job,
        )
    except Exception as exc:
        logger.warning("application_kit_llm_failed", error=str(exc))
        return _fallback_cover_letter(profile, job), _fallback_interview_prep(job, market=market)


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
        title="Hireschema - Resume Tailor",
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
    summary = resume_summary_line(html)
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
    resume_enabled: bool = True,
) -> dict[str, Any]:
    """Sequential resume path (used by callers that don't parallelise LLM work)."""
    if not resume_enabled:
        return {"resume_id": None, "status": "disabled", "download_path": None}

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
    job_id: str | None = None,
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
          interview_type, mode, status, job_id
        )
        VALUES ($1, $2, $3, $4, 'recruiter_screen', 'chat', 'in_progress', $5::uuid)
        """,
        mock_id,
        candidate_id,
        conv_id,
        job_title,
        uuid.UUID(job_id) if job_id else None,
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
               c.skills, c.years_experience, c.tailored_resume_enabled,
               u.full_name, u.email
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )
    if not candidate:
        return {"error": "Candidate not found"}

    return await _prepare_application_kit_for_candidate_row(
        db,
        candidate=candidate,
        job_id=job_id,
        settings=settings,
    )


async def prepare_application_kit_for_candidate(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    job_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Candidate-id entrypoint for durable background application-kit jobs."""
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.skills, c.years_experience, c.tailored_resume_enabled,
               u.full_name, u.email
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1::uuid AND c.deleted_at IS NULL
        """,
        candidate_id,
    )
    if not candidate:
        return {"error": "Candidate not found"}

    return await _prepare_application_kit_for_candidate_row(
        db,
        candidate=candidate,
        job_id=job_id,
        settings=settings,
    )


async def _prepare_application_kit_for_candidate_row(
    db: asyncpg.Connection,
    *,
    candidate: asyncpg.Record,
    job_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Shared generation path once the candidate row has been loaded."""
    candidate_id = candidate["id"]
    market = await fetch_candidate_market(db, candidate["id"])
    vis = job_visible_for_market_sql(market_param="$2")

    # Bookmark first so inactive / off-market jobs remain eligible for kits.
    await db.execute(
        """
        INSERT INTO public.saved_jobs (candidate_id, job_id)
        VALUES ($1::uuid, $2::uuid)
        ON CONFLICT (candidate_id, job_id) DO NOTHING
        """,
        candidate_id,
        uuid.UUID(job_id),
    )

    job_row = await db.fetchrow(
        f"""
        SELECT j.id, j.title, j.description, j.requirements, j.skills_required,
               j.apply_url, j.location_city, j.ctc_min, j.ctc_max,
               co.name AS company_name, co.logo_url
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE j.id = $1::uuid
          AND j.deleted_at IS NULL
          AND (
            (j.is_active = TRUE AND {vis})
            OR EXISTS (
              SELECT 1 FROM public.saved_jobs sj
              WHERE sj.candidate_id = $3::uuid AND sj.job_id = j.id
            )
          )
        """,
        uuid.UUID(job_id),
        market,
        candidate_id,
    )
    if not job_row:
        return {"error": "Job not found"}

    profile = await load_tailored_resume_profile(db, candidate_id)
    if not profile:
        profile = dict(candidate)
        profile["id"] = str(profile["id"])
    enrich_row = await db.fetchrow(
        "SELECT profile_enrichment FROM public.candidates WHERE id = $1::uuid",
        candidate_id,
    )
    if enrich_row:
        profile["profile_enrichment"] = _normalize_profile_enrichment(
            enrich_row["profile_enrichment"]
        )
    job = dict(job_row)
    job["id"] = str(job["id"])
    job["skills_required"] = job.get("skills_required") or []

    from hireloop_api.services.firecrawl.jd_fetcher import backfill_job_description

    job = await backfill_job_description(db, job, settings, persist=True)

    # DB setup (fast) before parallel LLM work — asyncpg connections are not concurrent-safe.
    existing_resume = await _fetch_existing_tailored_resume(
        db, candidate_id=candidate_id, job_id=str(job["id"])
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

    reviewer_notes = ""
    cover_letter, interview_prep, reviewer_notes = await review_and_revise_kit_text(
        settings=settings,
        profile=profile,
        job=job,
        cover_letter=cover_letter,
        interview_prep=interview_prep,
    )

    ats_report: dict[str, Any] | None = None
    trim_meta: dict[str, Any] | None = None

    if existing_resume:
        resume = existing_resume
    elif resume_html_task is not None:
        try:
            html = await resume_html_task
            html, trim_meta = trim_resume_html_for_job(html, job=job)
            ats_report = run_ats_check(html, profile=profile, job=job)
            resume = await _persist_tailored_resume(
                db, candidate_id=candidate_id, job=job, html=html
            )
        except Exception as exc:
            logger.error("application_kit_resume_failed", error=str(exc))
            resume = {"resume_id": None, "status": "failed", "download_path": None}
    else:
        resume = {"resume_id": None, "status": "unavailable", "download_path": None}

    intro_status_row = await db.fetchrow(
        """
        SELECT status FROM public.intro_requests
        WHERE candidate_id = $1::uuid AND job_id = $2::uuid
        ORDER BY created_at DESC LIMIT 1
        """,
        candidate_id,
        uuid.UUID(job_id),
    )
    intro_status = intro_status_row["status"] if intro_status_row else None
    interview_prep = build_kit_aware_interview_prep(
        base_prep=interview_prep,
        dossier=None,
        job=job,
        profile=profile,
        intro_status=intro_status,
    )

    dossier = build_dossier_snapshot(
        job=job,
        cover_letter=cover_letter,
        interview_prep=interview_prep,
        resume_id=resume.get("resume_id"),
        ats_report=ats_report,
        reviewer_notes=reviewer_notes or None,
    )
    if trim_meta:
        dossier["resume_trim"] = trim_meta

    try:
        mock = await _ensure_mock_interview(
            db,
            candidate_id=candidate_id,
            job_title=str(job.get("title") or "Role"),
            job_id=str(job["id"]),
        )
    except Exception as exc:
        logger.warning("application_kit_mock_interview_failed", error=str(exc))
        mock = {"mock_interview_id": None, "path": None}

    tailored_resume_id = resume.get("resume_id")
    mock_interview_id = mock.get("mock_interview_id")

    kit_row = await db.fetchrow(
        """
        INSERT INTO public.job_application_kits (
          candidate_id, job_id, cover_letter, interview_prep,
          tailored_resume_id, mock_interview_id,
          ats_report, dossier, reviewer_notes
        )
        VALUES ($1::uuid, $2::uuid, $3, $4, $5::uuid, $6::uuid, $7::jsonb, $8::jsonb, $9)
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
          cover_letter = EXCLUDED.cover_letter,
          interview_prep = EXCLUDED.interview_prep,
          tailored_resume_id = COALESCE(
            EXCLUDED.tailored_resume_id, public.job_application_kits.tailored_resume_id
          ),
          mock_interview_id = COALESCE(
            EXCLUDED.mock_interview_id, public.job_application_kits.mock_interview_id
          ),
          ats_report = COALESCE(EXCLUDED.ats_report, public.job_application_kits.ats_report),
          dossier = EXCLUDED.dossier,
          reviewer_notes = COALESCE(EXCLUDED.reviewer_notes, public.job_application_kits.reviewer_notes),
          updated_at = NOW()
        RETURNING id
        """,
        candidate_id,
        uuid.UUID(job_id),
        cover_letter,
        interview_prep,
        uuid.UUID(tailored_resume_id) if tailored_resume_id else None,
        uuid.UUID(mock_interview_id) if mock_interview_id else None,
        json.dumps(ats_report) if ats_report else None,
        json.dumps(dossier),
        reviewer_notes or None,
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
        "ats_report": ats_report,
        "reviewer_notes": reviewer_notes or None,
        "dossier": dossier,
    }


async def run_application_kit_job(settings: Settings, candidate_id: str, job_id: str) -> None:
    """Background worker entrypoint for one candidate/job application kit."""
    from hireloop_api.deps import get_db_pool

    pool = await get_db_pool(settings)
    async with pool.acquire() as db:
        result = await prepare_application_kit_for_candidate(
            db,
            uuid.UUID(candidate_id),
            job_id,
            settings,
        )
    if result.get("error"):
        raise RuntimeError(str(result["error"]))
    resume = result.get("resume") if isinstance(result.get("resume"), dict) else {}
    if not resume.get("resume_id"):
        status = str(resume.get("status") or "unavailable")
        raise RuntimeError(f"Application kit finished without a tailored resume ({status}).")


async def prepare_application_kit_operation(
    pool: asyncpg.Pool,
    *,
    settings: Settings,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    on_progress: ProgressCallback | None = None,
) -> PreparedApplicationKit:
    """Generate an application kit while holding DB connections only for reads."""

    async def _progress(percent: int, stage: str, message: str) -> None:
        if on_progress is not None:
            await on_progress(percent, stage, message)

    await _progress(10, "profile", "Loading your profile.")
    async with pool.acquire() as db:
        candidate = await db.fetchrow(
            """
            SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
                   c.skills, c.years_experience, c.tailored_resume_enabled,
                   c.profile_enrichment, u.full_name, u.email
            FROM public.candidates c JOIN public.users u ON u.id = c.user_id
            WHERE c.id = $1 AND c.deleted_at IS NULL
            """,
            candidate_id,
        )
        job_row = await db.fetchrow(
            """
            SELECT j.id, j.title, j.description, j.requirements, j.skills_required,
                   j.apply_url, j.location_city, j.ctc_min, j.ctc_max,
                   co.name AS company_name, co.logo_url
            FROM public.jobs j LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.id = $1 AND j.deleted_at IS NULL
            """,
            job_id,
        )
        profile = await load_tailored_resume_profile(db, candidate_id)
        existing_resume = await _fetch_existing_tailored_resume(
            db, candidate_id=candidate_id, job_id=str(job_id)
        )
        existing_kit_id = await db.fetchval(
            """SELECT id FROM public.job_application_kits
               WHERE candidate_id = $1 AND job_id = $2""",
            candidate_id,
            job_id,
        )
        existing_mock = await db.fetchrow(
            """
            SELECT id, conversation_id FROM public.mock_interviews
            WHERE candidate_id = $1 AND job_id = $2 AND status = 'in_progress'
            ORDER BY created_at DESC LIMIT 1
            """,
            candidate_id,
            job_id,
        )
        intro_status = await db.fetchval(
            """
            SELECT status FROM public.intro_requests
            WHERE candidate_id = $1 AND job_id = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            candidate_id,
            job_id,
        )
    if not candidate or not job_row:
        raise ValueError("Candidate profile or job is unavailable")
    if not profile:
        profile = dict(candidate)
    profile["profile_enrichment"] = _normalize_profile_enrichment(
        candidate.get("profile_enrichment")
    )
    job = dict(job_row)
    job["id"] = str(job_id)
    job["skills_required"] = job.get("skills_required") or []

    await _progress(35, "resume", "Preparing your tailored resume.")
    text_task = asyncio.create_task(
        _generate_text_assets(settings=settings, profile=profile, job=job)
    )
    resume_task: asyncio.Task[str] | None = None
    if existing_resume is None:
        if not settings.openrouter_api_key:
            raise ValueError("Resume generation is temporarily unavailable")
        resume_task = asyncio.create_task(
            _generate_tailored_html_only(settings=settings, profile=profile, job=job)
        )
    cover_letter, interview_prep = await text_task
    await _progress(60, "cover_letter", "Preparing your cover letter.")
    cover_letter, interview_prep, reviewer_notes = await review_and_revise_kit_text(
        settings=settings,
        profile=profile,
        job=job,
        cover_letter=cover_letter,
        interview_prep=interview_prep,
    )

    resume_html: str | None = None
    ats_report: dict[str, Any] | None = None
    trim_meta: dict[str, Any] | None = None
    if existing_resume is not None:
        resume_id = uuid.UUID(str(existing_resume["resume_id"]))
        resume_summary: str | None = None
    else:
        if resume_task is None:
            raise RuntimeError("Tailored resume generation was not started")
        resume_html = await resume_task
        resume_html, trim_meta = trim_resume_html_for_job(resume_html, job=job)
        ats_report = run_ats_check(resume_html, profile=profile, job=job)
        resume_id = uuid.uuid4()
        resume_summary = resume_summary_line(resume_html)

    await _progress(80, "interview_prep", "Preparing your interview guidance.")
    interview_prep = build_kit_aware_interview_prep(
        base_prep=interview_prep,
        dossier=None,
        job=job,
        profile=profile,
        intro_status=str(intro_status) if intro_status else None,
    )
    dossier = build_dossier_snapshot(
        job=job,
        cover_letter=cover_letter,
        interview_prep=interview_prep,
        resume_id=str(resume_id),
        ats_report=ats_report,
        reviewer_notes=reviewer_notes or None,
    )
    if trim_meta:
        dossier["resume_trim"] = trim_meta
    mock_id = uuid.UUID(str(existing_mock["id"])) if existing_mock else uuid.uuid4()
    conversation_id = None if existing_mock else uuid.uuid4()
    await _progress(95, "save", "Saving your application kit.")
    return PreparedApplicationKit(
        id=uuid.UUID(str(existing_kit_id)) if existing_kit_id else uuid.uuid4(),
        candidate_id=candidate_id,
        job_id=job_id,
        cover_letter=cover_letter,
        interview_prep=interview_prep,
        resume_id=resume_id,
        resume_html=resume_html,
        resume_summary=resume_summary,
        mock_interview_id=mock_id,
        conversation_id=conversation_id,
        job_title=str(job.get("title") or "Role"),
        ats_report=ats_report,
        dossier=dossier,
        reviewer_notes=reviewer_notes or None,
    )


async def persist_prepared_application_kit(
    db: asyncpg.Connection, prepared: PreparedApplicationKit
) -> None:
    """Persist every kit artifact in the worker's terminal transaction."""
    await db.execute(
        """INSERT INTO public.saved_jobs (candidate_id, job_id) VALUES ($1, $2)
           ON CONFLICT (candidate_id, job_id) DO NOTHING""",
        prepared.candidate_id,
        prepared.job_id,
    )
    if prepared.resume_html is not None:
        await db.execute(
            """
            INSERT INTO public.tailored_resumes
              (id, candidate_id, job_id, template, file_path, summary_line,
               html_content, status, expires_at)
            VALUES ($1, $2, $3, 'modern', $4, $5, $6, 'ready', NOW() + INTERVAL '30 days')
            ON CONFLICT (candidate_id, job_id) DO UPDATE SET
              file_path = EXCLUDED.file_path, summary_line = EXCLUDED.summary_line,
              html_content = EXCLUDED.html_content, status = 'ready',
              error_message = NULL, expires_at = EXCLUDED.expires_at
            """,
            prepared.resume_id,
            prepared.candidate_id,
            prepared.job_id,
            f"{prepared.candidate_id}/{prepared.job_id}/{prepared.resume_id}.html",
            prepared.resume_summary,
            prepared.resume_html[:500_000],
        )
    if prepared.conversation_id is not None:
        await db.execute(
            """INSERT INTO public.conversations (id, candidate_id, agent, title)
               VALUES ($1, $2, 'aarya', $3) ON CONFLICT (id) DO NOTHING""",
            prepared.conversation_id,
            prepared.candidate_id,
            f"Mock: {prepared.job_title[:60]}",
        )
        await db.execute(
            """
            INSERT INTO public.mock_interviews
              (id, candidate_id, conversation_id, role_target, interview_type, mode, status, job_id)
            VALUES ($1, $2, $3, $4, 'recruiter_screen', 'chat', 'in_progress', $5)
            ON CONFLICT (id) DO NOTHING
            """,
            prepared.mock_interview_id,
            prepared.candidate_id,
            prepared.conversation_id,
            prepared.job_title,
            prepared.job_id,
        )
        await db.execute(
            """INSERT INTO public.messages (conversation_id, role, content, content_type)
               VALUES ($1, 'assistant', $2, 'text')""",
            prepared.conversation_id,
            (
                f"Welcome to your mock interview for {prepared.job_title}. "
                "Tell me about yourself and why you're interested in this role."
            ),
        )
    await db.execute(
        """
        INSERT INTO public.job_application_kits
          (id, candidate_id, job_id, cover_letter, interview_prep,
           tailored_resume_id, mock_interview_id, ats_report, dossier, reviewer_notes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10)
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
          cover_letter = EXCLUDED.cover_letter,
          interview_prep = EXCLUDED.interview_prep,
          tailored_resume_id = EXCLUDED.tailored_resume_id,
          mock_interview_id = EXCLUDED.mock_interview_id,
          ats_report = EXCLUDED.ats_report,
          dossier = EXCLUDED.dossier,
          reviewer_notes = EXCLUDED.reviewer_notes,
          updated_at = NOW()
        """,
        prepared.id,
        prepared.candidate_id,
        prepared.job_id,
        prepared.cover_letter,
        prepared.interview_prep,
        prepared.resume_id,
        prepared.mock_interview_id,
        json.dumps(prepared.ats_report) if prepared.ats_report else None,
        json.dumps(prepared.dossier),
        prepared.reviewer_notes,
    )


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
