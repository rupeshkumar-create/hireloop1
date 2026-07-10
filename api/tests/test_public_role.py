from hireloop_api.services.public_role import _slug_base, public_role_path


def test_slug_base_from_title() -> None:
    assert (
        _slug_base("Go-To-Market Lead — AI Resume Builder") == "go-to-market-lead-ai-resume-builder"
    )
    assert _slug_base("") == "role"


def test_public_role_path() -> None:
    assert public_role_path("gtm-lead-a1b2c3") == "/r/gtm-lead-a1b2c3"
    assert public_role_path(None) is None
