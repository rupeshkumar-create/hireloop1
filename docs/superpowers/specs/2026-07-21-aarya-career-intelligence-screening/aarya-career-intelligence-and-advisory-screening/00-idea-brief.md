# Aarya Career Intelligence and Advisory Screening — Idea Brief

## Problem

Candidates often provide a resume without the context needed for high-quality
matching: actual ownership, skill depth, preferred roles, location scope,
notice period, constraints, and deal-breakers. Recruiters then repeat basic
screening and still receive opaque fit scores with weak evidence.

Hireschema will let a candidate start or schedule a private 15-minute voice
conversation with Aarya. Aarya will conduct a natural, adaptive career-discovery
interview. The candidate reviews every extracted fact before it becomes trusted.
When the candidate applies to a recruiter-posted role, they may separately
consent to share a job-specific advisory screening summary. Recruiters never
receive the raw transcript or audio and retain every hiring decision.

## Users, Inputs, and Outputs

| User | Inputs | Outputs |
| --- | --- | --- |
| Candidate | Resume, confirmed profile, voice answers, corrections, sharing consent | Confirmed career profile, preferences, improved matches, private call history |
| Recruiter | Job description, hiring brief, evaluation criteria | Evidence-based advisory screening, gaps, confidence, follow-up questions |
| Operator | Queue and quality telemetry | Retry controls, audit trail, model/version diagnostics |

## Confirmed Product Decisions

- Candidates can start immediately or schedule for later.
- Calls are 15 minutes and run in-app; AI capacity is not represented as a
  globally exclusive calendar slot.
- The transcript is private by default.
- Audio is not stored by default.
- Extracted facts require candidate review and confirmation.
- Sharing a job-specific screening requires separate application-time consent.
- The recruiter assessment is advisory and cannot automatically reject anyone.
- Protected or sensitive traits and voice characteristics are excluded from
  screening and ranking.

## Constraints

- Follow `.cursorrules`: one single-threaded Aarya master loop, Postgres as the
  system of record, durable background jobs, no agent-to-agent RPC, and every
  tool call audited in `agent_actions`.
- India-only marketplace behavior remains enforced.
- OpenRouter must use configured model fallback; Deepgram STT/TTS must retain
  bounded timeouts and browser fallbacks.
- All runtime data is validated with Pydantic v2. No untyped dictionaries cross
  service boundaries.
- Frontends use FastAPI through `src/lib/api.ts`; they do not write Supabase
  directly.
- DPDP consent must be specific, revocable, and auditable.
- An application succeeds even if advisory screening is delayed or unavailable.

## Runtime Roles

These are responsibilities inside one Aarya workflow plus deterministic workers,
not independently communicating agents.

| Role | Goal | Input | Typed output | Owner |
| --- | --- | --- | --- | --- |
| Aarya interview mode | Conduct an adaptive, human-feeling discovery call | Confirmed candidate context and coverage state | Conversation turns and updated coverage state | Aarya master loop |
| Fact extractor | Propose candidate-stated facts with provenance | Private transcript and existing confirmed facts | `CandidateFactProposal[]` | Durable job handler |
| Evidence builder | Compare confirmed evidence with role criteria | Frozen candidate and role snapshots | `ScreeningEvidenceMatrix` | Deterministic service |
| Screening composer | Explain evidence without making the hiring decision | Validated evidence matrix | `AdvisoryScreeningDraft` | Durable job handler |
| Screening validator | Block unsafe, unsupported, or stale output | Draft, evidence matrix, consent and versions | Publishable screening or failure reason | Deterministic policy service |

## Success Measures

- At least 80% of completed calls produce a reviewable proposal set.
- Zero unconfirmed call facts are exposed to recruiters.
- Screening generation completion rate exceeds 99% within five minutes; the
  application itself remains available immediately.
- Every screening claim maps to a confirmed fact, resume item, or explicit role
  criterion.
- Unknown information is labeled unknown rather than scored as failure.
- Match engagement improves after confirmed profile updates without materially
  increasing irrelevant impressions.

## Assumptions

- Existing `conversations` and `messages` remain the transcript store.
- Existing `voice_sessions` becomes the lifecycle record for both instant and
  scheduled calls.
- Existing candidate intelligence, matching, `background_jobs`,
  `job_applications`, `role_pipeline`, and recruiter pipeline UI are extended.
- Recruiter role criteria are confirmed before screening is generated.

