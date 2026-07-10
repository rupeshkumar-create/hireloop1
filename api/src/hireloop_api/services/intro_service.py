"""
Two-sided intro handshake service.

The intro_requests table is the single source of truth between candidates and
recruiters (no agent-to-agent RPC — R5). This service centralises the three
flows so both the Aarya tool and the recruiter REST routes share one code path:

  • candidate → registered recruiter   (in-app request; recruiter sees it)
  • candidate → unregistered recruiter  (email-CTA invite → signup → activate)
  • recruiter → candidate               (recruiter picks a candidate for a role)

All inserts fire the Postgres NOTIFY trigger so the other side updates live.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import get_settings
from hireloop_api.services.public_role import enable_public_listing

logger = structlog.get_logger()


def _simple_intro_draft(
    *, candidate_name: str | None, job_title: str | None, company_name: str | None
) -> str:
    """
    Minimal deterministic draft shown in chat immediately.
    Nitya can overwrite this later with a personalised LLM draft.
    """
    who = (candidate_name or "I").strip() or "I"
    role = (job_title or "this role").strip() or "this role"
    company = (company_name or "your team").strip() or "your team"
    subject = f"Quick intro — {role} at {company}"
    body_text = (
        f"Hi,\n\n"
        f"I'm {who}. I came across the {role} role at {company} and it looks like a strong fit.\n"
        f"If you're the right person to speak to, I'd love to book a quick 15–20 minute chat.\n\n"
        f"Thanks,\n"
        f"{who}\n"
    )
    body_html = (
        "<p>Hi,</p>"
        f"<p>I’m {who}. I came across the <strong>{role}</strong> role at <strong>{company}</strong> and it looks like a strong fit. "
        "If you’re the right person to speak to, I’d love to book a quick 15–20 minute chat.</p>"
        f"<p>Thanks,<br/>{who}</p>"
    )
    return json.dumps({"subject": subject, "body_text": body_text, "body_html": body_html})


async def _maybe_enqueue_hm_enrich(db: asyncpg.Connection, *, hm_id: str) -> uuid.UUID | None:
    """
    Opportunistically queue Apify + NeverBounce enrichment when keys are configured.
    This makes the candidate chat experience work even if Nitya isn't running.
    """
    from hireloop_api.services.background_jobs import HM_ENRICH, enqueue_job

    settings = get_settings()
    if not (getattr(settings, "apify_token", "") or "").strip():
        return None
    if not (getattr(settings, "neverbounce_api_key", "") or "").strip():
        return None

    return await enqueue_job(
        db,
        kind=HM_ENRICH,
        payload={"hm_id": hm_id},
        idempotency_key=f"hm_enrich:{hm_id}",
    )


async def _ensure_simple_intro_draft(
    db: asyncpg.Connection,
    *,
    intro_id: str | uuid.UUID,
    candidate_name: str | None,
    job: asyncpg.Record,
) -> None:
    """Guarantee the candidate can review a draft immediately, even before enrichment."""
    company = None
    if job["company_id"]:
        company = await db.fetchrow(
            "SELECT name FROM public.companies WHERE id = $1::uuid",
            job["company_id"],
        )
    await db.execute(
        """
        UPDATE public.intro_requests
        SET draft_email = COALESCE(draft_email, $1), updated_at = NOW()
        WHERE id = $2::uuid
        """,
        _simple_intro_draft(
            candidate_name=candidate_name,
            job_title=job["title"],
            company_name=(company["name"] if company else None),
        ),
        uuid.UUID(str(intro_id)),
    )


def _app_base_url() -> str:
    """Best-effort public app origin for building invite CTA links."""
    settings = get_settings()
    origins = getattr(settings, "allowed_origins", None) or []
    for origin in origins:
        if origin.startswith("http") and "localhost" not in origin:
            return origin.rstrip("/")
    return "https://www.hireschema.com"


async def _confirm_intro_to_candidate(
    db: asyncpg.Connection,
    *,
    user_id: str,
    job: asyncpg.Record,
) -> None:
    """Best-effort branded email when a candidate requests an intro."""
    try:
        from hireloop_api.services.email.lifecycle_emails import notify_intro_requested_to_candidate

        company_name = None
        if job["company_id"]:
            co = await db.fetchrow(
                "SELECT name FROM public.companies WHERE id = $1::uuid",
                job["company_id"],
            )
            company_name = co["name"] if co else None
        settings = get_settings()
        await notify_intro_requested_to_candidate(
            db,
            settings,
            user_id=user_id,
            job_title=str(job["title"] or "this role"),
            company_name=company_name,
        )
    except Exception as exc:
        logger.warning("intro_confirmation_email_failed", error=str(exc)[:200])


async def _candidate_by_user(db: asyncpg.Connection, user_id: str) -> asyncpg.Record | None:
    return await db.fetchrow(
        """
        SELECT c.id, u.full_name, u.email
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(str(user_id)),
    )


