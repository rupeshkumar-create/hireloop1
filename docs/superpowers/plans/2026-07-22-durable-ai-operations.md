# Durable AI Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every non-interactive external-AI generation flow onto Hireschema's durable PostgreSQL queue with safe progress, retry, cancellation, reload recovery, and tenant isolation.

**Architecture:** Keep `background_jobs` as the private execution queue and add `ai_operations` as the user-safe lifecycle projection. FastAPI submission routes return `202` with an operation ID, workers update progress and terminal state, and a shared React operation provider polls owned status records and restores active work after reload. Aarya chat, STT, TTS, and live voice remain real-time.

**Tech Stack:** PostgreSQL/Supabase migrations and RLS, FastAPI, Pydantic v2, asyncpg, existing Railway background worker, Next.js 15, TypeScript, Zod, TanStack Query, Vitest, Testing Library.

---

## File map

### New files

- `supabase/migrations/20260722173000_ai_operations.sql` — operation table, constraints, indexes, RLS, and policies.
- `api/src/hireloop_api/models/ai_operation.py` — Pydantic lifecycle and API response models.
- `api/src/hireloop_api/services/ai_operations.py` — enqueue, ownership, transition, progress, retry, and cancellation service.
- `api/src/hireloop_api/routes/ai_operations.py` — list, read, cancel, and retry endpoints.
- `api/tests/test_ai_operations.py` — unit lifecycle and error-mapping tests.
- `api/tests/test_ai_operation_routes.py` — route contract tests.
- `api/tests/integration/test_ai_operations_schema.py` — migration, RLS, idempotency, and transition integration tests.
- `app/src/lib/api/aiOperations.ts` — Zod schemas and API functions.
- `app/src/components/providers/AiOperationsProvider.tsx` — adaptive polling and recovery provider.
- `app/src/components/operations/AiOperationIndicator.tsx` — global active-task indicator.
- `app/src/components/operations/AiOperationProgress.tsx` — shared progress, retry, and cancellation UI.
- `app/src/lib/operations/polling.ts` — pure polling interval/state helpers.
- `app/src/lib/operations/polling.test.ts` — deterministic polling tests.
- `app/src/lib/api/aiOperations.test.ts` — response validation tests.
- `app/src/lib/api/auth-fetch.test.ts` — network, timeout, and caller-cancellation classification tests.
- `app/src/lib/operations/external-ai-route-audit.test.ts` — CI allowlist for intentionally real-time external-AI routes.
- `app/vitest.config.ts` and `app/src/test/setup.ts` — frontend unit-test setup.

### Modified files

- `api/src/hireloop_api/main.py` — register the operation router.
- `api/src/hireloop_api/services/background_jobs.py` — operation-aware job claiming and terminal updates; career generation handlers.
- `api/src/hireloop_api/routes/career.py` — return operations for path and intelligence generation.
- `api/src/hireloop_api/routes/application_kits.py` — attach Application Kit jobs to operations.
- `api/src/hireloop_api/routes/tailored_resumes.py` — attach tailoring jobs to operations.
- `api/src/hireloop_api/routes/learning_roadmaps.py` — attach roadmap jobs to operations.
- `api/src/hireloop_api/routes/resumes.py` — attach parsing and profile-expansion jobs to operations.
- `api/src/hireloop_api/services/career_path_resume.py` and relevant worker handlers — publish progress and results.
- `api/tests/test_background_jobs.py`, `api/tests/test_application_kit_routes.py`, `api/tests/test_career_path.py`, and `api/tests/integration/test_idor_cross_user.py` — queue and ownership coverage.
- `app/src/lib/api/career.ts`, `applicationKit.ts`, `tailored.ts`, `learningRoadmap.ts`, and `onboardingProfile.ts` — accept immediate or `202` responses.
- `app/src/app/layout.tsx` — mount the operation provider and indicator.
- Feature components that initiate generation — render shared operation progress.
- `app/src/lib/api/auth-fetch.ts` — accurate network-boundary error text.
- `app/tests/career-timeout.test.mjs` — remove after the synchronous career-generation workaround is replaced by operation tests.
- `app/package.json`, `pnpm-lock.yaml`, and `.github/workflows/ci.yml` — frontend test tooling and CI.

---

### Task 1: Add the operation schema and RLS

