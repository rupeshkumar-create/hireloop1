# Application Kit and Dashboard Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make application-kit creation, instant Job History, and dashboard recovery survive the confirmed production data-shape and transient network failures without exposing infrastructure details.

**Architecture:** Normalize asyncpg JSON text at the application-kit boundary, preserve instant-shelf fallback by fixing standard-library logging, and wrap every application-kit network request with the existing same-origin transient retry helper. Add a small pure recovery module for candidate-safe errors and one-time chunk reloads, plus a sanitized same-origin client-error logging endpoint.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pytest, Next.js 15, TypeScript, React, Zod, Node test runner, Vercel, Railway.

---

## File map

- Modify `api/src/hireloop_api/services/application_kit.py`: coerce JSON objects before generation.
- Modify `api/src/hireloop_api/services/outcome_learning.py`: tolerate malformed `profile_enrichment` defensively.
- Modify `api/src/hireloop_api/services/instant_shelf.py`: use valid standard-library logging context.
- Modify `api/tests/test_application_kit_guardrails.py`: regression coverage for asyncpg JSON text.
- Modify `api/tests/test_instant_shelf.py`: prove search failure still persists starter history.
- Modify `app/src/lib/api/applicationKit.ts`: same-origin retries, typed connectivity failure, resumable status checks.
- Create `app/src/lib/api/application-kit-recovery.ts`: pure candidate-safe error classification.
- Create `app/src/lib/api/application-kit-recovery.test.ts`: retry and safe-copy tests.
- Modify `app/src/components/chat/ChatInterface.tsx`: Check again and Retry recovery actions.
- Create `app/src/lib/client-error-report.ts`: chunk classification, one-reload guard, bounded report payload.
- Create `app/src/lib/client-error-report.test.ts`: pure recovery/sanitization tests.
- Create `app/src/app/api/client-errors/route.ts`: sanitize with Zod and log bounded reports.
- Modify `app/src/app/error.tsx`: report and auto-reload transient load failures once.
- Modify `app/src/app/global-error.tsx`: report last-resort client failures.
- Modify `app/package.json`: run all reliability tests.

### Task 1: Normalize application-kit JSON fields

**Files:**
- Modify: `api/src/hireloop_api/services/application_kit.py`
- Modify: `api/src/hireloop_api/services/outcome_learning.py`
- Test: `api/tests/test_application_kit_guardrails.py`

- [ ] **Step 1: Write failing JSON coercion tests**

Add tests that import `_coerce_json_object` and verify the production shapes:

```python
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"star_stories": ["Launch"]}, {"star_stories": ["Launch"]}),
        ('{"star_stories":["Launch"]}', {"star_stories": ["Launch"]}),
        ("not-json", {}),
        (["wrong-shape"], {}),
        (None, {}),
    ],
)
def test_coerce_json_object(value: object, expected: dict[str, object]) -> None:
    assert _coerce_json_object(value) == expected


def test_interview_prep_ignores_string_profile_enrichment() -> None:
    out = build_kit_aware_interview_prep(
        base_prep="## Likely questions",
        dossier=None,
        job={"title": "Growth Lead", "company_name": "Acme"},
        profile={"profile_enrichment": '{"star_stories":["Launch"]}'},
    )
    assert "Role focus" in out
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `cd api && uv run pytest tests/test_application_kit_guardrails.py -q`

Expected: import failure for `_coerce_json_object` and/or `'str' object has no attribute 'get'`.

- [ ] **Step 3: Implement minimal coercion at the boundary**

Add to `application_kit.py`:

```python
def _coerce_json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
```

When loading enrichment, assign:

```python
profile["profile_enrichment"] = _coerce_json_object(enrich_row["profile_enrichment"])
```

In `build_kit_aware_interview_prep`, guard the existing value:

```python
raw_enrich = profile.get("profile_enrichment")
enrich = raw_enrich if isinstance(raw_enrich, dict) else {}
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `cd api && uv run pytest tests/test_application_kit_guardrails.py tests/test_application_kit_routes.py -q`

Expected: all application-kit tests pass.

- [ ] **Step 5: Commit the API JSON repair**

```bash
git add api/src/hireloop_api/services/application_kit.py api/src/hireloop_api/services/outcome_learning.py api/tests/test_application_kit_guardrails.py
git commit -m "fix: normalize application kit profile json"
```

