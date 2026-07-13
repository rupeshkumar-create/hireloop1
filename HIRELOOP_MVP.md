# Hireschema MVP product contract

This document defines the release contract for the India-only MVP. It complements
`.cursorrules`; when they differ, `.cursorrules` wins.

## Product promise

Hireschema gets a candidate from CV to a relevant, explainable job match and a
candidate-approved warm intro. It gets a recruiter from a role brief to an
evidence-backed, consented shortlist and a two-sided conversation.

All existing product capabilities remain available. The MVP prioritises two clear
paths rather than hiding or deleting secondary tools.

## Candidate success path

1. Sign up and accept the India/DPDP terms.
2. Upload a PDF or DOCX CV; parsing continues durably if the API restarts.
3. Review extracted profile data and decide whether recruiter discovery or a
   public profile should be enabled. Both are off by default.
4. Ask Aarya for roles. Results must be India-based or explicitly India-eligible,
   explain the fit, and never require missing salary data before showing value.
5. Save a role or prepare an application kit. The candidate remains the source of
   truth for every application status.
6. Request an intro, review Nitya's draft as inert text, connect Gmail if needed,
   and explicitly approve before anything is sent.

## Recruiter success path

1. Create or import one role and confirm the role brief.
2. Search only candidates who opted into recruiter discovery, with the active
   role selected before outreach.
3. Review fit evidence, gaps, candidate intent, and pipeline history.
4. Request a two-sided intro. The candidate can accept or decline before chat.
5. Move the candidate through a role-specific pipeline with notes and a scorecard.

## Privacy and safety contract

- Candidate recruiter discovery and public-profile publishing are independent,
  explicit opt-ins and default to false.
- Public contact fields are hidden by default. Turning off sharing immediately
  removes the profile from the corresponding discovery surface.
- Uploaded CVs are size-, MIME-, and file-signature validated before parsing.
- AI-authored HTML is never executed in candidate or recruiter application UI.
- Gmail tokens are encrypted at rest, decrypted before revocation, and corrupt
  ciphertext fails closed.
- Candidate-to-HM email is never sent without candidate approval and always uses
  the candidate's Gmail OAuth connection.
- Public AI chat and public applications are IP-rate-limited; authenticated LLM
  actions are user-rate-limited.

## Reliability contract

- Resume parsing, application kits, enrichment, matching, and Nitya intro drafts
  use the Postgres durable job queue with idempotency keys, bounded retries, and
  stale-job recovery.
- Postgres rows are the source of truth. Realtime and LISTEN/NOTIFY reduce latency;
  they are not the only record of required work.
- Multiple workers claim jobs with `FOR UPDATE SKIP LOCKED`. Nitya additionally
  uses an advisory lock per intro.
- Every agent tool action is auditable through `agent_actions`.

## Release gates

- API Ruff, unit tests, integration/IDOR tests, migration bootstrap.
- Frontend lint, strict TypeScript checks, and production builds for `web` and `app`.
- Blocking secret scans and high-severity dependency audits.
- Manual beta smoke of both success paths with real Supabase, OpenRouter, Apify,
  Gmail OAuth, and optional MSG91 credentials.

## MVP success measures

- Candidate activation: CV parsed and first useful match viewed.
- Candidate value: saved role, application kit, or intro requested within the
  first session.
- Recruiter activation: role brief completed and first role-scoped candidate viewed.
- Marketplace quality: percentage of shown roles that are India-eligible and
  percentage of recruiter results that are consented.
- Reliability: durable-job completion rate, retries by kind, stuck jobs, resume
  parse latency, and intro draft latency.
- Trust: sharing opt-in rate, sharing opt-out completion, account deletion SLA,
  and zero unapproved outbound intros.

