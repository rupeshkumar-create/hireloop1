# Aarya Career Intelligence and Advisory Screening — Service Architecture

## Services

These are bounded modules in the existing Next.js, FastAPI, Railway, and
Supabase deployment—not new network services for the MVP.

| Module | Responsibility | Dependencies | Scaling |
| --- | --- | --- | --- |
| Voice UI | Start/resume/end calls, live captions, review entry point | Next.js, Deepgram proxy, chat SSE | Browser-local per session |
| Voice session routes | Instant/scheduled lifecycle, consent, ownership | FastAPI, Postgres, notifications | Stateless API |
| Aarya runtime | One-turn conversation and tool selection | OpenRouter, LangGraph checkpoint, Postgres | Existing single loop per session |
| Interview policy | Coverage selection and sensitive-topic rules | Confirmed snapshot, interview state | Pure deterministic module |
| Candidate review routes | List/edit/confirm proposals | FastAPI, Postgres transaction | Stateless API |
| Background worker | Extraction, match refresh, screening jobs | Existing `background_jobs` queue | Existing interactive lane |
| Screening service | Snapshot, evidence, composition, validation | Candidate intelligence, roles, OpenRouter | Concurrent interactive jobs |
| Recruiter API/UI | Authorized screening read and presentation | FastAPI, Next.js pipeline | Existing recruiter surface |

## API Contracts

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/voice/sessions/start` | Create an instant session or activate an owned scheduled session |
| `POST /api/v1/voice/sessions/{id}/complete` | Complete one row and enqueue extraction idempotently |
| `GET /api/v1/voice/sessions/{id}/review` | Return pending typed proposals and private recap |
| `PATCH /api/v1/voice/sessions/{id}/review` | Edit/reject proposals with optimistic version |
| `POST /api/v1/voice/sessions/{id}/confirm` | Confirm proposals, activate profile version, enqueue rematch |
| `POST /api/v1/job-applications/{id}/screening-consent` | Grant, decline, or withdraw job-specific sharing |
| `GET /api/v1/job-applications/{id}/screening` | Candidate-visible screening status and summary |
| `GET /api/v1/recruiter/roles/{role_id}/pipeline/{entry_id}/screening` | Recruiter-owned published advisory assessment |
| `POST /api/v1/recruiter/roles/{role_id}/pipeline/{entry_id}/screening/retry` | Authorized manual retry when inputs are current |

All request and response bodies use Pydantic v2 models. UUID ownership is checked
server-side. Existing phone-verification policy remains configurable rather than
being hard-coded into these routes.

## Event Contracts

Every background payload includes `workflow_id`, `task_id`, `attempt`,
`schema_version`, source IDs, source versions, and an idempotency key.

| Event/job | Producer | Consumer | Completion effect |
| --- | --- | --- | --- |
| `career_interview_extract` | Session completion route | Extraction handler | Proposals become `review_pending` |
| `candidate_profile_confirmed` | Review service | Match job enqueue | Active candidate version changes |
| `application_screening` | Application/consent service | Screening handler | Screening becomes published or failed |
| `screening_withdrawn` | Consent service | Recruiter read policy | Published result becomes inaccessible |

## Screening Pipeline

1. Verify application, recruiter-posted role, and active share consent.
2. Resolve and persist exact candidate, resume, role, and criteria versions.
3. Evaluate deterministic constraints and must-have criteria.
4. Construct an evidence matrix with `meets`, `partial`, `unknown`, or
   `constraint_mismatch` per criterion.
5. Generate an advisory narrative from the matrix.
6. Validate every narrative claim against evidence IDs.
7. Run protected-field and banned-reason checks.
8. Publish atomically and notify the recruiter.

## Scheduling Correction

AI calls do not require global slot exclusion or Google Meet. Scheduling creates
an owned future `voice_sessions` row and reminder. A candidate can start it from
Hireschema at the scheduled time. Google Calendar may receive an optional event
whose link returns to the in-app call, but one candidate's booking does not make
the time unavailable to others.

## Deployment

- Continue running the API and durable worker in the Railway FastAPI service for
  MVP, with interactive queue priority.
- Use existing Vercel-to-Railway API proxy and Supabase Postgres/Auth.
- Keep secrets in Railway/Vercel environment management.
- Use feature flags for interview coverage, fact review, and recruiter screening
  so each phase can be enabled independently.

