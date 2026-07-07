"""
Tailored resume generator (P20).

Claude rewrites bullets for JD fit; output stored as HTML in Supabase Storage.
PDF generation uses simple HTML — browser print or future Puppeteer sidecar.
"""

from __future__ import annotations

import html
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.services.ai_context import compose_candidate_prompt

logger = structlog.get_logger()

TAILOR_SYSTEM = """You tailor a candidate resume for a specific job description.
The output must be ATS-safe AND read like a polished professional document.

SOURCE OF TRUTH (critical):
- The candidate profile JSON is the ONLY authority for employers, job titles, dates,
  locations, degrees, skills, and metrics
- Include every role and degree from the profile; you may reorder by JD relevance
  and rephrase bullets, but NEVER omit roles, change companies/titles/dates/tenure,
  inflate seniority, or invent metrics
- If a fact is missing from the profile, leave it out — never guess

Rules:
- Never fabricate experience, employers, degrees, or dates
- Rewrite bullets to mirror this JD's vocabulary where truthful; reorder
  experience by relevance to this JD
- Output valid HTML fragment only (no <html>/<head>/<body>, no markdown fences)
- Single-column layout — NO tables, columns, images, icons, or text boxes
  (ATS parsers mangle them)
- Structure (exactly these tags/classes — the print/DOCX pipeline styles them):
  <h1>Full Name</h1>
  <p class="resume-contact">City, State · email · phone · LinkedIn URL (only if provided)</p>
  <h2>Professional Summary</h2>
  <p>2–3 lines positioning the candidate for THIS job</p>
  <h2>Core Skills</h2>
  <p>comma-separated keyword-rich skills (12–18 items), JD keywords first</p>
  <h2>Professional Experience</h2>
  For each role:
    <h3>Job Title — Company</h3>
    <p class="role-meta">Mon YYYY – Mon YYYY · Location</p>
    <ul><li>Quantified achievement bullets (3–5 per recent role)</li></ul>
  <h2>Education</h2>
  <p>Degree — Institution · Year</p>
- Use strong action verbs and metrics where truthful; use <strong> sparingly
  for key metrics only
- Spell out the exact job title and company keywords naturally where truthful
- Keep total length to one page (~500–700 words)
"""

PATH_RESUME_SYSTEM = """You write an ATS-friendly resume tailored to a career-path direction.

SOURCE OF TRUTH (critical):
- The candidate profile JSON is the ONLY authority for employers, job titles, dates,
  education, skills, and metrics — never invent or alter facts
- Include every role and degree from the profile; reorder and rephrase only

Rules:
- Never fabricate experience, employers, degrees, or dates
- Output valid HTML fragment only (no <html>/<head>/<body>, no markdown fences)
- Single-column layout — NO tables, columns, images, icons, or text boxes
- Structure:
  <h1>Full Name</h1>
  <p class="resume-contact">City, State · email · phone · LinkedIn URL (only if provided)</p>
  <h2>Professional Summary</h2>
  <p>2–3 lines positioning the candidate for the target role</p>
  <h2>Core Skills</h2>
  <p>comma-separated keyword-rich skills (12–18 items)</p>
  <h2>Professional Experience</h2>
  For each role:
    <h3>Job Title — Company</h3>
    <p class="role-meta">Mon YYYY – Mon YYYY · Location</p>
    <ul><li>Quantified achievement bullets (3–5 per recent role)</li></ul>
  <h2>Education</h2>
  <p>Degree — Institution · Year</p>
- Use strong action verbs and metrics where truthful
- Mirror keywords from the target role title naturally
- Keep total length to one page (~500–700 words)
"""


