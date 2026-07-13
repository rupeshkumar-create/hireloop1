# MVP release readiness

## Business capability map

| Capability | Candidate surface | Recruiter surface | System of record | Release invariant |
|---|---|---|---|---|
| Identity and consent | Signup, onboarding, privacy settings | Signup, recruiter onboarding | `users`, `candidates`, `recruiters`, `consent_logs` | No sharing without explicit opt-in |
| Career profile | CV upload, profile editor, Aarya updates | Opted-in talent view | Candidate graph in Postgres | Candidate can review and correct data |
| Job discovery | Aarya, matches, saved jobs | Published roles | `jobs`, `match_scores` | India or India-eligible only |
| Application support | Kits, tailored CV, tracker, mock interview | Inbound application view | `application_kits`, `job_applications` | Candidate owns application state |
| Warm intro | Draft preview, Gmail approval, inbox | Role-scoped request and inbox | `intro_requests`, `gmail_tokens` | No send before candidate approval |
| Recruiting workflow | Candidate consent controls | Brief, talent, pipeline, interview kit | `roles`, `pipeline_candidates` | Every outreach action has a role |
| Agent execution | Aarya actions | Nitya actions | `agent_actions`, `background_jobs` | Durable, retryable, auditable |

## Before inviting beta users

- Apply all Supabase migrations, including the candidate privacy opt-in migration.
- Confirm production secrets pass the configuration fail-fast checks.
- Run CI with the integration database enabled and resolve every blocking scan.
- Verify bucket policies prevent cross-user resume reads.
- Confirm public-profile chat and public apply return `429` after their limits.
- Test Gmail connect, expired-token refresh, disconnect/revoke, draft preview, and
  candidate-approved send with a dedicated test account.
- Stop and restart the API during a CV parse and during a Nitya draft; both jobs
  must finish after restart without duplicate output.
- Test a candidate opt-out while a recruiter has the talent directory open; the
  candidate must disappear on refresh.
- Test recruiter discovery with no selected role; chat must remain disabled until
  the recruiter chooses explicit role context.

## Operational dashboard

Track these by environment and job kind:

- HTTP error rate and p50/p95/p99 latency.
- Pending/running/failed background jobs, oldest pending age, retries, and dead jobs.
- Resume parse and match refresh latency.
- OpenRouter, Apify, Firecrawl, Gmail, Deepgram, and MSG91 error/cost rates.
- Intro funnel: requested → draft ready → approved → sent → replied.
- Candidate funnel: signup → CV parsed → first match → save/kit/intro.
- Recruiter funnel: signup → role brief ready → first candidate → first intro.

Alert on any unapproved email send, cross-tenant access test failure, production
default secret, oldest interactive job over five minutes, or a sustained external
provider failure.

