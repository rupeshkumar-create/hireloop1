"""
Aarya — candidate-facing AI agent.

Architecture (R6 — single-threaded master loop):
  while True:
    thought = llm.think(state)           # Claude-3-5-sonnet via OpenRouter
    action  = llm.choose_tool(thought)   # structured tool call
    result  = execute_tool(action)       # deterministic Python (tools.py)
    state   = update_state(result)       # LangGraph checkpoint (Postgres)
    write_agent_action(action, result)   # → agent_actions (for UI counter)
    if done(state): break

State is persisted in Postgres via LangGraph's Postgres checkpointer.
Each candidate-session gets a unique thread_id (= conversation.id).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Annotated, Any, Literal, TypedDict

import asyncpg
import structlog
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from hireloop_api.agents.aarya import tools as aarya_tools
from hireloop_api.config import Settings
from hireloop_api.services.tool_cache import (
    cache_key,
    clear_session_tool_cache,
    get_cached,
    set_cached,
)

logger = structlog.get_logger()

# ── System prompt ─────────────────────────────────────────────────────────────

AARYA_SYSTEM_PROMPT = """You are Aarya, Hireloop's AI career partner for job seekers \
in India, the US, and the UK.

Your personality:
- Warm, direct, and human - like a senior friend who happens to be a great recruiter
- Talk like a real person, not a brochure. Use contractions (I'll, you're, let's, that's)
  and natural phrasing. Vary your sentence length. Sound relaxed, never scripted.
- Greet people simply and warmly by their first name - "Hi Mayank, good to meet you."
  Never narrate emoji or symbols out loud and don't over-punctuate.
- You speak in clear English; mix in light Hinglish naturally only if the user does
  (mainly IN market)
- You never give generic advice - always specific to this candidate and this role
- You are upbeat but realistic about match quality
- Ask one question at a time and actually listen before moving on

Your capabilities:
1. Read the candidate's profile (profile_read)
2. Build a career path from their profile (build_career_path) — current role,
   next steps, and concrete target job titles
3. Search for matching jobs (job_search) — scoped to the candidate's home market (IN / US / GB)
4. Get match score for a specific job (get_match_score)
5. Request a warm intro to the hiring manager (request_intro)
6. Record a direct application (direct_apply)
7. Save a job to the candidate's Saved list (save_job)
8. Prepare application kit (prepare_application_kit) — save job(s) AND generate
   tailored resume, cover letter, interview prep, and mock-interview link per role
9. Update job search preferences (update_job_preferences) — remote vs on-site filter,
   and location_scope (city / state / country / global within their market)
10. Save profile details they share (update_profile) — title, company, experience,
    skills, CTC, notice period, location, target roles

Finding jobs — the right order:
- When the user wants to find jobs or plan their next move, FIRST call
  build_career_path. Briefly share the path (where they are → where they can go).
- If they have not picked a primary target role yet, offer the top 3 options ONCE.
  When they reply with 1/2/3, a role title, or "option 2", call
  prioritize_career_path immediately — never ask the same question twice.
- If turn context shows career_path_locked, job_search is allowed — do NOT re-ask.
- THEN call job_search once per promising target_title from the path to surface
  real openings. Lead with the best-fit roles.

Important rules:
- NEVER send an intro email without candidate's explicit approval
- Always show the match score and explain why before recommending "Request Intro"
- Start from LinkedIn, uploaded CV, and voice-session data already in the profile.
  Do not re-ask for current title, company, years of experience, or skills when
  profile_read already has them. Ask only for genuinely missing details, one at a
  time.
- Missing CTC or location preferences should not block job discovery. If needed,
  show reasonable matches first and ask salary/location as follow-up filters.
- Job location type: profile_read shows remote_preference (any | remote_only |
  onsite_only). When the user asks for only remote roles, only on-site/non-remote
  roles, or to stop seeing remote jobs: call update_job_preferences with the right
  value, then job_search so results match. onsite_only means exclude fully remote
  listings; remote_only means remote/WFH roles only.
- Location scope: when the user says where they'll work, call update_job_preferences
  with location_scope = city | state | country | global (e.g. "only Bengaluru" → city,
  "anywhere in my country" → country, "open globally" → global), then job_search. This
  actually re-ranks the feed by geography — confirm it's saved, don't just acknowledge.
- All jobs must match the candidate's home market (IN / US / GB) — never suggest roles
  outside their market unless the role is remote and worldwide-eligible
- Salary framing by market: IN → LPA (lakhs per annum) / INR; US → USD per year; GB → GBP
  per year. Use annual figures, not monthly, unless the user asks otherwise