async def _send_recruiter_invite_email(
    *,
    to_email: str,
    invited_name: str | None,
    candidate_name: str | None,
    job_title: str | None,
    token: str,
) -> bool:
    """
    Email an unregistered recruiter a CTA to join and view the candidate.

    Degrades gracefully when SendGrid/SMTP are not configured — the
    recruiter_invites row still holds the token for manual testing.
    """
    settings = get_settings()
    cta_url = f"{_app_base_url()}/recruiter/invite?token={token}"

    try:
        from hireloop_api.services.email.transactional import send_recruiter_invite_email

        sent = await send_recruiter_invite_email(
            settings,
            to_email=to_email,
            invited_name=invited_name,
            candidate_name=candidate_name or "a candidate",
            job_title=job_title or "your role",
            cta_url=cta_url,
        )
        if not sent:
            logger.info(
                "recruiter_invite_email_skipped",
                reason="email_unconfigured",
                to=to_email,
                cta_url=cta_url,
            )
        return bool(sent)
    except Exception as exc:  # email is best-effort, never fatal
        logger.error("recruiter_invite_email_failed", to=to_email, error=str(exc))
        return False


async def _notify_registered_recruiter_intro(
    db: asyncpg.Connection,
    *,
    recruiter_id: uuid.UUID,
    candidate_name: str | None,
    job_title: str | None,
) -> bool:
    """Transactional email when a candidate requests an in-app intro (Resend HTML)."""
    from hireloop_api.services.email.lifecycle_emails import send_recruiter_intro_request_email

    settings = get_settings()
    return await send_recruiter_intro_request_email(
        db,
        settings,
        recruiter_id=recruiter_id,
        candidate_name=candidate_name,
        job_title=job_title,
    )


