"""
Tests for the print-ready document wrapper (P20). Turns the LLM's resume HTML
fragment into a clean A4 doc so the browser's "Save as PDF" yields a real file.
"""

from __future__ import annotations

from hireloop_api.services.resume_tailor import wrap_print_document


def test_wraps_fragment_in_full_document() -> None:
    doc = wrap_print_document(
        "<h1>Asha Rao</h1><h2>Summary</h2><p>Designer.</p>", title="Asha — Resume"
    )
    assert doc.startswith("<!DOCTYPE html>")
    assert "<h1>Asha Rao</h1>" in doc  # body preserved
    assert "@page" in doc and "A4" in doc  # print sizing
    assert "Save as PDF" in doc  # manual fallback button
    assert "Asha — Resume" in doc  # title seeds the PDF filename


def test_auto_print_script_toggles() -> None:
    on = wrap_print_document("<h1>X</h1>", auto_print=True)
    off = wrap_print_document("<h1>X</h1>", auto_print=False)
    assert "window.print" in on
    # The manual button always references print(); the auto load-listener only on.
    assert "addEventListener('load'" in on
    assert "addEventListener('load'" not in off


def test_lifts_body_from_full_document_no_nesting() -> None:
    full = "<!DOCTYPE html><html><head><style>x{}</style></head><body><h1>Y</h1></body></html>"
    doc = wrap_print_document(full)
    assert "<h1>Y</h1>" in doc
    assert doc.count("<body") == 1  # not nested
    assert "<style>x{}</style>" not in doc  # the model's <head> was dropped


def test_title_is_html_escaped() -> None:
    doc = wrap_print_document("<h1>X</h1>", title="<script>bad</script>")
    assert "<title><script>bad</script></title>" not in doc
    assert "&lt;script&gt;" in doc
