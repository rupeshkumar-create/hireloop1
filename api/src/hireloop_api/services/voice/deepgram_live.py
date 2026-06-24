"""
Deepgram Speech-to-Text (live streaming) wrapper.

Used by:
  - WS /api/v1/voice/stream  (browser streams raw PCM, gets word-by-word
    interim + final transcripts back in real time)

Why streaming (vs the batch /stt endpoint)?
  Batch transcription only returns text once the whole snippet is uploaded,
  so the user sees nothing until they stop talking. The live endpoint emits
  `interim_results` as the user speaks, which the voice UI shows as captions.

We keep this server-side so the Deepgram key never reaches the browser. The
FastAPI WebSocket route proxies bytes both ways:
    browser mic (linear16 PCM) → here → Deepgram live → transcripts → browser
"""

from __future__ import annotations

from urllib.parse import urlencode

import structlog
from websockets.asyncio.client import ClientConnection, connect

from hireloop_api.services.voice.domain_terms import INDIA_RECRUITING_KEYTERMS

logger = structlog.get_logger()

DEEPGRAM_LIVE_URL = "wss://api.deepgram.com/v1/listen"


def build_live_url(
    *,
    sample_rate: int,
    model: str = "nova-3",
    language: str = "multi",
    keyterms: list[str] | None = None,
) -> str:
    """
    Build the Deepgram live-streaming URL.

    The browser sends mono linear16 PCM at its native AudioContext sample rate
    (typically 48000), so we pass `encoding=linear16` + the real `sample_rate`
    and skip resampling on either side.

    `interim_results` is what gives us word-by-word captions; `endpointing`
    and `utterance_end_ms` make Deepgram emit final segments + UtteranceEnd
    events at natural pauses.
    """
    params: dict[str, object] = {
        "model": model,
        "language": language,
        "smart_format": "true",
        "punctuate": "true",
        "interim_results": "true",
        "encoding": "linear16",
        "sample_rate": str(sample_rate),
        "channels": "1",
        "endpointing": "300",
        "utterance_end_ms": "1000",
        # nova-3 keyterm prompting → better recognition of money units, Indian
        # city/company names, and skills (doseq emits one keyterm= per value).
        "keyterm": INDIA_RECRUITING_KEYTERMS if keyterms is None else keyterms,
    }
    return f"{DEEPGRAM_LIVE_URL}?{urlencode(params, doseq=True)}"


async def connect_deepgram_live(*, api_key: str, sample_rate: int) -> ClientConnection:
    """
    Open a live-streaming connection to Deepgram.

    Caller is responsible for closing the returned connection. Raises if the
    handshake fails (bad key, network) — the route translates that into a clean
    WS close for the browser.
    """
    url = build_live_url(sample_rate=sample_rate)
    return await connect(
        url,
        additional_headers={"Authorization": f"Token {api_key}"},
        # Keep the socket responsive; Deepgram pings on its own cadence.
        open_timeout=10,
        max_size=None,
    )
