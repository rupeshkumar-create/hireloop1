import uuid

from hireloop_api.routes import chat
from hireloop_api.services.background_jobs import CAREER_PATH_INGEST


class EnqueueDb:
    pass


async def test_chat_job_search_enqueues_force_refresh_for_requested_title(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_enqueue(db: object, **kwargs: object) -> uuid.UUID:
        captured.update(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr("hireloop_api.services.background_jobs.enqueue_job", fake_enqueue)

    await chat._enqueue_live_job_ingest_for_search(
        EnqueueDb(),  # type: ignore[arg-type]
        candidate_id="11111111-1111-1111-1111-111111111111",
        search_title="UI/UX Designer",
        location_city="Bengaluru",
    )

    assert captured["kind"] == CAREER_PATH_INGEST
    assert captured["payload"] == {
        "candidate_id": "11111111-1111-1111-1111-111111111111",
        "derive_from_candidate": True,
        "requested_titles": ["UI/UX Designer"],
        "locations": ["Bengaluru"],
        "force_refresh": True,
    }
    assert captured["idempotency_key"] == (
        "career_path_ingest:11111111-1111-1111-1111-111111111111:ui-ux-designer"
    )
