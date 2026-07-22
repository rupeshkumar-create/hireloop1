"""
Voice routes.

STT (mic → text) and TTS (Aarya's reply → speech) are both handled server-side
via Deepgram: STT avoids browser SpeechRecognition `error=network` issues, and
TTS (Aura) gives one consistent natural female voice across all devices instead
of whatever voices the user's OS happens to ship. The client falls back to the
Web Speech API for both when no Deepgram key is configured. The LLM text
round-trip still goes through /chat/sessions/{id}/messages.

POST /api/v1/voice/stt        → Deepgram batch transcription (server-side)
WS   /api/v1/voice/stream     → Deepgram live STT (word-by-word captions)
POST /api/v1/voice/tts        → Deepgram Aura speech synthesis (server-side)
POST /api/v1/voice/sessions   → record a completed voice session
GET  /api/v1/voice/sessions   → list candidate's voice sessions

The /matches gate checks:
  voice_sessions WHERE candidate_id = ? AND status = 'completed'
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
import uuid

import asyncpg
import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import Response
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import _fetch_supabase_user, get_db, get_phone_verified_user
from hireloop_api.routes.voice_sessions import (
    CompleteCareerCallRequest,
    _complete_owned_career_call,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/voice", tags=["voice"])

ALLOWED_AUDIO_MIME_TYPES = {
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/ogg",
    "audio/ogg;codecs=opus",
    "video/webm",
    "video/webm;codecs=opus",
}
MAX_AUDIO_BYTES = 6 * 1024 * 1024  # 6MB (short snippets only)


# ── Speech text sanitization ───────────────────────────────────────────────────
# Mirror of the client-side sanitizeForSpeech() — strip anything that a TTS
# voice would read out literally ("smiley face", "asterisk", "hash") so Aarya's
# spoken replies sound natural. Defense in depth: the agent's voice_mode prompt
# already avoids emoji/markdown, but we never trust that fully.

_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # symbols, emoji, pictographs, supplemental
    "\U00002600-\U000027bf"  # misc symbols + dingbats
    "\U0001f1e6-\U0001f1ff"  # regional indicators (flags)
    "\U00002190-\U000021ff"  # arrows
    "\U00002300-\U000023ff"  # technical (incl. ⌚⏰)
    "\U00002b00-\U00002bff"  # misc symbols & arrows
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "]",
    flags=re.UNICODE,
)
_EMOTICON_RE = re.compile(r"(^|\s)[:;=8][-^]?[)\](\[dpDP3]")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BULLET_RE = re.compile(r"(?m)^[ \t]*[-•·*]\s+")
_NUMBERED_RE = re.compile(r"(?m)^[ \t]*\d+[.)]\s+")
_SYMBOL_RE = re.compile(r"[*_`#>~|]")


def _sanitize_for_speech(text: str) -> str:
    """Strip emoji, emoticons, and markdown so nothing odd gets read aloud."""
    if not text:
        return ""
    out = _MD_LINK_RE.sub(r"\1", text)
    out = _EMOJI_RE.sub("", out)
    out = _EMOTICON_RE.sub(r"\1", out)
    out = _BULLET_RE.sub("", out)
    out = _NUMBERED_RE.sub("", out)
    out = _SYMBOL_RE.sub("", out)
    out = re.sub(r"\n{2,}", ". ", out)
    out = out.replace("\n", ", ")
    out = re.sub(r"\s+,", ".", out)
    out = re.sub(r"\s+([.,!?])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


# ── Session recording ─────────────────────────────────────────────────────────


class VoiceSessionCreate(BaseModel):
    """Sent by the client when a voice session ends."""

    duration_seconds: int = 0
    # Maps to voice_sessions.status CHECK: 'completed' | 'cancelled'
    status: str = "completed"
    conversation_id: str | None = None
    session_id: uuid.UUID | None = None


class VoiceSessionResponse(BaseModel):
    id: str
    status: str
    duration_seconds: int


class VoiceSTTResponse(BaseModel):
    transcript: str


class VoiceConfigResponse(BaseModel):
    # "deepgram" → server-side STT (DEEPGRAM_API_KEY set); the client uploads
    #              audio to POST /voice/stt.
    # "browser"  → no server STT configured; the client should use the native
    #              Web Speech API (SpeechRecognition) so voice still works with
    #              zero extra keys. The LLM brain stays OpenRouter either way.
    stt_provider: str
    # "deepgram" → server-side Aura TTS (POST /voice/tts) for a consistent,
    #              natural female voice across devices.
    # "browser"  → no key; fall back to SpeechSynthesis on the client.
    tts_provider: str


class VoiceTTSRequest(BaseModel):
    text: str


@router.get("/config", response_model=VoiceConfigResponse, status_code=200)
async def voice_config(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
) -> VoiceConfigResponse:
    """Tell the client which STT/TTS path to use, so voice works with or without
    a Deepgram key. OpenRouter has no speech API, so STT/TTS is always Deepgram
    (server) or the browser's Web Speech API (client) — never OpenRouter."""
    provider = "deepgram" if settings.deepgram_api_key else "browser"
    return VoiceConfigResponse(stt_provider=provider, tts_provider=provider)


