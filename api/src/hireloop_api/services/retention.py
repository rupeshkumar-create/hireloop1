"""
Candidate retention — daily digests, save/intro nudges, return summaries.

R1: day-2 return hooks (daily digest, save nudge, pending intro nudge)
R2: return visit summary for proactive Aarya copy
R3: application stale reminders, market movement insights
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.markets import job_visible_for_market_sql, normalize_market

logger = structlog.get_logger()

MATCH_DIGEST_MIN_SCORE = 0.65
SAVE_NUDGE_AFTER_HOURS = 48
INTRO_NUDGE_AFTER_HOURS = 48
APPLICATION_STALE_DAYS = 7
MAX_SWEEP_PER_PASS = 25


def _app_base(settings: Settings) -> str:
    base = settings.public_app_url.rstrip("/") if settings.public_app_url else ""
    if base and "localhost" not in base:
        return base
    if settings.allowed_origins:
        for origin in settings.allowed_origins:
            if "hireschema" in origin:
                return origin.rstrip("/")
    return "https://www.hireschema.com"


async def count_new_matches_since(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    since: datetime | None,
    market: str,
    min_score: float = MATCH_DIGEST_MIN_SCORE,
) -> int:
    """How many scored matches appeared after ``since`` (or all if first visit)."""
    vis = job_visible_for_market_sql(market_param="$3")
    if since is None:
        row = await db.fetchrow(
            f"""
            SELECT count(*)::int AS n
            FROM public.match_scores ms
            JOIN public.jobs j ON j.id = ms.job_id
            WHERE ms.candidate_id = $1::uuid
              AND ms.overall_score >= $2
              AND j.is_active = TRUE
              AND j.deleted_at IS NULL
              AND {vis}
            """,
            candidate_id,
            min_score,
            market,
        )
    else:
        row = await db.fetchrow(
            f"""
            SELECT count(*)::int AS n
            FROM public.match_scores ms
            JOIN public.jobs j ON j.id = ms.job_id
            WHERE ms.candidate_id = $1::uuid
              AND ms.overall_score >= $2
              AND j.is_active = TRUE
              AND j.deleted_at IS NULL
              AND {vis}
              AND GREATEST(
                    ms.computed_at,
                    COALESCE(j.scraped_at, j.created_at)
                  ) > $4::timestamptz
            """,
            candidate_id,
            min_score,
            market,
            since,
        )
    return int(row["n"] or 0) if row else 0


async def fetch_return_summary(
    db: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    settings: Settings,
) -> dict[str, Any]:
    """Read-only summary for dashboard return (before last_visit_at is bumped)."""
    row = await db.fetchrow(
        """
        SELECT c.id, c.looking_for, c.current_title, c.market, c.last_visit_at
        FROM public.candidates c
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        user_id,
    )
    if not row:
        return {"ok": False, "new_matches_count": 0, "proactive_message": None}

    market = normalize_market(row.get("market"))
    since = row["last_visit_at"]
    new_count = await count_new_matches_since(
        db, candidate_id=row["id"], since=since, market=market
    )

    title = (row.get("looking_for") or row.get("current_title") or "your profile").strip()
    proactive: str | None = None
    if new_count > 0:
        proactive = (
            f"While you were away I found **{new_count} new role"
            f"{'s' if new_count != 1 else ''}** matching {title}. "
            "Check **New since your last visit** in Matches — or ask me to walk through the best ones."
        )
    elif since is not None:
        days = max(1, int((datetime.now(UTC) - since).total_seconds() // 86400))
        proactive = (
            f"Welcome back! I'm still scanning {title} openings in your market. "
            f"Say **find new jobs** and I'll pull anything posted in the last {days} day"
            f"{'s' if days != 1 else ''}."
        )

    return {
        "ok": True,
        "new_matches_count": new_count,
        "since_visit_at": since.isoformat() if since and hasattr(since, "isoformat") else None,
        "proactive_message": proactive,
        "dashboard_deep_link": f"{_app_base(settings)}/dashboard?panel=jobs",
    }


async def send_daily_match_digest(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: str,
) -> dict[str, Any]:
    """Top 3 new strong matches since yesterday — max one email per calendar day."""
    from hireloop_api.services.notifications import (
        _already_notified,
        _log_in_app,
        send_category_email,
        send_whatsapp_if_allowed,
    )

    uid = uuid.UUID(user_id)
    day_key = datetime.now(UTC).strftime("%Y-%m-%d")
    dedupe_key = f"daily_digest:{day_key}"
    if await _already_notified(
        db,
        user_id=user_id,
        notif_type="job_match",
        dedupe_key=dedupe_key,
        within_hours=36,
    ):
        return {"sent": False, "skipped": "deduped"}

    row = await db.fetchrow(
        """
        SELECT c.id AS candidate_id, c.market, u.email, u.full_name
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL AND c.onboarding_complete = TRUE
        """,
        uid,
    )
    if not row or not row["email"]:
        return {"sent": False, "skipped": "no_candidate"}

    market = normalize_market(row.get("market"))
    vis = job_visible_for_market_sql(market_param="$3")
    since = datetime.now(UTC) - timedelta(hours=24)
    matches = await db.fetch(
        f"""
        SELECT j.title, co.name AS company_name, ms.overall_score, j.id AS job_id
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ms.candidate_id = $1::uuid
          AND ms.overall_score >= $2
          AND ms.computed_at > $4::timestamptz
          AND j.is_active = TRUE
          AND j.deleted_at IS NULL
          AND {vis}
        ORDER BY ms.overall_score DESC
        LIMIT 3
        """,
        row["candidate_id"],
        MATCH_DIGEST_MIN_SCORE,
        market,
        since,
    )
    if not matches:
        return {"sent": False, "skipped": "no_new_matches"}

    jobs_payload = [
        {
            "title": m["title"],
            "company": m["company_name"],
            "score_pct": round(float(m["overall_score"] or 0) * 100),
            "job_id": str(m["job_id"]),
        }
        for m in matches
    ]
    app_base = _app_base(settings)
    cta_url = f"{app_base}/dashboard?panel=jobs"
    name = row["full_name"] or "there"

    email_result = await send_category_email(
        db,
        settings,
        user_id=user_id,
        category="job_match_alerts",
        to_email=row["email"],
        to_name=name,
        template_data={
            "full_name": name,
            "jobs": jobs_payload,
            "cta_url": cta_url,
        },
    )
    channels = ["in_app"]
    if email_result.get("sent"):
        channels.append("email")

    top = jobs_payload[0]
    wa = await send_whatsapp_if_allowed(
        db,
        settings,
        user_id=user_id,
        template_name="job_match_alert",
        purpose="job_match_alerts",
        body_params=[
            name,
            top["title"],
            top.get("company") or "a company",
            str(top["score_pct"]),
            cta_url,
        ],
    )
    if wa.get("sent"):
        channels.append("whatsapp")

    body = f"{len(jobs_payload)} new match{'es' if len(jobs_payload) != 1 else ''} today"
    await _log_in_app(
        db,
        user_id=user_id,
        notif_type="job_match",
        title="Today's job matches",
        body=body,
        data={"dedupe_key": dedupe_key, "jobs": jobs_payload, "deep_link": cta_url},
        channels=channels,
    )
    return {"sent": True, "count": len(jobs_payload), "channels": channels}


async def schedule_daily_digest(
    db: asyncpg.Connection,
    *,
    user_id: str,
    first_run_hours: int = 24,
) -> None:
    """Enqueue first daily digest ~24h after onboarding."""
    from hireloop_api.services.background_jobs import AARYA_DAILY_DIGEST, enqueue_job

    run_after = datetime.now(UTC) + timedelta(hours=first_run_hours)
    day_bucket = run_after.strftime("%Y-%m-%d")
    await enqueue_job(
        db,
        kind=AARYA_DAILY_DIGEST,
        payload={"user_id": user_id},
        idempotency_key=f"daily_digest:{user_id}:{day_bucket}",
        run_after=run_after,
    )


async def run_save_nudge_sweep(db: asyncpg.Connection, settings: Settings) -> int:
    """Nudge candidates who saved a job 48h+ ago but took no action."""
    from hireloop_api.services.notifications import (
        _already_notified,
        _log_in_app,
        send_category_email,
    )

    rows = await db.fetch(
        f"""
        SELECT sj.candidate_id, sj.job_id, sj.saved_at,
               c.user_id, u.email, u.full_name,
               j.title AS job_title, co.name AS company_name
        FROM public.saved_jobs sj
        JOIN public.candidates c ON c.id = sj.candidate_id AND c.deleted_at IS NULL
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        JOIN public.jobs j ON j.id = sj.job_id AND j.deleted_at IS NULL
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE sj.saved_at < NOW() - INTERVAL '{SAVE_NUDGE_AFTER_HOURS} hours'
          AND NOT EXISTS (
            SELECT 1 FROM public.intro_requests ir
            WHERE ir.candidate_id = sj.candidate_id AND ir.job_id = sj.job_id
          )
          AND NOT EXISTS (
            SELECT 1 FROM public.job_application_kits k
            WHERE k.candidate_id = sj.candidate_id AND k.job_id = sj.job_id
          )
          AND NOT EXISTS (
            SELECT 1 FROM public.job_applications ja
            WHERE ja.candidate_id = sj.candidate_id AND ja.job_id = sj.job_id
          )
        ORDER BY sj.saved_at ASC
        LIMIT {MAX_SWEEP_PER_PASS}
        """
    )
    sent = 0
    app_base = _app_base(settings)
    for row in rows:
        user_id = str(row["user_id"])
        job_id = str(row["job_id"])
        dedupe_key = f"save_nudge:{job_id}"
        if await _already_notified(
            db, user_id=user_id, notif_type="save_nudge", dedupe_key=dedupe_key, within_hours=168
        ):
            continue
        title = row["job_title"] or "a role"
        company = row["company_name"] or "the company"
        cta = f"{app_base}/dashboard?panel=jobs&kit_job_id={job_id}"
        msg = f"You saved **{title}** at {company} — want me to prep your application kit or find similar roles?"
        await _log_in_app(
            db,
            user_id=user_id,
            notif_type="save_nudge",
            title="Still interested?",
            body=msg,
            data={"job_id": job_id, "dedupe_key": dedupe_key, "deep_link": cta},
            channels=["in_app"],
        )
        if row["email"]:
            await send_category_email(
                db,
                settings,
                user_id=user_id,
                category="job_match_alerts",
                to_email=row["email"],
                to_name=row["full_name"],
                template_data={
                    "full_name": row["full_name"] or "there",
                    "job_title": title,
                    "company_name": company,
                    "score_pct": 0,
                    "cta_url": cta,
                },
            )
        sent += 1
    return sent


async def run_pending_intro_nudge_sweep(db: asyncpg.Connection, settings: Settings) -> int:
    """Candidate-facing nudge when intro is still pending 48h+."""
    from hireloop_api.services.notifications import _already_notified, _log_in_app

    rows = await db.fetch(
        f"""
        SELECT ir.id, ir.candidate_id, ir.job_id, ir.created_at,
               c.user_id, j.title AS job_title, co.name AS company_name
        FROM public.intro_requests ir
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ir.status IN ('pending', 'enriching', 'drafting', 'draft_ready')
          AND ir.created_at < NOW() - INTERVAL '{INTRO_NUDGE_AFTER_HOURS} hours'
        ORDER BY ir.created_at ASC
        LIMIT {MAX_SWEEP_PER_PASS}
        """
    )
    sent = 0
    app_base = _app_base(settings)
    for row in rows:
        user_id = str(row["user_id"])
        intro_id = str(row["id"])
        dedupe_key = f"intro_pending:{intro_id}"
        if await _already_notified(
            db, user_id=user_id, notif_type="intro_nudge", dedupe_key=dedupe_key, within_hours=168
        ):
            continue
        title = row["job_title"] or "your role"
        company = row["company_name"] or "the company"
        cta = f"{app_base}/dashboard?panel=inbox"
        await _log_in_app(
            db,
            user_id=user_id,
            notif_type="intro_nudge",
            title="Intro in progress",
            body=f"Your intro to **{title}** at {company} is still moving — I'll update you when the hiring manager replies.",
            data={"intro_id": intro_id, "dedupe_key": dedupe_key, "deep_link": cta},
            channels=["in_app"],
        )
        sent += 1
    return sent


async def run_application_reminder_sweep(db: asyncpg.Connection, settings: Settings) -> int:
    """R3: remind candidates with stale applied/screening status."""
    from hireloop_api.services.notifications import notify_application_update

    rows = await db.fetch(
        f"""
        SELECT ja.id, ja.candidate_id, ja.job_id, ja.status, ja.applied_at,
               c.user_id, j.title AS job_title, co.name AS company_name
        FROM public.job_applications ja
        JOIN public.candidates c ON c.id = ja.candidate_id
        JOIN public.jobs j ON j.id = ja.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ja.status IN ('applied', 'screening')
          AND ja.applied_at < NOW() - INTERVAL '{APPLICATION_STALE_DAYS} days'
          AND ja.updated_at < NOW() - INTERVAL '{APPLICATION_STALE_DAYS} days'
        ORDER BY ja.applied_at ASC
        LIMIT {MAX_SWEEP_PER_PASS}
        """
    )
    sent = 0
    for row in rows:
        try:
            await notify_application_update(
                db,
                settings,
                candidate_user_id=str(row["user_id"]),
                job_id=str(row["job_id"]),
                job_title=str(row["job_title"] or "Role"),
                company_name=str(row["company_name"] or "Company"),
                status=str(row["status"]),
            )
            sent += 1
        except Exception as exc:
            logger.warning("application_reminder_failed", error=str(exc)[:200])
    return sent


async def run_market_insight_sweep(db: asyncpg.Connection, settings: Settings) -> int:
    """R3: notify when new jobs landed in the candidate's market in the last 24h."""
    from hireloop_api.services.notifications import _already_notified, _log_in_app

    candidates = await db.fetch(
        """
        SELECT c.id, c.user_id, c.market, c.looking_for
        FROM public.candidates c
        WHERE c.deleted_at IS NULL AND c.onboarding_complete = TRUE
        LIMIT 200
        """
    )
    sent = 0
    day_key = datetime.now(UTC).strftime("%Y-%m-%d")
    app_base = _app_base(settings)
    for cand in candidates:
        user_id = str(cand["user_id"])
        market = normalize_market(cand.get("market"))
        dedupe_key = f"market_insight:{day_key}:{market}"
        if await _already_notified(
            db, user_id=user_id, notif_type="market_insight", dedupe_key=dedupe_key, within_hours=36
        ):
            continue
        vis = job_visible_for_market_sql(market_param="$1")
        n = await db.fetchval(
            f"""
            SELECT count(*)::int
            FROM public.jobs j
            WHERE j.is_active = TRUE
              AND j.deleted_at IS NULL
              AND j.scraped_at > NOW() - INTERVAL '24 hours'
              AND {vis}
            """,
            market,
        )
        if int(n or 0) < 5:
            continue
        title = (cand.get("looking_for") or "roles").strip()
        await _log_in_app(
            db,
            user_id=user_id,
            notif_type="market_insight",
            title="Your market moved",
            body=(
                f"**{int(n)} new {title} openings** landed in {market} in the last 24 hours. "
                "Open Matches to see what's new."
            ),
            data={"dedupe_key": dedupe_key, "deep_link": f"{app_base}/dashboard?panel=jobs"},
            channels=["in_app"],
        )
        sent += 1
    return sent


async def run_retention_sweep(db: asyncpg.Connection, settings: Settings) -> dict[str, int]:
    """Single sweep pass for all candidate retention nudges."""
    save_n = await run_save_nudge_sweep(db, settings)
    intro_n = await run_pending_intro_nudge_sweep(db, settings)
    app_n = await run_application_reminder_sweep(db, settings)
    market_n = await run_market_insight_sweep(db, settings)
    return {
        "save_nudges": save_n,
        "intro_nudges": intro_n,
        "application_reminders": app_n,
        "market_insights": market_n,
    }