### Task 2: Keep instant Job History alive after search failure

**Files:**
- Modify: `api/src/hireloop_api/services/instant_shelf.py`
- Modify: `api/tests/test_instant_shelf.py`

- [ ] **Step 1: Write the failing fallback-persistence test**

```python
@pytest.mark.asyncio
async def test_search_failure_logs_and_persists_starter_history() -> None:
    db = AsyncMock()
    candidate_id = uuid.uuid4()
    db.fetchrow.return_value = {
        "id": candidate_id,
        "looking_for": "Growth",
        "current_title": None,
        "market": "IN",
        "remote_preference": "any",
    }
    starter = [{"job_id": str(uuid.uuid4()), "title": "Growth Lead"}]
    with (
        patch("hireloop_api.agents.aarya.tools.job_search", new_callable=AsyncMock, side_effect=RuntimeError("temporary")),
        patch("hireloop_api.routes.matches._fetch_starter_market_jobs", new_callable=AsyncMock, return_value=starter),
    ):
        result = await fetch_instant_shelf(db, user_id=str(uuid.uuid4()), settings=MagicMock())
    assert result == starter
    db.executemany.assert_awaited_once()
```

- [ ] **Step 2: Run and verify RED**

Run: `cd api && uv run pytest tests/test_instant_shelf.py::test_search_failure_logs_and_persists_starter_history -q`

Expected: failure with `Logger._log() got an unexpected keyword argument 'user_id'`.

- [ ] **Step 3: Fix the standard logger call**

Replace unsupported fields with:

```python
logger.warning(
    "instant_shelf_job_search_failed",
    extra={"user_id": user_id, "error": str(exc)[:200]},
)
```

- [ ] **Step 4: Run instant-shelf and history tests**

Run: `cd api && uv run pytest tests/test_instant_shelf.py tests/test_chat_match_persist.py -q`

Expected: all tests pass and starter rows are persisted.

- [ ] **Step 5: Commit the Job History repair**

```bash
git add api/src/hireloop_api/services/instant_shelf.py api/tests/test_instant_shelf.py
git commit -m "fix: preserve instant job history on search failure"
```

### Task 3: Retry application-kit requests and expose safe recovery state

**Files:**
- Create: `app/src/lib/api/application-kit-recovery.ts`
- Create: `app/src/lib/api/application-kit-recovery.test.ts`
- Modify: `app/src/lib/api/applicationKit.ts`
- Modify: `app/package.json`

- [ ] **Step 1: Write failing client recovery tests**

Test a transient start failure followed by success, a transient poll failure followed by ready, and safe error copy:

```typescript
test("connectivity failures never expose infrastructure", () => {
  const raw = Object.assign(new Error("Can't reach API at https://railway.example: Failed to fetch"), {
    name: "ApiUnreachableError",
  });
  const safe = toApplicationKitFailure(raw);
  assert.equal(safe.kind, "connectivity");
  assert.equal(safe.message, "We had trouble connecting. Your application kit is still being prepared.");
  assert.doesNotMatch(safe.message, /railway|failed to fetch/i);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `cd app && node --experimental-strip-types --test src/lib/api/application-kit-recovery.test.ts`

Expected: module/function not found.

- [ ] **Step 3: Add the pure recovery contract**

Create:

```typescript
export const APPLICATION_KIT_CONNECTIVITY_MESSAGE =
  "We had trouble connecting. Your application kit is still being prepared.";

export type ApplicationKitFailure = {
  kind: "connectivity" | "failed";
  message: string;
};

export function toApplicationKitFailure(error: unknown): ApplicationKitFailure {
  if (
    error instanceof Error &&
    ["ApiUnreachableError", "AbortError", "TimeoutError", "TypeError"].includes(error.name)
  ) {
    return { kind: "connectivity", message: APPLICATION_KIT_CONNECTIVITY_MESSAGE };
  }
  return {
    kind: "failed",
    message: "We couldn't finish your application kit. Please retry.",
  };
}
```

- [ ] **Step 4: Wrap start, requeue, and each status request**

In `applicationKit.ts`, call `withTransientRetry` around each `apiAuthFetch`. Export:

```typescript
export async function checkApplicationKit(jobId: string): Promise<ApplicationKit> {
  return pollApplicationKit(jobId);
}

