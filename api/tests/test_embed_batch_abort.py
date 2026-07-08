"""Embedding batch must abort on OpenRouter 402 instead of looping forever."""

from __future__ import annotations

import pytest

from hireloop_api.services.embeddings import (
    EmbeddingService,
    InsufficientCreditsError,
    _is_insufficient_credits_error,
)


def test_is_insufficient_credits_detects_402_message() -> None:
    assert _is_insufficient_credits_error(
        Exception("Client error '402 Payment Required' for url '…/embeddings'")
    )
    assert _is_insufficient_credits_error(Exception("Insufficient credits. Add more"))
    assert not _is_insufficient_credits_error(Exception("timeout"))


@pytest.mark.asyncio
async def test_embed_jobs_batch_stops_after_consecutive_failures(monkeypatch) -> None:
    svc = EmbeddingService(api_key="test", db=None)  # type: ignore[arg-type]
    calls = {"n": 0}

    async def _fail(_job_id: str) -> bool:
        calls["n"] += 1
        return False

    monkeypatch.setattr(svc, "embed_job", _fail)
    results = await svc.embed_jobs_batch([f"job-{i}" for i in range(20)])
    assert calls["n"] == 3  # abort after consecutive failure streak
    assert sum(1 for ok in results.values() if ok) == 0
    assert len(results) == 20


@pytest.mark.asyncio
async def test_embed_jobs_batch_aborts_on_insufficient_credits(monkeypatch) -> None:
    svc = EmbeddingService(api_key="test", db=None)  # type: ignore[arg-type]
    calls = {"n": 0}

    async def _raise(_job_id: str) -> bool:
        calls["n"] += 1
        raise InsufficientCreditsError("OpenRouter insufficient credits (402)")

    monkeypatch.setattr(svc, "embed_job", _raise)
    results = await svc.embed_jobs_batch([f"job-{i}" for i in range(10)])
    assert calls["n"] == 1
    assert len(results) == 10
    assert all(ok is False for ok in results.values())
