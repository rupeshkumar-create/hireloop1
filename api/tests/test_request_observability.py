"""Candidate-flow requests carry non-PII correlation metadata."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from starlette.requests import Request

from hireloop_api.main import _request_timing, app


def test_every_response_has_request_id() -> None:
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert str(uuid.UUID(response.headers["X-Request-ID"])) == response.headers["X-Request-ID"]


def _request(path: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers or [],
            "scheme": "https",
            "server": ("api.hireschema.com", 443),
            "client": ("127.0.0.1", 1234),
        }
    )


@pytest.mark.asyncio
async def test_tracked_request_forwards_id_and_logs_retry_metadata() -> None:
    request_id = str(uuid.uuid4())
    request = _request(
        "/api/v1/resumes/upload",
        [(b"x-request-id", request_id.encode()), (b"x-retry-attempt", b"2")],
    )

    async def call_next(_request: Request) -> Response:
        return Response(status_code=201)

    with patch("hireloop_api.main.logger") as mock_logger:
        response = await _request_timing(request, call_next)

    assert response.headers["X-Request-ID"] == request_id
    tracked = [
        call for call in mock_logger.info.call_args_list if call.args == ("candidate_flow_request",)
    ]
    assert len(tracked) == 1
    fields = tracked[0].kwargs
    assert fields["request_id"] == request_id
    assert fields["retry_attempt"] == "2"
    assert fields["path"] == "/api/v1/resumes/upload"
    assert fields["status_code"] == 201
    assert "body" not in fields
