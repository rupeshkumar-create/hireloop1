# Aarya Career Intelligence and Advisory Screening — Failure Recovery

## Failure Matrix

| Failure | Detection | User impact | Automatic response | Manual response |
| --- | --- | --- | --- | --- |
| Live STT disconnect | WebSocket close/timeout | Captions or input pause | Reconnect once, then batch/browser STT | Candidate retries utterance or continues in text |
| TTS failure | Ten-second timeout/provider error | Aarya cannot speak | Browser TTS, then text-only response | Continue chat without audio |
| Browser closes mid-call | Session heartbeat expires | Call interrupted | Preserve turns and allow resume window | Candidate resumes or completes partial call |
| Aarya LLM timeout | Bounded OpenRouter error | One response delayed | Fallback model and concise retry | Candidate retries turn |
| Extraction invalid | Pydantic/evidence validation fails | Review not ready | Strict retry, fallback model, queue retry | Operator retry; candidate profile unchanged |
| Candidate confirmation conflict | Stale proposal/state version | Confirmation rejected | Return current version | Candidate reviews refreshed proposals |
| Queue lag | Oldest pending interactive job age | Review/screening delayed | Interactive prioritization and alert | Scale worker or replay safe jobs |
| Match refresh failure | Background job failed | Existing recommendations remain | Bounded retry | Manual retry; no profile rollback |
| Screening model failure | Job error or invalid output | Screening card pending | Fallback model; deterministic evidence retained | Retry or show resume-only view |
| Bias/evidence validation failure | Unsupported claim or banned field | Screening not published | One constrained regeneration | Review safe diagnostics, never publish draft |
| Consent withdrawn | Consent state change | Screening disappears for recruiter | Mark screening withdrawn and enforce read policy | No regeneration without new consent |
| Source version changes | Version mismatch before publish/read | Screening becomes stale | Abort publish or mark stale | Regenerate with current versions |
| Database unavailable | Connection/transaction failure | State-changing action unavailable | Fail closed; do not acknowledge confirmation | Retry after recovery |

## Resilience Controls

- Three queue attempts with exponential backoff and existing stuck-job recovery.
- Version-aware idempotency keys for extraction, confirmation side effects,
  matching, and screening.
- Compare-and-swap `state_version` for interview coverage and candidate review.
- Circuit-break OpenRouter generation after sustained provider failures while
  leaving deterministic evidence and ordinary applications available.
- Store safe error codes separately from detailed server logs; never place
  transcript content or candidate facts in errors.
- Operator views show job kind, attempt, age, model, source versions, and safe
  reason code.

## Degraded Modes

- Voice failure: continue the same Aarya session through text.
- Extraction failure: candidate retains the transcript and existing profile;
  provide “Try processing again.”
- Partial call: extract only explicitly stated facts and label the session
  partial; candidate review remains mandatory.
- Screening failure or declined consent: recruiter sees the existing applicant
  card, resume, and ordinary matching data only.
- Stale screening: display the timestamp and stale label; do not silently blend
  old and new evidence.

## Observability

Metrics:

- Call start, completion, interruption, and resume rates
- STT/TTS latency and fallback rates
- Coverage by topic and repeated-question rate
- Extraction latency, invalid-output rate, and proposal confirmation/edit/reject rates
- Time from confirmation to refreshed matches
- Screening queue latency, publish/failure/stale rates, and consent rate
- Evidence-validator and bias-validator rejection rates
- Recruiter opening and follow-up usage, separated from hiring decisions

Correlate logs using `voice_session_id`, `conversation_id`, `workflow_id`,
`background_job_id`, `application_id`, and `screening_id`. Sentry must receive
exceptions without PII.

## Operational Recovery

Provide admin-only actions to retry failed extraction or screening jobs and to
reconcile stuck session states. Manual recovery never confirms facts, grants
consent, or publishes an unvalidated screening on behalf of a user.

