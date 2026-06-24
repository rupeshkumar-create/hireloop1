"""
Résumé parser extracts the Indian-staple fields (CTC, notice period) so the
profile form / Aarya don't re-ask them. Pure regex tier — no key, no network.
"""

from __future__ import annotations

from hireloop_api.services.resume_parser import (
    ResumeParserService,
    _clean_int,
    _infer_ctc,
    _infer_notice_period,
)


def test_clean_int_handles_formats() -> None:
    assert _clean_int(1800000) == 1800000
    assert _clean_int("1,800,000") == 1800000
    assert _clean_int("18") == 18
    assert _clean_int(None) is None
    assert _clean_int(True) is None
    assert _clean_int(-5) is None


def test_infer_ctc_single_values() -> None:
    exp_min, exp_max, cur = _infer_ctc("Current CTC: 18 LPA\nExpected CTC: 25 LPA")
    assert cur == 1_800_000
    assert exp_min == 2_500_000
    assert exp_max is None


def test_infer_ctc_range() -> None:
    exp_min, exp_max, _ = _infer_ctc("Expected CTC: 12-15 LPA")
    assert exp_min == 1_200_000 and exp_max == 1_500_000


def test_infer_ctc_crore_and_decimal() -> None:
    exp_min, _, _ = _infer_ctc("Expected CTC: 1.2 Cr")
    assert exp_min == 12_000_000


def test_infer_notice_period() -> None:
    assert _infer_notice_period("Notice Period: 30 days") == 30
    assert _infer_notice_period("Notice period - 2 months") == 60
    assert _infer_notice_period("Notice Period: Immediate joiner") == 0
    assert _infer_notice_period("no mention here") is None


def test_parse_from_text_fills_ctc_and_notice() -> None:
    text = (
        "Asha Rao\nProduct Designer at LimeDock\n"
        "Bengaluru, Karnataka\n"
        "Current CTC: 18 LPA\nExpected CTC: 25 LPA\nNotice Period: 60 days\n"
        "Skills: Figma, UX research\n"
    )
    parsed = ResumeParserService.parse_from_text(text)
    assert parsed.current_ctc == 1_800_000
    assert parsed.expected_ctc_min == 2_500_000
    assert parsed.notice_period_days == 60
