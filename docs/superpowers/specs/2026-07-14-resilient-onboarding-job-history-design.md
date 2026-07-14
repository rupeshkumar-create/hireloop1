# Resilient Onboarding and Durable Job History

## Problem

Candidate onboarding can encounter a transient browser-to-Vercel-to-FastAPI failure while uploading a CV. The current UI exposes internal infrastructure instructions and requires a manual retry with no server-side idempotency guarantee. Separately, onboarding starter jobs can disappear after refresh because fallback cards are stored only in browser session storage and are not always persisted to `match_scores` and `candidate_job_impressions`.

## Root causes

1. `POST /api/v1/resumes/upload` creates a new resume UUID for every request. If a response is interrupted after the server stores the CV, a retry can create a duplicate resume.
2. Onboarding sends each request once. A network exception becomes a terminal, developer-facing error even when a short retry succeeds.
3. The React state already retains the chosen `File` and consent values after failure, but the page provides no explicit retry action or retry progress state.
4. `fetch_instant_shelf()` calls Aarya search with `session_id="instant-shelf"`, while `agent_actions.session_id` is written as UUID. That can fail before search results are persisted.
5. Starter fallback rows are returned to the browser without durable score/impression rows, so one-time session storage is the only record.

## Design

### Idempotent CV upload

The browser generates one UUID idempotency key when a CV is selected and reuses it for every retry of that file. It sends the key in `Idempotency-Key`. The API validates the UUID, derives a deterministic resume UUID from the user and key, stores the key on the resume row, and uses an upsert-safe deterministic storage path. A partial unique index on `(candidate_id, upload_idempotency_key)` prevents duplicate rows. If the request is replayed after completion, the API returns the existing resume payload without consuming another rate-limit attempt or queuing duplicate parsing work.

### Transient retry and candidate UX

A focused frontend retry helper retries network exceptions and HTTP 502/503/504 responses twice with short backoff. During a retry, onboarding displays exactly “We had trouble connecting. Retrying…”. If retries are exhausted, it displays “We had trouble connecting. Please try again.” and a `Retry setup` button. The component remains mounted, so the selected `File`, required consent, and optional marketing consent remain unchanged.

### Durable Job History

The instant shelf uses a deterministic UUID session identifier. After assembling search and fallback cards, it upserts every surfaced job into `match_scores` and `candidate_job_impressions` before returning. History therefore survives navigation, refresh, expiration from the live feed, and one-time session-storage consumption.

### Production observability

The API timing middleware assigns or forwards `X-Request-ID`, returns it on every response, and emits structured completion logs for the onboarding upload, consent, completion, and match-history routes. Logs include request ID, method, path, status, duration, and retry attempt, but no CV content, filename, email, token, or other PII.

## Error handling

- Invalid or missing upload idempotency keys receive a clear 400 response. The frontend always supplies a valid key.
- Only connectivity failures and 502/503/504 responses retry. Validation, authentication, rate limiting, and other 4xx responses remain terminal.
- A retry reuses the same idempotency key. Selecting a different file creates a new key.
- History persistence failures are logged and allowed to propagate during onboarding shelf construction so an apparently successful shelf cannot silently disappear.

## Verification

- API regression tests cover replayed upload lookup, deterministic resume identity, job-card persistence, valid UUID session use, and request logging metadata.
- Frontend regression tests cover retryable versus non-retryable outcomes and bounded backoff.
- Run targeted tests, full API tests, Ruff, frontend typecheck/lint/build, deploy the API and app, then smoke-test health, onboarding request logs, CV replay behavior, and non-empty history after an onboarding/search flow.