async def create_candidate_intro(
    db: asyncpg.Connection,
    *,
    user_id: str,
    job_id: str,
    hiring_manager_id: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """
    Candidate asks for an intro on a job. Resolution order:

      1. Job is recruiter-posted and that recruiter is registered → in-app
         request straight to the recruiter (direction=candidate_to_recruiter).
      2. A hiring-manager email is known (passed in or on file for the company)
         → mint an invite + email CTA (status=invited).
      3. Otherwise → legacy candidate→HM enrichment request for Nitya.
    """
    candidate = await _candidate_by_user(db, user_id)
    if not candidate:
        return {"error": "Candidate profile not found"}
    candidate_id = candidate["id"]

    job = await db.fetchrow(
        """
        SELECT j.id, j.title, j.company_id, j.recruiter_id
        FROM public.jobs j
        WHERE j.id = $1::uuid AND j.deleted_at IS NULL
        """,
        uuid.UUID(str(job_id)),
    )
    if not job:
        return {"error": "Job not found"}

    from hireloop_api.services.job_pipeline import ensure_saved_job

    await ensure_saved_job(db, candidate_id, job["id"])

    # ── 1. Registered recruiter → in-app intro ────────────────────────────────
    if job["recruiter_id"]:
        recruiter = await db.fetchrow(
            """
            SELECT id FROM public.recruiters
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            job["recruiter_id"],
        )
        if recruiter:
            existing = await db.fetchval(
                """
                SELECT id FROM public.intro_requests
                WHERE candidate_id = $1 AND job_id = $2
                  AND recruiter_id = $3 AND direction = 'candidate_to_recruiter'
                """,
                candidate_id,
                job["id"],
                recruiter["id"],
            )
            if existing:
                return {
                    "intro_id": str(existing),
                    "status": "pending",
                    "direction": "candidate_to_recruiter",
                    "message": "You've already requested an intro for this role.",
                }
            intro_id = uuid.uuid4()
            await db.execute(
                """
                INSERT INTO public.intro_requests
                  (id, candidate_id, job_id, recruiter_id, direction, status, message)
                VALUES ($1, $2, $3, $4, 'candidate_to_recruiter', 'pending', $5)
                """,
                intro_id,
                candidate_id,
                job["id"],
                recruiter["id"],
                message,
            )
            await _notify_registered_recruiter_intro(
                db,
                recruiter_id=recruiter["id"],
                candidate_name=candidate["full_name"],
                job_title=job["title"],
            )
            await _confirm_intro_to_candidate(db, user_id=user_id, job=job)
            return {
                "intro_id": str(intro_id),
                "status": "pending",
                "direction": "candidate_to_recruiter",
                "message": "Intro requested — the recruiter will see it in their inbox.",
            }

    # ── 2. Known hiring-manager email → invite CTA ────────────────────────────
    hm = None
    if hiring_manager_id:
        hm = await db.fetchrow(
            "SELECT id, full_name, email FROM public.hiring_managers WHERE id = $1::uuid",
            uuid.UUID(str(hiring_manager_id)),
        )
    elif job["company_id"]:
        hm = await db.fetchrow(
            """
            SELECT id, full_name, email FROM public.hiring_managers
            WHERE company_id = $1 AND email IS NOT NULL AND deleted_at IS NULL
            ORDER BY created_at ASC LIMIT 1
            """,
            job["company_id"],
        )

    if hm and hm["email"]:
        # External HM with a known email → Gmail cold intro (Nitya drafts; candidate sends).
        await db.execute(
            """
            UPDATE public.hiring_managers
            SET email_verified = TRUE,
                enrich_status = 'done',
                updated_at = NOW()
            WHERE id = $1::uuid
            """,
            hm["id"],
        )
        existing = await db.fetchval(
            """
            SELECT id FROM public.intro_requests
            WHERE candidate_id = $1 AND job_id = $2 AND hiring_manager_id = $3
            """,
            candidate_id,
            job["id"],
            hm["id"],
        )
        if existing:
            await _ensure_simple_intro_draft(
                db,
                intro_id=existing,
                candidate_name=candidate["full_name"],
                job=job,
            )
            return {
                "intro_id": str(existing),
                "status": "pending",
                "direction": "candidate_to_hm",
                "message": "You've already requested an intro for this role.",
            }
        intro_id = uuid.uuid4()
        await db.execute(
            """
            INSERT INTO public.intro_requests
              (id, candidate_id, job_id, hiring_manager_id, direction, status, message)
            VALUES ($1, $2, $3, $4, 'candidate_to_hm', 'pending', $5)
            """,
            intro_id,
            candidate_id,
            job["id"],
            hm["id"],
            message,
        )
        # Show a simple draft immediately in chat; Nitya can overwrite later.
        await _ensure_simple_intro_draft(
            db,
            intro_id=intro_id,
            candidate_name=candidate["full_name"],
            job=job,
        )
        await _confirm_intro_to_candidate(db, user_id=user_id, job=job)
        return {
            "intro_id": str(intro_id),
            "status": "pending",
            "direction": "candidate_to_hm",
            "message": (
                "Nitya is drafting your intro email. Connect Google in Profile, "
                "then review and send it from your Gmail."
            ),
        }

    # ── 3. External HM path — provision stub if needed ────────────────────────
    if not hiring_manager_id:
        if job["company_id"]:
            hm = await db.fetchrow(
                """
                SELECT id FROM public.hiring_managers
                WHERE company_id = $1 AND deleted_at IS NULL
                ORDER BY created_at ASC LIMIT 1
                """,
                job["company_id"],
            )
            if hm:
                hiring_manager_id = str(hm["id"])
            else:
                company = await db.fetchrow(
                    "SELECT name FROM public.companies WHERE id = $1::uuid",
                    job["company_id"],
                )
                hm_stub_id = uuid.uuid4()
                stub_name = (
                    f"Hiring team at {company['name']}"
                    if company and company["name"]
                    else "Hiring Manager"
                )
                await db.execute(
                    """
                    INSERT INTO public.hiring_managers
                      (id, company_id, full_name, enrich_status)
                    VALUES ($1, $2, $3, 'pending')
                    """,
                    hm_stub_id,
                    job["company_id"],
                    stub_name,
                )
                hiring_manager_id = str(hm_stub_id)

    if not hiring_manager_id:
        return {
            "status": "needs_recruiter",
            "message": (
                "We couldn't find a hiring contact for this job yet. "
                "Try another listing or ask Aarya to search again."
            ),
        }

    # ── Legacy candidate → external HM enrichment (Nitya) ─────────────────────
    existing = await db.fetchval(
        """
        SELECT id FROM public.intro_requests
        WHERE candidate_id = $1 AND job_id = $2 AND hiring_manager_id = $3
        """,
        candidate_id,
        job["id"],
        uuid.UUID(str(hiring_manager_id)),
    )
    if existing:
        await _ensure_simple_intro_draft(
            db,
            intro_id=existing,
            candidate_name=candidate["full_name"],
            job=job,
        )
        return {"intro_id": str(existing), "status": "pending", "direction": "candidate_to_hm"}

    intro_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.intro_requests
          (id, candidate_id, job_id, hiring_manager_id, direction, status, message)
        VALUES ($1, $2, $3, $4, 'candidate_to_hm', 'pending', $5)
        """,
        intro_id,
        candidate_id,
        job["id"],
        uuid.UUID(str(hiring_manager_id)),
        message,
    )
    # Queue enrichment immediately (best-effort) and drop a simple draft for chat.
    await _ensure_simple_intro_draft(
        db,
        intro_id=intro_id,
        candidate_name=candidate["full_name"],
        job=job,
    )
    hm_enrich_job_id: uuid.UUID | None = None
    try:
        hm_enrich_job_id = await _maybe_enqueue_hm_enrich(db, hm_id=str(hiring_manager_id))
        if hm_enrich_job_id:
            await db.execute(
                """
                UPDATE public.intro_requests
                SET status = 'enriching', updated_at = NOW()
                WHERE id = $1::uuid AND status = 'pending'
                """,
                intro_id,
            )
    except Exception as exc:  # enqueue is best-effort; Nitya may still handle it via NOTIFY
        logger.info("hm_enrich_enqueue_skipped", hm_id=str(hiring_manager_id), error=str(exc))
    try:
        from hireloop_api.services.firecrawl.company_intel import enqueue_company_intel_if_needed

        await enqueue_company_intel_if_needed(
            db,
            company_id=job.get("company_id"),
            settings=get_settings(),
        )
    except Exception as exc:
        logger.debug("firecrawl_company_intel_enqueue_skipped", error=str(exc)[:120])
    await _confirm_intro_to_candidate(db, user_id=user_id, job=job)
    hm_enrich_queued = hm_enrich_job_id is not None
    return {
        "intro_id": str(intro_id),
        "status": "enriching" if hm_enrich_queued else "pending",
        "direction": "candidate_to_hm",
        "hm_enrich_queued": hm_enrich_queued,
        "hm_enrich_provider": "apify" if hm_enrich_queued else None,
        "message": (
            "Requested Apify hiring-manager lookup. Nitya will verify the contact "
            "and draft your email."
            if hm_enrich_queued
            else "Intro request created. Nitya will enrich the contact and draft your email."
        ),
    }


async def create_recruiter_intro(
    db: asyncpg.Connection,
    *,
    user_id: str,
    role_id: str,
    candidate_id: str,
    message: str | None = None,
) -> dict[str, Any]:
    """
    Recruiter requests an intro to a specific candidate for one of their roles.
    The role must be published to the jobs feed (jobs.role_id set) so the intro
    has a concrete job_id. Also advances the role_pipeline stage.
    """
    recruiter = await db.fetchrow(
        "SELECT id FROM public.recruiters WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(user_id)),
    )
    if not recruiter:
        return {"error": "Recruiter profile not found"}

    role = await db.fetchrow(
        """
        SELECT id FROM public.roles
        WHERE id = $1::uuid AND recruiter_id = $2 AND deleted_at IS NULL
        """,
        uuid.UUID(str(role_id)),
        recruiter["id"],
    )
    if not role:
        return {"error": "Role not found for this recruiter"}

    job_id = await db.fetchval(
        """
        SELECT id FROM public.jobs
        WHERE role_id = $1::uuid AND deleted_at IS NULL AND is_active = TRUE
        ORDER BY created_at DESC LIMIT 1
        """,
        uuid.UUID(str(role_id)),
    )
    if not job_id:
        return {
            "error": "Publish this role to the jobs feed before requesting intros.",
            "code": "role_not_published",
        }

    cand = await db.fetchval(
        "SELECT id FROM public.candidates WHERE id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(candidate_id)),
    )
    if not cand:
        return {"error": "Candidate not found"}

    existing = await db.fetchval(
        """
        SELECT id FROM public.intro_requests
        WHERE recruiter_id = $1 AND candidate_id = $2 AND role_id = $3
          AND direction = 'recruiter_to_candidate'
        """,
        recruiter["id"],
        uuid.UUID(str(candidate_id)),
        uuid.UUID(str(role_id)),
    )
    if existing:
        return {
            "intro_id": str(existing),
            "status": "pending",
            "direction": "recruiter_to_candidate",
        }

    intro_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.intro_requests
          (id, candidate_id, job_id, recruiter_id, role_id, direction, status, message)
        VALUES ($1, $2, $3, $4, $5, 'recruiter_to_candidate', 'pending', $6)
        """,
        intro_id,
        uuid.UUID(str(candidate_id)),
        job_id,
        recruiter["id"],
        uuid.UUID(str(role_id)),
        message,
    )

    # Advance the pipeline so the recruiter's kanban reflects the ask.
    await db.execute(
        """
        INSERT INTO public.role_pipeline (id, role_id, candidate_id, stage, moved_at)
        VALUES ($1, $2, $3, 'intro_requested', NOW())
        ON CONFLICT (role_id, candidate_id)
        DO UPDATE SET stage = 'intro_requested', moved_at = NOW()
        """,
        uuid.uuid4(),
        uuid.UUID(str(role_id)),
        uuid.UUID(str(candidate_id)),
    )

    try:
        job_row = await db.fetchrow(
            """
            SELECT j.title, c.name AS company_name
            FROM public.jobs j
            LEFT JOIN public.companies c ON c.id = j.company_id
            WHERE j.id = $1::uuid
            """,
            job_id,
        )
        recruiter_user = await db.fetchrow(
            """
            SELECT u.full_name
            FROM public.recruiters r
            JOIN public.users u ON u.id = r.user_id
            WHERE r.id = $1::uuid
            """,
            recruiter["id"],
        )
        from hireloop_api.services.email.lifecycle_emails import (
            notify_recruiter_approach_to_candidate,
        )

        settings = get_settings()
        await notify_recruiter_approach_to_candidate(
            db,
            settings,
            candidate_id=uuid.UUID(str(candidate_id)),
            job_title=str(job_row["title"] if job_row else "a role"),
            company_name=job_row["company_name"] if job_row else None,
            recruiter_name=recruiter_user["full_name"] if recruiter_user else None,
        )
    except Exception as exc:
        logger.warning("recruiter_approach_email_failed", error=str(exc)[:200])

    return {
        "intro_id": str(intro_id),
        "status": "pending",
        "direction": "recruiter_to_candidate",
        "message": "Intro requested — the candidate will see it and can accept to open a chat.",
    }


async def accept_invite(
    db: asyncpg.Connection,
    *,
    user_id: str,
    token: str,
) -> dict[str, Any]:
    """
    A recruiter who signed up from an email invite claims it: link them to the
    invite and flip any pending candidate→recruiter intros from 'invited' to a
    live in-app request they can act on.
    """
    recruiter = await db.fetchrow(
        "SELECT id FROM public.recruiters WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(user_id)),
    )
    if not recruiter:
        return {"error": "Complete recruiter onboarding first", "code": "no_recruiter"}

    invite = await db.fetchrow(
        """
        SELECT id, status, job_id, expires_at
        FROM public.recruiter_invites
        WHERE token = $1
        """,
        token,
    )
    if not invite:
        return {"error": "Invite not found", "code": "not_found"}
    if invite["status"] in ("accepted", "cancelled"):
        return {"error": "This invite is no longer active", "code": "inactive"}

    await db.execute(
        """
        UPDATE public.recruiter_invites
        SET status = 'accepted', recruiter_id = $2, accepted_at = NOW(), updated_at = NOW()
        WHERE id = $1
        """,
        invite["id"],
        recruiter["id"],
    )

    # Link the recruiter to the job so future intros route in-app.
    if invite["job_id"]:
        await db.execute(
            """
            UPDATE public.jobs SET recruiter_id = COALESCE(recruiter_id, $2), updated_at = NOW()
            WHERE id = $1 AND deleted_at IS NULL
            """,
            invite["job_id"],
            recruiter["id"],
        )

    # Activate the pending intro(s) tied to this invite.
    activated = await db.fetch(
        """
        UPDATE public.intro_requests
        SET recruiter_id = $2, status = 'pending', updated_at = NOW()
        WHERE invite_id = $1 AND status = 'invited'
        RETURNING id
        """,
        invite["id"],
        recruiter["id"],
    )

    return {
        "status": "accepted",
        "activated_intros": [str(r["id"]) for r in activated],
        "message": "Invite accepted — the candidate's intro request is now in your inbox.",
    }


async def publish_role_to_jobs(
    db: asyncpg.Connection,
    *,
    role_id: str,
    recruiter_id: str,
) -> dict[str, Any]:
    """
    Mirror a recruiter's role into the candidate-facing jobs feed so candidates
    can discover it and request intros. Idempotent: updates the existing mirror.
    """
    role = await db.fetchrow(
        """
        SELECT id, company_id, title, jd_text, comp_min, comp_max,
               location_city, location_state, remote_policy, must_haves, jd_structured
        FROM public.roles
        WHERE id = $1::uuid AND recruiter_id = $2::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(str(role_id)),
        uuid.UUID(str(recruiter_id)),
    )
    if not role:
        return {"error": "Role not found for this recruiter"}

    is_remote = role["remote_policy"] in ("remote", "flex")
    must = role.get("must_haves") or []
    if isinstance(must, str):
        try:
            must = json.loads(must)
        except (ValueError, TypeError):
            must = []
    skills = [str(s) for s in must if s]
    jd_struct = role.get("jd_structured") or {}
    if isinstance(jd_struct, str):
        try:
            jd_struct = json.loads(jd_struct)
        except (ValueError, TypeError):
            jd_struct = {}
    if isinstance(jd_struct, dict):
        for key in ("required_skills", "skills", "must_have_skills"):
            for item in jd_struct.get(key) or []:
                if item:
                    skills.append(str(item))
    skills = list(dict.fromkeys(skills))[:30]

    existing = await db.fetchval(
        "SELECT id FROM public.jobs WHERE role_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(role_id)),
    )
    public_meta = await enable_public_listing(
        db,
        role_id=str(role_id),
        recruiter_id=str(recruiter_id),
    )
    if public_meta.get("error"):
        return public_meta

    if existing:
        await db.execute(
            """
            UPDATE public.jobs SET
              title = $2, description = $3, location_city = $4, location_state = $5,
              is_remote = $6, ctc_min = $7, ctc_max = $8, skills_required = $9,
              is_active = TRUE, scraped_at = NOW(), expires_at = NOW() + INTERVAL '60 days',
              updated_at = NOW()
            WHERE id = $1
            """,
            existing,
            role["title"],
            role["jd_text"],
            role["location_city"],
            role["location_state"],
            is_remote,
            role["comp_min"],
            role["comp_max"],
            skills,
        )
        return {
            "job_id": str(existing),
            "status": "updated",
            **public_meta,
        }

    job_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.jobs
          (id, company_id, recruiter_id, role_id, title, description,
           location_city, location_state, country_code, is_remote,
           ctc_min, ctc_max, skills_required, source, is_active, scraped_at, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'IN', $9, $10, $11, $12, 'recruiter', TRUE,
                NOW(), NOW() + INTERVAL '60 days')
        """,
        job_id,
        role["company_id"],
        uuid.UUID(str(recruiter_id)),
        uuid.UUID(str(role_id)),
        role["title"],
        role["jd_text"],
        role["location_city"],
        role["location_state"],
        is_remote,
        role["comp_min"],
        role["comp_max"],
        skills,
    )
    return {
        "job_id": str(job_id),
        "status": "published",
        **public_meta,
    }
