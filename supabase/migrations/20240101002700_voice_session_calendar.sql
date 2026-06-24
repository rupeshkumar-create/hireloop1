-- P07 re-scope: Cal.com → in-house Google Calendar booking.
-- The booking row is now the source of truth; the Google Calendar event id
-- (with Meet link) is an optional enrichment created via the same Google OAuth
-- app as P13. Rename the legacy Cal.com column to reflect the new semantics.

ALTER TABLE public.voice_sessions
  RENAME COLUMN cal_booking_uid TO calendar_event_id;

COMMENT ON COLUMN public.voice_sessions.calendar_event_id IS
  'Google Calendar event id (P07). NULL when booked in-app without the calendar.events scope connected.';
