# Aarya Text And Voice Upgrade Design

## Goal

Make Aarya feel more advanced, faster, and smoother across text chat and voice without replacing the existing LangGraph, Deepgram, memory, or chat UI foundations.

## Current Context

- `api/src/hireloop_api/agents/aarya/agent.py` already contains separate text and voice prompts, tool calling, profile/memory injection, and LangGraph orchestration.
- `api/src/hireloop_api/routes/chat.py` already streams Server-Sent Events with partial text and basic tool statuses.
- `app/src/components/chat/ChatInterface.tsx` already supports a unified chat composer with text, resume upload, inline mic capture, transcript review, TTS playback, and recovery from dropped streams.
- `app/src/lib/hooks/useVoice.ts` already supports Deepgram live STT, batch fallback, browser fallback, mic level, captions, and TTS.
- `app/src/app/voice/VoiceSession.tsx` already provides the 15-minute Aarya call flow and unlock behavior.

## Recommended Approach

Improve orchestration and perceived smoothness rather than rebuilding realtime voice from scratch.

### Agent Brain

- Add a deterministic conversation context helper that derives useful turn guidance from message history, memory, open questions, and `content_type`.
- Inject that guidance into Aarya’s system prompt so replies are shorter, more specific, and more action-oriented.
- Keep the current single-threaded LangGraph loop and existing tools.
- Preserve India-first behavior, profile-first behavior, no repeated known-fact questions, and explicit approval before intros.

### Stream And Status UX

- Make streamed status labels more specific and voice-aware.
- Add a small status helper so chat and voice can map phases consistently.
- Reduce generic “Working on your request…” moments when the tool name is known.
- Preserve partial response recovery.

### Text Chat UX

- Show live voice captions in the composer while recording.
- Make empty transcript handling friendly instead of silent.
- Allow the mic button to stop current speech before recording, so users can naturally interrupt Aarya.
- Keep transcript review before send so users stay in control.

### Voice Call UX

- Reuse the same stream parser behavior as chat where practical.
- Surface stream statuses during voice processing.
- Recover cleanly when STT returns no speech.
- Keep `/voice` as the 15-minute unlock call path, but make it feel less dead-air and more stateful.

### Error Handling

- Voice STT empty transcript should produce a clear retry hint.
- TTS failures should fall back to text without blocking the conversation.
- Chat stream failures should keep saved partial output and offer continuation.

### Testing

- Add API unit tests for Aarya prompt context, tool status labels, and speech sanitization.
- Add frontend unit tests for transcript/caption helper behavior if adjacent patterns exist; otherwise rely on TypeScript and build validation.
- Run focused API tests, full API tests when practical, TypeScript checks, lint, and build.

## Non-Goals

- No full realtime media architecture rewrite.
- No new provider beyond existing Deepgram/browser fallbacks.
- No direct frontend database writes.
- No changes to LinkedIn scraping behavior.
- No removal of the 15-minute `/voice` route in this pass.

## Success Criteria

- Aarya asks fewer redundant questions and gives cleaner next steps.
- Users see clearer progress during job search, profile reading, and match scoring.
- Voice input shows live captions when available and gives a useful retry state when no speech is captured.
- Spoken replies remain short, natural, markdown-free, and TTS-safe.
- Existing chat, resume upload, job cards, and voice session unlock behavior continue to pass validation.