**Files:**
- Create: `supabase/migrations/20260722173000_ai_operations.sql`
- Create: `api/tests/integration/test_ai_operations_schema.py`

- [ ] **Step 1: Write the failing schema test**

```python
@pytest.mark.asyncio
async def test_ai_operations_schema_and_rls(db_conn: asyncpg.Connection) -> None:
    columns = await db_conn.fetch(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema='public' AND table_name='ai_operations'"""
    )
    assert {row["column_name"] for row in columns} >= {
        "id", "user_id", "kind", "background_job_id", "idempotency_key",
        "status", "progress_percent", "stage", "message", "error_code",
        "result_type", "result_id", "expires_at", "deleted_at",
    }
    assert await db_conn.fetchval(
        """SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relname='ai_operations'"""
    ) is True
```

- [ ] **Step 2: Run the test and verify it fails because `ai_operations` does not exist**

Run: `cd api && uv run pytest tests/integration/test_ai_operations_schema.py -v`  
Expected: FAIL with missing table/columns.

- [ ] **Step 3: Add the migration**

The migration must create the approved columns plus `retry_of UUID REFERENCES public.ai_operations(id)`, foreign keys to `public.users`, `public.candidates`, `public.recruiters`, and `public.background_jobs`, lifecycle/progress checks, an active idempotency partial unique index, owner/status and expiry indexes, `set_updated_at()` trigger, RLS, candidate/recruiter own-read policy using `auth.uid() = user_id`, and admin read policy using non-deleted `public.users.role = 'admin'`. Do not add client INSERT/UPDATE/DELETE policies.

- [ ] **Step 4: Add integration assertions for invalid transitions and active idempotency**

Insert two active rows with the same idempotency key and assert the second fails; insert a terminal row with the same key and assert a new queued row succeeds. Verify `progress_percent=-1` and `101` fail.

- [ ] **Step 5: Run the migration test**

Run: `cd api && uv run pytest tests/integration/test_ai_operations_schema.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/20260722173000_ai_operations.sql api/tests/integration/test_ai_operations_schema.py
git commit -m "feat: add durable AI operation schema"
```

### Task 2: Implement typed lifecycle and enqueue service

**Files:**
- Create: `api/src/hireloop_api/models/ai_operation.py`
- Create: `api/src/hireloop_api/services/ai_operations.py`
- Create: `api/tests/test_ai_operations.py`

- [ ] **Step 1: Write failing model and transition tests**

Cover `queued → running → succeeded`, retryable failure classification, progress monotonicity, terminal immutability, cancellation, and safe serialization that omits queue payload and raw errors.

- [ ] **Step 2: Run the unit tests and verify import/behavior failures**

Run: `cd api && uv run pytest tests/test_ai_operations.py -v`  
Expected: FAIL because the service and models do not exist.

- [ ] **Step 3: Add Pydantic models**

```python
AiOperationStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]

class AiOperationResponse(BaseModel):
    id: uuid.UUID
    kind: str
    status: AiOperationStatus
    progress_percent: int = Field(ge=0, le=100)
    stage: str
    message: str
    result_type: str | None = None
    result_id: uuid.UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

class AiOperationAccepted(BaseModel):
    operation_id: uuid.UUID
    status: Literal["queued", "running"]
    status_url: str
    retry_after_ms: int = 1500
```

- [ ] **Step 4: Implement service functions**

Implement `enqueue_ai_operation`, `get_owned_operation`, `list_owned_operations`, `mark_operation_running`, `update_operation_progress`, `mark_operation_succeeded`, `mark_operation_failed`, `cancel_owned_operation`, and `retry_owned_operation`. `enqueue_ai_operation` must create/reuse the operation and queue job in one caller-owned transaction, inject `operation_id` into the private job payload, and update `background_job_id`.

- [ ] **Step 5: Implement stable error mapping**

Map provider timeout, rate limit, unavailable, validation, profile, permission, expiry, cancellation, and unknown exceptions to the approved codes. Store only truncated user-safe messages in `ai_operations`; keep raw exception text in `background_jobs.last_error` and structured logs.

- [ ] **Step 6: Run unit tests and Ruff**

Run: `cd api && uv run pytest tests/test_ai_operations.py -v && uv run ruff check src/hireloop_api/models/ai_operation.py src/hireloop_api/services/ai_operations.py tests/test_ai_operations.py`  
Expected: PASS and no Ruff findings.

