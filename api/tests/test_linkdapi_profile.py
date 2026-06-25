from hireloop_api.services.linkdapi_profile import _infer_years_experience


def test_infer_years_experience_from_earliest_role() -> None:
    roles = [
        {"start_date": "2018", "end_date": "2021"},
        {"start_date": "2021", "end_date": None},
    ]
    years = _infer_years_experience(roles)
    assert years is not None
    assert years >= 6


def test_infer_years_experience_empty_roles() -> None:
    assert _infer_years_experience([]) is None
