# Candidate Flow Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the candidate journey feel faster by warming dashboard data, reusing cached panel payloads, and reducing avoidable skeleton/loading flashes.

**Architecture:** Keep changes client-side and surgical. Add a match-feed cache beside the existing profile/intros caches, warm candidate data once from `DashboardClient`, and let panels render cached data instantly while revalidating in the background.

**Tech Stack:** Next.js 15 App Router, React 18 client components, TypeScript strict mode, existing API wrappers, Tailwind CSS.

---

### Task 1: Add Match Feed Cache

**Files:**
- Modify: `app/src/lib/api/matches.ts`
- Create: `app/scripts/test-candidate-cache.cjs`

- [ ] **Step 1: Write the failing cache test**

Create a small script that imports the match API module and asserts it exports cache helpers:

```js
const assert = require("node:assert/strict");
const path = require("node:path");
const jiti = require("jiti")(__filename, {
  alias: {
    "@": path.join(__dirname, "../src"),
  },
});

const mod = jiti("../src/lib/api/matches.ts");

assert.equal(typeof mod.getCachedMatchFeed, "function");
assert.equal(typeof mod.invalidateMatchFeedCache, "function");
assert.equal(typeof mod.fetchMatchFeed, "function");
```

- [ ] **Step 2: Verify red**

Run: `cd app && ./node_modules/.bin/jiti scripts/test-candidate-cache.cjs`

Expected: fail because `getCachedMatchFeed` is not exported yet.

- [ ] **Step 3: Implement minimal cache helpers**

Add a module-level cache keyed by serialized `MatchFeedFilters`, de-dupe in-flight requests, and expose:

```ts
export function getCachedMatchFeed(filters: MatchFeedFilters = {}): MatchedJob[] | null
export function invalidateMatchFeedCache(): void
```

- [ ] **Step 4: Verify green**

Run: `cd app && ./node_modules/.bin/jiti scripts/test-candidate-cache.cjs`

Expected: pass.

### Task 2: Warm Dashboard Candidate Data

**Files:**
- Modify: `app/src/app/dashboard/DashboardClient.tsx`

- [ ] **Step 1: Prefetch routes and data on mount**

Use `useRouter` and a mount effect to prefetch `/voice`, `/resumes`, `/intros`, and `/dashboard?panel=jobs`, while warming `fetchSavedJobIds`, `fetchMatchFeed`, `fetchIntros`, and `fetchMyProfile`.

- [ ] **Step 2: Remove duplicate saved-job fetch**

Keep one warmup effect and reuse `setSavedJobIds`; avoid adding a second saved-job request.

### Task 3: Render Jobs Instantly From Cache

**Files:**
- Modify: `app/src/components/jobs/MatchFeed.tsx`

- [ ] **Step 1: Seed state from cache**

Initialize `jobs`, `loading`, `hasMore`, and `offset` from `getCachedMatchFeed({ min_score: 0, limit: 10, offset: 0 })` for the default feed.

- [ ] **Step 2: Revalidate quietly**

If cached jobs exist, render them immediately and fetch fresh data without showing the full skeleton.

### Task 4: Validate

**Files:**
- Test: `app/scripts/test-candidate-cache.cjs`

- [ ] **Step 1: Run focused cache test**

Run: `cd app && ./node_modules/.bin/jiti scripts/test-candidate-cache.cjs`

Expected: pass.

- [ ] **Step 2: Run TypeScript and lint**

Run: `cd app && pnpm typecheck && pnpm lint`

Expected: pass, or only pre-existing warnings.
