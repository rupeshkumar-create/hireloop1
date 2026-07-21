# Aarya Career Intelligence and Advisory Screening — Roadmap

## Phase 1 — Trustworthy 15-Minute Career Call

- Unify instant and scheduled session lifecycle on one `voice_sessions` row.
- Change scheduling from scarce global slots to candidate-owned reminders.
- Add explicit private-call consent and no-audio default.
- Add typed interview coverage state and adaptive question policy.
- Persist interruption/completion reasons and support text degradation.
- Done when a candidate can start or schedule, complete or resume a call, and
  receive a private recap without direct profile mutation.

## Phase 2 — Candidate-Confirmed Intelligence

- Add fact proposals, provenance, validation, review APIs, and review UI.
- Create immutable candidate profile versions.
- Project confirmed facts into existing candidate intelligence and job
  preferences.
- Trigger embedding and match recomputation only after confirmation.
- Done when every voice-derived active fact has candidate confirmation and a
  source session, and matching uses the new confirmed version.

## Phase 3 — Job-Specific Advisory Screening

- Add application-time share consent.
- Freeze candidate/resume/role/criteria versions.
- Build deterministic constraint and criterion evidence.
- Add advisory composition, evidence validation, bias validation, and retries.
- Add recruiter screening card and candidate-visible shared summary.
- Done when screening failure never blocks application and recruiters cannot
  access transcripts, unconfirmed facts, or withdrawn assessments.

## Phase 4 — Quality Calibration and Operations

- Add queue dashboards, alerts, reconciliation, and manual safe retry.
- Add aggregate outcome analytics and screening-quality sampling.
- Measure false-positive/false-negative evidence mappings through human review.
- Tune prompts and deterministic rules under explicit versions.
- Do not automatically rewrite candidate facts or train ranking directly from
  recruiter decisions without a separately approved fairness design.

## Test Strategy

### Unit tests

- Coverage selection, time budget, declined topics, and repetition prevention
- Pydantic extraction contracts and prohibited inference rejection
- Proposal confirmation transactions and version conflicts
- Evidence matrix states, unknown handling, and constraint rules
- Consent and recruiter-ownership policies
- Narrative evidence-link and protected-field validation

### Integration tests

- Instant and scheduled call lifecycle using one session row
- Completed/partial call to durable extraction to candidate confirmation
- Confirmation to profile version to matching refresh
- Application plus grant/decline/withdraw consent flows
- Screening generation, retry, stale-input abort, and recruiter authorization
- RLS tests proving transcript and proposals are never recruiter-readable

### End-to-end beta tests

- Real Deepgram/OpenRouter call in English and Hinglish
- Resume-rich and resume-light candidates
- City-only, state-wide, remote, relocation, and all-India preferences
- Recruiter role with clear criteria, ambiguous criteria, and missing criteria
- Network interruption, provider outage, malformed model output, and queue delay

### Fairness and safety tests

- Counterfactual tests changing names or protected attributes without changing
  job evidence must not change the assessment.
- Accent, grammar, speaking speed, and emotion must never appear as evidence.
- Unsupported claims, transcript leakage, and automatic rejection language must
  fail publication.

## Release Gates

- Migrations applied with RLS on every new table.
- Focused Python tests, full relevant API tests, Ruff, TypeScript typecheck, lint,
  and production builds pass.
- Privacy review confirms consent copy, access paths, retention, and withdrawal.
- Real-provider smoke validates success and degraded modes.
- Metrics and safe alerts are live before recruiter screening is enabled.

## Recommended Implementation Order

Create a detailed plan for Phase 1 only, implement and beta-test it, then repeat
the design-to-plan checkpoint for each later phase. This keeps the candidate
trust boundary testable before recruiter-visible AI output is introduced.