- Be honest about weak matches — don't oversell. But don't contradict the UI: the
  "matches ready" count is the TOTAL roles scored for the candidate. If few are
  strong fits, say that plainly ("200+ roles scored, but only a handful are strong
  fits for your niche") — never imply the feed is empty when it shows matches.

Reply structure (text chat):
- Use this flow: **What I found** → **What I recommend** → **What you can do next**.
- Keep mobile replies short (2-4 sentences) unless the user asks "why?" or "tell me more".
- Use market-local context from profile_read (market, city, currency). IN → notice period,
  LPA, Indian cities; US → USD, states; GB → GBP, UK cities. Never assume US framing for IN users.
- Ask ONE high-value profiling question at a time, tied to a benefit
  ("This unlocks better salary estimates"). Never re-ask facts already in resume,
  LinkedIn OAuth, or memory.

Profile improvement vs job search:
- When the user asks what to add to their profile, how to improve match quality,
  or what's missing: call profile_read and give 2-4 concrete fields to fill in
  (skills, CTC, notice period, location) and why each helps. Do NOT call
  job_search or build_career_path in that turn unless they explicitly ask to see jobs.
- After profile_read returns, you MUST reply with the full gap analysis in the
  next turn. Never stop at "let me pull your profile" — that is not an answer.
- Whenever the candidate tells you a concrete profile fact (CTC, notice period,
  skills, current role/company, experience, city, target roles) — especially when
  you're collecting their details on a call — call update_profile to SAVE it. Don't
  just acknowledge it verbally; persist it so their profile % and matches improve.
- On voice calls this is mandatory: if they state a fact, call update_profile in
  the same turn before you reply — never rely on chat memory alone.
- Profile completeness is a single source of truth: the turn context provides
  `profile_completeness` — the exact % shown in the UI. If you reference how
  complete the profile is, use THAT number verbatim. Never invent or estimate a
  different figure (e.g. don't say "80% there" when the context says 35%).

Tool-call turns:
- When you call a tool, do NOT write user-facing text in that same turn — emit
  only the tool call. All user-facing advice belongs in the turn AFTER tool results.

When presenting jobs:
- The app renders each role as its own card — cards are the ONLY job UI in chat.
- Lead with 1-2 sentences summarising the best fits, then stop. Do NOT write a long
  numbered list of roles; the cards show title, company, match %, CTC, and location.
- If the user asks to filter ("only remote", "above 20 LPA"), acknowledge and call
  update_job_preferences or job_search as needed — the UI will filter cards in-thread.
- Tell the user they can Save, Request intro, or Apply from each card.

When the candidate wants to apply (or asks for apply assets):
- Call prepare_application_kit with job_id(s) from the conversation or their latest
  job_search results (max 3 roles per turn).
- This automatically saves each role and generates: tailored resume (download),
  cover letter, interview prep guide, and a mock-interview session link.
- After the tool returns, summarise what was prepared — the UI renders asset cards
  beneath your message. Do NOT paste the full cover letter in chat.

Memory (user-wide, stored in Supabase):
- You receive memory_summary + known_facts from every past chat with this user.
  Treat them as ground truth for preferences — do not re-ask what memory already
  states unless the user is changing their mind.

Start every new conversation by reading the candidate's profile first.
"""

# Appended only when the user is talking out loud (voice mode). The reply is
# read aloud by a text-to-speech voice, so it must sound like natural speech -
# never like a document being read.
AARYA_VOICE_PROMPT = """

YOU ARE A SENIOR RECRUITER ON A LIVE PHONE SCREEN right now. The candidate is
speaking to you out loud and your reply is read aloud by a voice.

The call is already in progress: it has connected, you've ALREADY greeted the
candidate by their first name, introduced yourself as a senior recruiter at
Hireloop, and asked your opening question about what they do now and what they
want next. So:
- Do NOT greet again, do NOT say "hi"/"hello" again, do NOT reintroduce yourself,
  and do NOT repeat that opening question. Just respond to what they actually said.
- Carry yourself like an experienced recruiter doing a screen: warm but sharp,
  genuinely curious, and steering the conversation. Acknowledge what they said in
  a few words, then ask the one most useful follow-up.

Voice delivery rules:
- Write exactly the way you'd SAY it on a phone call. Spoken sentences, not prose.
- NO emojis, NO emoticons like :) , NO markdown, NO asterisks, NO bullet points,
  NO numbered lists, NO headings, NO hashes. None of it - it gets read out as
  "smiley face" or "asterisk" and sounds broken.
- Keep it short: usually 1 to 3 sentences. This is a back-and-forth conversation,
  not a monologue. Say one thing, then let them respond.
- Use natural spoken connectors ("so", "okay", "got it", "alright", "honestly").
- When you list a job or a few options, say them in a flowing sentence -
  "I found two that look strong - a backend role at Razorpay around 30 to 40 lakhs,
  and one at Zerodha a bit lower." Don't read out symbols or numbers as digits-only;
  say "thirty to forty lakhs", not "30-40 LPA".
- Spell things out the way they sound. Sound like a friendly Indian career coach
  chatting on the phone, warm and easy.
- If the candidate mixes Hindi and English (Hinglish), mirror their tone lightly
  but keep your reply in clear English unless they speak mostly Hindi.
- After job_search on a voice call: give a brief spoken summary of the top 1-2
  roles only, then say the full list is in their chat — do NOT read every job aloud.
- Voice tool budget: you get ONE tool round per turn. Batch related tools together
  (e.g. profile_read + build_career_path + job_search in one round). After tools
  return, reply in speech only — no second tool round.
"""


def _last_human_text(messages: list[BaseMessage]) -> str:
    """Return the latest candidate-authored text in the current turn context."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""


def _detect_likely_intent(text: str) -> str:
    """Small deterministic turn classifier used only as prompt guidance."""
    lowered = text.lower()

    profile_signals = (
        "what should i add",
        "improve my match",
        "match quality",
        "complete my profile",
        "profile completeness",
        "missing from my profile",
        "add to my profile",
        "improve my profile",
        "fill in my profile",
        "profile gap",
    )
    if any(signal in lowered for signal in profile_signals):
        return "profile_improvement"
    if any(token in lowered for token in ("resume", "cv", "linkedin", "profile")) and any(
        word in lowered
        for word in ("improve", "add", "update", "missing", "complete", "fill", "gap")
    ):
        return "profile_improvement"

    apply_signals = (
        "want to apply",
        "help me apply",
        "apply for",
        "apply to",
        "application kit",
        "cover letter",
        "interview prep",
        "prepare my application",
        "apply assets",
    )
    if any(signal in lowered for signal in apply_signals):
        return "job_application"
    if any(token in lowered for token in ("apply", "applying")) and any(
        w in lowered for w in ("job", "role", "position", "these", "this")
    ):
        return "job_application"

    if any(token in lowered for token in ("intro", "hiring manager", "refer", "connect")):
        return "intro_request"
    if any(token in lowered for token in ("salary", "ctc", "lpa", "notice")):
        return "preference_update"

    job_signals = (
        "find job",
        "find role",
        "find me",
        "show me my",
        "job match",
        "best match",
        "show only remote",
        "show only on-site",
        "only looking for roles",
        "opening",
    )
    if any(signal in lowered for signal in job_signals):
        return "job_search"
    if any(token in lowered for token in ("job", "jobs", "role", "roles", "opening", "openings")):
        return "job_search"
    if "match" in lowered and "quality" not in lowered and "improve" not in lowered:
        return "job_search"
    if any(token in lowered for token in ("remote", "onsite", "on-site")):
        return "job_search"

    if any(token in lowered for token in ("resume", "cv", "linkedin", "profile")):
        return "profile_improvement"

    chit_signals = (
        "hello",
        "hi ",
        "hey",
        "thanks",
        "thank you",
        "what can you do",
        "who are you",
        "namaste",
        "good morning",
        "good evening",
        "how are you",
    )
    if len(lowered) < 120 and any(signal in lowered for signal in chit_signals):
        return "chit_chat"

    return "general_career_chat"


# Conversational / low-complexity intents that don't need the heavy model.
_FAST_MODEL_INTENTS = frozenset({"general_career_chat", "preference_update", "chit_chat"})
# Greetings and meta questions — answer directly without tool calls.
_NO_TOOL_INTENTS = frozenset({"chit_chat"})
_JOB_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _detect_hinglish(text: str) -> bool:
    """True when the utterance likely mixes Hindi and English."""
    if not text.strip():
        return False
    # Devanagari script
    if re.search(r"[\u0900-\u097F]", text):
        return True
    lowered = text.lower()
    hinglish_markers = (
        "kya",
        "hai",
        "nahi",
        "acha",
        "theek",
        "bhai",
        "yaar",
        "matlab",
        "bas",
        "abhi",
        "chahiye",
        "salary kitni",
        "job chahiye",
        "kaam",
        "batao",
        "samjha",
    )
    latin_words = re.findall(r"[a-z']+", lowered)
    if not latin_words:
        return False
    hits = sum(1 for w in latin_words if w in hinglish_markers)
    return hits >= 2 or (hits >= 1 and len(latin_words) <= 6)


def _prefer_fast_model(
    *,
    voice_mode: bool,
    last_human_text: str,
    has_tool_results: bool,
) -> bool:
    """
    Choose the fast/cheaper model for low-complexity turns to cut latency.

    Voice: primary for tool selection; fast model only for post-tool synthesis.
    Text: primary for complex reasoning; fast for simple turns and some synthesis.
    """
    if voice_mode:
        return has_tool_results
    intent = _detect_likely_intent(last_human_text)
    if has_tool_results:
        # Post-tool synthesis: profile/job/intro need careful reasoning; application
        # kits already have full JSON from prepare_application_kit — brief walkthrough only.
        if intent in {"profile_improvement", "job_search", "intro_request"}:
            return False
        return True
    if intent in _FAST_MODEL_INTENTS:
        return True
    # Explicit kit request with job id — tool choice is deterministic.
    if intent == "job_application" and _JOB_UUID_RE.search(last_human_text):
        return True
    return False


def build_turn_context_prompt(
    *,
    messages: list[BaseMessage],
    voice_mode: bool,
    memory: str,
    open_questions: list[str],
    profile_completeness: int | None = None,
    known_facts: str = "",
    candidate_display_name: str | None = None,
    career_path_prioritized_title: str | None = None,
    career_path_just_prioritized: str | None = None,
    career_path_pending_options: list[str] | None = None,
) -> str:
    """Build compact, deterministic guidance for the next Aarya turn."""
    last_text = _last_human_text(messages).strip()
    likely_intent = _detect_likely_intent(last_text)
    guidance: list[str] = [
        "Current turn context:",
        f"- mode: {'voice' if voice_mode else 'text'}",
        f"- likely_intent: {likely_intent}",
    ]
    name = (candidate_display_name or "").strip()
    if name:
        guidance.append(
            f"- candidate_name: {name} (authoritative — from their profile/résumé; "
            "always greet and address them by this name unless they correct you)"
        )

    just_locked = (career_path_just_prioritized or "").strip()
    locked = (career_path_prioritized_title or "").strip()
    if just_locked:
        guidance.append(
            f"- career_path_locked: {just_locked} (user JUST chose this — call "
            "job_search now; do NOT ask them to pick again)"
        )
    elif locked:
        guidance.append(
            f"- career_path_locked: {locked} (already saved — proceed with job_search; "
            "never re-ask which path to focus on)"
        )
    else:
        pending = [o.strip() for o in (career_path_pending_options or []) if o and o.strip()]
        if pending:
            numbered = "; ".join(f"{i + 1}. {t}" for i, t in enumerate(pending[:3]))
            guidance.append(
                "- career_path_pending: user must pick ONE primary target before job_search. "
                f"Options: {numbered}. If they reply 1/2/3 or a title, call "
                "prioritize_career_path then job_search — ask at most once."
            )
    if last_text:
        guidance.append(f"- candidate_signal: {last_text[:240]}")

    # Ground any completeness claim in the SAME number the UI pill shows, so the
    # chat text ("80% there") can never contradict the "35% complete" badge.
    if profile_completeness is not None:
        guidance.append(
            f"- profile_completeness: {profile_completeness}% (authoritative — this is the "
            "exact figure shown in the UI. If you mention how complete the profile is, "
            "use THIS number verbatim; never state a different or estimated percentage)."
        )

    if likely_intent == "job_search":
        completeness = profile_completeness or 0
        if completeness >= 80:
            guidance.append(
                "- action_policy: profile is strong (≥80%) — skip build_career_path; "
                "call job_search directly (use prefetched matches when provided)."
            )
        else:
            guidance.append(
                "- action_policy: build_career_path before job_search; search roles in the "
                "candidate's home market only."
            )
    elif likely_intent == "intro_request":
        guidance.append(
            "- action_policy: require explicit candidate approval before request_intro."
        )
    elif likely_intent == "profile_improvement":
        guidance.append(
            "- action_policy: call profile_read without narrating first; then reply with "
            "**What I found** → **What I recommend** (2-4 specific gaps + why) → "
            "**What you can do next**. Do NOT call job_search or build_career_path "
            "unless the user explicitly asks to see jobs or openings."
        )
    elif likely_intent == "preference_update":
        guidance.append(
            "- action_policy: update saved preferences when the candidate states a clear filter."
        )
    elif likely_intent == "job_application":
        guidance.append(
            "- action_policy: call prepare_application_kit for each role they want to apply to "
            "(max 3 job_ids). Do not only save_job — the kit includes resume, cover letter, "
            "and interview prep."
        )
    else:
        guidance.append("- action_policy: answer directly, then ask at most one useful follow-up.")

    if voice_mode:
        guidance.append(
            "- delivery: Keep the next reply short and spoken; no markdown, "
            "emoji, bullets, or headings."
        )
        if likely_intent not in ("job_search", "job_application", "intro_request"):
            guidance.append(
                "- action_policy: voice turn — respond directly. Do NOT call "
                "job_search or build_career_path unless the candidate explicitly "
                "asks to see jobs, roles, openings, or matches."
            )
        guidance.append(
            "- voice_tool_budget: ONE tool round only — batch tools when needed; "
            "let the candidate ask before searching roles."
        )
        if _detect_hinglish(last_text):
            guidance.append(
                "- hinglish_detected: candidate used Hindi/English mix — keep reply "
                "clear; they can switch to text in the app if voice is unclear."
            )
    else:
        guidance.append(
            "- delivery: Keep the next reply compact and mobile-friendly with "
            "one clear next action."
        )

    facts = (known_facts or "").strip()
    if facts:
        guidance.append(
            "- known_facts (already on file from past chats — rely on these and do NOT "
            "re-ask them): " + facts[:600]
        )

    trimmed_memory = memory.strip()
    if trimmed_memory:
        guidance.append(f"- memory_hint: {trimmed_memory[:500]}")

    clean_questions = [q.strip() for q in open_questions if q.strip()]
    if clean_questions:
        guidance.append("- best_profile_gap_to_ask_if_natural: " + clean_questions[0])

    return "\n".join(guidance)


# ── State ─────────────────────────────────────────────────────────────────────


class AaryaState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str  # = conversation.id
    action_count: int
    tool_rounds: int  # voice tool-budget counter (max 1 chain per turn)
    ui_job_cards: list[dict[str, Any]]  # emitted to chat UI via SSE after job_search
    voice_mode: bool  # True when the turn came from the voice call (TTS reply)
    hinglish_detected: bool
    memory: str  # rolling cross-conversation memory of this candidate
    known_facts: str  # compact line of captured career_facts (don't re-ask)
    open_questions: list[str]  # profile gaps to weave into the conversation
    profile_completeness: int | None  # authoritative % shown in the UI pill
    prefetched_jobs: list[dict[str, Any]]  # warmup shortlist injected at turn start
    candidate_display_name: str | None  # résumé/profile name — overrides stale memory
    career_path_prioritized_title: str | None
    career_path_just_prioritized: str | None
    career_path_pending_options: list[str]


# ── Tool definitions (for OpenAI function calling format) ──────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "profile_read",
            "description": "Read the candidate's full profile from the database.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "job_search",
            "description": (
                "Search for matching jobs in the candidate's home market (IN / US / GB) "
                "using semantic search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {
                        "type": "string",
                        "description": "Role title or description to search for",
                    },
                    "skills_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific skills to filter by",
                    },
                    "location_city": {
                        "type": "string",
                        "description": "City to filter by (within the candidate's market)",
                    },
                    "ctc_min": {
                        "type": "integer",
                        "description": (
                            "Minimum expected annual salary in the market currency "
                            "(INR paise for IN; USD/GBP for US/GB)"
                        ),
                    },
                    "remote_preference": {
                        "type": "string",
                        "enum": ["any", "remote_only", "onsite_only"],
                        "description": (
                            "Optional one-off filter for this search. Omit to use "
                            "the saved profile preference."
                        ),
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_job_preferences",
            "description": (
                "Update the candidate's saved job-search preferences, then run job_search. "
                "Set remote_preference when they ask for only remote, only on-site, or both. "
                "Set open_to_relocation=true when they say they're open to relocating / want "
                "to apply anywhere in their country "
                "(so out-of-city roles stop being penalized), or "
                "false when they only want their current city. Provide at least one field."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "remote_preference": {
                        "type": "string",
                        "enum": ["any", "remote_only", "onsite_only"],
                        "description": (
                            "any = remote and on-site; remote_only = WFH/remote only; "
                            "onsite_only = exclude fully remote roles"
                        ),
                    },
                    "location_scope": {
                        "type": "string",
                        "enum": ["city", "state", "country", "global"],
                        "description": (
                            "How wide to search: city = current city only; state = across "
                            "their state/region; country = anywhere in their home country; "
                            "global = anywhere. "
                            "Set this when they say where they'll work."
                        ),
                    },
                    "open_to_relocation": {
                        "type": "boolean",
                        "description": (
                            "Legacy: true ≈ location_scope 'country'. Prefer location_scope."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": (
                "Save profile details the candidate tells you (current role, company, "
                "experience, skills, CTC, notice period, location, target roles). Use this "
                "whenever they share a fact that fills a profile gap — especially on a call "
                "where you're gathering their details. Pass only the fields you just learned. "
                "Compensation fields: for IN market use LPA; for US/GB use annual amount in "
                "local currency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "current_title": {"type": "string", "description": "Current job title"},
                    "current_company": {"type": "string", "description": "Current employer"},
                    "years_experience": {
                        "type": "integer",
                        "description": "Total years of experience",
                    },
                    "skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key skills (replaces the stored skills list)",
                    },
                    "expected_ctc_min_lpa": {
                        "type": "number",
                        "description": "Minimum expected CTC in LPA",
                    },
                    "expected_ctc_max_lpa": {
                        "type": "number",
                        "description": "Maximum expected CTC in LPA",
                    },
                    "current_ctc_lpa": {"type": "number", "description": "Current CTC in LPA"},
                    "notice_period_days": {
                        "type": "integer",
                        "description": "Notice period in days (0 = immediate)",
                    },
                    "location_city": {"type": "string", "description": "Current city"},
                    "location_state": {"type": "string", "description": "Current state/region"},
                    "looking_for": {
                        "type": "string",
                        "description": "Target roles / what they want next",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prioritize_career_path",
            "description": (
                "Lock in the candidate's chosen primary target role from their career "
                "path (required before job_search). Use when they pick 1/2/3 or name "
                "a path title. Pass the number or full title."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Chosen path title, or 1/2/3 for the offered list",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_career_path",
            "description": (
                "Generate the candidate's career path: their current role, a few "
                "next steps, and concrete target job titles to search for. Call this "
                "when the user wants to find jobs or plan their next move. Then use "
                "the returned target_titles to drive job_search."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_match_score",
            "description": "Get the precomputed match score for a candidate-job pair.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_intro",
            "description": (
                "Request a warm intro to the hiring manager. Only call after "
                "explicit user approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "hiring_manager_id": {"type": "string"},
                },
                "required": ["job_id", "hiring_manager_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "direct_apply",
            "description": "Record a direct application via the job's native apply link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "apply_url": {"type": "string"},
                },
                "required": ["job_id", "apply_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_job",
            "description": "Save a job to the candidate's Saved jobs list for later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID of the job"},
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_application_kit",
            "description": (
                "When the candidate wants to apply: save the job(s) and generate tailored "
                "resume, cover letter, interview prep, and a mock-interview link per role."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One or more job UUIDs (max 3)",
                    },
                    "job_id": {
                        "type": "string",
                        "description": "Single job UUID when only one role",
                    },
                },
            },
        },
    },
]


# ── Agent builder ─────────────────────────────────────────────────────────────


def build_aarya_graph(settings: Settings) -> Any:
    """
    Build and compile the Aarya LangGraph state machine.
    Returns a compiled graph ready to .ainvoke() or .astream().
    """

    # OpenRouter as the LLM provider (R3)
    # extra_headers: identifies this app to OpenRouter (required for rate limits
    # and analytics — see openrouter.ai/docs#headers)
    def _make_llm(model: str) -> Any:
        return ChatOpenAI(
            model=model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            max_tokens=2048,
            default_headers={
                "HTTP-Referer": "https://app.hireloop.in",
                "X-Title": "Hireloop - Aarya Career AI",
            },
        ).bind_tools(TOOL_DEFINITIONS)  # type: ignore[arg-type]

    def _make_llm_plain(model: str) -> Any:
        return ChatOpenAI(
            model=model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.3,
            max_tokens=2048,
            default_headers={
                "HTTP-Referer": "https://app.hireloop.in",
                "X-Title": "Hireloop - Aarya Career AI",
            },
        )

    # Two tiers: the heavy primary for tool selection / reasoning, and a fast,
    # cheap model for short conversational turns and tool-result summarisation.
    # Routing per turn (see _prefer_fast_model) is the main latency lever.
    llm_primary = _make_llm(settings.openrouter_primary_model)
    llm_fast = _make_llm(settings.openrouter_fallback_model or settings.openrouter_primary_model)
    llm_primary_plain = _make_llm_plain(settings.openrouter_primary_model)
    llm_fast_plain = _make_llm_plain(
        settings.openrouter_fallback_model or settings.openrouter_primary_model
    )

    async def agent_node(state: AaryaState, config: RunnableConfig) -> dict:
        """Main LLM reasoning step."""
        messages = state["messages"]

        # Inject system prompt if first message. In voice mode, append the
        # spoken-style rules so the reply sounds natural when read aloud.
        if not any(isinstance(m, SystemMessage) for m in messages):
            voice = bool(state.get("voice_mode"))
            prompt = AARYA_SYSTEM_PROMPT
            if voice:
                prompt += AARYA_VOICE_PROMPT
            # Carry what Aarya already knows about this candidate across
            # conversations, so a brand-new chat isn't starting from zero.
            # Voice turns are latency-critical: trim the memory block hard —
            # every extra prompt token delays the first spoken sentence.
            memory = (state.get("memory") or "").strip()
            if voice and len(memory) > 300:
                memory = memory[:300].rsplit(" ", 1)[0] + "…"
            if memory:
                prompt += (
                    "\n\nWhat you already know about this candidate from past "
                    "conversations (treat as background, confirm gently rather "
                    "than re-asking):\n" + memory
                )
            # Progressive profiling: there are still gaps in this person's career
            # profile. Weave at most one or two into the conversation when it
            # feels natural — never interrogate or dump a list of questions.
            # In voice mode pass at most ONE gap (shorter prompt, and a spoken
            # reply should never juggle multiple profiling questions anyway).
            open_questions = [q for q in (state.get("open_questions") or []) if q.strip()]
            if voice:
                open_questions = open_questions[:1]
            if open_questions:
                prompt += (
                    "\n\nYou're still missing a few details about this person that "
                    "would help you advise them better. When the moment fits "
                    "naturally — and only after helping with what they actually "
                    "asked — gently ask AT MOST ONE of these per reply (never more, "
                    "never as a list, and skip if it would feel like an "
                    "interrogation). Once they answer, it's saved automatically.\n"
                    + "\n".join(f"- {q}" for q in open_questions[:8])
                )
            prompt += "\n\n" + build_turn_context_prompt(
                messages=messages,
                voice_mode=bool(state.get("voice_mode")),
                memory=memory,
                open_questions=open_questions,
                profile_completeness=state.get("profile_completeness"),
                known_facts=(state.get("known_facts") or ""),
                candidate_display_name=state.get("candidate_display_name"),
                career_path_prioritized_title=state.get("career_path_prioritized_title"),
                career_path_just_prioritized=state.get("career_path_just_prioritized"),
                career_path_pending_options=state.get("career_path_pending_options"),
            )
            messages = [SystemMessage(content=prompt), *messages]

        prefetched = state.get("prefetched_jobs") or []
        if prefetched:
            titles = ", ".join(str(j.get("title") or "role")[:40] for j in prefetched[:3])
            messages = [
                *messages,
                SystemMessage(
                    content=(
                        f"Prefetch hint: top matches already loaded ({titles}). "
                        "Summarise these for the candidate — call job_search only if "
                        "they want different roles or filters."
                    )
                ),
            ]

        # Route to the fast model for low-complexity / voice / summarisation turns.
        has_tool_results = any(isinstance(m, ToolMessage) for m in state["messages"])
        last_human = _last_human_text(state["messages"])
        turn_intent = _detect_likely_intent(last_human)
        no_tools_turn = turn_intent in _NO_TOOL_INTENTS and not has_tool_results
        use_fast = _prefer_fast_model(
            voice_mode=bool(state.get("voice_mode")),
            last_human_text=last_human,
            has_tool_results=has_tool_results,
        )
        voice_budget_done = bool(state.get("voice_mode")) and state.get("tool_rounds", 0) >= 1
        if no_tools_turn:
            active = llm_fast_plain
        elif voice_budget_done:
            active = llm_fast_plain if use_fast else llm_primary_plain
        elif use_fast:
            active = llm_fast
        else:
            active = llm_primary
        # Resilience: if the fast model errors (e.g. a misconfigured / invalid
        # model ID), fall back to the primary so chat never hard-fails on a turn.
        if use_fast and not voice_budget_done and not no_tools_turn:
            try:
                response = await active.ainvoke(messages)
            except Exception as exc:
                logger.warning("aarya_fast_model_failed_fallback_to_primary", error=str(exc)[:200])
                response = await (llm_primary_plain if voice_budget_done else llm_primary).ainvoke(
                    messages
                )
        else:
            response = await active.ainvoke(messages)

        return {
            "messages": [response],
            "action_count": state["action_count"],
        }

    async def tools_node(state: AaryaState, config: RunnableConfig) -> dict:
        """Execute tool calls from the LLM response (parallel when independent)."""
        db: asyncpg.Connection = config["configurable"]["db"]
        last_message = state["messages"][-1]

        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {
                "messages": [],
                "action_count": state["action_count"],
                "tool_rounds": state.get("tool_rounds", 0),
            }

        action_count = state["action_count"]
        ui_job_cards: list[dict[str, Any]] = list(state.get("ui_job_cards") or [])

        async def _execute_one(tool_call: dict[str, Any]) -> tuple[ToolMessage, int, list[dict]]:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            user_id = state["user_id"]
            session_id = state["session_id"]
            local_actions = 0
            cards: list[dict] = []

            try:
                cacheable = tool_name in ("profile_read", "job_search")
                ck = cache_key(session_id, tool_name, tool_args if cacheable else None)
                if cacheable:
                    cached = get_cached(ck)
                    if cached is not None:
                        result = cached
                        if tool_name == "job_search" and isinstance(result, dict):
                            cards = list(result.get("job_cards") or [])
                        local_actions = 0
                        return (
                            ToolMessage(
                                content=json.dumps(result, default=str),
                                tool_call_id=tool_call["id"],
                            ),
                            local_actions,
                            cards,
                        )

                if tool_name == "profile_read":
                    result = await aarya_tools.profile_read(db, user_id, session_id)
                elif tool_name == "job_search":
                    result = await aarya_tools.job_search(
                        db, user_id, session_id, settings=settings, **tool_args
                    )
                    if isinstance(result, dict) and isinstance(result.get("job_cards"), list):
                        cards = result["job_cards"]
                elif tool_name == "prioritize_career_path":
                    result = await aarya_tools.prioritize_career_path(
                        db, user_id, session_id, **tool_args
                    )
                    if isinstance(result, dict) and result.get("prioritized_title"):
                        clear_session_tool_cache(session_id, "job_search")
                elif tool_name == "build_career_path":
                    result = await aarya_tools.build_career_path(db, user_id, session_id, settings)
                elif tool_name == "get_match_score":
                    result = await aarya_tools.get_match_score(db, user_id, session_id, **tool_args)
                elif tool_name == "request_intro":
                    result = await aarya_tools.request_intro(db, user_id, session_id, **tool_args)
                elif tool_name == "direct_apply":
                    result = await aarya_tools.direct_apply(db, user_id, session_id, **tool_args)
                elif tool_name == "save_job":
                    result = await aarya_tools.save_job(db, user_id, session_id, **tool_args)
                elif tool_name == "prepare_application_kit":
                    result = await aarya_tools.prepare_application_kit(
                        db, user_id, session_id, settings, **tool_args
                    )
                elif tool_name == "update_job_preferences":
                    result = await aarya_tools.update_job_preferences(
                        db, user_id, session_id, **tool_args
                    )
                elif tool_name == "update_profile":
                    result = await aarya_tools.update_profile(db, user_id, session_id, **tool_args)
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

                local_actions = 1

            except Exception as exc:
                logger.error("tool_execution_error", tool=tool_name, error=str(exc))
                result = {"error": str(exc)}

            if tool_name in ("profile_read", "job_search") and "error" not in result:
                set_cached(cache_key(session_id, tool_name, tool_args), result)

            return (
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tool_call["id"],
                ),
                local_actions,
                cards,
            )

        outcomes = await asyncio.gather(*[_execute_one(tc) for tc in last_message.tool_calls])
        tool_messages: list[ToolMessage] = []
        for tm, inc, cards in outcomes:
            tool_messages.append(tm)
            action_count += inc
            if cards:
                ui_job_cards = cards

        return {
            "messages": tool_messages,
            "action_count": action_count,
            "tool_rounds": state.get("tool_rounds", 0) + 1,
            "ui_job_cards": ui_job_cards,
        }

    def should_continue(state: AaryaState) -> Literal["tools", "__end__"]:
        """Route: if last message has tool calls → tools, else → end."""
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            if state.get("voice_mode") and state.get("tool_rounds", 0) >= 1:
                return END
            return "tools"
        return END

    # Build graph
    graph = StateGraph(AaryaState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")

    return graph.compile()


# Singleton graph (initialised at app startup)
_aarya_graph = None


def get_aarya_graph(settings: Settings) -> Any:
    global _aarya_graph
    if _aarya_graph is None:
        _aarya_graph = build_aarya_graph(settings)
    return _aarya_graph
