from hireloop_api.services.recruiter_profile import (
    build_hiring_focus_from_roles,
    resolve_company_name_from_roles,
)


def test_build_hiring_focus_from_roles_joins_titles_and_locations() -> None:
    focus = build_hiring_focus_from_roles(
        [
            {
                "title": "Senior Backend Engineer",
                "location_city": "Bangalore",
                "location_state": "KA",
                "hiring_brief": "Python, Postgres, AWS",
            },
            {
                "title": "Product Manager",
                "location_city": None,
                "location_state": None,
                "jd_text": "Own roadmap for hiring tools.",
            },
        ]
    )
    assert focus is not None
    assert "Senior Backend Engineer (Bangalore, KA)" in focus
    assert "Python, Postgres, AWS" in focus
    assert "Product Manager" in focus
    assert "Own roadmap for hiring tools." in focus


def test_resolve_company_name_prefers_role_company_over_placeholder() -> None:
    name = resolve_company_name_from_roles(
        {"name": "My Company"},
        [{"company_name": "Acme India Pvt Ltd", "title": "Engineer"}],
    )
    assert name == "Acme India Pvt Ltd"
