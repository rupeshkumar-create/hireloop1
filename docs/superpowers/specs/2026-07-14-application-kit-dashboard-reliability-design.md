# Application Kit and Dashboard Reliability Design

## Goal

Make application-kit generation and instant Job History durable across PostgreSQL JSON decoding differences, transient browser-to-API failures, and frontend deployment transitions, without exposing infrastructure details to candidates.

## Confirmed production failures

1. An application-kit background job was accepted and retried three times, then failed permanently with `'str' object has no attribute 'get'`. PostgreSQL `jsonb` values are returned as JSON text by the current asyncpg pool, while the application-kit interview-prep path assumes `profile_enrichment` is a dictionary.
2. Instant Job History persistence calls Python's standard `logging.Logger` with structlog-style keyword fields. That raises `Logger._log() got an unexpected keyword argument 'user_id'` and aborts the instant shelf.
3. Application-kit start and status polling use the same-origin proxy correctly, but one thrown network error stops the whole client workflow. `ApiUnreachableError` then renders the compiled Railway hostname, creating a misleading infrastructure error.
4. The dashboard error boundary had no matching Vercel or Railway 5xx. The affected dashboard loads after a hard refresh, which is consistent with a transient browser chunk/render failure during a deployment transition.

## Architecture

### PostgreSQL JSON normalization

Add a small application-kit JSON coercion function that accepts dictionaries and JSON strings and returns a dictionary or an empty dictionary. Normalize `profile_enrichment` before it is added to the candidate profile. Also make the interview-prep helper defensive so malformed enrichment cannot terminate kit creation.

The background job remains idempotent per candidate/job. A successful retry may reuse an existing tailored resume and upsert the final kit.

### Durable instant Job History

Keep the existing standard-library logger in `instant_shelf.py`, but pass contextual values through `extra={...}` rather than unsupported keyword arguments. Job search failures remain non-fatal, allowing starter jobs to be persisted to match scores and impressions.

### Resilient application-kit client

Reuse the shared transient retry helper for the initial `POST /prepare`, status polls, and the one requeue request. Retry only network errors, timeouts, and 502/503/504 responses with short backoff. All browser requests continue through `/hireloop-api`; no direct Railway request is introduced.

Expose a typed application-kit connectivity error with candidate-safe text. Chat renders the exact recovery message:

> We had trouble connecting. Your application kit is still being prepared.

The recovery UI provides:

- **Check again**: resume status polling without creating duplicate work.
- **Retry**: idempotently call the prepare endpoint again, then resume polling.

Raw exception messages, hostnames, and `Failed to fetch` never enter candidate-visible chat.

### Dashboard recovery and client diagnostics

The route error boundary classifies chunk/dynamic-import/load failures using conservative message patterns. For those errors it performs one full-page reload per pathname within a short session window. A session-storage guard prevents reload loops. Other errors retain the existing manual **Try again** and **Go to dashboard** actions.

Both route and global error boundaries send a best-effort report to a same-origin Next.js route. The report contains only a bounded error name, sanitized message, optional digest, pathname, and recovery classification. The server route strips URL-like content and control characters before logging. It never accepts stack traces, query strings, form values, authentication tokens, or user identifiers.

Telemetry failure must never interfere with recovery UI.

## Data flow

1. Candidate requests a kit.
2. Browser posts through `/hireloop-api/api/v1/application-kits/jobs/{id}/prepare` with transient retries.
3. FastAPI idempotently enqueues the candidate/job background job.
4. Worker loads candidate data, coerces JSON fields, generates assets, and upserts the kit.
5. Browser polls status through the same-origin proxy with per-request retries.
6. A ready kit renders normally. A transient disconnect shows recovery actions and continues to preserve server-side work.
7. A browser chunk failure reports a sanitized diagnostic and reloads once; persistent errors retain manual recovery.

## Failed-job recovery

After deployment, requeue only the confirmed failed application-kit job by calling the existing idempotent prepare path for its candidate/job pair or by safely resetting that exact durable job. Do not bulk-requeue unrelated failed jobs. Confirm the new attempt completes and creates a tailored resume before marking the smoke test successful.

## Testing

### API regression tests

- JSON dictionary input remains unchanged.
- JSON string input is decoded.
- malformed, list, and null JSON inputs become an empty dictionary.
- application-kit interview prep tolerates string enrichment.
- instant-shelf logging failure path falls back and still persists starter jobs.

### Frontend regression tests

- application-kit start retries a transient network failure and succeeds.
- status polling retries a transient failure instead of terminating.
- non-transient 4xx responses do not retry.
- candidate-visible connectivity errors contain no Railway URL or `Failed to fetch`.
- transient dashboard load errors reload exactly once.
- persistent/non-load errors do not auto-reload.
- client telemetry sanitizes URLs and bounds every field.

### Release verification

- Run focused and full API tests, Ruff, frontend tests, lint, typecheck, and production build.
- Deploy Railway and Vercel from the committed branch.
- Verify public health and dashboard routes.
- Requeue the one confirmed failed application kit and confirm the background job completes.
- Confirm the kit status endpoint reports ready for that candidate/job and production logs contain sanitized request/client diagnostics only.

## Non-goals

- Replacing polling with WebSockets or Supabase Realtime.
- Changing application-kit content or resume templates.
- Requeueing all historical failures.
- Capturing browser stack traces or candidate PII.