@router.post("/stt", response_model=VoiceSTTResponse, status_code=200)
async def speech_to_text(
    file: UploadFile = File(..., description="Audio snippet (webm/wav/mp4), max 6MB"),
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
) -> VoiceSTTResponse:
    """
    Transcribe a short audio snippet via Deepgram (Nova-3).

    This avoids the browser SpeechRecognition "network" failure mode and
    keeps API keys off the client.
    """
    if not settings.deepgram_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice STT is not configured (missing DEEPGRAM_API_KEY).",
        )

    content_type = (file.content_type or "").strip()
    if content_type not in ALLOWED_AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio type '{content_type}'.",
        )

    audio_bytes = await file.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio snippet too large. Please keep it under 6MB.",
        )

    from hireloop_api.services.voice.deepgram_stt import DeepgramSTTError, transcribe_audio

    try:
        transcript = await transcribe_audio(
            api_key=settings.deepgram_api_key,
            audio_bytes=audio_bytes,
            content_type=content_type,
            model="nova-3",
            language="multi",
        )
    except DeepgramSTTError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Voice transcription failed. Please try again.",
        ) from exc

    if not transcript:
        # Keep it non-fatal; return empty transcript so the client can prompt retry.
        return VoiceSTTResponse(transcript="")

    return VoiceSTTResponse(transcript=transcript)


