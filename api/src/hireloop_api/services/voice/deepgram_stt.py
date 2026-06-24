"""
Deepgram Speech-to-Text (batch) wrapper.

Used by:
  - POST /api/v1/voice/stt  (client uploads a short audio snippet)

We keep this server-side so:
  - we never expose API keys to the browser
  - STT works even when browser SpeechRecognition fails with "network"
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from hireloop_api.services.voice.domain_terms import INDIA_RECRUITING_KEYTERMS

logger = structlog.get_logger()

DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"


class DeepgramSTTError(RuntimeError):
    pass


def _extract_transcript(payload: dict[str, Any]) -> str:
    """
    Deepgram response shape:
      results.channels[0].alternatives[0].transcript
    """
    try:
        channels = payload.get("results", {}).get("channels", [])
        if not channels:
            return ""
        alts = channels[0].get("alternatives", [])
        if not alts:
            return ""
        return str(alts[0].get("transcript") or "").strip()
    except Exception:
        return ""


async def transcribe_audio(
    *,
    api_key: str,
    audio_bytes: bytes,
    content_type: str,
    model: str = "nova-3",
    language: str | None = "en",
    keyterms: list[str] | None = None,
) -> str:
    """
    Transcribe a short audio snippet.
    Docs: https://developers.deepgram.com/docs/nova-quickstart

    `keyterms` are nova-3 keyterm prompts (defaults to the India-recruiting set)
    that boost recognition of money units, city/company names, and skills.
    """
    if keyterms is None:
        keyterms = INDIA_RECRUITING_KEYTERMS

    # List of tuples so multiple `keyterm` values can be sent.
    params: list[tuple[str, str]] = [
        ("model", model),
        ("smart_format", "true"),
        ("punctuate", "true"),
    ]
    if language:
        params.append(("language", language))
    params.extend(("keyterm", term) for term in keyterms)

    # Deepgram expects a base media type in Content-Type; strip codec params.
    ct = (content_type or "").split(";", 1)[0].strip() or "application/octet-stream"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": ct,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            DEEPGRAM_LISTEN_URL,
            headers=headers,
            params=params,
            content=audio_bytes,
        )

    if resp.status_code != 200:
        logger.error(
            "deepgram_stt_failed",
            status=resp.status_code,
            body=resp.text[:500],
        )
        raise DeepgramSTTError(f"Deepgram STT failed: {resp.status_code}")

    payload: dict[str, Any] = resp.json()
    transcript = _extract_transcript(payload)
    return transcript
