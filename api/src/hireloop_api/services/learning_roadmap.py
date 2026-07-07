"""
Personal AI learning roadmap generator.

Given a candidate profile + a specific job, an LLM produces a structured,
personalized upskilling plan (gaps → phased milestones → resources). We render
that JSON into a self-contained, interactive single-file HTML "app" the
candidate can open or download — milestones are checkable and progress is saved
in the browser (localStorage), so it's a living plan rather than a static doc.
"""

from __future__ import annotations

import html
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.services.ai_context import compose_candidate_prompt
from hireloop_api.services.skills import canonical_skill

logger = structlog.get_logger()

ROADMAP_SYSTEM = """You are a career coach who builds personalized upskilling \
plans. Given a candidate's profile and a specific job, design a realistic \
learning roadmap that closes the gap between them.

These three inputs are FIXED and already known — never ask the learner for them:
- Background & level: infer entirely from the candidate's resume/profile below. \
Set the starting point, sequence, and depth from what they already know — skip \
what they've clearly mastered, go deeper where they're weak.
- Time available: assume ~1 hour per day (~7 hours/week). Size every phase's \
duration and weekly workload to that budget — be realistic, not aspirational.
- Goal: become job-ready for the specific TARGET job provided. Every phase must \
move them toward that exact role's requirements; the final phase is a capstone \
that proves readiness for it.

Rules:
- Be specific to THIS candidate and THIS job — reference their actual skills/gaps.
- Never invent the candidate's experience.
- Prefer free or widely-available resources; name concrete topics, not vague advice.
- When you know a real, canonical documentation or course URL for a resource, \
include it in "url" (e.g. official docs, a well-known free course). If unsure, omit url.
- 3 to 5 phases, ordered from foundations to job-ready, paced for ~1 hour/day.
- Output ONLY valid JSON (no markdown fences) matching the requested schema.
"""

_SCHEMA_HINT = """Return JSON with exactly this shape:
{
  "summary": "2-3 sentence personalized overview of the plan",
  "target_role": "the job title",
  "current_strengths": ["strength the candidate already has", ...],
  "gaps": ["skill/area to develop for this role", ...],
  "phases": [
    {
      "title": "Phase 1: ...",
      "duration": "Weeks 1-2",
      "focus": "one-line focus for this phase",
      "milestones": ["concrete, checkable task", ...],
      "skills": ["skill covered", ...],
      "resources": [{"label": "resource or topic", "url": "https://real-link-if-known (else omit)", "note": "what/why"}]
    }
  ],
  "stretch_goals": ["optional advanced goal", ...]
}"""

_PLACEHOLDER_VALUES = {"", "null", "none", "undefined", "n/a", "na", "-", "—"}


