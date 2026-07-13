# Gmail outbound kit (approve-first) — design

**Date:** 2026-07-13  
**Status:** Approved (user)  
**Approach:** A (minimal glue) + approve-first follow-ups  

## Goals

1. Change intro **72h follow-ups** from auto-send to **draft → candidate edit/approve → Gmail send** (same trust model as Request Intro).
2. Add **thank-you** emails: manual action + one auto-prompt when intro becomes `replied` or `interview`.
3. **Polish voice-session booking** UX when Google Calendar is connected (Meet link); clear Connect Google CTA when not.
4. Stay within existing scopes: `gmail.send` + `calendar.events` (+ email identity). No inbox read.

## Non-goals

- Auto-detect HM replies from Gmail inbox (`gmail.readonly`)
- Auto-send follow-ups without approval
- HM interview calendar events (deferred)
- Multi-HM blast sequences
- Changing MatchingEngine / job ingest

## Decisions locked

| Topic | Choice |
|-------|--------|
| Follow-ups | Approve-first after 72h |
| Thank-yous | Both: manual + status-triggered prompt |
| Booking this ship | Voice / Aarya sessions only (polish) |
| Architecture | Minimal glue on existing intro + voice routes |

## Current state (reuse)

| Piece | Today |
|-------|--------|
| Intro approve-send | `POST /api/v1/intros/{id}/approve-send` + `IntroDraftPanel` |
| Follow-up sweep | `intro_followups.run_intro_followup_sweep` **auto-sends** after 72h, sets `nudged_at` |
| Thread fields | `gmail_thread_id`, `gmail_subject`, `gmail_message_id`, `nudged_at` on `intro_requests` |
| Gmail send | `GmailOAuthService.send_intro_email` (supports `thread_id`) |
| Voice booking | `GET/POST /api/v1/voice-sessions/*` + `GoogleCalendarService.create_event` |
| Google connect | `GET /api/v1/gmail/auth-url`, status, `GoogleConnectCard` |
| Candidate nudges | `retention.run_pending_intro_nudge_sweep` (in-app notifs for pending intros) |

## 1. Follow-ups (approve-first)

### Behavior

1. Background sweep (existing ~15m worker hook) finds intros where:
   - `status = 'sent'`
   - `replied_at IS NULL`
   - `nudged_at IS NULL`
   - no follow-up draft already pending
   - `sent_at < NOW() - 72 hours`
   - `gmail_thread_id IS NOT NULL`
2. For each (capped, e.g. 10/sweep): write a **follow-up draft** into the intro row; **do not** call Gmail; **do not** set `nudged_at`.
3. Create in-app notification (and reuse retention-style dedupe) so the candidate sees “Follow-up ready for {role}”.
4. Candidate opens draft UI (extend intro detail / draft panel), edits subject/body, taps **Approve & send**.
5. On send success: Gmail reply in same thread → set `nudged_at = NOW()`. Keep `status = 'sent'` (or set a clear `followed_up` only if status enum already allows a non-breaking value; prefer not expanding enum if avoidable — use `nudged_at` as source of truth that follow-up was sent).

### Data model

Prefer columns on `intro_requests` (minimal migration):

- `followup_draft_email` JSONB/text — `{subject, body_html, body_text}` (nullable)
- `followup_draft_at` timestamptz — when draft was created (nullable)
- Existing `nudged_at` — set only when follow-up is **sent**

Sweep selection: `followup_draft_at IS NULL AND nudged_at IS NULL AND …`

Optional: clear `followup_draft_email` after successful send (or keep for history — keep until send, then null out to avoid re-showing).

### API

- Extend `GET /api/v1/intros/{id}` to return `followup_draft_email`, `followup_draft_at`, `nudged_at`, `gmail_connected`.
- `PATCH /api/v1/intros/{id}/followup-draft` — candidate edits draft body/subject (while pending).
- `POST /api/v1/intros/{id}/approve-send-followup` — send via Gmail with `thread_id`; requires Google connected; sets `nudged_at`.