@router.post("/tts", status_code=200)
async def text_to_speech(
    body: VoiceTTSRequest,
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    """
    Synthesize Aarya's reply text into spoken audio via Deepgram Aura.

    Returns audio/mpeg (MP3) bytes the browser plays directly. We sanitize the
    text server-side too (defense in depth) so emoji/markdown never get read
    aloud, then hand it to Aura's warm female voice.
    """
    if not settings.deepgram_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice TTS is not configured (missing DEEPGRAM_API_KEY).",
        )

    spoken = _sanitize_for_speech(body.text)
    if not spoken:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to speak.",
        )

    from hireloop_api.services.voice.deepgram_tts import DeepgramTTSError, synthesize_speech

    try:
        audio = await synthesize_speech(
            api_key=settings.deepgram_api_key,
            text=spoken,
            model=settings.deepgram_tts_model,
        )
    except DeepgramTTSError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Voice synthesis failed. Please try again.",
        ) from exc

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/sessions", response_model=VoiceSessionResponse, status_code=201)
async def create_voice_session(
    body: VoiceSessionCreate,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Record a completed voice session.

    Writing this row is the trigger that unlocks the /matches gate
    (voice_sessions WHERE candidate_id = ? AND status = 'completed').

    Column mapping (migrations/20240101000400):
      session_type = 'career_chat'
      duration_secs ← body.duration_seconds
      started_at = ended_at = NOW()
    """
    status = body.status if body.status in ("completed", "cancelled") else "completed"

    if body.session_id and body.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Use the voice-session cancellation endpoint for an existing session",
        )

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    if body.session_id and status == "completed":
        completed = await _complete_owned_career_call(
            session_id=body.session_id,
            candidate_id=candidate["id"],
            body=CompleteCareerCallRequest(
                completion_reason="candidate_ended",
                duration_seconds=min(max(0, body.duration_seconds), 16 * 60),
            ),
            db=db,
        )
        return {
            "id": completed.id,
            "status": completed.status,
            "duration_seconds": body.duration_seconds,
        }

    session_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.voice_sessions (
          id, candidate_id, session_type, status,
          duration_secs, started_at, ended_at
        )
        VALUES ($1, $2, 'career_chat', $3, $4, NOW(), NOW())
        """,
        session_id,
        candidate["id"],
        status,
        max(0, body.duration_seconds),
    )
    logger.info(
        "voice_session_recorded",
        candidate_id=str(candidate["id"]),
        duration_seconds=body.duration_seconds,
        status=status,
    )
    return {
        "id": str(session_id),
        "status": status,
        "duration_seconds": body.duration_seconds,
    }


# ── Live streaming STT (WebSocket proxy → Deepgram live) ───────────────────────

# Clamp client-reported sample rates to a sane range. Browser AudioContext is
# almost always 44100 or 48000; we pass it straight through to Deepgram.
_MIN_SAMPLE_RATE = 8000
_MAX_SAMPLE_RATE = 48000
VOICE_WEBSOCKET_PROTOCOL = "hireschema.voice.v1"
_VOICE_AUTH_PROTOCOL_PREFIX = "auth."
_MAX_VOICE_ACCESS_TOKEN_BYTES = 4096


def _extract_voice_auth_token(protocol_header: str | None) -> str | None:
    """Decode a private auth subprotocol without selecting it in the response."""
    if not protocol_header:
        return None
    protocols = [part.strip() for part in protocol_header.split(",") if part.strip()]
    if VOICE_WEBSOCKET_PROTOCOL not in protocols:
        return None
    auth_protocols = [
        protocol for protocol in protocols if protocol.startswith(_VOICE_AUTH_PROTOCOL_PREFIX)
    ]
    if len(auth_protocols) != 1 or len(protocols) != 2:
        return None
    encoded = auth_protocols[0][len(_VOICE_AUTH_PROTOCOL_PREFIX) :]
    max_encoded_length = (_MAX_VOICE_ACCESS_TOKEN_BYTES * 4 + 2) // 3
    if not encoded or len(encoded) > max_encoded_length:
        return None
    try:
        padding = "=" * (-len(encoded) % 4)
        raw = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
        token = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if not token or len(raw) > _MAX_VOICE_ACCESS_TOKEN_BYTES:
        return None
    if any(char.isspace() for char in token):
        return None
    return token