async def generate_roadmap(
    *,
    llm: ChatOpenAI,
    candidate_profile: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    """LLM produces a structured learning roadmap as a dict."""
    task_prompt = f"""{_SCHEMA_HINT}

Fixed inputs (do not ask — calibrate to these):
- Background/level: infer from the candidate resume below.
- Time budget: ~1 hour/day (~7 hours/week).
- Goal: become job-ready for the TARGET job below.

TARGET job (this is the goal):
Title: {job.get("title")}
Company: {job.get("company_name", "Company")}
Required skills: {job.get("skills_required")}
Description: {(job.get("description") or "")[:4000]}

Produce the roadmap JSON now, paced for ~1 hour/day."""
    prompt = compose_candidate_prompt(
        candidate_profile,
        task="learning_roadmap",
        task_prompt=task_prompt,
    )

    resp = await llm.ainvoke(
        [
            SystemMessage(content=ROADMAP_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return normalize_learning_roadmap(
        _parse_roadmap_json(content),
        candidate_profile=candidate_profile,
        job=job,
    )


def _parse_roadmap_json(raw: str) -> dict[str, Any]:
    """Best-effort parse: strip fences, isolate the JSON object."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Roadmap JSON was not an object")
    return data


def normalize_learning_roadmap(
    roadmap: dict[str, Any],
    *,
    candidate_profile: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    """Validate and repair parsed roadmap JSON before rendering/persistence."""
    target_role = _clean_text(roadmap.get("target_role")) or str(job.get("title") or "this role")
    candidate_skills = _clean_list(candidate_profile.get("skills"))
    job_skills = _clean_list(job.get("skills_required"))
    gaps = _skill_gaps(candidate_skills, job_skills)
    strengths = _unique_nonempty(
        [*_skill_overlap(candidate_skills, job_skills), *candidate_skills[:4]]
    )
    if not strengths:
        current_title = _clean_text(candidate_profile.get("current_title"))
        strengths = [current_title] if current_title else ["Existing role experience"]
    if not gaps:
        gaps = _clean_list(roadmap.get("gaps")) or ["Role-specific practice"]

    normalized = {
        "summary": _clean_text(roadmap.get("summary"))
        or _fallback_summary(target_role, strengths, gaps),
        "target_role": target_role,
        "current_strengths": _unique_nonempty(
            [*_clean_list(roadmap.get("current_strengths")), *strengths]
        ),
        "gaps": _unique_nonempty([*_clean_list(roadmap.get("gaps")), *gaps]),
        "phases": _normalize_phases(
            roadmap.get("phases"),
            target_role=target_role,
            gaps=gaps,
            strengths=strengths,
        ),
        "stretch_goals": _clean_list(roadmap.get("stretch_goals")),
    }
    if len(normalized["phases"]) < 3:
        normalized["phases"] = _fallback_phases(
            target_role=target_role,
            gaps=gaps,
            strengths=strengths,
        )
    if not normalized["stretch_goals"]:
        normalized["stretch_goals"] = [f"Build a small portfolio project for {target_role}."]
    return normalized


def _unique_nonempty(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _PLACEHOLDER_VALUES else text


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _skill_overlap(candidate_skills: list[str], job_skills: list[str]) -> list[str]:
    cand = {canonical_skill(skill): skill for skill in candidate_skills if canonical_skill(skill)}
    return [skill for skill in job_skills if canonical_skill(skill) in cand]


def _skill_gaps(candidate_skills: list[str], job_skills: list[str]) -> list[str]:
    cand = {canonical_skill(skill) for skill in candidate_skills if canonical_skill(skill)}
    return [skill for skill in job_skills if canonical_skill(skill) not in cand]


def _fallback_summary(target_role: str, strengths: list[str], gaps: list[str]) -> str:
    strength_line = ", ".join(strengths[:3]) if strengths else "your existing experience"
    gap_line = ", ".join(gaps[:3]) if gaps else "role-specific practice"
    return (
        f"This roadmap builds from {strength_line} toward {target_role}. "
        f"It focuses on closing gaps in {gap_line} with practical weekly milestones."
    )


def _normalize_phases(
    phases: Any,
    *,
    target_role: str,
    gaps: list[str],
    strengths: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(phases, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(phases[:5]):
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title")) or f"Phase {index + 1}: Build role readiness"
        milestones = _clean_list(raw.get("milestones"))
        focus = _clean_text(raw.get("focus")) or f"Make progress toward {target_role}."
        skills = _clean_list(raw.get("skills")) or gaps[:3] or strengths[:3]
        if not milestones:
            milestones = _phase_milestones(focus=focus, skills=skills, target_role=target_role)
        normalized.append(
            {
                "title": title,
                "duration": _clean_text(raw.get("duration")) or f"Weeks {index + 1}-{index + 2}",
                "focus": focus,
                "milestones": milestones,
                "skills": skills,
                "resources": _normalize_resources(raw.get("resources"), skills=skills),
            }
        )
    return normalized


def _normalize_resources(resources: Any, *, skills: list[str]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if isinstance(resources, list):
        for resource in resources:
            if isinstance(resource, dict):
                label = _clean_text(resource.get("label"))
                note = _clean_text(resource.get("note"))
                url = _clean_text(resource.get("url"))
                if label:
                    item = {"label": label, "note": note or "Use this for focused practice."}
                    if url.startswith("http"):
                        item["url"] = url
                    normalized.append(item)
            else:
                label = _clean_text(resource)
                if label:
                    normalized.append({"label": label, "note": "Use this for focused practice."})
    if normalized:
        return normalized
    topic = skills[0] if skills else "role fundamentals"
    return [{"label": f"{topic} official docs or practice guide", "note": "Review and apply it."}]


def _fallback_phases(
    *,
    target_role: str,
    gaps: list[str],
    strengths: list[str],
) -> list[dict[str, Any]]:
    topics = (gaps + strengths + [target_role])[:3]
    while len(topics) < 3:
        topics.append("role-specific practice")
    return [
        {
            "title": "Phase 1: Map the role and close foundations",
            "duration": "Weeks 1-2",
            "focus": f"Understand the {target_role} requirements and refresh {topics[0]}.",
            "milestones": _phase_milestones(
                focus=f"Refresh {topics[0]}", skills=[topics[0]], target_role=target_role
            ),
            "skills": [topics[0]],
            "resources": _normalize_resources([], skills=[topics[0]]),
        },
        {
            "title": "Phase 2: Practice role-specific execution",
            "duration": "Weeks 3-4",
            "focus": f"Turn {topics[1]} into visible {target_role} work samples.",
            "milestones": _phase_milestones(
                focus=f"Practice {topics[1]}", skills=[topics[1]], target_role=target_role
            ),
            "skills": [topics[1]],
            "resources": _normalize_resources([], skills=[topics[1]]),
        },
        {
            "title": "Phase 3: Prove readiness with a capstone",
            "duration": "Weeks 5-6",
            "focus": f"Create a compact capstone that demonstrates readiness for {target_role}.",
            "milestones": _phase_milestones(
                focus=f"Build a {target_role} capstone",
                skills=[topics[2]],
                target_role=target_role,
            ),
            "skills": [topics[2]],
            "resources": _normalize_resources([], skills=[topics[2]]),
        },
    ]


def _phase_milestones(*, focus: str, skills: list[str], target_role: str) -> list[str]:
    topic = skills[0] if skills else focus
    return [
        f"Spend three focused sessions reviewing {topic}.",
        f"Create one practical exercise connected to {target_role}.",
        "Write a short reflection with evidence, gaps, and next actions.",
    ]


# ── HTML rendering ────────────────────────────────────────────────────────────

_E = html.escape


def _li_items(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return "".join(f"<li>{_E(str(i))}</li>" for i in items if str(i).strip())


def render_roadmap_html(
    roadmap: dict[str, Any],
    *,
    job_title: str,
    company_name: str,
    candidate_name: str,
    storage_key: str,
) -> str:
    """Render the roadmap dict into a self-contained interactive HTML app."""
    summary = _E(str(roadmap.get("summary") or ""))
    target = _E(str(roadmap.get("target_role") or job_title or "this role"))
    strengths = _li_items(roadmap.get("current_strengths"))
    gaps = _li_items(roadmap.get("gaps"))
    stretch = _li_items(roadmap.get("stretch_goals"))

    phases = roadmap.get("phases") or []
    phase_blocks: list[str] = []
    milestone_index = 0
    total_milestones = 0
    for pi, phase in enumerate(phases if isinstance(phases, list) else []):
        if not isinstance(phase, dict):
            continue
        title = _E(str(phase.get("title") or f"Phase {pi + 1}"))
        duration = _E(str(phase.get("duration") or ""))
        focus = _E(str(phase.get("focus") or ""))
        skills = phase.get("skills") or []
        skill_chips = "".join(
            f"<span class='chip'>{_E(str(s))}</span>" for s in skills if str(s).strip()
        )
        milestones = phase.get("milestones") or []
        mrows: list[str] = []
        for m in milestones if isinstance(milestones, list) else []:
            if not str(m).strip():
                continue
            mid = f"m{milestone_index}"
            milestone_index += 1
            total_milestones += 1
            mrows.append(
                f"<label class='milestone'>"
                f"<input type='checkbox' data-id='{mid}' data-phase='{pi}'>"
                f"<span>{_E(str(m))}</span></label>"
            )
        resources = phase.get("resources") or []
        rrows: list[str] = []
        for r in resources if isinstance(resources, list) else []:
            if isinstance(r, dict):
                label = _E(str(r.get("label") or ""))
                note = _E(str(r.get("note") or ""))
                url = str(r.get("url") or "").strip()
                if label:
                    link = (
                        f"<a href='{_E(url)}' target='_blank' rel='noopener noreferrer'>"
                        f"{label} ↗</a>"
                        if url.startswith("http")
                        else f"<strong>{label}</strong>"
                    )
                    rrows.append(f"<li>{link}" + (f" — {note}" if note else "") + "</li>")
            elif str(r).strip():
                rrows.append(f"<li>{_E(str(r))}</li>")

        phase_blocks.append(
            f"""<section class="phase" data-phase="{pi}">
  <div class="phase-head">
    <div class="phase-title"><span class="phase-num">{pi + 1}</span><h3>{title}</h3></div>
    <div class="phase-meta">{f'<span class="duration">{duration}</span>' if duration else ""}<span class="phase-status" id="status-{pi}"></span></div>
  </div>
  {f'<p class="focus">{focus}</p>' if focus else ""}
  {f'<div class="chips">{skill_chips}</div>' if skill_chips else ""}
  {f'<div class="milestones">{"".join(mrows)}</div>' if mrows else ""}
  {f'<div class="resources"><h4>Resources</h4><ul>{"".join(rrows)}</ul></div>' if rrows else ""}
</section>"""
        )

    phases_html = "\n".join(phase_blocks) or "<p>No phases generated.</p>"
    header_sub = _E(
        f"{candidate_name} → {job_title}" + (f" at {company_name}" if company_name else "")
    ).strip(" →")

    return _DOC_TEMPLATE.format(
        title=_E(f"Learning roadmap — {job_title}"),
        target=target,
        header_sub=header_sub,
        summary_block=(f'<p class="summary">{summary}</p>' if summary else ""),
        strengths_block=(
            f'<div class="card"><h4>You already bring</h4><ul>{strengths}</ul></div>'
            if strengths
            else ""
        ),
        gaps_block=(
            f'<div class="card"><h4>Focus areas for this role</h4><ul>{gaps}</ul></div>'
            if gaps
            else ""
        ),
        phases=phases_html,
        stretch_block=(
            f'<section class="phase"><div class="phase-head"><h3>Stretch goals</h3>'
            f"</div><ul>{stretch}</ul></section>"
            if stretch
            else ""
        ),
        total=total_milestones,
        storage_key=_E(storage_key),
    )


# Literal CSS/JS braces are doubled for str.format.
_DOC_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #f3f4f6; color: #1a1a1a; line-height: 1.55;
    font-family: -apple-system, system-ui, "Segoe UI", Roboto, Arial, sans-serif;
  }}
  .wrap {{ max-width: 820px; margin: 0 auto; padding: 28px 20px 64px; }}
  header.top {{ margin-bottom: 20px; }}
  header.top h1 {{ font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }}
  header.top .sub {{ color: #555; font-size: 14px; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
  .pill {{ font-size: 12px; font-weight: 600; background: #eff4ff; color: #2563eb;
    padding: 4px 11px; border-radius: 999px; }}
  .summary {{ font-size: 15px; margin: 14px 0 22px; }}
  .progress-wrap {{
    position: sticky; top: 0; background: #f3f4f6; padding: 12px 0; z-index: 5;
    margin-bottom: 18px;
  }}
  .bar {{ height: 10px; background: #e2e4e8; border-radius: 999px; overflow: hidden; }}
  .bar > i {{ display: block; height: 100%; width: 0; background: #2563eb; transition: width .25s; }}
  .progress-label {{ font-size: 13px; color: #444; margin-top: 6px; font-weight: 600; }}
  .grid {{ display: grid; gap: 14px; grid-template-columns: 1fr 1fr; margin-bottom: 22px; }}
  @media (max-width: 560px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px 16px; }}
  .card h4, .resources h4 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .06em;
    color: #6b7280; margin: 0 0 8px; }}
  .card ul {{ margin: 0; padding-left: 18px; }} .card li {{ font-size: 14px; margin: 3px 0; }}
  .phase {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 14px;
    padding: 18px 20px; margin-bottom: 14px; transition: border-color .2s, box-shadow .2s; }}
  .phase.phase-done {{ border-color: #bbf7d0; box-shadow: 0 0 0 1px #bbf7d0 inset; }}
  .phase-head {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
  .phase-title {{ display: flex; align-items: center; gap: 11px; min-width: 0; }}
  .phase-title h3 {{ font-size: 17px; margin: 0; }}
  .phase-num {{ flex: none; width: 28px; height: 28px; border-radius: 9px; color: #fff;
    font-size: 14px; font-weight: 700; display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #6366f1, #2563eb); }}
  .phase-done .phase-num {{ background: linear-gradient(135deg, #16a34a, #22c55e); }}
  .phase-meta {{ display: flex; align-items: center; gap: 8px; white-space: nowrap; }}
  .phase-status {{ font-size: 12px; font-weight: 600; color: #6b7280; }}
  .phase-status.complete {{ color: #16a34a; }}
  .duration {{ font-size: 12px; font-weight: 600; color: #2563eb; background: #eff4ff;
    padding: 3px 9px; border-radius: 999px; white-space: nowrap; }}
  .resources a {{ color: #2563eb; text-decoration: none; font-weight: 600; }}
  .resources a:hover {{ text-decoration: underline; }}
  .focus {{ color: #555; font-size: 14px; margin: 6px 0 10px; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
  .chip {{ font-size: 12px; background: #f1f3f5; color: #374151; padding: 3px 9px; border-radius: 6px; }}
  .milestones {{ display: flex; flex-direction: column; gap: 2px; }}
  .milestone {{ display: flex; gap: 10px; align-items: flex-start; padding: 7px 8px;
    border-radius: 8px; cursor: pointer; font-size: 14px; }}
  .milestone:hover {{ background: #f7f8fa; }}
  .milestone input {{ margin-top: 3px; width: 16px; height: 16px; accent-color: #2563eb; flex: none; }}
  .milestone.done span {{ text-decoration: line-through; color: #9ca3af; }}
  .resources {{ margin-top: 12px; border-top: 1px solid #f0f1f3; padding-top: 10px; }}
  .resources ul {{ margin: 0; padding-left: 18px; }} .resources li {{ font-size: 13.5px; margin: 4px 0; }}
  .toolbar {{ text-align: right; margin-bottom: 14px; }}
  .toolbar button {{ font: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
    color: #fff; background: #1a1a1a; border: 0; border-radius: 999px; padding: 8px 15px; }}
  .reset {{ background: none !important; color: #6b7280 !important; }}
  @media print {{ .no-print {{ display: none !important; }} body {{ background: #fff; }}
    .progress-wrap {{ position: static; }} }}
</style>
</head>
<body>
  <div class="wrap">
    <div class="toolbar no-print">
      <button type="button" onclick="window.print()">Save as PDF</button>
      <button type="button" class="reset" onclick="resetProgress()">Reset progress</button>
    </div>
    <header class="top">
      <h1>Your learning roadmap to {target}</h1>
      <div class="sub">{header_sub}</div>
      <div class="meta">
        <span class="pill">Based on your resume</span>
        <span class="pill">~1 hour/day · 7 hrs/week</span>
        <span class="pill">Target: {target}</span>
      </div>
    </header>
    {summary_block}
    <div class="progress-wrap no-print">
      <div class="bar"><i id="bar"></i></div>
      <div class="progress-label"><span id="done">0</span> of {total} milestones complete</div>
    </div>
    <div class="grid">{strengths_block}{gaps_block}</div>
    {phases}
    {stretch_block}
  </div>
<script>
  var KEY = "hireloop-roadmap-{storage_key}";
  var TOTAL = {total};
  function load() {{ try {{ return JSON.parse(localStorage.getItem(KEY)) || {{}}; }} catch (e) {{ return {{}}; }} }}
  function save(s) {{ try {{ localStorage.setItem(KEY, JSON.stringify(s)); }} catch (e) {{}} }}
  function refresh() {{
    var boxes = document.querySelectorAll('.milestone input');
    var done = 0;
    boxes.forEach(function (b) {{ if (b.checked) {{ done++; b.closest('.milestone').classList.add('done'); }}
      else {{ b.closest('.milestone').classList.remove('done'); }} }});
    document.getElementById('done').textContent = done;
    var pct = TOTAL ? Math.round((done / TOTAL) * 100) : 0;
    document.getElementById('bar').style.width = pct + '%';
    // Per-phase completion (the "skill tree" reward).
    document.querySelectorAll('.phase[data-phase]').forEach(function (sec) {{
      var pi = sec.getAttribute('data-phase');
      var pboxes = sec.querySelectorAll('.milestone input');
      if (!pboxes.length) return;
      var pdone = 0;
      pboxes.forEach(function (b) {{ if (b.checked) pdone++; }});
      var status = document.getElementById('status-' + pi);
      var complete = pdone === pboxes.length;
      sec.classList.toggle('phase-done', complete);
      if (status) {{
        status.textContent = complete ? '✓ Complete' : pdone + '/' + pboxes.length;
        status.classList.toggle('complete', complete);
      }}
    }});
  }}
  function resetProgress() {{ save({{}}); document.querySelectorAll('.milestone input').forEach(function (b) {{ b.checked = false; }}); refresh(); }}
  (function init() {{
    var state = load();
    document.querySelectorAll('.milestone input').forEach(function (b) {{
      var id = b.getAttribute('data-id');
      if (state[id]) b.checked = true;
      b.addEventListener('change', function () {{ var s = load(); s[id] = b.checked; save(s); refresh(); }});
    }});
    refresh();
  }})();
</script>
</body>
</html>"""


async def save_learning_roadmap(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    html_content: str,
    summary_line: str = "",
) -> uuid.UUID:
    """Persist the roadmap row; mirrors save_tailored_resume."""
    roadmap_id = uuid.uuid4()
    file_path = f"{candidate_id}/{job_id}/{roadmap_id}.html"
    expires_at = datetime.now(UTC) + timedelta(days=90)

    await db.execute(
        """
        INSERT INTO public.learning_roadmaps (
          id, candidate_id, job_id, file_path,
          summary_line, html_content, status, expires_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, 'ready', $7)
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
          file_path = EXCLUDED.file_path,
          summary_line = EXCLUDED.summary_line,
          html_content = EXCLUDED.html_content,
          status = 'ready',
          error_message = NULL,
          expires_at = EXCLUDED.expires_at
        """,
        roadmap_id,
        candidate_id,
        job_id,
        file_path,
        summary_line[:500] if summary_line else None,
        html_content[:500_000],
        expires_at,
    )
    return roadmap_id
