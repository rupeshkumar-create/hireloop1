"""
Deepgram Aura Text-to-Speech wrapper.

Used by:
  - POST /api/v1/voice/tts  (Aarya's reply text → spoken audio)

Why server-side (vs the browser SpeechSynthesis API)?
  Browser TTS can only use voices installed on the user's OS, so the voice is
  inconsistent across devices and rarely a natural Indian-sounding female. Aura
  gives us one consistent, warm female voice everywhere — and keeps the Deepgram
  key off the client (same as STT).

Returns MP3 bytes that the browser plays via an <audio> element.
Docs: https://developers.deepgram.com/docs/text-to-speech
"""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()

DEEPGRAM_SPEAK_URL = "https://api.deepgram.com/v1/speak"

# Aura's warm female voice. Aura-1 "asteria" is broadly available and sounds
# natural and friendly — the closest fit for Aarya's persona. Override via
# DEEPGRAM_TTS_MODEL if a different (e.g. Aura-2) voice is provisioned.
DEFAULT_AURA_MODEL = "aura-asteria-en"

# Deepgram /speak rejects very long single requests; keep snippets reasonable.
MAX_TTS_CHARS = 1800


class DeepgramTTSError(RuntimeError):
    pass


async def synthesize_speech(
    *,
    api_key: str,
    text: str,
    model: str = DEFAULT_AURA_MODEL,
) -> bytes:
    """
    Synthesize `text` into MP3 audio using Deepgram Aura.

    The caller is responsible for sanitizing `text` (stripping emoji/markdown)
    before passing it in, so nothing odd gets read aloud.
    """
    clean = (text or "").strip()
    if not clean:
        raise DeepgramTTSError("Empty text for TTS")
    if len(clean) > MAX_TTS_CHARS:
        clean = clean[:MAX_TTS_CHARS]

    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }
    # encoding=mp3 → a compact, browser-friendly audio container.
    params = {"model": model, "encoding": "mp3"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            DEEPGRAM_SPEAK_URL,
            headers=headers,
            params=params,
            json={"text": clean},
        )

    if resp.status_code != 200:
        logger.error(
            "deepgram_tts_failed",
            status=resp.status_code,
            body=resp.text[:500],
            model=model,
        )
        raise DeepgramTTSError(f"Deepgram TTS failed: {resp.status_code}")

    audio = resp.content
    if not audio:
        raise DeepgramTTSError("Deepgram TTS returned empty audio")
    return audio
