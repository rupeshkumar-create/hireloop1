from hireloop_api.services.recruiter_search import (
    _candidate_search_clause,
    _live_platform_candidate_sql,
)


def test_live_platform_sql_includes_active_profile_gates() -> None:
    sql = _live_platform_candidate_sql(recruiter_user_param="rec.user_id")
    assert "is_active = TRUE" in sql
    assert "visibility" in sql
    assert "rec.user_id" in sql
    assert "onboarding_complete" in sql


def test_candidate_search_clause_binds_explicit_param() -> None:
    clause = _candidate_search_clause("$4")
    assert "$4" in clause
    assert "ILIKE" in clause
