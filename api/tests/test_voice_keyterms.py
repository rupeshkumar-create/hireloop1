"""
Tests for Deepgram keyterm prompting wiring (voice accuracy).

No network: we only assert the request URL/params carry the India-recruiting
keyterms so nova-3 boosts money units, city/company names, and skills.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from hireloop_api.services.voice.deepgram_live import build_live_url
from hireloop_api.services.voice.domain_terms import INDIA_RECRUITING_KEYTERMS


def test_live_url_includes_keyterms_by_default() -> None:
    url = build_live_url(sample_rate=48000)
    qs = parse_qs(urlparse(url).query)
    assert qs["model"] == ["nova-3"]
    # One keyterm= entry per term, and key India terms are present.
    assert "LPA" in qs["keyterm"]
    assert "Bengaluru" in qs["keyterm"]
    assert len(qs["keyterm"]) == len(INDIA_RECRUITING_KEYTERMS)


def test_live_url_accepts_custom_keyterms() -> None:
    url = build_live_url(sample_rate=16000, keyterms=["Kubernetes", "Razorpay"])
    qs = parse_qs(urlparse(url).query)
    assert sorted(qs["keyterm"]) == ["Kubernetes", "Razorpay"]
    assert qs["sample_rate"] == ["16000"]


def test_domain_terms_are_unique_and_nonempty() -> None:
    assert INDIA_RECRUITING_KEYTERMS
    assert all(t.strip() for t in INDIA_RECRUITING_KEYTERMS)
    assert len(INDIA_RECRUITING_KEYTERMS) == len(set(INDIA_RECRUITING_KEYTERMS))
