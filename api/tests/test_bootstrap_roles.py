from hireloop_api.services.bootstrap_roles import resolve_bootstrap_role


def test_recruiter_tab_always_recruiter() -> None:
    assert resolve_bootstrap_role("recruiter", has_recruiter=False) == "recruiter"


def test_existing_recruiter_not_downgraded() -> None:
    assert resolve_bootstrap_role("candidate", has_recruiter=True) == "recruiter"


def test_new_candidate_stays_candidate() -> None:
    assert resolve_bootstrap_role("candidate", has_recruiter=False) == "candidate"
