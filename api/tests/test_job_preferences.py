"""Tests for remote / on-site job preference helpers."""

from hireloop_api.services.job_preferences import (
    REMOTE_PREFERENCE_ANY,
    REMOTE_PREFERENCE_ONSITE_ONLY,
    REMOTE_PREFERENCE_REMOTE_ONLY,
    normalize_remote_preference,
    remote_filter_sql,
    resolve_remote_preference,
)


def test_normalize_defaults_to_any() -> None:
    assert normalize_remote_preference(None) == REMOTE_PREFERENCE_ANY
    assert normalize_remote_preference("invalid") == REMOTE_PREFERENCE_ANY


def test_resolve_prefers_override() -> None:
    assert (
        resolve_remote_preference(stored="any", override="onsite_only")
        == REMOTE_PREFERENCE_ONSITE_ONLY
    )
    assert (
        resolve_remote_preference(stored="remote_only", override=None)
        == REMOTE_PREFERENCE_REMOTE_ONLY
    )


def test_remote_filter_sql() -> None:
    assert remote_filter_sql(REMOTE_PREFERENCE_ANY) == ""
    assert "is_remote = TRUE" in remote_filter_sql(REMOTE_PREFERENCE_REMOTE_ONLY)
    assert "is_remote = FALSE" in remote_filter_sql(REMOTE_PREFERENCE_ONSITE_ONLY)
