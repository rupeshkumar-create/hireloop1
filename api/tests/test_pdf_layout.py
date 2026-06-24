"""#16: layout-aware PDF extraction — words must rebuild in reading order."""

from __future__ import annotations

from hireloop_api.services.resume_parser import _words_to_lines


def _w(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + 10 * len(text), "top": top}


def test_words_group_into_lines_top_to_bottom() -> None:
    words = [
        _w("Engineer", 60, 100.5),  # same line as "Senior" (within tolerance)
        _w("Senior", 10, 100.0),
        _w("Acme", 10, 120.0),
    ]
    assert _words_to_lines(words) == "Senior Engineer\nAcme"


def test_column_isolation() -> None:
    # A right-column sidebar (skills) must NOT interleave with left-column
    # history when each column is rendered separately — the bug this fixes.
    left = [_w("Led", 10, 100), _w("payments", 50, 100), _w("team", 10, 115)]
    right = [_w("Python", 300, 100), _w("React", 300, 115)]
    assert _words_to_lines(left) == "Led payments\nteam"
    assert _words_to_lines(right) == "Python\nReact"


def test_empty_words() -> None:
    assert _words_to_lines([]) == ""
