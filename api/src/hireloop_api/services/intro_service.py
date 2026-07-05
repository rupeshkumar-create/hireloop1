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

logger = structlog.get_logger()


def _app_base_url() -> str:
    """Best-effort public app origin for building invite CTA links."""
    settings = get_settings()
    origins = getattr(settings, "allowed_origins", None) or []
    for origin in origins:
        if origin.startswith("http") and "localhost" not in origin:
            return origin.rstrip("/")
    return "https://app.hireloop.in"


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
    """
    Transactional email when a candidate requests an in-app intro (R9).
    Degrades gracefully when SendGrid is not configured.
    """
    row = await db.fetchrow(
        """
        SELECT u.email, u.full_name
        FROM public.recruiters r
        JOIN public.users u ON u.id = r.user_id
        WHERE r.id = $1::uuid AND r.deleted_at IS NULL
        """,
        recruiter_id,
    )
    if not row or not row["email"]:
        return False

    settings = get_settings()
    api_key = getattr(settings, "sendgrid_api_key", "") or ""
    template_id = (getattr(settings, "sg_template_recruiter_intro_request", "") or "") or (
        getattr(settings, "sg_template_intro_status", "") or ""
    )
    cta_url = f"{_app_base_url()}/recruiter/inbox"
    if not api_key or not template_id:
        logger.info(
            "recruiter_intro_notify_skipped",
            reason="sendgrid_unconfigured",
            recruiter_id=str(recruiter_id),
            cta_url=cta_url,
        )
        return False

    try:
        from hireloop_api.services.email.sendgrid_service import SendGridService

        svc = SendGridService(
            api_key,
            settings.sendgrid_from_email,
            settings.sendgrid_from_name,
        )
        try:
            sent = await svc.send_recruiter_intro_request(
                to_email=row["email"],
                recruiter_name=row["full_name"],
                template_id=template_id,
                candidate_name=candidate_name or "A candidate",
                job_title=job_title or "your role",
                cta_url=cta_url,
            )
        finally:
            await svc.close()
        return bool(sent)
    except Exception as exc:
        logger.error(
            "recruiter_intro_notify_failed",
            recruiter_id=str(recruiter_id),
            error=str(exc),
        )
        return False


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
    return {
        "intro_id": str(intro_id),
        "status": "pending",
        "direction": "candidate_to_hm",
        "message": "Intro request created. Nitya will enrich the contact and draft your email.",
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
        return {"job_id": str(existing), "status": "updated"}

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
    return {"job_id": str(job_id), "status": "published"}
