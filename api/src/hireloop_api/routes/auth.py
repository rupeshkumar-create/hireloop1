"""
Authentication routes — phone collection and optional OTP.

Flow:
  1. POST /api/v1/auth/save-phone   → saves phone for supported market (onboarding)
  2. POST /api/v1/auth/send-otp     → optional OTP via MSG91 SMS (+91 / India only)
  3. POST /api/v1/auth/verify-otp   → optional OTP verification
  4. GET  /api/v1/auth/me           → returns current user profile

Onboarding uses save-phone only (no OTP round-trip). The number is used for
WhatsApp job-match and intro alerts.

Note: LinkedIn OAuth is handled entirely by Supabase Auth + /auth/callback
on the Next.js side.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator, model_validator

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import (
    _provision_user_row,
    get_current_user,
    get_current_user_with_supabase,
    get_db,
    get_db_optional,
    get_supabase_identity,
)
from hireloop_api.markets import normalize_market, validate_e164_phone
from hireloop_api.routes.me import _ensure_candidate_row
from hireloop_api.services import otp_store
from hireloop_api.services.bootstrap_roles import can_switch_roles, resolve_bootstrap_role
from hireloop_api.services.consent import log_consent
from hireloop_api.services.email.transactional import maybe_send_signup_confirmation
from hireloop_api.services.linkedin_oauth import (
    extract_linkedin_display_name,
    extract_linkedin_headline,
    extract_linkedin_profile_url,
    heal_candidate_headline_from_linkedin,
)
from hireloop_api.services.notifications import ensure_default_notification_prefs
from hireloop_api.services.supabase_auth_admin import (
    ensure_oauth_email_confirmed,
)
from hireloop_api.services.user_profiles import user_profile_flags
from hireloop_api.services.whatsapp.msg91 import Msg91Client

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])

# OTP state lives in Postgres (services/otp_store) so it's shared across API
# workers and survives restarts — not a per-process dict (HIR-46).
OTP_TTL_MINUTES = 10
MAX_OTP_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30


# ── Request/Response models ───────────────────────────────────────────────────


class SendOTPRequest(BaseModel):
    phone: str
    market: str = "IN"

    @model_validator(mode="after")
    def validate_phone(self) -> "SendOTPRequest":
        try:
            self.phone = validate_e164_phone(self.phone, self.market)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class VerifyOTPRequest(BaseModel):
    phone: str
    otp: str
    market: str = "IN"

    @model_validator(mode="after")
    def validate_phone(self) -> "VerifyOTPRequest":
        try:
            self.phone = validate_e164_phone(self.phone, self.market)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("OTP must be 6 digits")
        return v


class SendOTPResponse(BaseModel):
    message: str
    expires_in_seconds: int
    resend_available_in_seconds: int
    delivery_channel: str
    dev_otp: str | None = None


class VerifyOTPResponse(BaseModel):
    message: str
    phone_verified: bool


class SavePhoneRequest(BaseModel):
    phone: str
    market: str = "IN"

    @model_validator(mode="after")
    def validate_phone(self) -> "SavePhoneRequest":
        try:
            self.phone = validate_e164_phone(self.phone, self.market)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class SavePhoneResponse(BaseModel):
    message: str
    phone_verified: bool


class BootstrapRequest(BaseModel):
    role: str = "candidate"  # candidate | recruiter

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("candidate", "recruiter"):
            raise ValueError("role must be candidate or recruiter")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hash_otp(otp: str, phone: str, secret: str) -> str:
    """Keyed HMAC-SHA256 of the OTP so a leaked store can't be brute-forced
    offline without the server secret (a bare 6-digit OTP is only 10^6 wide)."""
    return hmac.new(
        (secret or "hireloop-otp").encode(),
        f"{otp}:{phone}".encode(),
        hashlib.sha256,
    ).hexdigest()


async def _send_msg91_sms_otp(phone: str, otp: str, settings: Settings) -> None:
    """Send OTP via MSG91 SMS. Raises HTTPException on failure."""
    client = Msg91Client(
        settings.msg91_auth_key,
        sender_id=settings.msg91_sender_id,
    )
    try:
        result = await client.send_sms_otp(
            to_phone=phone,
            otp=otp,
            template_id=settings.msg91_otp_template_id,
        )
    finally:
        await client.close()

    if not result.get("sent"):
        logger.error("msg91_otp_failed", phone=phone[-4:], response=result.get("error"))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to send OTP. Please try again.",
        )


def _is_msg91_configured(settings: Settings) -> bool:
    return bool(settings.msg91_auth_key and settings.msg91_otp_template_id)


def _select_otp_provider(
    settings: Settings,
    market: str = "IN",
) -> Literal["msg91", "local", "unconfigured"]:
    """MSG91 for India; local dev OTP elsewhere when ENVIRONMENT=development."""
    m = normalize_market(market)
    if m == "IN" and _is_msg91_configured(settings):
        return "msg91"
    if settings.is_development:
        return "local"
    return "unconfigured"


# ── Endpoints ─────────────────────────────────────────────────────────────────


async def _send_signup_welcome_email(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    email: str | None,
    full_name: str | None,
    role: str,
) -> None:
    """Best-effort welcome email — must not block bootstrap or /me."""
    try:
        await ensure_default_notification_prefs(db, user_id)
        result = await maybe_send_signup_confirmation(
            db,
            settings,
            user_id=user_id,
            email=email,
            full_name=full_name,
            role=role,
        )
        if not result.get("sent"):
            logger.info(
                "signup_welcome_email",
                user_id=str(user_id),
                **{k: result[k] for k in ("skipped",) if k in result},
            )
    except Exception as exc:
        logger.warning("signup_welcome_email_failed", user_id=str(user_id), error=str(exc)[:200])


@router.post("/bootstrap", status_code=200)
async def bootstrap_user(
    body: BootstrapRequest,
    current_user: dict = Depends(get_current_user_with_supabase),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    After Supabase OAuth, sync profile + create candidate/recruiter row.
    Called from /auth/callback (app) with Bearer token.
    """
    user_id = uuid.UUID(str(current_user["id"]))
    supabase_user: dict[str, Any] = current_user.get("_supabase_user") or {}

    # Self-heal: OAuth can beat the auth.users trigger — ensure public.users exists
    # before we attach candidate/recruiter rows (FK would otherwise 500).
    if not await _provision_user_row(db, supabase_user):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create your account. Please try signing in again.",
        )

    # Honor the Job Seeker vs Recruiter intent from this login (signup tab /
    # LinkedIn signup_role / email redirect). Dual-role switch stays on POST /auth/role.
    has_recruiter = await db.fetchval(
        """
        SELECT 1 FROM public.recruiters
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
    )
    effective_role = resolve_bootstrap_role(body.role, has_recruiter=bool(has_recruiter))

    await db.execute(
        """
        UPDATE public.users SET
          role = $2,
          updated_at = NOW()
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        effective_role,
    )

    is_new_user = True

    if effective_role == "candidate":
        # ── Signup pipeline, stages 1 → 2 (the fixed order) ──────────────────
        # 1. Extract details from the LinkedIn OAuth login (below): pull the
        #    profile URL + headline from Supabase's OAuth metadata and persist
        #    them to candidates.linkedin_data.
        # 2. Run the Apify LinkedIn profile scraper: scheduled immediately after
        #    extraction via background_jobs (see end of this block). It runs
        #    off the request so the OAuth redirect isn't blocked, but it is
        #    always kicked off AFTER step 1 has persisted the OAuth data.
        # Stages 3 (CV scrape) and 4 (Aarya call) run in the /onboarding wizard.
        #
        # Save LinkedIn/OAuth profile payload from Supabase for downstream enrichment.
        # DPDP note: we redact any token-like fields before persisting.

        def _redact(value: Any) -> Any:
            if isinstance(value, dict):
                out: dict[str, Any] = {}
                for raw_k, v in value.items():
                    k = str(raw_k)
                    lk = k.lower()
                    if "token" in lk or "secret" in lk:
                        continue
                    out[k] = _redact(v)
                return out
            if isinstance(value, list):
                return [_redact(v) for v in value]
            return value

        linkedin_data = _redact(
            {
                "provider": (supabase_user.get("app_metadata") or {}).get("provider"),
                "providers": (supabase_user.get("app_metadata") or {}).get("providers"),
                "user_metadata": supabase_user.get("user_metadata") or {},
                "identities": supabase_user.get("identities") or [],
            }
        )
        linkedin_url = extract_linkedin_profile_url(linkedin_data)
        linkedin_headline = extract_linkedin_headline(linkedin_data)
        initial_headline = linkedin_headline or "New candidate"

        existing = await db.fetchrow(
            "SELECT id FROM public.candidates WHERE user_id = $1",
            user_id,
        )
        is_new_user = existing is None
        await _ensure_candidate_row(db, user_id, headline=initial_headline)
        if is_new_user:
            try:
                await log_consent(db, user_id=user_id, purpose="profile_creation", granted=True)
            except Exception as exc:
                logger.error(
                    "candidate_consent_log_failed",
                    user_id=str(user_id),
                    error=str(exc),
                )

        # Persist linkedin_data blob (best-effort, non-fatal)
        try:
            await db.execute(
                """
                UPDATE public.candidates
                SET linkedin_data = $2::jsonb,
                    linkedin_url  = COALESCE(linkedin_url, $3),
                    updated_at = NOW()
                WHERE user_id = $1::uuid AND deleted_at IS NULL
                """,
                user_id,
                __import__("json").dumps(linkedin_data),
                linkedin_url,
            )
        except Exception as exc:
            logger.error("linkedin_data_persist_failed", user_id=str(user_id), error=str(exc))

        linkedin_name = extract_linkedin_display_name(linkedin_data)
        if linkedin_name:
            try:
                await db.execute(
                    """
                    UPDATE public.users
                    SET full_name = COALESCE(NULLIF(TRIM(full_name), ''), $2),
                        updated_at = NOW()
                    WHERE id = $1::uuid AND deleted_at IS NULL
                    """,
                    user_id,
                    linkedin_name,
                )
            except Exception as exc:
                logger.warning(
                    "linkedin_name_persist_failed",
                    user_id=str(user_id),
                    error=str(exc)[:200],
                )

        try:
            await heal_candidate_headline_from_linkedin(
                db,
                user_id=user_id,
                linkedin_data=linkedin_data,
                user_full_name=current_user.get("full_name"),
            )
        except Exception as exc:
            logger.warning(
                "linkedin_headline_heal_failed",
                user_id=str(user_id),
                error=str(exc)[:200],
            )

        if is_new_user:
            try:
                new_cand = await db.fetchrow(
                    """
                    SELECT id FROM public.candidates
                    WHERE user_id = $1::uuid AND deleted_at IS NULL
                    """,
                    user_id,
                )
                if new_cand:
                    from hireloop_api.services.public_profile import (
                        bootstrap_candidate_public_profile,
                    )

                    user_name = await db.fetchval(
                        "SELECT full_name FROM public.users WHERE id = $1::uuid",
                        user_id,
                    )
                    await bootstrap_candidate_public_profile(
                        db,
                        new_cand["id"],
                        user_id=user_id,
                        display_name=str(user_name) if user_name else None,
                    )
            except Exception as exc:
                logger.warning(
                    "candidate_sharing_bootstrap_failed",
                    user_id=str(user_id),
                    error=str(exc)[:200],
                )

        # LinkedIn URL + OAuth metadata saved above. LinkDAPI enrichment runs
        # after DPDP consent (POST /me/onboarding-consent).
    else:
        existing = await db.fetchrow(
            """
            SELECT id FROM public.recruiters
            WHERE user_id = $1::uuid AND deleted_at IS NULL
            """,
            user_id,
        )
        is_new_user = existing is None
        await db.execute(
            """
            INSERT INTO public.recruiters (user_id, title)
            VALUES ($1::uuid, 'Hiring Manager')
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id,
        )
        if is_new_user:
            try:
                await log_consent(db, user_id=user_id, purpose="profile_creation", granted=True)
            except Exception as exc:
                logger.error(
                    "recruiter_consent_log_failed",
                    user_id=str(user_id),
                    error=str(exc),
                )

    # LinkedIn/OAuth: trust the IdP — confirm email server-side, no verification mail.
    # Email/magic-link signups still verify via Supabase's inbox link or OTP.
    try:
        await ensure_oauth_email_confirmed(settings, supabase_user)
    except Exception as exc:
        logger.warning("oauth_email_confirm_failed", user_id=str(user_id), error=str(exc)[:200])

    # Welcome email once per account (deduped in consent_log).
    welcome_email = current_user.get("email") or (
        supabase_user.get("email") if supabase_user else None
    )
    if welcome_email:
        await _send_signup_welcome_email(
            db,
            settings,
            user_id=user_id,
            email=welcome_email,
            full_name=current_user.get("full_name")
            or (supabase_user.get("user_metadata") or {}).get("full_name")
            or (supabase_user.get("user_metadata") or {}).get("name"),
            role=effective_role,
        )

    # `is_new_user` lets /auth/callback route first-time candidates into the
    # onboarding wizard while sending returning users straight to their home.
    return {"ok": True, "role": effective_role, "is_new_user": is_new_user}


class RoleSwitchRequest(BaseModel):
    role: Literal["candidate", "recruiter"]


@router.post("/role")
async def switch_active_role(
    body: RoleSwitchRequest,
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Switch the signed-in account's active role when both profiles exist."""
    user_id = uuid.UUID(str(current_user["id"]))
    has_candidate, has_recruiter = await user_profile_flags(db, user_id)

    if body.role == "candidate":
        if not has_candidate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No candidate profile for this account",
            )
    elif not has_recruiter:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recruiter profile for this account",
        )

    await db.execute(
        "UPDATE public.users SET role = $2, updated_at = NOW() WHERE id = $1::uuid",
        user_id,
        body.role,
    )
    return {
        "ok": True,
        "role": body.role,
        "has_candidate": has_candidate,
        "has_recruiter": has_recruiter,
    }


