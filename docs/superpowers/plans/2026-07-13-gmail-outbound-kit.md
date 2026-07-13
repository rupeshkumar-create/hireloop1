# Gmail Outbound Kit Implementation Plan

> **For agentic workers:** Execute task-by-task. Checkboxes track progress.

**Goal:** Approve-first intro follow-ups, thank-you drafts/sends, and voice booking Google/Meet polish.

**Architecture:** Extend `intro_requests` with follow-up/thank-you draft columns; flip `intro_followups` sweep to draft+notify; add intros API endpoints; mirror UI on IntroDraftPanel; polish voice book CTA.

**Tech Stack:** FastAPI, asyncpg, Gmail OAuth send, Next.js intros UI, existing notifications.

---

### Task 1: Migration
### Task 2: Follow-up sweep → draft + notify
### Task 3: Follow-up + thank-you API routes
### Task 4: Status-transition thank-you prompt hook
### Task 5: Frontend intros UI + API client
### Task 6: Voice booking Meet / Connect Google polish
### Task 7: Tests
