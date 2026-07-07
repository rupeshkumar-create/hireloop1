"""
Application configuration — loaded from environment variables via pydantic-settings.
All secrets MUST live in .env / AWS Secrets Manager. Never hardcode.
"""

from functools import lru_cache
from typing import ClassVar, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "api/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
    )

    # ── App ──────────────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production", "test"] = "development"
    secret_key: str = "change-me"
    allowed_origins: list[str] = [
        "http://localhost:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3000",
    ]

    # Browser-reachable URL of THIS API (FastAPI). Used to build OAuth redirect
    # URIs that Google must redirect the browser to.
    # Dev: http://localhost:8000
    # Prod (Vercel → Railway proxy): https://hireloop1-app.vercel.app/hireloop-api
    public_api_url: str = "http://localhost:8000"
    # Where the OAuth callback sends the browser after success (the SPA origin).
    public_app_url: str = "http://localhost:3001"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:54322/postgres"

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_service_key: str = ""

    # ── Error tracking (Sentry) ───────────────────────────────────────────────
    # Optional: when set, unhandled errors are reported to Sentry. Empty → no-op.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0  # APM sampling (0 = errors only)

    # ── OpenRouter ────────────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    # Primary: strong reasoning/tool-use model for Aarya chat, resume tailor,
    # mock interview, Nitya intro emails. MUST be a valid OpenRouter model ID
    # (https://openrouter.ai/models) — override via OPENROUTER_PRIMARY_MODEL.
    openrouter_primary_model: str = "anthropic/claude-opus-4.7"
    # Fallback: fast + cheap for quick/utility turns and tool-result summaries.
    openrouter_fallback_model: str = "anthropic/claude-haiku-4.5"
    # Fast lane: cheap/low-latency model for short, high-volume utility calls
    # (match-feed rationales, classification) where the strong model is overkill.
    openrouter_fast_model: str = "anthropic/claude-haiku-4.5"
    # Free fallback router. OpenRouter filters for requested capabilities (tools,
    # max_tokens, etc.) and routes to currently available free models.
    openrouter_free_model: str = "openrouter/free"
    # Chat response budget. Keep this modest: Aarya replies are short and high
    # max_tokens can trigger OpenRouter 402 when credits are low.
    openrouter_chat_max_tokens: int = 700
    # Emergency retry budget when OpenRouter says the account can only afford a
    # small completion. 256 is intentionally below the 268-token example error.
    openrouter_low_credit_max_tokens: int = 256
    # Opt-in: generate Aarya's per-card "why you fit" rationale on the match feed
    # via an LLM call (top of the first screen only). Off by default so it never
    # fires in tests/dev without an explicit MATCH_RATIONALE_ENABLED=true.
    match_rationale_enabled: bool = False
    # Opt-in: when Aarya's job_search returns nothing, fire a background
    # career-path-scoped Apify scrape to warm the index for next time. Off by
    # default — it spends Apify credits, so enable deliberately in production.
    auto_ingest_on_empty_search: bool = False

    # Poll the durable background_jobs queue from the API process (disable in unit tests).
    background_worker_enabled: bool = True
    background_worker_poll_seconds: float = 2.0

    # ── Voice (STT + TTS via Deepgram, server-side) ────────────────────────
    # STT (mic) and TTS (Aarya's voice) both go through Deepgram server-side so
    # API keys never reach the browser and the voice is consistent across
    # devices. If no key is set, the client falls back to the browser's Web
    # Speech API for both.
    deepgram_api_key: str = ""
    # Aura voice for Aarya's spoken replies. "aura-asteria-en" is a warm,
    # natural female voice. Override to swap voices without a code change.
    deepgram_tts_model: str = "aura-asteria-en"

    # ── Super admin (internal) ───────────────────────────────────────────────
    # Operator-controlled allow-list (comma-separated emails) used to bootstrap
    # the first admin. Everything else is granted via users.role == 'admin', set
    # server-side through the audited super-admin endpoint. Admin is NEVER
    # derived from a user-editable field (see deps.get_admin_user).
    # Example: SUPER_ADMIN_EMAILS=founder@hireschema.com
    super_admin_emails: list[str] = []

    # ── Apify ─────────────────────────────────────────────────────────────────
    apify_token: str = ""
    # Job ingestion uses only johnvc/Google-Jobs-Scraper.
    apify_jobs_actor: str = "johnvc/Google-Jobs-Scraper"
    google_jobs_time_range: str = "24h"
    google_jobs_candidate_time_range: str = "7d"
    # Legacy env names kept for deploy compatibility; ignored by JobIngester.
    apify_enable_career_site_ingest: bool = False
    apify_linkedin_jobs_actor: str = "johnvc/Google-Jobs-Scraper"
    apify_career_site_actor: str = "johnvc/Google-Jobs-Scraper"
    # No-cookie LinkedIn profile actor for candidate onboarding (R16).
    apify_linkedin_profile_actor: str = "dev_fusion/linkedin-profile-scraper"

    # ── Legacy Fantastic.jobs env names ───────────────────────────────────────
    # Retained only so existing production env vars do not fail settings parsing.
    # Job ingestion ignores these and calls johnvc/Google-Jobs-Scraper instead.
    fantastic_jobs_time_range: str = "24h"
    fantastic_jobs_candidate_time_range: str = "7d"
    fantastic_jobs_remove_agency: bool = True
    fantastic_jobs_recruiter_only: bool = False
    fantastic_jobs_exclude_ats_duplicate: bool = True
    fantastic_jobs_populate_ai_remote: bool = True
    fantastic_jobs_require_salary: bool = False
    fantastic_jobs_visa_sponsorship_only: bool = False
    fantastic_jobs_no_direct_apply: bool = False
    fantastic_jobs_direct_apply_only: bool = False
    fantastic_jobs_use_description_search_for_candidates: bool = True
    fantastic_jobs_max_description_search_terms: int = 3
    fantastic_jobs_org_employees_min: int = 0
    fantastic_jobs_org_employees_max: int = 0
    # Comma-separated lists retained for legacy env compatibility.
    fantastic_jobs_title_exclusions: list[str] = ["Intern:*", "Trainee:*", "Apprentice:*"]
    fantastic_jobs_location_exclusions: list[str] = []
    fantastic_jobs_description_exclusions: list[str] = []
    fantastic_jobs_organization_exclusions: list[str] = []
    fantastic_jobs_organization_slug_exclusions: list[str] = []
    fantastic_jobs_industry_exclusions: list[str] = []
    fantastic_jobs_ai_work_arrangement: list[str] = []
    # AI-enrichment filters EXCLUDE any job Fantastic hasn't enriched — listing
    # all types is not "allow everything", it silently drops unenriched rows
    # (zeroed out a 7d Customer Success run that returned jobs on the console).
    # Off by default; enable via env only with intent.
    fantastic_jobs_ai_employment_types: list[str] = []
    fantastic_jobs_ai_experience_levels: list[str] = []
    fantastic_jobs_ai_languages: list[str] = []  # same enrichment-exclusion trap
    fantastic_jobs_seniority_filter: list[str] = []
    fantastic_jobs_industry_filter: list[str] = []
    fantastic_jobs_organization_search: list[str] = []
    fantastic_jobs_organization_slug_filter: list[str] = []
    fantastic_jobs_organization_size_filter: list[str] = []
    fantastic_jobs_ai_taxonomies: list[str] = []
    fantastic_jobs_ai_taxonomies_primary: list[str] = []
    fantastic_jobs_ai_taxonomies_exclusions: list[str] = []

    # ── ATS feeds (#26) — free first-party boards, no Apify spend ─────────────
    # Comma-separated allowlists. Greenhouse board tokens (the slug in
    # boards.greenhouse.io/<token>) and Lever company slugs (jobs.lever.co/<slug>).
    ats_greenhouse_boards: list[str] = []
    ats_lever_companies: list[str] = []

    # ── LinkDAPI (linkdapi.com) — LinkedIn profile enrichment ─────────────────
    # Resolves a candidate's LinkedIn URL into full profile details (overview,
    # experience, education, skills) at onboarding so the dashboard is pre-filled.
    # Secret lives in .env only — never hardcoded/committed.
    linkdapi_key: str = ""
    linkdapi_base_url: str = "https://linkdapi.com"

    # ── Resume parsing (Affinda) ─────────────────────────────────────────────
    affinda_api_key: str = ""

    # ── Google OAuth (Gmail send scope — R9 cold outreach) ────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    # Optional override — must match an Authorized redirect URI in Google Cloud Console.
    gmail_oauth_redirect_uri_override: str = ""
    # P07 voice-session booking reuses the Google OAuth app above with the
    # calendar.events scope. Booking works in-app without it; this enriches the
    # confirmed slot with a real Calendar event + Meet link.
    google_calendar_id: str = "primary"

    # ── SendGrid template IDs (transactional only — R9) ───────────────────────
    sg_template_signup_confirmation: str = ""
    sg_template_job_match_alert: str = ""
    sg_template_interview_reminder: str = ""
    sg_template_intro_status: str = ""
    sg_template_recruiter_invite: str = ""
    sg_template_recruiter_intro_request: str = ""

    # ── NeverBounce ───────────────────────────────────────────────────────────
    neverbounce_api_key: str = ""

    # ── SendGrid ──────────────────────────────────────────────────────────────
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@hireschema.com"
    sendgrid_from_name: str = "Hireschema"
    # Resend — preferred transactional provider (welcome + job-match emails).
    # Also used as Supabase's custom SMTP for magic-link deliverability.
    resend_api_key: str = ""
    resend_from_email: str = "noreply@hireschema.com"
    resend_from_name: str = "Hireschema"
    # Generic SMTP — free path to email ANY recipient without a verified domain.
    # For a free Gmail account: smtp_host=smtp.gmail.com, smtp_port=587,
    # smtp_user=<the gmail>, smtp_password=<a Google App Password>. Preferred
    # over Resend when configured (Resend free tier only mails the account owner).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # defaults to smtp_user

    # ── MSG91 (SMS OTP + WhatsApp transactional templates — R10) ──────────────
    msg91_auth_key: str = ""
    msg91_sender_id: str = "HLLOOP"
    msg91_whatsapp_number: str = ""  # integrated WABA number, e.g. 919876543210
    msg91_otp_template_id: str = ""  # DLT SMS OTP template ID
    msg91_whatsapp_otp_template: str = ""
    msg91_job_match_template: str = ""
    msg91_intro_status_template: str = ""

    # Dev-only: when True and is_development, save-phone also sets phone_verified.
    allow_phone_save_bypass: bool = False

    # ── Multi-region markets ─────────────────────────────────────────────────
    # Comma-separated ISO codes. Default IN-only until ingest + UX are ready per market.
    enabled_markets: list[str] = ["IN", "US", "GB"]
    default_market: str = "IN"

    # ── Twilio Verify (optional OTP provider) ────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_verify_service_sid: str = ""
    # Temporary MVP/dev bypass: keep OTP enforcement configurable while LinkedIn
    # + resume onboarding is being tested. Production should set this to true.
    require_phone_verification: bool = False

    # ── Internal service secret ───────────────────────────────────────────────
    service_secret: str = "change-me"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("super_admin_emails", mode="before")
    @classmethod
    def split_super_admin_emails(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [s.strip().lower() for s in v.split(",") if s.strip()]
        return [str(s).strip().lower() for s in v if str(s).strip()]

    @field_validator(
        "ats_greenhouse_boards",
        "ats_lever_companies",
        "fantastic_jobs_title_exclusions",
        "fantastic_jobs_location_exclusions",
        "fantastic_jobs_description_exclusions",
        "fantastic_jobs_organization_exclusions",
        "fantastic_jobs_organization_slug_exclusions",
        "fantastic_jobs_industry_exclusions",
        "fantastic_jobs_ai_work_arrangement",
        "fantastic_jobs_ai_employment_types",
        "fantastic_jobs_ai_experience_levels",
        "fantastic_jobs_ai_languages",
        "fantastic_jobs_seniority_filter",
        "fantastic_jobs_industry_filter",
        "fantastic_jobs_organization_search",
        "fantastic_jobs_organization_slug_filter",
        "fantastic_jobs_organization_size_filter",
        "fantastic_jobs_ai_taxonomies",
        "fantastic_jobs_ai_taxonomies_primary",
        "fantastic_jobs_ai_taxonomies_exclusions",
        mode="before",
    )
    @classmethod
    def split_csv_lists(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return [str(s).strip() for s in v if str(s).strip()]

    @field_validator("enabled_markets", mode="before")
    @classmethod
    def split_enabled_markets(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            parts = [s.strip().upper() for s in v.split(",") if s.strip()]
        else:
            parts = [str(s).strip().upper() for s in v if str(s).strip()]
        return parts or ["IN"]

    # Secrets that MUST be overridden in production. Their insecure defaults gate
    # privileged surfaces (service-secret webhooks, admin job ingest/cron, token
    # signing), so a default value in prod is a critical misconfiguration.
    _PROD_REQUIRED_SECRETS: ClassVar[tuple[str, ...]] = ("secret_key", "service_secret")
    _INSECURE_SECRET_DEFAULTS: ClassVar[frozenset[str]] = frozenset({"", "change-me"})

    @model_validator(mode="after")
    def _resolve_public_api_url(self) -> "Settings":
        """In production, never OAuth-redirect to localhost — use the Vercel proxy."""
        url = self.public_api_url.rstrip("/")
        if self.environment == "production" and ("localhost" in url or "127.0.0.1" in url):
            app = self.public_app_url.rstrip("/")
            if app and "localhost" not in app and "127.0.0.1" not in app:
                self.public_api_url = f"{app}/hireloop-api"
        return self

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> "Settings":
        """Fail fast on boot if production is left with default/empty secrets."""
        if self.environment != "production":
            return self
        missing = [
            name
            for name in self._PROD_REQUIRED_SECRETS
            if str(getattr(self, name, "")).strip() in self._INSECURE_SECRET_DEFAULTS
        ]
        if missing:
            raise ValueError(
                "Insecure configuration for production: "
                + ", ".join(missing)
                + " must be set to a strong non-default value "
                "(currently empty or 'change-me'). Refusing to start."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def gmail_oauth_redirect_uri(self) -> str:
        """
        Browser redirect URI registered in Google Cloud Console.

        In production we always use the app-origin /hireloop-api proxy so Google
        redirects through www.hireschema.com (not the raw Railway hostname).
        """
        override = self.gmail_oauth_redirect_uri_override.strip()
        if override:
            return override.rstrip("/")
        if self.environment == "production":
            app = self.public_app_url.rstrip("/")
            if app and "localhost" not in app and "127.0.0.1" not in app:
                return f"{app}/hireloop-api/api/v1/gmail/callback"
        return f"{self.public_api_url.rstrip('/')}/api/v1/gmail/callback"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Use as FastAPI dependency."""
    return Settings()