async def generate_path_resume_html(
    *,
    llm: ChatOpenAI,
    candidate_profile: dict[str, Any],
    path_title: str,
    path_summary: str | None = None,
) -> str:
    """LLM generates an ATS-oriented career-path resume HTML fragment."""
    task_prompt = f"""Target career direction: {path_title}
{f"Path context: {path_summary}" if path_summary else ""}

Produce the ATS-friendly resume HTML fragment for the target direction."""
    prompt = compose_candidate_prompt(
        candidate_profile,
        task="path_resume",
        task_prompt=task_prompt,
    )

    resp = await llm.ainvoke(
        [
            SystemMessage(content=PATH_RESUME_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return normalize_tailored_resume_html(content, candidate_profile=candidate_profile)


async def generate_tailored_html(
    *,
    llm: ChatOpenAI,
    candidate_profile: dict[str, Any],
    job: dict[str, Any],
    template: str,
) -> str:
    """LLM generates tailored resume HTML."""
    task_prompt = f"""Template style: {template}

Job:
Title: {job.get("title")}
Company: {job.get("company_name", "Company")}
Description: {(job.get("description") or "")[:4000]}

Produce tailored resume HTML."""
    prompt = compose_candidate_prompt(
        candidate_profile,
        task="tailored_resume",
        task_prompt=task_prompt,
    )

    resp = await llm.ainvoke(
        [
            SystemMessage(content=TAILOR_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    return normalize_tailored_resume_html(content, candidate_profile=candidate_profile)


def json_dumps_safe(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str, indent=2)[:12000]


_PLACEHOLDER_RE = re.compile(r"^(?:null|none|undefined|n/a|na|—|-)?$", re.IGNORECASE)
_DANGEROUS_BLOCK_RE = re.compile(
    r"<(script|style|iframe|object|embed|form|table|thead|tbody|tr|td|th|svg|canvas|button)"
    r"[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_VOID_RE = re.compile(
    r"<(?:img|input|link|meta|source|video|audio)[^>]*>", re.IGNORECASE | re.DOTALL
)
_ALLOWED_INLINE_TAGS = ("strong", "b", "em", "i", "u", "a")


def normalize_tailored_resume_html(
    raw_html: str,
    *,
    candidate_profile: dict[str, Any],
) -> str:
    """Sanitize and complete an LLM-produced ATS resume fragment.

    The model may style, omit, or placeholder sections. This guardrail keeps the
    stored document single-column, removes null-like display text, and restores
    source-of-truth roles/education from the backend profile without inventing.
    """
    inner = _extract_resume_body(_strip_markdown_fence(raw_html))
    inner = _sanitize_resume_fragment(inner)
    inner = _remove_placeholder_blocks(inner)
    inner = _ensure_header(inner, candidate_profile)
    inner = _ensure_summary(inner, candidate_profile)
    inner = _ensure_skills(inner, candidate_profile)
    inner = _ensure_experience(inner, candidate_profile)
    inner = _ensure_education(inner, candidate_profile)
    return _compact_html(inner)


def resume_summary_line(html_content: str) -> str:
    """Plain-text summary snippet safe for list views."""
    for paragraph in re.findall(r"<p[^>]*>(.*?)</p>", html_content or "", flags=re.I | re.S):
        text = _plain_text(paragraph)
        if text and not _is_placeholder_text(text):
            return text[:200]
    return ""


def _strip_markdown_fence(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return text.strip()


def _extract_resume_body(content: str) -> str:
    body_match = re.search(r"<body[^>]*>(.*)</body>", content, re.IGNORECASE | re.DOTALL)
    if body_match:
        return body_match.group(1).strip()
    content = re.sub(r"<head[^>]*>.*?</head>", "", content, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"</?(?:html|body)[^>]*>", "", content, flags=re.IGNORECASE).strip()


def _sanitize_resume_fragment(content: str) -> str:
    content = _DANGEROUS_BLOCK_RE.sub("", content or "")
    content = _DANGEROUS_VOID_RE.sub("", content)
    content = re.sub(r"\s+on\w+=(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", content, flags=re.I)
    content = re.sub(r"""href=(["'])\s*javascript:[^"']*\1""", 'href="#"', content, flags=re.I)
    return content


def _remove_placeholder_blocks(content: str) -> str:
    for tag in ("p", "li", "span", "div"):
        content = re.sub(
            rf"<{tag}[^>]*>\s*(?:null|none|undefined|n/a|na|—|-)\s*</{tag}>",
            "",
            content,
            flags=re.I,
        )
    content = re.sub(r"\b(?:null|none|undefined)\b\s*(?:·\s*)?", "", content, flags=re.I)
    return content


def _ensure_header(content: str, profile: dict[str, Any]) -> str:
    name = _first_text(profile.get("full_name"), profile.get("name")) or "Resume"
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", content, flags=re.I | re.S)
    h1 = f"<h1>{html.escape(name)}</h1>"
    if h1_match and _is_placeholder_text(_plain_text(h1_match.group(1))):
        content = content[: h1_match.start()] + h1 + content[h1_match.end() :]
    elif not h1_match:
        content = f"{h1}\n{content}"

    contact = _contact_line(profile)
    if contact:
        contact_html = f'<p class="resume-contact">{html.escape(contact)}</p>'
        contact_match = re.search(
            r"<p[^>]*class=[\"'][^\"']*resume-contact[^\"']*[\"'][^>]*>.*?</p>",
            content,
            flags=re.I | re.S,
        )
        if contact_match and _is_placeholder_text(_plain_text(contact_match.group(0))):
            content = (
                content[: contact_match.start()] + contact_html + content[contact_match.end() :]
            )
        elif not contact_match:
            h1_end = re.search(r"</h1>", content, flags=re.I)
            if h1_end:
                content = content[: h1_end.end()] + f"\n{contact_html}" + content[h1_end.end() :]
    return content


def _ensure_summary(content: str, profile: dict[str, Any]) -> str:
    if _has_heading(content, "Professional Summary"):
        return content
    summary = _first_text(
        profile.get("summary"), profile.get("headline"), profile.get("looking_for")
    )
    if not summary:
        return content
    return f"{content}\n<h2>Professional Summary</h2>\n<p>{html.escape(summary)}</p>"


def _ensure_skills(content: str, profile: dict[str, Any]) -> str:
    if _has_heading(content, "Core Skills"):
        return content
    skills = [_first_text(skill) for skill in (profile.get("skills") or [])]
    skills = [s for s in skills if s]
    if not skills:
        return content
    return f"{content}\n<h2>Core Skills</h2>\n<p>{html.escape(', '.join(skills[:18]))}</p>"


def _ensure_experience(content: str, profile: dict[str, Any]) -> str:
    roles = [r for r in (profile.get("experience") or []) if isinstance(r, dict)]
    if not roles:
        return content
    if not _has_heading(content, "Professional Experience"):
        content = f"{content}\n<h2>Professional Experience</h2>"
    text = _plain_text(content).lower()
    missing: list[str] = []
    for role in roles[:12]:
        title = _first_text(role.get("title"), role.get("current_title"))
        company = _first_text(role.get("company"), role.get("company_name"), role.get("employer"))
        if not title and not company:
            continue
        key = " ".join(part for part in (title, company) if part).lower()
        if key and all(part.lower() in text for part in key.split()):
            continue
        heading = " — ".join(html.escape(part) for part in (title, company) if part)
        meta = _role_meta(role)
        missing.append(
            f"<h3>{heading}</h3>{f'<p class="role-meta">{html.escape(meta)}</p>' if meta else ''}"
        )
    if missing:
        content = f"{content}\n" + "\n".join(missing)
    return content


def _ensure_education(content: str, profile: dict[str, Any]) -> str:
    education = [e for e in (profile.get("education") or []) if isinstance(e, dict)]
    if not education:
        return content
    if not _has_heading(content, "Education"):
        content = f"{content}\n<h2>Education</h2>"
    text = _plain_text(content).lower()
    missing: list[str] = []
    for item in education[:8]:
        degree = _first_text(item.get("degree"), item.get("qualification"), item.get("program"))
        institution = _first_text(
            item.get("institution"), item.get("school"), item.get("university")
        )
        year = _first_text(item.get("year"), item.get("end_date"), item.get("graduation_year"))
        if not degree and not institution:
            continue
        key = " ".join(part for part in (degree, institution) if part).lower()
        if key and all(part.lower() in text for part in key.split()):
            continue
        line = " — ".join(html.escape(part) for part in (degree, institution) if part)
        if year:
            line = f"{line} · {html.escape(year)}"
        missing.append(f"<p>{line}</p>")
    if missing:
        content = f"{content}\n" + "\n".join(missing)
    return content


def _role_meta(role: dict[str, Any]) -> str:
    dates = " – ".join(
        part
        for part in (
            _first_text(role.get("start_date"), role.get("start")),
            _first_text(role.get("end_date"), role.get("end")) or "Present",
        )
        if part
    )
    location = _first_text(role.get("location"), role.get("location_city"))
    return " · ".join(part for part in (dates, location) if part)


def _contact_line(profile: dict[str, Any]) -> str:
    location = ", ".join(
        part
        for part in (
            _first_text(profile.get("location_city")),
            _first_text(profile.get("location_state")),
        )
        if part
    )
    return " · ".join(
        part
        for part in (
            location,
            _first_text(profile.get("email")),
            _first_text(profile.get("phone")),
            _first_text(profile.get("linkedin_url")),
        )
        if part
    )


def _has_heading(content: str, heading: str) -> bool:
    return bool(
        re.search(
            rf"<h2[^>]*>\s*{re.escape(heading)}\s*</h2>",
            content or "",
            flags=re.I,
        )
    )


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text and not _is_placeholder_text(text):
            return text
    return None


def _is_placeholder_text(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.match(_plain_text(value).strip()))


def _plain_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text).replace("\xa0", " ")
    return " ".join(text.split())


def _compact_html(content: str) -> str:
    content = re.sub(r"\n{3,}", "\n\n", content or "")
    content = re.sub(r">\s+<", ">\n<", content)
    return content.strip()


# A4, print-optimized shell. Wrapping the LLM's resume body in this turns the
# browser's "Save as PDF" into a clean, professional file — no headless-browser
# / weasyprint dependency. Literal CSS braces are doubled for str.format.
_PRINT_DOC_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #f3f4f6; color: #1a1a1a; line-height: 1.5;
    font-family: -apple-system, system-ui, "Segoe UI", Roboto, Arial, sans-serif;
  }}
  .sheet {{
    background: #fff; max-width: 794px; margin: 24px auto; padding: 48px 56px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.12);
  }}
  .sheet h1 {{ font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; font-weight: 700; }}
  .sheet .resume-contact {{
    font-size: 12.5px; color: #444; margin: 0 0 16px; line-height: 1.45;
  }}
  .sheet h2 {{
    font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.1em; color: #333;
    border-bottom: 1.5px solid #222; padding-bottom: 3px; margin: 20px 0 8px;
    font-weight: 700;
  }}
  .sheet h3 {{ font-size: 14.5px; margin: 14px 0 2px; font-weight: 600; }}
  .sheet .role-meta {{ font-size: 12px; color: #555; margin: 0 0 4px; font-style: italic; }}
  .sheet p, .sheet li {{ font-size: 13px; line-height: 1.5; }}
  .sheet ul {{ margin: 4px 0 8px 18px; padding: 0; }}
  .sheet li {{ margin-bottom: 3px; }}
  .sheet a {{ color: #1a1a1a; text-decoration: none; }}
  .toolbar {{ position: fixed; top: 16px; right: 16px; display: flex; gap: 8px; }}
  .toolbar button {{
    font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; color: #fff;
    background: #1a1a1a; border: 0; border-radius: 999px; padding: 9px 16px;
  }}
  .toolbar .hint {{
    font-size: 12px; color: #666; background: #fff; border: 1px solid #ddd;
    border-radius: 8px; padding: 8px 12px; max-width: 220px; line-height: 1.35;
  }}
  @media print {{
    body {{ background: #fff; }}
    .no-print {{ display: none !important; }}
    .sheet {{ box-shadow: none; margin: 0; max-width: none; padding: 0; }}
  }}
  @page {{ size: A4; margin: 16mm; }}
</style>
</head>
<body>
  <div class="toolbar no-print">
    <span class="hint">Private preview — use Save as PDF for a one-page ATS file.</span>
    <button type="button" onclick="window.print()">Save as PDF</button>
  </div>
  <div class="sheet">
{body}
  </div>
  {auto_print_script}
</body>
</html>"""


def wrap_print_document(body_html: str, *, title: str = "Resume", auto_print: bool = False) -> str:
    """
    Wrap LLM-generated resume HTML in a clean, A4 print-ready document so the
    browser's "Save as PDF" yields a professional file. Lifts the <body> if the
    model returned a full document; otherwise strips stray html/head wrappers.
    """
    inner = (body_html or "").strip()
    body_match = re.search(r"<body[^>]*>(.*)</body>", inner, re.IGNORECASE | re.DOTALL)
    if body_match:
        inner = body_match.group(1).strip()
    else:
        inner = re.sub(r"<head[^>]*>.*?</head>", "", inner, flags=re.IGNORECASE | re.DOTALL)
        inner = re.sub(r"</?(?:html|body)[^>]*>", "", inner, flags=re.IGNORECASE)
    script = (
        "<script>addEventListener('load',()=>setTimeout(()=>print(),300));</script>"
        if auto_print
        else ""
    )
    # LLM HTML may contain literal `{` / `}` (CSS, placeholders) — escape for str.format.
    safe_body = inner.replace("{", "{{").replace("}", "}}")
    return _PRINT_DOC_TEMPLATE.format(
        title=html.escape(title or "Resume"),
        body=safe_body,
        auto_print_script=script,
    )


async def save_tailored_resume(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    job_id: uuid.UUID,
    template: str,
    html_content: str,
    summary_line: str = "",
) -> uuid.UUID:
    """Persist tailored resume row; file_path is storage key."""
    resume_id = uuid.uuid4()
    file_path = f"{candidate_id}/{job_id}/{resume_id}.html"
    expires_at = datetime.now(UTC) + timedelta(days=30)

    await db.execute(
        """
        INSERT INTO public.tailored_resumes (
          id, candidate_id, job_id, template, file_path,
          summary_line, html_content, status, expires_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'ready', $8)
        ON CONFLICT (candidate_id, job_id) DO UPDATE SET
          template = EXCLUDED.template,
          file_path = EXCLUDED.file_path,
          summary_line = EXCLUDED.summary_line,
          html_content = EXCLUDED.html_content,
          status = 'ready',
          expires_at = EXCLUDED.expires_at
        """,
        resume_id,
        candidate_id,
        job_id,
        template,
        file_path,
        summary_line[:500] if summary_line else None,
        html_content[:500_000],
        expires_at,
    )
    return resume_id
