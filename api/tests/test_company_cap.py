"""#39: cap a company to N roles on the opening screen."""

from __future__ import annotations

from hireloop_api.services.ranking import cap_company_repeats


def _job(jid: str, company: str) -> dict:
    return {"job_id": jid, "company_name": company}


def test_caps_company_within_screen() -> None:
    items = [
        _job("1", "Acme"),
        _job("2", "Acme"),
        _job("3", "Acme"),  # 3rd Acme — should be pushed below the screen
        _job("4", "Beta"),
        _job("5", "Gamma"),
    ]
    out = cap_company_repeats(items, screen_size=4, max_per_company=2)
    screen = [j["job_id"] for j in out[:4]]
    assert screen.count("3") == 0  # the 3rd Acme is not on the screen
    assert "3" in [j["job_id"] for j in out]  # but still present overall
    # First screen has ≤2 Acme.
    acme_on_screen = sum(1 for j in out[:4] if j["company_name"] == "Acme")
    assert acme_on_screen <= 2


def test_no_company_name_is_stable() -> None:
    items = [_job("1", ""), _job("2", ""), _job("3", "")]
    out = cap_company_repeats(items, screen_size=8)
    assert [j["job_id"] for j in out] == ["1", "2", "3"]


def test_below_fold_untouched() -> None:
    # Past the screen, repeats are allowed (no reordering of the tail).
    items = [_job(str(i), "Acme") for i in range(10)]
    out = cap_company_repeats(items, screen_size=2, max_per_company=2)
    assert [j["job_id"] for j in out[:2]] == ["0", "1"]
    assert len(out) == 10