- [ ] **Step 7: Commit**

```bash
git add api/src/hireloop_api/models/ai_operation.py api/src/hireloop_api/services/ai_operations.py api/tests/test_ai_operations.py
git commit -m "feat: add AI operation lifecycle service"
```

### Task 3: Add owned operation APIs and IDOR coverage

**Files:**
- Create: `api/src/hireloop_api/routes/ai_operations.py`
- Create: `api/tests/test_ai_operation_routes.py`
- Modify: `api/src/hireloop_api/main.py`
- Modify: `api/tests/integration/test_idor_cross_user.py`

- [ ] **Step 1: Write failing route tests**

Test `GET /api/v1/ai-operations/{id}`, active list, cancel, retry, invalid UUID, non-owned 404, terminal cancel conflict, and non-retryable retry conflict.

- [ ] **Step 2: Verify the routes return 404 before registration**

Run: `cd api && uv run pytest tests/test_ai_operation_routes.py -v`  
Expected: FAIL with route 404s.

- [ ] **Step 3: Implement and register the router**

Use `APIRouter(prefix="/ai-operations", tags=["ai-operations"])`, `get_phone_verified_user`, `get_db`, Pydantic responses, and service ownership methods. Return 404 for non-owned IDs to avoid resource enumeration. Return `409` for invalid lifecycle actions.

- [ ] **Step 4: Add cross-user integration tests**

Seed an operation for candidate B and prove candidate A cannot read, cancel, retry, or obtain its result reference. Verify A can list only A's active operations.

- [ ] **Step 5: Run route and IDOR tests**

Run: `cd api && uv run pytest tests/test_ai_operation_routes.py tests/integration/test_idor_cross_user.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/src/hireloop_api/routes/ai_operations.py api/src/hireloop_api/main.py api/tests/test_ai_operation_routes.py api/tests/integration/test_idor_cross_user.py
git commit -m "feat: expose owned AI operation APIs"
```

### Task 4: Make the worker operation-aware

**Files:**
- Modify: `api/src/hireloop_api/services/background_jobs.py`
- Modify: `api/tests/test_background_jobs.py`
- Modify: `api/tests/integration/test_background_jobs_integration.py`

- [ ] **Step 1: Write failing worker lifecycle tests**

Assert a linked operation becomes running before its handler, succeeds with progress 100 after completion, stays running/pending while a retry is scheduled, fails only after the final attempt, and remains cancelled when a late handler returns.

- [ ] **Step 2: Verify the new tests fail against the current worker**

Run: `cd api && uv run pytest tests/test_background_jobs.py -v`  
Expected: FAIL because `process_job` does not update operations.

- [ ] **Step 3: Add operation lifecycle calls around handlers**

Before a handler, read `payload.get("operation_id")`, check cancellation, and mark running. On success, require the handler or job metadata to provide a result reference, then mark success. On retryable failure, update the operation message and attempt count without terminal failure. On the final failure, apply stable error mapping and mark terminal failure.

- [ ] **Step 4: Add a progress helper for handlers**

```python
async def publish_operation_progress(
    settings: Settings,
    payload: dict[str, Any],
    *,
    progress_percent: int,
    stage: str,
    message: str,
) -> None:
    operation_id = payload.get("operation_id")
    if not operation_id:
        return
    pool = await get_db_pool(settings)
    async with pool.acquire() as db:
        await update_operation_progress(
            db, uuid.UUID(str(operation_id)), progress_percent, stage, message
        )
```

- [ ] **Step 5: Add database integration coverage**

Run a real queued no-op job linked to an operation and assert queue and operation terminal states agree. Simulate final failure and cancellation.

- [ ] **Step 6: Run worker tests**

Run: `cd api && uv run pytest tests/test_background_jobs.py tests/integration/test_background_jobs_integration.py -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add api/src/hireloop_api/services/background_jobs.py api/tests/test_background_jobs.py api/tests/integration/test_background_jobs_integration.py
git commit -m "feat: publish AI operation worker progress"
```

### Task 5: Convert career path and intelligence generation

