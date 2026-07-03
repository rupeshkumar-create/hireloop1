"""Tests for OAuth vs email auth provider detection."""

from hireloop_api.services.supabase_auth_admin import (
    is_oauth_signup,
    primary_auth_provider,
)


def test_primary_auth_provider_linkedin_oidc() -> None:
    user = {"app_metadata": {"provider": "linkedin_oidc", "providers": ["linkedin_oidc"]}}
    assert primary_auth_provider(user) == "linkedin_oidc"
    assert is_oauth_signup(user) is True


def test_primary_auth_provider_email() -> None:
    user = {"app_metadata": {"provider": "email", "providers": ["email"]}}
    assert primary_auth_provider(user) == "email"
    assert is_oauth_signup(user) is False


def test_is_oauth_from_identities_fallback() -> None:
    user = {
        "app_metadata": {},
        "identities": [{"provider": "linkedin_oidc"}],
    }
    assert primary_auth_provider(user) == "linkedin_oidc"
    assert is_oauth_signup(user) is True
