# Resilient Onboarding and Durable Job History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CV onboarding safely retryable and ensure every job shown to a candidate remains visible in Job History.

**Architecture:** The browser owns a stable per-file idempotency UUID and a bounded transient-retry helper. FastAPI makes upload replay deterministic through a database key and deterministic storage identity. The instant shelf persists the final combined job-card list, while request middleware adds non-PII production correlation logs.

**Tech Stack:** Next.js 15, TypeScript, React, FastAPI, Python 3.12, asyncpg, Postgres/Supabase, pytest, Node test runner.

---

### Task 1: Idempotent resume upload contract

**Files:**
- Create: `supabase/migrations/20260714143000_resume_upload_idempotency.sql`
- Modify: `api/src/hireloop_api/routes/resumes.py`
- Create: `api/tests/test_resume_upload_idempotency.py`

- [ ] **Step 1: Write failing tests**

Test that a valid `Idempotency-Key` maps to a deterministic resume UUID and that an existing `(candidate_id, key)` row is serialized as a replay without storage upload, rate-limit use, or parsing enqueue.

- [ ] **Step 2: Verify RED**

Run `cd api && uv run pytest tests/test_resume_upload_idempotency.py -v`. Expect failure because the idempotency helpers and header do not exist.

- [ ] **Step 3: Add schema and minimal implementation**

Add `upload_idempotency_key TEXT`, a partial unique index on `(candidate_id, upload_idempotency_key)`, a UUID header validator, deterministic `uuid5` identity, replay lookup, storage upsert, and structured `resume_upload_started|replayed|completed` logs.

- [ ] **Step 4: Verify GREEN**

Run `cd api && uv run pytest tests/test_resume_upload_idempotency.py -v`. Expect all tests to pass.

### Task 2: Bounded onboarding retry UX

**Files:**
- Create: `app/src/lib/api/transient-retry.ts`
- Create: `app/src/lib/api/transient-retry.test.ts`
- Modify: `app/src/lib/api/onboardingProfile.ts`
- Modify: `app/src/app/onboarding/OnboardingFlow.tsx`
- Modify: `app/package.json`

- [ ] **Step 1: Write failing retry tests**

Cover one network failure followed by success, one 503 followed by success, no retry for 400, and exhaustion after three total attempts.

- [ ] **Step 2: Verify RED**

Run `cd app && node --experimental-strip-types --test src/lib/api/transient-retry.test.ts`. Expect module-not-found failure.

- [ ] **Step 3: Implement retry helper and UI**

Implement `withTransientRetry(operation, { attempts: 3, delaysMs: [350, 900], onRetry })`. Generate and retain an idempotency UUID per selected file, pass it to `uploadResumeAndApply`, retry upload/consent/profile/completion calls, show “We had trouble connecting. Retrying…” during retry, and expose `Retry setup` after exhaustion without clearing component state.

- [ ] **Step 4: Verify GREEN**

Run the Node test command and `pnpm --filter app typecheck`. Expect passing tests and zero TypeScript errors.

### Task 3: Persist onboarding jobs to Job History

**Files:**
- Modify: `api/src/hireloop_api/services/instant_shelf.py`
- Modify: `api/tests/test_instant_shelf.py`

- [ ] **Step 1: Write failing persistence tests**

Assert the Aarya call receives a UUID session string and the final merged cards are upserted into both `match_scores` and `candidate_job_impressions`, including fallback-only cards.

- [ ] **Step 2: Verify RED**

Run `cd api && uv run pytest tests/test_instant_shelf.py -v`. Expect failures because the current literal session ID is invalid and fallback cards are not persisted.

- [ ] **Step 3: Implement durable persistence**

Use a deterministic UUID5 session value. Call the existing score persistence helper for final cards and upsert impressions with source `matches`, incrementing `seen_count` and `last_seen_at` on conflict.

- [ ] **Step 4: Verify GREEN**

Run the targeted instant-shelf and match-history tests. Expect all tests to pass.

### Task 4: Production request correlation logging

**Files:**
- Modify: `api/src/hireloop_api/main.py`
- Create: `api/tests/test_request_observability.py`

- [ ] **Step 1: Write failing middleware tests**

Assert responses return `X-Request-ID`, forwarded IDs are retained, and tracked onboarding/history routes emit method, path, status, duration, request ID, and retry attempt without request bodies.

- [ ] **Step 2: Verify RED**

Run `cd api && uv run pytest tests/test_request_observability.py -v`. Expect missing header/log fields.

- [ ] **Step 3: Implement tracked request logging**

Extend `_request_timing` to create/validate a correlation UUID, set `request.state.request_id`, attach the response header, and log `candidate_flow_request` for the four tracked paths.

- [ ] **Step 4: Verify GREEN**

Run the targeted middleware tests. Expect all tests to pass.

### Task 5: Full verification and production release

**Files:**
- Modify only files required by failures introduced by Tasks 1–4.

- [ ] **Step 1: Run complete verification**

Run `cd api && uv run pytest tests/ -v`, `cd api && uv run ruff check .`, `cd api && uv run ruff format --check .`, `pnpm --filter app lint`, `pnpm --filter app typecheck`, and `pnpm --filter app build`. Expect zero failures.

- [ ] **Step 2: Review scoped diff**

Confirm no unrelated Aarya/chat files from the original dirty workspace are present and no secrets or PII logging were added.

- [ ] **Step 3: Commit and deploy**

Commit the repair, deploy the API through the repository’s Railway release path, and deploy `app/` to Vercel production.

- [ ] **Step 4: Smoke-test production**

Verify `/hireloop-api/api/v1/health` returns 200, the new Vercel deployment is Ready, tracked request logs contain correlation fields, an authenticated CV retry returns one resume ID for the same key, and a surfaced onboarding job remains in `/api/v1/matches/history` after refresh.