**Files:**
- Modify: `api/src/hireloop_api/services/background_jobs.py`
- Modify: `api/src/hireloop_api/routes/career.py`
- Modify: `api/tests/test_career_path.py`
- Modify: `app/src/lib/api/career.ts` in Task 8

- [ ] **Step 1: Write failing route tests for `202` responses**

Test that path and intelligence submissions return in queued/running state with `operation_id`, reuse an active operation on double-click, and return existing recent results without duplicate LLM work.

- [ ] **Step 2: Verify current synchronous responses fail the new contract**

Run: `cd api && uv run pytest tests/test_career_path.py -k operation -v`  
Expected: FAIL because both routes await generation.

- [ ] **Step 3: Add `CAREER_PATH_GENERATE` and `CAREER_INTELLIGENCE_GENERATE` handlers**

Handlers call the existing services, publish stages at 10/35/80 percent, persist through existing service methods, and return result references through the operation service. Add both kinds to the interactive lane.

- [ ] **Step 4: Convert submission routes**

Resolve the candidate, enforce existing rate limits, call `enqueue_ai_operation`, and return `202` with `AiOperationAccepted`. Use server-derived idempotency keys scoped to candidate and a five-minute generation window.

- [ ] **Step 5: Run focused tests and the production timing contract**

Assert provider mocks are not awaited inside the request coroutine and submission completes under one second in tests.

Run: `cd api && uv run pytest tests/test_career_path.py tests/test_career_intelligence_context.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/src/hireloop_api/services/background_jobs.py api/src/hireloop_api/routes/career.py api/tests/test_career_path.py
git commit -m "feat: queue career AI generation"
```

### Task 6: Standardize already-queued generation features

**Files:**
- Modify: `api/src/hireloop_api/routes/application_kits.py`
- Modify: `api/src/hireloop_api/routes/tailored_resumes.py`
- Modify: `api/src/hireloop_api/routes/learning_roadmaps.py`
- Modify: `api/src/hireloop_api/routes/career.py`
- Modify: `api/src/hireloop_api/routes/resumes.py`
- Modify: their existing unit tests

- [ ] **Step 1: Add failing contract tests for each submission route**

For Application Kits, tailored resumes, learning roadmaps, career-path resumes, and resume parsing/profile expansion, assert every queued response includes `operation_id`, `status_url`, and `retry_after_ms`, and duplicate submissions reuse the active operation.

- [ ] **Step 2: Verify the tests fail because routes return feature-specific processing shapes**

Run the focused route suites and record the expected response mismatches.

- [ ] **Step 3: Replace direct `enqueue_job` calls with `enqueue_ai_operation`**

Preserve existing domain-row creation and existing ready-result fast paths. Pass domain `result_type` and expected resource ID where known. Keep private handler payloads unchanged except for injected `operation_id`.

- [ ] **Step 4: Publish meaningful handler progress**

Application Kit stages: profile 10, resume 35, cover letter 60, interview prep 80, save 95. Resume and roadmap handlers use equivalent bounded, monotonic stages. No progress message contains resume text, candidate names, or provider output.

- [ ] **Step 5: Run all affected backend suites**

Run: `cd api && uv run pytest tests/test_application_kit_routes.py tests/test_tailored_resume_settings.py tests/test_learning_roadmap_guardrails.py tests/test_resume_candidate_profile.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/src/hireloop_api/routes/application_kits.py api/src/hireloop_api/routes/tailored_resumes.py api/src/hireloop_api/routes/learning_roadmaps.py api/src/hireloop_api/routes/career.py api/src/hireloop_api/routes/resumes.py api/tests
git commit -m "feat: standardize queued AI generation contracts"
```

### Task 7: Add frontend operation schemas, polling, and provider

**Files:**
- Create: `app/vitest.config.ts`
- Create: `app/src/test/setup.ts`
- Create: `app/src/lib/api/aiOperations.ts`
- Create: `app/src/lib/api/aiOperations.test.ts`
- Create: `app/src/lib/operations/polling.ts`
- Create: `app/src/lib/operations/polling.test.ts`
- Create: `app/src/components/providers/AiOperationsProvider.tsx`
- Modify: `app/package.json`, `pnpm-lock.yaml`, `.github/workflows/ci.yml`

- [ ] **Step 1: Add Vitest and write failing schema/polling tests**