Do **not** reuse `approve-send` for the initial intro (status `draft_ready`) vs follow-up — separate endpoint avoids status confusion.

### UI

- Intros list/detail: badge “Follow-up ready” when `followup_draft_at` set and `nudged_at` null.
- Panel patterned on `IntroDraftPanel`: edit + Approve & send + Connect Google gate.
- Copy: explain this is a polite bump in the **same thread**, not a new cold email.

### Sweep change

Replace send logic in `intro_followups.py` with draft creation + notification. Remove auto-send path entirely.

## 2. Thank-yous (manual + prompt)

### Behavior

- **Manual:** On intro detail (status `sent` / `replied` / `interview` / after nudge), action “Send thank-you” → generate short draft → edit → approve → `gmail.send` (new thread or same thread if `gmail_thread_id` present — prefer **same thread** when available).
- **Prompt:** When intro status transitions to `replied` or `interview`, if no thank-you sent yet, create one draft (or notification with deep link) once per intro (dedupe key / column `thankyou_draft_at` / `thankyou_sent_at`).

### Data model

On `intro_requests`:

- `thankyou_draft_email` JSONB/text nullable
- `thankyou_draft_at` timestamptz nullable  
- `thankyou_sent_at` timestamptz nullable  

Or a single JSON `outbound_meta` — prefer explicit columns for clarity and indexes.

### API

- `POST /api/v1/intros/{id}/thankyou-draft` — create/regenerate draft (manual or called by status transition hook).
- `PATCH /api/v1/intros/{id}/thankyou-draft` — edit.
- `POST /api/v1/intros/{id}/approve-send-thankyou` — send; set `thankyou_sent_at`.

Status transition hook: wherever intro status is updated to `replied`/`interview` (recruiter or candidate path), enqueue draft+notification if `thankyou_sent_at IS NULL` and `thankyou_draft_at IS NULL`.

### UI

- Button on intro detail; optional toast/banner when draft ready from status change.
- Same Connect Google gate as intros.

### Copy defaults

Short, professional India-market tone; include role title + HM first name; no fake claims.

## 3. Voice booking polish

### Behavior (no new product surface)

- On book success: if Calendar event + Meet created, show Meet URL prominently in confirmation UI / chat tool result.
- If Google not connected or calendar scope missing: booking still succeeds in-app; show **Connect Google to get a Meet link on your calendar** CTA (`startGoogleConnect`).
- `GET /api/v1/gmail/status` already exposes `calendar_enabled` — use it in voice booking UI.

### Out of scope here

- HM interview events
- Changing slot grid / business hours

## Constraints (hard)

- R9: all HM-facing mail via candidate Gmail OAuth only.
- No `gmail.readonly`.
- Candidate must explicitly approve each follow-up and thank-you send.
- History of intros unchanged; match feed expired/dedupe work is orthogonal.

## Testing

- Unit: sweep creates draft, does not call send; approve-send-followup sets `nudged_at` and calls send with `thread_id`.
- Unit: thank-you draft created once on status transition; second transition no-ops.
- Unit/API: approve endpoints 409 without draft / without Gmail.
- UI smoke (manual): Connect Google → follow-up badge → edit → send; thank-you button; book voice with/without Google.

## Rollout

1. Migration for new columns.
2. Sweep flip (draft-only) + APIs.
3. Intro UI for follow-up + thank-you.
4. Voice booking CTA/Meet display polish.
5. Feature flag optional: none required for MVP if deploy is atomic; if needed, `INTRO_FOLLOWUP_APPROVE_FIRST=true` default on.

## Success criteria

- No Gmail send from the 72h worker without candidate approval.
- Candidate can complete follow-up and thank-you from intros UI with Google connected.
- Voice book shows Meet when calendar connected; CTA when not.