export async function retryApplicationKit(jobId: string): Promise<ApplicationKit> {
  return startAndPollApplicationKit(jobId);
}
```

Pass test-only retry options through an internal dependency object so tests use a no-op sleeper; production keeps 350/900ms backoff. Throw the safe typed failure only after transient retries are exhausted.

- [ ] **Step 5: Run and verify GREEN**

Run: `cd app && node --experimental-strip-types --test src/lib/api/application-kit-recovery.test.ts src/lib/api/transient-retry.test.ts`

Expected: all retry and safe-copy tests pass.

- [ ] **Step 6: Update the package test script and commit**

Set `test:reliability` to run both test files, then:

```bash
git add app/src/lib/api/applicationKit.ts app/src/lib/api/application-kit-recovery.ts app/src/lib/api/application-kit-recovery.test.ts app/package.json
git commit -m "fix: retry application kit connectivity failures"
```

### Task 4: Render Check again and Retry in chat

**Files:**
- Modify: `app/src/components/chat/ChatInterface.tsx`

- [ ] **Step 1: Add a typed recovery state**

Extend the local message type with:

```typescript
kitRecovery?: { jobId: string; title: string; company: string };
```

On `toApplicationKitFailure(error).kind === "connectivity"`, set the exact safe message and `kitRecovery` instead of interpolating the raw exception.

- [ ] **Step 2: Add deterministic recovery handlers**

```typescript
const runKitRecovery = useCallback(
  async (messageId: string, request: KitRecovery, mode: "check" | "retry") => {
    const kit = mode === "check"
      ? await checkApplicationKit(request.jobId)
      : await retryApplicationKit(request.jobId);
    // Replace the same assistant message with ready content and kit cards.
  },
  [],
);
```

Disable both buttons while the recovery request is active.

- [ ] **Step 3: Render explicit actions in `MessageBubble`**

Render two buttons only when `message.kitRecovery` exists:

```tsx
<button type="button" onClick={() => onKitRecovery("check")}>Check again</button>
<button type="button" onClick={() => onKitRecovery("retry")}>Retry</button>
```

Use existing button classes and clear recovery state after success.

- [ ] **Step 4: Verify frontend statically**

Run: `corepack pnpm --filter app lint && corepack pnpm --filter app typecheck`

Expected: no warnings or TypeScript errors.

- [ ] **Step 5: Commit the recovery UI**

```bash
git add app/src/components/chat/ChatInterface.tsx
git commit -m "fix: add application kit recovery actions"
```

### Task 5: Add one-time dashboard reload and sanitized client telemetry

**Files:**
- Create: `app/src/lib/client-error-report.ts`
- Create: `app/src/lib/client-error-report.test.ts`
- Create: `app/src/app/api/client-errors/route.ts`
- Modify: `app/src/app/error.tsx`
- Modify: `app/src/app/global-error.tsx`
- Modify: `app/package.json`

- [ ] **Step 1: Write failing pure recovery tests**

Cover:

```typescript
assert.equal(classifyClientLoadError(new Error("ChunkLoadError: Loading chunk 123 failed")), "chunk_load");
assert.equal(classifyClientLoadError(new Error("ordinary render bug")), "other");
assert.equal(shouldReloadOnce("/dashboard", null), true);
assert.equal(shouldReloadOnce("/dashboard", "/dashboard"), false);
assert.doesNotMatch(sanitizeClientErrorText("fetch https://secret.example/path?token=abc"), /https|token=abc/);
```

- [ ] **Step 2: Run and verify RED**

Run: `cd app && node --experimental-strip-types --test src/lib/client-error-report.test.ts`

Expected: module/function not found.

- [ ] **Step 3: Implement pure classification and sanitization**

Use conservative patterns for `ChunkLoadError`, `Loading chunk`, and `Failed to fetch dynamically imported module`. Replace URL-like substrings with `[url]`, remove control characters, and truncate name/message/digest/path to fixed limits. Do not include stack traces or query strings.

- [ ] **Step 4: Add the same-origin telemetry route**

Validate with Zod:

```typescript
const schema = z.object({
  name: z.string().max(80),
  message: z.string().max(300),
  digest: z.string().max(120).optional(),
  pathname: z.string().max(160),
  classification: z.enum(["chunk_load", "other"]),
});
```

Log one JSON object with event name `client_error_report`; return `204`. Reject invalid bodies with `400`. Never log headers, cookies, body extras, stack traces, or query strings.

- [ ] **Step 5: Wire both error boundaries**

On mount, fire-and-forget `reportClientError`. In route `error.tsx`, if classification is `chunk_load` and the pathname has not reloaded in this session, set the session key and call `window.location.reload()`. Keep the existing manual buttons for all persistent errors.

- [ ] **Step 6: Run and verify GREEN**

Run: `cd app && node --experimental-strip-types --test src/lib/client-error-report.test.ts`

Expected: all classification/sanitization tests pass.

- [ ] **Step 7: Commit telemetry and recovery**

```bash
git add app/src/lib/client-error-report.ts app/src/lib/client-error-report.test.ts app/src/app/api/client-errors/route.ts app/src/app/error.tsx app/src/app/global-error.tsx app/package.json
git commit -m "fix: recover transient dashboard load failures"
```

### Task 6: Full verification and review

**Files:**
- Review all changed files from Tasks 1–5.

- [ ] **Step 1: Run focused tests**

```bash
cd api && uv run pytest tests/test_application_kit_guardrails.py tests/test_application_kit_routes.py tests/test_instant_shelf.py tests/test_chat_match_persist.py -q
cd app && corepack pnpm test:reliability
```

- [ ] **Step 2: Run full API verification**

```bash
cd api && uv run pytest tests/ -q
cd api && uv run ruff check .
cd api && uv run ruff format --check .
```

- [ ] **Step 3: Run full frontend verification**

```bash
corepack pnpm --filter app lint
corepack pnpm --filter app typecheck
corepack pnpm --filter app build
```

- [ ] **Step 4: Self-review security and recovery behavior**

Confirm that no candidate-visible string contains `Railway`, a backend hostname, `NEXT_PUBLIC_API_URL`, or `Failed to fetch`; telemetry contains no stack, cookie, authorization, email, user ID, or query string; reload guards cannot loop.

- [ ] **Step 5: Commit any test-only corrections**

```bash
git add api app
git commit -m "test: cover application kit production recovery"
```

Skip the commit when the worktree is already clean.

### Task 7: Deploy and safely recover the failed production kit

**Files:**
- No source changes expected.

- [ ] **Step 1: Push the feature branch and update PR #14**

Run: `git push origin codex/onboarding-job-history`

Expected: GitHub PR #14 includes all reliability commits.

- [ ] **Step 2: Deploy Railway and monitor readiness**

Run from `api/`: `railway up --detach`, then inspect `railway status` and deployment logs until the new deployment is Online and `/api/v1/health` returns 200 through `www.hireschema.com`.

- [ ] **Step 3: Deploy Vercel production and monitor readiness**

Run: `npx vercel --prod --yes`, then `npx vercel inspect https://www.hireschema.com`.

Expected: target `production`, status `Ready`, aliases include both Hireschema domains.

- [ ] **Step 4: Requeue only the confirmed failed job**

Read durable job `de37d279-a15a-440c-ba27-e428b30575b1` to retrieve its candidate/job payload. Reset only that row from `failed` to `pending`, clear `last_error`, set `attempts = 0`, and set `run_after = NOW()`. Do not print candidate data and do not touch any other job.

- [ ] **Step 5: Verify the recovered job**

Poll that exact background job until `completed`. Verify its candidate/job row in `job_application_kits` has a non-null `tailored_resume_id`. If it fails, stop and inspect the new logged stage before attempting another requeue.

- [ ] **Step 6: Smoke-test public production**

Verify:

```text
GET /hireloop-api/api/v1/health -> 200
GET /dashboard -> 200 or auth redirect
POST /api/client-errors with sanitized synthetic payload -> 204
unauthenticated application-kit route -> 401 (proves proxy route without data mutation)
```

Inspect Railway/Vercel logs for the smoke request IDs and confirm the telemetry event contains bounded, sanitized fields.

- [ ] **Step 7: Final repository check**

Run `git status --short` and confirm the worktree is clean, the GitHub branch is current, and PR #14 remains mergeable.
