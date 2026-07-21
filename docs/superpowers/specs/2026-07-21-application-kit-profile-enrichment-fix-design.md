# Application Kit Profile-Enrichment Fix

## Problem

Production Application Kit jobs fail for candidates whose `profile_enrichment`
JSONB column is populated. The durable queue exhausts all three attempts with:

```text
AttributeError: 'str' object has no attribute 'get'
```

The Application Kit service reads `profile_enrichment` through `asyncpg`, which
returns JSONB as a JSON string with the current pool configuration. It places
that string into the candidate profile. Interview-prep generation later treats
the value as a dictionary and calls `.get("star_stories")`.

## Scope

Fix only Application Kit profile-enrichment handling. Do not change the global
database pool codec, database schema, queue architecture, or unrelated JSONB
consumers.

## Design

At the Application Kit database boundary, normalize `profile_enrichment` into a
dictionary:

- Preserve dictionary values.
- Decode JSON strings whose top-level value is an object.
- Treat null, malformed JSON, JSON arrays, and other unexpected values as an
  empty dictionary.

Store only the normalized dictionary in the profile passed to downstream kit
generators.

As defense in depth, interview-prep generation must treat a non-dictionary
`profile_enrichment` value as empty enrichment. This prevents a malformed or
legacy caller from crashing the entire durable job after the expensive LLM and
resume work has already run.

## Error Handling

Malformed optional enrichment is ignored; core profile, cover-letter, resume,
and interview-prep generation continue. No candidate data is rewritten and no
new production logging includes profile content or PII.

## Tests

Regression tests will first reproduce the current crash with JSON-string
enrichment. Coverage will verify:

1. A valid JSON-object string exposes `star_stories` to interview prep.
2. An existing dictionary remains unchanged.
3. Malformed JSON is treated as empty enrichment.
4. JSON arrays and other non-object values are treated as empty enrichment.
5. Interview-prep generation does not crash when directly passed malformed
   enrichment.

Focused Application Kit tests, the broader API test suite relevant to the
changed services, and Ruff checks will verify the implementation.

## Deployment and Recovery

No migration is required. After the API fix is deployed, affected users can
retry from the job card. The queue permits a new job after the prior job reaches
`failed`, while its active-job idempotency protection continues to prevent
duplicate pending or running work.
