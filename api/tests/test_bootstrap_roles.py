from hireloop_api.services.bootstrap_roles import can_switch_roles, resolve_bootstrap_role


def test_recruiter_tab_always_recruiter() -> None:
    assert resolve_bootstrap_role("recruiter", has_recruiter=False) == "recruiter"


def test_existing_recruiter_not_downgraded() -> None:
    assert resolve_bootstrap_role("candidate", has_recruiter=True) == "recruiter"


def test_new_candidate_stays_candidate() -> None:
    assert resolve_bootstrap_role("candidate", has_recruiter=False) == "candidate"


def test_can_switch_roles_requires_both_profiles() -> None:
    assert can_switch_roles(True, True) is True
    assert can_switch_roles(True, False) is False
    assert can_switch_roles(False, True) is False
    assert can_switch_roles(False, False) is False
