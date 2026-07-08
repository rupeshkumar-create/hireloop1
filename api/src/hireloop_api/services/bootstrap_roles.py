"""Resolve effective account role during OAuth/email bootstrap."""


def can_switch_roles(has_candidate: bool, has_recruiter: bool) -> bool:
    """True when the same login has both profile rows."""
    return has_candidate and has_recruiter


def resolve_bootstrap_role(requested_role: str, *, has_recruiter: bool) -> str:
    """
    Pick the role written to public.users during bootstrap.

    Honor the explicit Job Seeker vs Recruiter intent from this login
    (signup tab / OAuth ``signup_role`` / email redirect). Dual-role accounts
    keep both profile rows and switch via POST /auth/role — we must not force
    recruiter just because a recruiter row exists from an earlier mistaken
    LinkedIn signup with a sticky recruiter cookie.

    ``has_recruiter`` is retained for call-site compatibility / telemetry.
    """
    _ = has_recruiter
    if requested_role == "recruiter":
        return "recruiter"
    return "candidate"