@router.websocket("/stream")
async def voice_stream(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Real-time STT: the browser streams mono linear16 PCM frames; we proxy them
    to Deepgram's live endpoint and relay interim + final transcripts back so
    the voice UI can show word-by-word captions.

    Auth: browsers can't set Authorization on the WS handshake, so they offer a
    fixed application subprotocol plus a private base64url auth subprotocol.
    Only the fixed protocol is selected in the response. The client sends
    `?sr=<sample_rate>` (its AudioContext rate) so we avoid resampling.

    Protocol (client → server):
      - binary frames: raw linear16 PCM (little-endian, mono)
      - text "CloseStream": flush + finalize (sent right before stopping)
    Protocol (server → client), JSON text frames:
      - {"transcript": str, "is_final": bool, "speech_final": bool}
      - {"utterance_end": true}
      - {"error": str}  (then the socket closes)
    """
    token = _extract_voice_auth_token(websocket.headers.get("sec-websocket-protocol"))
    try:
        sample_rate = int(websocket.query_params.get("sr", "48000"))
    except (TypeError, ValueError):
        sample_rate = 48000
    sample_rate = max(_MIN_SAMPLE_RATE, min(_MAX_SAMPLE_RATE, sample_rate))

    # Reject before accepting the socket where we can — keeps the handshake clean.
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return
    try:
        await _fetch_supabase_user(token, settings)
    except HTTPException:
        await websocket.close(code=1008, reason="Authentication required")
        return
    if not settings.deepgram_api_key:
        await websocket.close(code=1011, reason="Service unavailable")
        return

    await websocket.accept(subprotocol=VOICE_WEBSOCKET_PROTOCOL)

    from websockets.exceptions import ConnectionClosed

    from hireloop_api.services.voice.deepgram_live import connect_deepgram_live

    try:
        dg = await connect_deepgram_live(api_key=settings.deepgram_api_key, sample_rate=sample_rate)
    except Exception as exc:
        logger.error("deepgram_live_connect_failed", error=str(exc)[:200])
        try:
            await websocket.send_json({"error": "Could not start live transcription."})
        finally:
            await websocket.close(code=1011)
        return

    async def pump_client_to_deepgram() -> None:
        """Forward browser audio → Deepgram. On stop, ask Deepgram to flush."""
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is not None:
                    await dg.send(data)
                    continue
                text = msg.get("text")
                if text == "CloseStream":
                    # Tell Deepgram to finalize any buffered audio.
                    await dg.send(json.dumps({"type": "CloseStream"}))
        except (WebSocketDisconnect, ConnectionClosed):
            pass
        finally:
            try:
                await dg.send(json.dumps({"type": "CloseStream"}))
            except Exception as exc:
                logger.debug("deepgram_close_stream_failed", error=str(exc)[:200])

    async def pump_deepgram_to_client() -> None:
        """Relay Deepgram transcripts → browser."""
        try:
            async for raw in dg:
                try:
                    payload = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                msg_type = payload.get("type")
                if msg_type == "Results":
                    alts = payload.get("channel", {}).get("alternatives", [])
                    transcript = (alts[0].get("transcript") if alts else "") or ""
                    if transcript:
                        await websocket.send_json(
                            {
                                "transcript": transcript,
                                "is_final": bool(payload.get("is_final")),
                                "speech_final": bool(payload.get("speech_final")),
                            }
                        )
                elif msg_type == "UtteranceEnd":
                    await websocket.send_json({"utterance_end": True})
        except (WebSocketDisconnect, ConnectionClosed):
            pass

    up = asyncio.create_task(pump_client_to_deepgram())
    down = asyncio.create_task(pump_deepgram_to_client())
    try:
        _, pending = await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    finally:
        try:
            await dg.close()
        except Exception as exc:
            logger.debug("deepgram_socket_close_failed", error=str(exc)[:200])
        try:
            await websocket.close()
        except Exception as exc:
            logger.debug("voice_websocket_close_failed", error=str(exc)[:200])
    logger.info("voice_stream_closed", sample_rate=sample_rate)


@router.get("/sessions")
async def list_voice_sessions(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """List the candidate's voice sessions (for profile/dashboard display)."""
    rows = await db.fetch(
        """
        SELECT vs.id, vs.session_type, vs.status, vs.duration_secs, vs.created_at
        FROM public.voice_sessions vs
        JOIN public.candidates c ON c.id = vs.candidate_id
        WHERE c.user_id = $1
        ORDER BY vs.created_at DESC
        LIMIT 20
        """,
        uuid.UUID(current_user["id"]),
    )
    return [dict(r) | {"id": str(r["id"])} for r in rows]
