"""Pure coverage policy for Aarya's career interview."""

from __future__ import annotations

import re

from hireloop_api.models.career_interview import (
    CareerInterviewCoverage,
    InterviewTopic,
    NextInterviewFocus,
)

INTERVIEW_TOPIC_PRIORITY: tuple[InterviewTopic, ...] = (
    InterviewTopic.CURRENT_WORK,
    InterviewTopic.IMPACT,
    InterviewTopic.SKILLS,
    InterviewTopic.TARGET_ROLES,
    InterviewTopic.LOCATION_SCOPE,
    InterviewTopic.WORK_MODE,
    InterviewTopic.NOTICE_PERIOD,
    InterviewTopic.COMPENSATION,
    InterviewTopic.RELOCATION,
    InterviewTopic.INDUSTRIES,
    InterviewTopic.LANGUAGES,
    InterviewTopic.DEAL_BREAKERS,
)

PROMPT_HINTS: dict[InterviewTopic, str] = {
    InterviewTopic.CURRENT_WORK: "Ask what the candidate does in their current or most recent work.",
    InterviewTopic.IMPACT: "Ask for a concrete outcome or impact they are proud of.",
    InterviewTopic.SKILLS: "Ask which skills they use most and want to keep building.",
    InterviewTopic.TARGET_ROLES: "Ask which roles and responsibilities they want next.",
    InterviewTopic.LOCATION_SCOPE: "Ask which Indian cities or location scope they would consider.",
    InterviewTopic.WORK_MODE: "Ask whether they prefer remote, hybrid, or on-site work.",
    InterviewTopic.NOTICE_PERIOD: "Ask about their notice period or earliest possible start date.",
    InterviewTopic.COMPENSATION: (
        "Make compensation optional, then ask their preferred INR/LPA range if they wish to share."
    ),
    InterviewTopic.RELOCATION: "Ask whether relocation within India is possible or off the table.",
    InterviewTopic.INDUSTRIES: "Ask which industries interest them and which they want to avoid.",
    InterviewTopic.LANGUAGES: (
        "Ask which languages you use and invite the candidate to declare their own proficiency."
    ),
    InterviewTopic.DEAL_BREAKERS: "Ask about any role, employer, or working-condition deal-breakers.",
}

_WRAP_HINT = "Recap what was learned, name any uncertainty, and close the interview warmly."
_PREFER_NOT_REFUSAL_PATTERN = re.compile(r"\b(?:rather|prefer) not\b")
_SKIP_REFUSAL_PATTERN = re.compile(r"\bskip this\b")
_WANT_TO_REFUSAL_PATTERN = re.compile(
    r"^\s*(?:i\s+)?(?:don't|do not) want to"
    r"(?:\s+(?:discuss|share|answer|talk(?: about)?|go into|say|tell)\b"
    r"(?:\s+[^,;.!?]+)?)?[.!?]*\s*$"
)
_NEGATED_SKIP_PATTERN = re.compile(r"\b(?:(?:don't|do not) want to|not) skip this\b")
_NON_ANSWER_PATTERN = re.compile(r"\b(?:don't know|do not know|not sure|no idea)\b")
_CONTINUATION_PATTERN = re.compile(
    r"(?:\b(?:but|however|although|though|yet)\b|[;.!?])(?P<detail>.*)$"
)
_SUBSTANTIVE_FACT_PATTERN = re.compile(r"\b\d|\b(?:lpa|ctc|days?)\b")
_CONTRAST_FILLER_WORDS = frozenset(
    {
        "am",
        "do",
        "don't",
        "honestly",
        "i",
        "idea",
        "just",
        "know",
        "maybe",
        "no",
        "not",
        "perhaps",
        "really",
        "still",
        "sure",
        "yet",
    }
)


def _is_explicit_refusal(answer: str) -> bool:
    refusal_candidate = _NEGATED_SKIP_PATTERN.sub("", answer)
    if _WANT_TO_REFUSAL_PATTERN.fullmatch(refusal_candidate) and not _has_meaningful_continuation(
        refusal_candidate
    ):
        return True
    if _PREFER_NOT_REFUSAL_PATTERN.search(refusal_candidate):
        return not _has_meaningful_continuation(refusal_candidate)
    return _SKIP_REFUSAL_PATTERN.search(refusal_candidate) is not None


def _has_meaningful_continuation(answer: str) -> bool:
    for match in _CONTINUATION_PATTERN.finditer(answer):
        detail = match.group("detail")
        if _SUBSTANTIVE_FACT_PATTERN.search(detail):
            return True
        if _NON_ANSWER_PATTERN.search(detail):
            continue
        detail_words = re.findall(r"[a-z']+", detail)
        if any(word not in _CONTRAST_FILLER_WORDS for word in detail_words):
            return True
    return False


def _is_standalone_non_answer(answer: str) -> bool:
    if not _NON_ANSWER_PATTERN.search(answer):
        return False
    if _SUBSTANTIVE_FACT_PATTERN.search(answer) or _has_meaningful_continuation(answer):
        return False
    return True


def select_next_focus(
    state: CareerInterviewCoverage,
    *,
    elapsed_seconds: int | float,
) -> NextInterviewFocus:
    """Choose the next uncovered, non-declined topic or wrap the interview."""
    if elapsed_seconds >= 14 * 60:
        return NextInterviewFocus(topic=None, prompt_hint=_WRAP_HINT, should_wrap=True)

    unavailable = set(state.covered_topics) | set(state.declined_topics)
    for topic in INTERVIEW_TOPIC_PRIORITY:
        if topic not in unavailable:
            return NextInterviewFocus(topic=topic, prompt_hint=PROMPT_HINTS[topic])

    return NextInterviewFocus(topic=None, prompt_hint=_WRAP_HINT, should_wrap=True)


def record_candidate_answer(
    state: CareerInterviewCoverage,
    answer: str,
) -> CareerInterviewCoverage:
    """Return new coverage state after evaluating an answer to the current focus."""
    updated = state.model_copy(deep=True)
    updated.turn_count += 1

    topic = updated.current_focus
    if topic is None:
        return updated

    normalized_answer = answer.casefold()
    if _is_explicit_refusal(normalized_answer):
        if topic not in updated.declined_topics:
            updated.declined_topics.append(topic)
        return updated

    is_non_answer = _is_standalone_non_answer(normalized_answer)
    if not is_non_answer and len(answer.split()) >= 3 and topic not in updated.covered_topics:
        updated.covered_topics.append(topic)

    return updated
