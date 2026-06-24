"""
LLM match rationale — Aarya's personalized "why you fit" line per job (P10).

This is the cross-encoder-style rerank/explanation layer: instead of cosine over
two separately-embedded vectors, an LLM reads the candidate AND each job together
and writes one specific, evidence-based sentence ("Strong on React + your 4 yrs;
same city; one gap: they want GraphQL"). That specificity is what makes the feed
feel intelligent on first view.

Design:
  * The LLM caller is injectable (`llm=`), so tests run with a fake — no key,
    no network.
  * Everything is best-effort: any failure (no key, timeout, bad JSON, an id the
    model hallucinated) degrades gracefully to an empty result, and the caller
    keeps the existing rule-based explanation. It must never break the feed.
  * Bounded to the top `max_jobs` (the opening screen) for cost/latency control.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable

import structlog

from hireloop_api.config import Settings

logger = structlog.get_logger()

# (system_prompt, user_prompt) -> raw model text
LLMComplete = Callable[[str, str], Awaitable[str]]

_MAX_REASON_CHARS = 200

_SYSTEM_PROMPT = (
    "You are Aarya, an India-focused career copilot. For each job, write ONE "
    "concise sentence (max ~24 words) explaining why THIS candidate fits, citing "
    "concrete overlaps — skills, years of experience, location, seniority. Be "
    "honest: if there is a notable gap you may briefly note it. No greeting, no "
    "fluff, no markdown. Respond with STRICT JSON only, of the form: "
    '{"matches": [{"job_id": "<id>", "reason": "<one sentence>"}]}'
)


def _candidate_brief(candidate: dict) -> str:
    parts: list[str] = []
    if candidate.get("current_title"):
        parts.append(f"Current role: {candidate['current_title']}")
    yrs = candidate.get("years_experience")
    if yrs is not None:
        parts.append(f"Experience: {yrs} years")
    skills = candidate.get("skills") or []
    if skills:
        parts.append("Skills: " + ", ".join(str(s) for s in skills[:15]))
    loc = " ".join(
        str(p) for p in (candidate.get("location_city"), candidate.get("location_state")) if p
    )
    if loc:
        parts.append(f"Location: {loc}")
    if candidate.get("expected_ctc_min"):
        parts.append(f"Expected CTC (min, INR p.a.): {candidate['expected_ctc_min']}")
    return "\n".join(parts) or "No structured profile data available."


def _jobs_block(jobs: list[dict]) -> str:
    lines: list[str] = []
    for job in jobs:
        skills = job.get("skills_required") or []
        loc = job.get("location_city") or ("Remote" if job.get("is_remote") else "—")
        lines.append(
            f"- job_id={job.get('job_id')} | {job.get('title')} @ "
            f"{job.get('company_name') or 'a company'} | seniority="
            f"{job.get('seniority') or '—'} | location={loc} | "
            f"skills={', '.join(str(s) for s in skills[:12])}"
        )
    return "\n".join(lines)


def _parse_matches(content: str) -> dict[str, str]:
    """Extract {job_id: reason} from the model's JSON (tolerant of code fences)."""
    if not content:
        return {}
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    obj: object = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, str] = {}
    for item in obj.get("matches") or []:
        if not isinstance(item, dict):
            continue
        jid = item.get("job_id")
        reason = item.get("reason")
        if isinstance(jid, str) and isinstance(reason, str) and reason.strip():
            out[jid] = reason.strip()[:_MAX_REASON_CHARS]
    return out


def _build_openrouter_llm(settings: Settings) -> LLMComplete:
    """Default LLM caller backed by OpenRouter (mirrors career_intelligence)."""

    async def _complete(system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.2,
            max_tokens=900,
            timeout=12,
            default_headers={
                "HTTP-Referer": "https://app.hireloop.in",
                "X-Title": "Hireloop - Match Rationale",
            },
        )
        resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
        return resp.content if isinstance(resp.content, str) else str(resp.content)

    return _complete


async def generate_match_rationales(
    candidate: dict,
    jobs: list[dict],
    *,
    settings: Settings,
    llm: LLMComplete | None = None,
    max_jobs: int = 8,
) -> dict[str, str]:
    """
    Return {job_id: one-line rationale} for up to `max_jobs` jobs.

    Best-effort: returns {} (so the caller falls back to the rule-based
    explanation) when there's no LLM available or anything goes wrong.
    """
    short = [j for j in jobs[:max_jobs] if j.get("job_id")]
    if not short:
        return {}

    caller = llm
    if caller is None:
        if not settings.openrouter_api_key:
            return {}
        caller = _build_openrouter_llm(settings)

    user_prompt = (
        "CANDIDATE\n"
        f"{_candidate_brief(candidate)}\n\n"
        "JOBS (write a reason for each job_id)\n"
        f"{_jobs_block(short)}"
    )

    try:
        content = await caller(_SYSTEM_PROMPT, user_prompt)
    except Exception as exc:  # network/timeout/provider errors must not break the feed
        logger.warning("match_rationale_llm_failed", error=str(exc)[:300])
        return {}

    parsed = _parse_matches(content)
    valid_ids = {str(j["job_id"]) for j in short}
    # Guard against hallucinated ids: only keep reasons for jobs we actually sent.
    return {jid: reason for jid, reason in parsed.items() if jid in valid_ids}
