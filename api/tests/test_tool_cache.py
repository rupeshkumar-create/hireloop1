import pytest

from hireloop_api.services.tool_cache import cache_key, get_cached, set_cached


def test_tool_cache_roundtrip() -> None:
    key = cache_key("session-1", "profile_read", {})
    assert get_cached(key) is None
    set_cached(key, {"full_name": "Ada"})
    assert get_cached(key) == {"full_name": "Ada"}


def test_tool_cache_key_includes_args() -> None:
    k1 = cache_key("s1", "job_search", {"query": "engineer"})
    k2 = cache_key("s1", "job_search", {"query": "designer"})
    assert k1 != k2
