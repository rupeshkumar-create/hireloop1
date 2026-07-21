# Aarya Career Intelligence and Advisory Screening — Tool Execution

## Tooling Model

The Aarya loop may call small, policy-checked tools. Mutating tools write through
FastAPI services using the current authenticated candidate. Post-call workers
do not use arbitrary tools; they execute one typed function with a frozen input.

## Tool Access

| Tool or operation | Called by | Access | Guardrails | Fallback |
| --- | --- | --- | --- | --- |
| `career_interview_read` | Aarya | Read | Current candidate and active session only; confirmed facts only | Continue with resume/basic profile |
| `career_interview_coverage_update` | Aarya | Write | Fixed field allow-list, optimistic state version, `agent_actions` audit | Re-read state and retry once |
| Transcript turn persistence | Chat route | Write | Authenticated conversation ownership; text only | Return retryable turn error |
| Deepgram live STT | Voice proxy | External read | 30-second utterance guard, no retained audio | Batch STT, then browser STT |
| Deepgram TTS | Voice route | External output | Ten-second timeout and speech sanitization | Browser speech synthesis or text |
| Fact extraction | Durable worker | Read/write | Transcript-owner check, Pydantic output, no direct profile update | Retry with fallback model; manual retry |
| Fact confirmation | Candidate review API | Write | Candidate ownership, proposal status/version, transaction | Conflict response with refreshed proposals |
| Match recomputation | Durable worker | Write | Confirmed profile version and existing matching policy | Existing profile remains active |
| Screening generation | Durable worker | Read/write | Consent, immutable versions, role ownership, Pydantic contracts | Resume-only recruiter view |
| Recruiter screening read | Recruiter API | Read | Recruiter owns role; screening is published and consent active | Hide screening; retain applicant card |

## Prompt Strategy

### Aarya interview prompt

The system prompt contains the interview purpose, the confirmed candidate
snapshot, the next focus selected by policy, previously asked questions, and a
strict prohibition on protected-trait or voice-characteristic inference. It
asks one concise question at a time and never exposes internal coverage labels.

### Fact extraction prompt

The model returns `CandidateFactProposal[]` with field name, typed value,
confidence, and supporting message IDs. It may return `unknown` or no proposal.
It cannot infer facts from Aarya's messages, tone, accent, hesitation, or silence.

### Screening prompt

The model sees only a validated evidence matrix and role context. It does not
receive the transcript, audio, protected attributes, or arbitrary recruiter
notes. It produces strengths, gaps, confidence explanation, and follow-up
questions. It cannot issue accept/reject instructions.

## Execution Lifecycle

1. Validate auth, ownership, consent, schema version, and idempotency key.
2. Load the minimal allowed snapshot.
3. Execute deterministic work first.
4. Call OpenRouter only when narrative or structured extraction is required.
5. Validate Pydantic output and evidence references.
6. Retry once with stricter formatting if output is invalid.
7. Use the configured fallback model for provider failure.
8. Persist status, model version, prompt version, latency, and safe error code.
9. Publish only after deterministic policy validation.

## Risk Controls

- Mutating calls fail closed when Postgres is unavailable.
- No prompt or log contains raw audio; transcript content is excluded from
  production logs and `agent_actions` payloads.
- LLM timeouts use the existing bounded OpenRouter setting.
- Queue attempts are bounded at three with exponential backoff.
- Every published screening includes evidence IDs, snapshot versions, policy
  version, and creation time.
- Candidate confirmation and screening-share consent are human approval gates;
  recruiters do not approve facts on a candidate's behalf.

