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

logger = structlog.get_logger()

ROADMAP_SYSTEM = """You are a career coach who builds personalized upskilling \
plans. Given a candidate's profile and a specific job, design a realistic \
learning roadmap that closes the gap between them.

Rules:
- Be specific to THIS candidate and THIS job — reference their actual skills/gaps.
- Never invent the candidate's experience.
- Prefer free or widely-available resources; name concrete topics, not vague advice.
- 3 to 5 phases, each a couple of weeks, ordered from foundations to job-ready.
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
      "resources": [{"label": "resource or topic", "note": "what/why"}]
    }
  ],
  "stretch_goals": ["optional advanced goal", ...]
}"""


async def generate_roadmap(
    *,
    llm: ChatOpenAI,
    candidate_profile: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    """LLM produces a structured learning roadmap as a dict."""
    prompt = f"""{_SCHEMA_HINT}

Candidate profile:
{json.dumps(candidate_profile, default=str, indent=2)[:6000]}

Job:
Title: {job.get("title")}
Company: {job.get("company_name", "Company")}
Required skills: {job.get("skills_required")}
Description: {(job.get("description") or "")[:4000]}

Produce the roadmap JSON now."""

    resp = await llm.ainvoke(
        [
            SystemMessage(content=ROADMAP_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return _parse_roadmap_json(content)


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
                f"<label class='milestone'><input type='checkbox' data-id='{mid}'>"
                f"<span>{_E(str(m))}</span></label>"
            )
        resources = phase.get("resources") or []
        rrows: list[str] = []
        for r in resources if isinstance(resources, list) else []:
            if isinstance(r, dict):
                label = _E(str(r.get("label") or ""))
                note = _E(str(r.get("note") or ""))
                if label:
                    rrows.append(
                        f"<li><strong>{label}</strong>"
                        + (f" — {note}" if note else "")
                        + "</li>"
                    )
            elif str(r).strip():
                rrows.append(f"<li>{_E(str(r))}</li>")

        phase_blocks.append(
            f"""<section class="phase">
  <div class="phase-head">
    <h3>{title}</h3>{f'<span class="duration">{duration}</span>' if duration else ''}
  </div>
  {f'<p class="focus">{focus}</p>' if focus else ''}
  {f'<div class="chips">{skill_chips}</div>' if skill_chips else ''}
  {f'<div class="milestones">{"".join(mrows)}</div>' if mrows else ''}
  {f'<div class="resources"><h4>Resources</h4><ul>{"".join(rrows)}</ul></div>' if rrows else ''}
</section>"""
        )

    phases_html = "\n".join(phase_blocks) or "<p>No phases generated.</p>"
    header_sub = _E(
        f"{candidate_name} → {job_title}"
        + (f" at {company_name}" if company_name else "")
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
    padding: 18px 20px; margin-bottom: 14px; }}
  .phase-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }}
  .phase-head h3 {{ font-size: 17px; margin: 0; }}
  .duration {{ font-size: 12px; font-weight: 600; color: #2563eb; background: #eff4ff;
    padding: 3px 9px; border-radius: 999px; white-space: nowrap; }}
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