Add `vitest`, `jsdom`, `@testing-library/react`, and `@testing-library/jest-dom` as dev dependencies. Configure the `@` alias and jsdom. Test Zod rejection of malformed status/progress/result IDs and polling intervals of 1500ms initially, 3000ms while running, 5000ms after sustained work, and paused while hidden.

- [ ] **Step 2: Verify tests fail before implementation**

Run: `pnpm --filter app test`  
Expected: FAIL because operation modules do not exist.

- [ ] **Step 3: Implement Zod schemas and API functions**

Export `submit` response schemas, `getAiOperation`, `listActiveAiOperations`, `cancelAiOperation`, and `retryAiOperation`, all through `apiAuthFetch`. Validate every response before returning it.

- [ ] **Step 4: Implement the provider**

Maintain a map keyed by operation ID, restore active operations on authenticated mount, poll with TanStack Query, pause through `document.visibilityState`, expose `trackOperation`, `cancelOperation`, and `retryOperation`, and show completion/error toasts once per operation.

- [ ] **Step 5: Run frontend tests, typecheck, and lint**

Run: `pnpm --filter app test && pnpm --filter app typecheck && pnpm --filter app lint`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/vitest.config.ts app/src/test app/src/lib/api/aiOperations.ts app/src/lib/api/aiOperations.test.ts app/src/lib/operations app/src/components/providers/AiOperationsProvider.tsx app/package.json pnpm-lock.yaml .github/workflows/ci.yml
git commit -m "feat: add frontend AI operation manager"
```

### Task 8: Integrate feature progress and reload recovery

**Files:**
- Create: `app/src/components/operations/AiOperationIndicator.tsx`
- Create: `app/src/components/operations/AiOperationProgress.tsx`
- Modify: `app/src/app/layout.tsx`
- Modify: `app/src/lib/api/career.ts`, `applicationKit.ts`, `tailored.ts`, `learningRoadmap.ts`, `onboardingProfile.ts`
- Modify: `app/src/hooks/useJobCardAssets.ts`
- Modify: `app/src/components/career/CareerPathOptionCards.tsx`
- Modify: `app/src/components/chat/CareerKickoffFlow.tsx`
- Modify: `app/src/components/chat/ChatInterface.tsx`
- Modify: `app/src/components/jobs/CareerPathPanel.tsx`
- Modify: `app/src/components/profile/CareerIntelligencePanel.tsx`
- Modify: `app/src/components/resumes/ResumePreviewModal.tsx`
- Modify: `app/src/components/settings/CandidateSharingSettings.tsx`
- Modify: `app/src/app/onboarding/OnboardingFlow.tsx`

- [ ] **Step 1: Write failing component tests**

Test queued/running/succeeded/failed/cancelled rendering, retry visibility only for retryable failures, cancel visibility only for active work, and recovery display after provider mount.

- [ ] **Step 2: Implement shared components and mount the provider**

Place `AiOperationsProvider` inside `QueryProvider`; render the global indicator without exposing operation payloads. Use accessible `role="status"`, progressbar attributes, and button labels.

- [ ] **Step 3: Update API clients for immediate-or-operation unions**

Each submission validates either its existing ready response or `AiOperationAccepted`. On `202`, track the operation; on success, invalidate/fetch the existing domain query. Remove feature-owned ad hoc polling where the shared manager replaces it.

- [ ] **Step 4: Integrate all scoped feature entry points**

Cover career path, career intelligence, Application Kits, tailored resumes, learning roadmaps, career-path resumes, resume upload parsing, and enrichment. Preserve current success screens and downloads by loading results from existing domain endpoints after operation success.

- [ ] **Step 5: Run component tests and production build**

Run: `pnpm --filter app test && pnpm --filter app typecheck && pnpm --filter app lint && pnpm --filter app build`  
Expected: PASS and 32 static/generated pages.

- [ ] **Step 6: Commit**

```bash
git add app/src/app app/src/components app/src/lib/api app/src/lib/operations
git commit -m "feat: show recoverable AI generation progress"
```

### Task 9: Correct network errors and protect real-time paths

**Files:**
- Modify: `app/src/lib/api/auth-fetch.ts`
- Modify: `app/src/lib/chat/aaryaStream.ts`
- Modify: `app/src/lib/hooks/useVoice.ts`
- Create: `app/src/lib/api/auth-fetch.test.ts`
- Create: `app/src/lib/operations/external-ai-route-audit.test.ts`
- Delete: `app/tests/career-timeout.test.mjs`

- [ ] **Step 1: Write failing error-classification tests**

Prove same-origin proxy failures report the requested API path, operation failures retain their operation error code, aborts caused by a caller are not rewritten as server timeouts, and chat/voice retain their purpose-specific behavior.

- [ ] **Step 2: Implement boundary-accurate errors**

`ApiUnreachableError` must carry `path`, `reason`, and `timeoutMs`; browser copy must not claim the raw Railway hostname was contacted when the request used `/hireloop-api`. Preserve `AbortSignal` supplied by callers and distinguish caller cancellation from timeout.

- [ ] **Step 3: Audit remaining synchronous external-AI calls**

Use repository search and a test-maintained allowlist in `external-ai-route-audit.test.ts`. The allowlist contains chat message streaming, voice config/STT/TTS, and live voice endpoints only. Fail CI if a non-allowlisted frontend call targets a synchronous external-AI route. Delete the static career-timeout test because career generation now returns `202` instead of waiting 120 seconds.

- [ ] **Step 4: Run frontend tests and build**

Run: `pnpm --filter app test && pnpm --filter app typecheck && pnpm --filter app lint && pnpm --filter app build`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/src/lib/api/auth-fetch.ts app/src/lib/api/auth-fetch.test.ts app/src/lib/chat/aaryaStream.ts app/src/lib/hooks/useVoice.ts app/src/lib/operations/external-ai-route-audit.test.ts app/tests/career-timeout.test.mjs
git commit -m "fix: distinguish AI job and network failures"
```

