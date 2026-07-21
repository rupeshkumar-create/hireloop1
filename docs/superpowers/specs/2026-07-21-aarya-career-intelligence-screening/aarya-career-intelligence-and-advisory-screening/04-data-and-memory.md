# Aarya Career Intelligence and Advisory Screening — Data and Memory

## Storage Principles

- Postgres is the system of record for session state, consent, facts, versions,
  applications, screenings, and audits.
- Existing conversation messages hold the private text transcript.
- No audio object is written by default.
- Confirmed facts and job preferences feed candidate intelligence; raw transcript
  text does not enter embeddings or recruiter search.
- Recruiter-facing screening records contain derived evidence summaries, never
  transcript excerpts.

## Schema Changes

Create one migration, tentatively
`supabase/migrations/20260721HHMMSS_aarya_career_screening.sql`.

### Extend `voice_sessions`

Add `conversation_id`, `consent_version`, `transcript_version`,
`completion_reason`, `extraction_status`, `profile_version_before`, and
`profile_version_after`. Starting a scheduled call updates the scheduled row;
completion updates that same row.

### `career_interview_states`

| Column | Purpose |
| --- | --- |
| `session_id` | Primary key and FK to `voice_sessions` |
| `candidate_id` | Ownership and indexed lookup |
| `state` | Typed coverage JSONB |
| `state_version` | Optimistic concurrency counter |
| `created_at`, `updated_at` | Audit timing |

### `candidate_fact_proposals`

| Column | Purpose |
| --- | --- |
| `id`, `candidate_id`, `session_id` | Identity and ownership |
| `domain`, `field_name`, `value` | Typed proposed fact |
| `source_message_ids` | Private provenance, never recruiter-visible |
| `confidence` | Extraction confidence, not candidate quality |
| `status` | `pending`, `confirmed`, `edited`, `rejected`, `superseded` |
| `reviewed_at` | Candidate action time |

### `candidate_profile_versions`

Store an immutable typed snapshot containing confirmed career facts, job
preferences, negative preferences, source fact IDs, schema version, and creation
reason. Only one version is active per candidate. Activation and candidate table
projection occur in one transaction.

### `application_screening_consents`

One record per application and policy version: `granted`, `declined`, or
`withdrawn`, with timestamp and consent copy version. This is separate from
general recruiter-discovery consent.

### `application_screenings`

| Field group | Contents |
| --- | --- |
| Identity | Application, candidate, role, recruiter ownership |
| Frozen inputs | Candidate profile version, resume version, role/brief version |
| Status | `pending`, `running`, `published`, `failed`, `withdrawn`, `stale` |
| Results | Recommendation band, confidence, evidence matrix, strengths, gaps, follow-ups |
| Safety | Bias audit, validation results, policy version |
| Reproducibility | Model, prompt, evidence-builder and schema versions |
| Operations | Attempts, safe error code, timestamps |

Use recommendation bands `strong_evidence`, `potential_fit`,
`limited_evidence`, and `constraint_mismatch`. Do not store an automatic
rejection field.

## Candidate Fact Domains

- Career history and responsibilities
- Candidate-stated achievements
- Skills with depth and recency
- Candidate-declared languages and proficiency
- Target roles, seniority, and industries
- City, state, remote, relocation, and all-India scope
- CTC range and notice period
- Work preferences and explicit exclusions

Protected traits, inferred health data, family status, religion, caste, gender,
age, accent, emotion, and personality inference are prohibited fact domains.

## Version and Staleness Rules

- Confirming proposals creates a new candidate profile version.
- Editing a role brief creates or references a new role version.
- A screening is current only when its candidate, resume, role, prompt, and
  policy versions match the application record.
- Later profile edits mark the screening stale but do not silently replace the
  historical assessment. Regeneration creates a new screening version.
- Recruiter UI always displays the assessment timestamp and stale state.

## RLS and Retention

- Candidates can read their sessions, proposals, profile versions, consents,
  and their own screening summary.
- Recruiters can read only published, consent-active screenings for their roles.
- Service-role workers perform extraction and screening writes.
- Admin access is audited and follows existing admin policies.
- Account deletion follows the existing soft-delete and purge process, including
  transcript, proposals, versions, and screenings.
- Withdrawing screening consent immediately hides recruiter access; the minimal
  consent audit remains according to the legal retention policy.

