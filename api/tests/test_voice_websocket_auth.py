"""Voice WebSocket credentials never travel in request URLs."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from hireloop_api.config import Settings
from hireloop_api.routes import voice


def _auth_protocol(token: str) -> str:
    encoded = base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")
    return f"auth.{encoded}"


def test_extracts_token_from_private_subprotocol_without_echoing_it() -> None:
    header = f"{voice.VOICE_WEBSOCKET_PROTOCOL}, {_auth_protocol('header.payload.signature')}"
    assert voice._extract_voice_auth_token(header) == "header.payload.signature"


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "auth.not-base64!",
        "auth.",
        "hireschema.voice.v1, auth.dG9rZW4=",
        "hireschema.voice.v1, auth.dG9r+W4",
        "hireschema.voice.v1, auth.dG9r/W4",
        "hireschema.voice.v1, auth.dG9rZW4,",
        "hireschema.voice.v1, hireschema.voice.v1, auth.dG9rZW4",
        "other.protocol, auth.dG9rZW4",
        "hireschema.voice.v1, auth.dG9rZW4, auth.b3RoZXI",
        f"hireschema.voice.v1, auth.{'YQ' * 5000}",
    ],
)
def test_rejects_missing_malformed_duplicate_or_oversized_auth_protocols(
    header: str | None,
) -> None:
    assert voice._extract_voice_auth_token(header) is None


class _FakeWebSocket:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.query_params = {"token": "legacy-url-secret", "sr": "48000"}
        self.client = SimpleNamespace(host="127.0.0.1")
        self.closed: tuple[int, str] | None = None
        self.accepted_protocol: str | None = None
        self.messages: list[dict[str, str]] = []

    async def close(self, *, code: int, reason: str = "") -> None:
        self.closed = (code, reason)

    async def accept(self, *, subprotocol: str) -> None:
        self.accepted_protocol = subprotocol

    async def send_json(self, message: dict[str, str]) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_voice_stream_does_not_fall_back_to_query_string_token(monkeypatch) -> None:
    socket = _FakeWebSocket()
    auth_called = False

    async def fake_fetch(*_args: object) -> None:
        nonlocal auth_called
        auth_called = True

    monkeypatch.setattr(voice, "_fetch_supabase_user", fake_fetch)
    settings = Settings(_env_file=None, environment="test", deepgram_api_key="configured")

    await voice.voice_stream(socket, settings)  # type: ignore[arg-type]

    assert auth_called is False
    assert socket.closed == (1008, "Authentication required")


@pytest.mark.asyncio
async def test_voice_stream_echoes_only_fixed_non_secret_protocol(monkeypatch) -> None:
    from hireloop_api.services.voice import deepgram_live

    socket = _FakeWebSocket()
    secret = "header.payload.signature"
    socket.headers["sec-websocket-protocol"] = (
        f"{voice.VOICE_WEBSOCKET_PROTOCOL}, {_auth_protocol(secret)}"
    )

    async def fake_fetch(*_args: object) -> None:
        return None

    async def unavailable_deepgram(**_kwargs: object) -> None:
        raise RuntimeError("offline")

    monkeypatch.setattr(voice, "_fetch_supabase_user", fake_fetch)
    monkeypatch.setattr(deepgram_live, "connect_deepgram_live", unavailable_deepgram)
    settings = Settings(_env_file=None, environment="test", deepgram_api_key="configured")

    await voice.voice_stream(socket, settings)  # type: ignore[arg-type]

    assert socket.accepted_protocol == voice.VOICE_WEBSOCKET_PROTOCOL
    assert secret not in socket.accepted_protocol