@router.post("/send-otp", response_model=SendOTPResponse, status_code=200)
async def send_otp(
    body: SendOTPRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> SendOTPResponse:
    """
    Send OTP for phone verification.

    India (+91): MSG91 SMS when configured.
    Other markets / dev: local OTP logged in API when ENVIRONMENT=development.
    Rate limited: max 3 OTP sends per phone per hour (enforced by Cloudflare WAF + this code).
    """
    phone = body.phone
    market = normalize_market(body.market)

    # Cooldown: allow resend only after a short wait (UI shows countdown).
    elapsed = await otp_store.seconds_since_last_send(db, phone)
    if elapsed is not None:
        remaining = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
        if remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining}s before resending the OTP.",
                headers={"Retry-After": str(remaining)},
            )

    provider = _select_otp_provider(settings, market)

    if provider == "unconfigured":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "SMS OTP is only available for India (+91) right now. "
                "You can continue without phone verification."
            ),
        )

    # Generate cryptographically secure 6-digit OTP
    otp = str(secrets.randbelow(900000) + 100000)  # 100000-999999

    if provider == "msg91":
        await _send_msg91_sms_otp(phone, otp, settings)
    else:
        logger.info("dev_otp", phone_last4=phone[-4:], otp=otp)

    # Store hashed OTP with expiry (also stamps last_sent_at for the cooldown).
    await otp_store.store_otp(
        db,
        phone,
        otp_hash=_hash_otp(otp, phone, settings.secret_key),
        ttl_minutes=OTP_TTL_MINUTES,
    )

    logger.info("otp_sent", phone_last4=phone[-4:])

    return SendOTPResponse(
        message="OTP sent successfully",
        expires_in_seconds=OTP_TTL_MINUTES * 60,
        resend_available_in_seconds=OTP_RESEND_COOLDOWN_SECONDS,
        delivery_channel="sms" if provider == "msg91" else "local_dev",
        dev_otp=otp if provider == "local" else None,
    )


