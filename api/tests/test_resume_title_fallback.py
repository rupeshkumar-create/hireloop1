"""
current_title must be populated from work history when the parser leaves the
'current' entry's title blank — it feeds both the profile and the matching
engine's title-affinity signal.
"""

from __future__ import annotations

from hireloop_api.services.resume_parser import WorkExperience, _first_work_title


def test_prefers_current_role_title() -> None:
    work = [
        WorkExperience(company="OldCo", title="Junior Designer", is_current=False),
        WorkExperience(company="LimeDock", title="Product Designer", is_current=True),
    ]
    assert _first_work_title(work) == "Product Designer"


def test_falls_back_when_current_title_blank() -> None:
    # The current role parsed as company-only ("Founder, LimeDock") → title blank;
    # fall back to the next entry that has a title.
    work = [
        WorkExperience(company="LimeDock", title=None, is_current=True),
        WorkExperience(company="Acme", title="Senior Engineer", is_current=False),
    ]
    assert _first_work_title(work) == "Senior Engineer"


def test_uses_first_entry_when_none_current() -> None:
    work = [WorkExperience(company="Acme", title="UX Designer")]
    assert _first_work_title(work) == "UX Designer"


def test_none_when_no_titles() -> None:
    assert _first_work_title([]) is None
    assert _first_work_title([WorkExperience(company="Acme", title="  ")]) is None
