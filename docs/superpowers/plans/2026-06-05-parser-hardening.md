# Parser Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make resume and LinkedIn profile extraction more accurate, resilient, and explainable for candidate profile creation and matching.

**Architecture:** Add deterministic normalization helpers inside the existing parser modules rather than introducing a new dependency. Resume parsing stays Affinda → LLM → regex, then applies canonicalization/quality metadata. LinkedIn enrichment keeps the CrawlerBros no-cookie Apify actor and maps variant actor shapes into candidate fields plus source metadata.

**Tech Stack:** FastAPI, Python 3.12, Pydantic v2, asyncpg, httpx, pytest, Ruff.

---

### Task 1: Resume Normalization Red Tests

**Files:**
- Modify: `api/tests/test_resume_parser_fallback.py`
- Modify: `api/src/hireloop_api/services/resume_parser.py`

- [ ] **Step 1: Add messy resume test**

Add a test with multi-line current role, fuzzy dates, alias-heavy skills, +91 phone normalization, GitHub/LinkedIn URLs with trailing punctuation, and parser metadata assertions.

- [ ] **Step 2: Verify red**

Run: `cd api && ./.venv/bin/pytest tests/test_resume_parser_fallback.py -q`

Expected: fail on missing stronger canonicalization/metadata.

- [ ] **Step 3: Implement resume normalizer**

Add helper functions to canonicalize skill aliases, reject junk skills, sanitize URLs, normalize Indian phones, improve current-role/date parsing, estimate experience from fuzzy date ranges, and attach `parser_metadata`.

- [ ] **Step 4: Verify green**

Run: `cd api && ./.venv/bin/pytest tests/test_resume_parser_fallback.py -q`

Expected: pass.

### Task 2: LinkedIn Mapping Red Tests

**Files:**
- Modify: `api/tests/test_linkedin_profile_enrichment.py`
- Modify: `api/src/hireloop_api/services/apify/linkedin_profile_scraper.py`

- [ ] **Step 1: Add actor variant test**

Add a test covering `currentCompany`, nested `location`, skill objects, profile image aliases, and historical/current positions.

- [ ] **Step 2: Verify red**

Run: `cd api && ./.venv/bin/pytest tests/test_linkedin_profile_enrichment.py -q`

Expected: fail on unsupported actor variants/metadata.

- [ ] **Step 3: Implement LinkedIn normalizer**

Map variant fields, parse location strings/objects, normalize skill objects/aliases, keep no-cookie actor input, and add `linkedin_parser_metadata` to `linkedin_data`.

- [ ] **Step 4: Verify green**

Run: `cd api && ./.venv/bin/pytest tests/test_linkedin_profile_enrichment.py -q`

Expected: pass.

### Task 3: Integration Validation

**Files:**
- Test: `api/tests/test_resume_parser_fallback.py`
- Test: `api/tests/test_linkedin_profile_enrichment.py`

- [ ] **Step 1: Run focused parser tests**

Run: `cd api && ./.venv/bin/pytest tests/test_resume_parser_fallback.py tests/test_linkedin_profile_enrichment.py -q`

Expected: pass.

- [ ] **Step 2: Run full API validation**

Run: `cd api && ./.venv/bin/ruff check src/hireloop_api/services/resume_parser.py src/hireloop_api/services/apify/linkedin_profile_scraper.py tests/test_resume_parser_fallback.py tests/test_linkedin_profile_enrichment.py && ./.venv/bin/pytest tests -q`

Expected: Ruff passes and all API tests pass.