@router.post("/verify-otp", response_model=VerifyOTPResponse, status_code=200)
async def verify_otp(
    body: VerifyOTPRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    current_user: dict = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
) -> VerifyOTPResponse:
    """
    Verify OTP. On success, marks the user as phone_verified = TRUE.
    Requires the user to already have a Supabase Auth session.
    """
    phone = body.phone
    market = normalize_market(body.market)
    stored = await otp_store.get_active(db, phone)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP found for this number. Please request a new one.",
        )

    # Check expiry
    if datetime.now(UTC) > stored["expires_at"]:
        await otp_store.clear(db, phone)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one.",
        )

    # Check attempts (brute-force protection)
    attempts = await otp_store.increment_attempts(db, phone)
    if attempts > MAX_OTP_ATTEMPTS:
        await otp_store.clear(db, phone)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Please request a new OTP.",
        )

    # Verify hash (timing-safe)
    if not hmac.compare_digest(_hash_otp(body.otp, phone, settings.secret_key), stored["otp_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP.",
        )

    # OTP valid — clean up store
    await otp_store.clear(db, phone)

    user_id = uuid.UUID(str(current_user["id"]))

    # ── UPDATE users — catch UNIQUE(phone) violation cleanly ──────────────
    try:
        result = await db.execute(
            """
            UPDATE public.users SET
              phone = $2,
              phone_verified = TRUE,
              market = $3,
              phone_country = $3,
              updated_at = NOW()
            WHERE id = $1 AND deleted_at IS NULL
            """,
            user_id,
            phone,
            market,
        )
    except asyncpg.UniqueViolationError as exc:
        # Most likely: another account already verified this number.
        logger.warning(
            "phone_already_claimed",
            user_id=str(user_id),
            phone_last4=phone[-4:],
            constraint=exc.constraint_name,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This phone number is already linked to another Hireschema "
                "account. Sign in with that account, or use a different number."
            ),
        ) from exc

    # asyncpg execute returns e.g. "UPDATE 1" — if 0, the row didn't exist
    if result.endswith(" 0"):
        logger.error(
            "verify_otp_user_missing",
            user_id=str(user_id),
            result=result,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Your user record is missing. Sign out and sign in again.",
        )

    await db.execute(
        """
        UPDATE public.candidates
        SET market = $2, updated_at = NOW()
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        market,
    )

    # ── INSERT consent_log — non-fatal if it fails, log and continue ─────
    try:
        await log_consent(
            db,
            user_id=user_id,
            purpose="phone_verification",
            granted=True,
            request=request,
        )
    except Exception as exc:
        # DPDP audit trail is important but we don't want to fail the user's
        # signup over a logging insert. Log loudly so it's caught in review.
        logger.error(
            "consent_log_insert_failed",
            user_id=str(user_id),
            error=str(exc),
        )

    logger.info("otp_verified", user_id=str(user_id), phone_last4=phone[-4:])

    try:
        await maybe_send_signup_confirmation(
            db,
            settings,
            user_id=user_id,
        )
    except Exception as exc:
        logger.error("signup_confirmation_email_failed", user_id=str(user_id), error=str(exc))

    return VerifyOTPResponse(
        message="Phone verified successfully",
        phone_verified=True,
    )


@router.post("/save-phone", response_model=SavePhoneResponse, status_code=200)
async def save_phone(
    body: SavePhoneRequest,
    request: Request,
    supabase_user: dict = Depends(get_supabase_identity),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection | None = Depends(get_db_optional),
) -> SavePhoneResponse:
    """
    Save the user's +91 mobile number (format-validated, unique).

    Onboarding flow: collect the number and mark phone_verified so gated routes
    unlock. WhatsApp alerts use this number — no OTP required for signup.
    """
    phone = body.phone
    market = normalize_market(body.market)
    user_id = uuid.UUID(str(supabase_user["id"]))

    saved_via_rest = False
    if db is not None:
        try:
            result = await db.execute(
                """
                UPDATE public.users SET
                  phone = $2,
                  phone_verified = TRUE,
                  market = $3,
                  phone_country = $3,
                  updated_at = NOW()
                WHERE id = $1 AND deleted_at IS NULL
                """,
                user_id,
                phone,
                market,
            )
            if result.endswith(" 0"):
                provisioned = await _provision_user_row(db, supabase_user)
                if not provisioned:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Your user record is missing. Sign out and sign in again.",
                    )
                result = await db.execute(
                    """
                    UPDATE public.users SET
                      phone = $2,
                      phone_verified = TRUE,
                      market = $3,
                      phone_country = $3,
                      updated_at = NOW()
                    WHERE id = $1 AND deleted_at IS NULL
                    """,
                    user_id,
                    phone,
                    market,
                )
                if result.endswith(" 0"):
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Your user record is missing. Sign out and sign in again.",
                    )
            try:
                await log_consent(
                    db,
                    user_id=user_id,
                    purpose="phone_collection",
                    granted=True,
                    request=request,
                )
            except Exception as exc:
                logger.error("consent_log_insert_failed", user_id=str(user_id), error=str(exc))
            await db.execute(
                """
                UPDATE public.candidates
                SET market = $2, updated_at = NOW()
                WHERE user_id = $1::uuid AND deleted_at IS NULL
                """,
                user_id,
                market,
            )
        except asyncpg.UniqueViolationError as exc:
            logger.warning(
                "phone_already_claimed",
                user_id=str(user_id),
                phone_last4=phone[-4:],
                constraint=exc.constraint_name,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This phone number is already linked to another Hireschema "
                    "account. Use a different number."
                ),
            ) from exc
        except Exception as exc:
            logger.warning("save_phone_asyncpg_failed_using_rest", error=str(exc)[:200])
            saved_via_rest = True
    else:
        saved_via_rest = True

    if saved_via_rest:
        from hireloop_api.services import supabase_users as rest_users

        try:
            await rest_users.save_phone(
                settings,
                user_id=user_id,
                phone=phone,
                supabase_user=supabase_user,
            )
            try:
                await rest_users.log_consent_rest(
                    settings,
                    user_id=user_id,
                    purpose="phone_collection",
                    granted=True,
                )
            except Exception as exc:
                logger.error("consent_log_rest_failed", user_id=str(user_id), error=str(exc))
        except ValueError as exc:
            if str(exc) == "phone_already_claimed":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This phone number is already linked to another Hireschema "
                        "account. Use a different number."
                    ),
                ) from exc
            raise
        except Exception as exc:
            logger.error("save_phone_rest_failed", user_id=str(user_id), error=str(exc)[:300])
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Couldn't save your number right now. Try again in a moment.",
            ) from exc

    logger.info("phone_saved", user_id=str(user_id), phone_last4=phone[-4:])

    try:
        email = supabase_user.get("email")
        name = supabase_user.get("user_metadata", {}).get("full_name") or supabase_user.get(
            "user_metadata", {}
        ).get("name")
        await maybe_send_signup_confirmation(
            db,
            settings,
            user_id=user_id,
            email=email,
            full_name=name,
        )
    except Exception as exc:
        logger.error("signup_confirmation_email_failed", user_id=str(user_id), error=str(exc))

    return SavePhoneResponse(
        message="Phone number saved",
        phone_verified=True,
    )


@router.get("/me", status_code=200)
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Return current user profile."""
    user_id = uuid.UUID(str(current_user["id"]))
    has_candidate, has_recruiter = await user_profile_flags(db, user_id)

    # Backfill welcome email if bootstrap background send was missed (deduped).
    if current_user.get("email"):
        await _send_signup_welcome_email(
            db,
            settings,
            user_id=user_id,
            email=current_user.get("email"),
            full_name=current_user.get("full_name"),
            role=str(current_user.get("role") or "candidate"),
        )

    return {
        "id": str(current_user["id"]),
        "email": current_user["email"],
        "role": current_user["role"],
        "phone_verified": current_user["phone_verified"],
        "full_name": current_user["full_name"],
        "has_candidate": has_candidate,
        "has_recruiter": has_recruiter,
        "can_switch_roles": can_switch_roles(has_candidate, has_recruiter),
    }
