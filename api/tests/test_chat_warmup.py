import uuid

from hireloop_api.routes import chat


class WarmupDb:
    def __init__(self) -> None:
        self.candidate_id = uuid.uuid4()
        self.fetchval_calls = 0

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        return {"id": self.candidate_id}

    async def fetchval(self, query: str, *args: object) -> int:
        self.fetchval_calls += 1
        return 7


async def test_chat_warmup_does_not_prefetch_jobs_by_default(monkeypatch) -> None:
    db = WarmupDb()
    prefetch_called = False

    async def fake_completeness(db_arg: object, candidate_id: str) -> int:
        return 64

    async def fake_prefetch(db_arg: object, candidate_id: str, *, limit: int = 5) -> list[dict]:
        nonlocal prefetch_called
        prefetch_called = True
        return [{"title": "Should not load"}]

    monkeypatch.setattr(chat.CareerIntelligenceService, "get_completeness", fake_completeness)
    monkeypatch.setattr(chat, "_prefetch_top_jobs", fake_prefetch)

    out = await chat.chat_warmup(
        include_jobs=False,
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert out["profile_completeness"] == 64
    assert out["prefetched_jobs"] == []
    assert out["match_count"] == 0
    assert prefetch_called is False
    assert db.fetchval_calls == 0


async def test_chat_warmup_can_prefetch_jobs_when_explicitly_requested(monkeypatch) -> None:
    db = WarmupDb()
    prefetched = [{"title": "GTM Lead"}]

    async def fake_completeness(db_arg: object, candidate_id: str) -> int:
        return 72

    async def fake_market(db_arg: object, candidate_id: uuid.UUID) -> str:
        return "india"

    async def fake_prefetch(db_arg: object, candidate_id: str, *, limit: int = 5) -> list[dict]:
        assert candidate_id == str(db.candidate_id)
        assert limit == 5
        return prefetched

    monkeypatch.setattr(chat.CareerIntelligenceService, "get_completeness", fake_completeness)
    monkeypatch.setattr(chat, "fetch_candidate_market", fake_market)
    monkeypatch.setattr(chat, "_prefetch_top_jobs", fake_prefetch)

    out = await chat.chat_warmup(
        include_jobs=True,
        current_user={"id": str(uuid.uuid4())},
        db=db,  # type: ignore[arg-type]
    )

    assert out["profile_completeness"] == 72
    assert out["prefetched_jobs"] == prefetched
    assert out["match_count"] == 7
    assert db.fetchval_calls == 1