### Task 10: Full verification, migration dry run, and rollout gate

**Files:**
- Modify: `PHASE_TRACKER.md`
- Modify: `docs/superpowers/plans/2026-07-22-durable-ai-operations.md` to check completed steps during execution

- [ ] **Step 1: Run the complete backend verification**

Run: `cd api && uv run ruff check . && uv run ruff format --check . && uv run pytest tests/ -v`  
Expected: all tests pass; integration skips are acceptable only when `REQUIRE_INTEGRATION_DB` is not set.

- [ ] **Step 2: Run the complete frontend verification**

Run: `pnpm --filter app test && pnpm typecheck && pnpm lint && pnpm build:web && pnpm build:app`  
Expected: all tests, type checks, lint, and both production builds pass.

- [ ] **Step 3: Run dependency and secret audits**

Run: `pnpm audit --prod --audit-level high` and export the frozen Python requirements with `uv export --format requirements-txt --no-dev --no-emit-project` for `pip-audit`. Run the repository secret scan used by CI.

- [ ] **Step 4: Dry-run the production migration**

Run: `supabase db push --linked --dry-run`  
Expected: only `20260722173000_ai_operations.sql` is pending at this stage.

- [ ] **Step 5: Deploy backend-first and smoke-test compatibility**

After explicit production approval, apply the migration, deploy Railway, verify health and authenticated old-client feature calls, then deploy Vercel. Do not reverse this order.

- [ ] **Step 6: Run authenticated production smoke tests**

For each scoped operation: submit, observe `202` under five seconds, refresh during execution, restore progress, complete, fetch the domain result, retry a simulated retryable failure, cancel queued work, and verify cross-user access returns 404.

- [ ] **Step 7: Audit Railway latency**

Query seven days of HTTP logs for non-streaming requests over 20 seconds. The only permitted long requests are explicitly documented real-time streams; all converted submissions must remain below the ordinary request budget.

- [ ] **Step 8: Update phase tracking and commit**

```bash
git add PHASE_TRACKER.md docs/superpowers/plans/2026-07-22-durable-ai-operations.md
git commit -m "docs: record durable AI operation rollout"
```

---

## Plan self-review

- Every approved design requirement maps to Tasks 1–10.
- Internal queue payloads remain private; frontend reads only owned operation projections.
- Backend-first deployment and immediate-result compatibility prevent version skew.
- Existing async handlers are reused instead of duplicated.
- Deterministic local analysis stays synchronous; only external non-interactive AI work is queued.
- Chat and voice remain real-time and are covered by an explicit allowlist test.
- No production mutation occurs without a separate approval and successful verification gate.
