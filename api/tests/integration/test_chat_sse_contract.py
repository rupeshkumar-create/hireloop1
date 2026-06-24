"""Integration: chat SSE contract — text/event-stream with data: lines."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from langchain_core.messages import AIMessage

from hireloop_api.config import Settings


class _FakeGraph:
    async def astream(
        self,
        initial_state: object,
        *,
        config: object = None,
        stream_mode: object = None,
    ) -> AsyncIterator[tuple[str, object]]:
        yield (
            "messages",
            (AIMessage(content="Hello from integration test"), {"langgraph_node": "agent"}),
        )


@pytest.mark.asyncio
async def test_chat_message_streams_sse(
    api_client: AsyncClient,
    integration_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hireloop_api.routes.chat.get_aarya_graph",
        lambda _settings: _FakeGraph(),
    )
    monkeypatch.setattr("hireloop_api.routes.chat.run_memory_update", lambda *a, **k: None)

    session_res = await api_client.post("/api/v1/chat/sessions")
    assert session_res.status_code == 201, session_res.text
    conversation_id = session_res.json()["conversation_id"]

    async with api_client.stream(
        "POST",
        f"/api/v1/chat/sessions/{conversation_id}/messages",
        json={"content": "Hi Aarya", "content_type": "text"},
    ) as response:
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")

        data_lines: list[str] = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data_lines.append(line[6:])

    assert data_lines, "expected at least one SSE data line"
    assert data_lines[-1] == "[DONE]"

    payloads = []
    for raw in data_lines[:-1]:
        if raw.startswith("{"):
            payloads.append(json.loads(raw))

    assert any(p.get("status") for p in payloads)
    assert any(p.get("text") == "Hello from integration test" for p in payloads)
