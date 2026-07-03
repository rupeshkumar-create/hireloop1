"""Tests for display name resolution."""

from hireloop_api.services.display_name import looks_like_email_derived_name, pick_display_name


def test_looks_like_email_derived_exact_local_part() -> None:
    assert looks_like_email_derived_name("rupesh.kumar", "rupesh.kumar@example.com")


def test_looks_like_email_derived_spaces_instead_of_dots() -> None:
    assert looks_like_email_derived_name("rupesh kumar", "rupesh.kumar@example.com")


def test_looks_like_email_derived_empty_name() -> None:
    assert looks_like_email_derived_name(None, "rupesh.kumar@example.com")
    assert looks_like_email_derived_name("", "rupesh.kumar@example.com")


def test_real_name_not_email_derived() -> None:
    assert not looks_like_email_derived_name("Rupesh Kumar", "rupesh.kumar@example.com")


def test_pick_display_name_prefers_resume_over_email_local() -> None:
    assert (
        pick_display_name(
            user_full_name="rupesh.kumar",
            email="rupesh.kumar@example.com",
            resume_full_name="Rupesh Kumar",
        )
        == "Rupesh Kumar"
    )


def test_pick_display_name_keeps_real_user_name() -> None:
    assert (
        pick_display_name(
            user_full_name="Rupesh Kumar",
            email="rupesh.kumar@example.com",
            resume_full_name="R. Kumar",
        )
        == "Rupesh Kumar"
    )


def test_pick_display_name_falls_back_to_linkedin() -> None:
    assert (
        pick_display_name(
            user_full_name="rupesh.kumar",
            email="rupesh.kumar@example.com",
            linkedin_full_name="Rupesh Kumar",
        )
        == "Rupesh Kumar"
    )
