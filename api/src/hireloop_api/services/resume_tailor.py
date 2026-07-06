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

logger = structlog.get_logger()

TAILOR_SYSTEM = """You tailor a candidate resume for a specific job description.
Rules:
- Never fabricate experience, employers, or degrees
- Rewrite bullets to mirror JD vocabulary where truthful
- Reorder experience by relevance to this JD
- Add a 2-line tailored summary at the top
- Output valid HTML only (no markdown fences), using a clean single-column layout
- Use <h1> for name, <h2> for sections: Summary, Experience, Skills, Education
"""

PATH_RESUME_SYSTEM = """You write an ATS-friendly resume tailored to a career-path direction.
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
    prompt = f"""Target career direction: {path_title}
{f"Path context: {path_summary}" if path_summary else ""}

Candidate profile (source of truth — do not invent beyond this):
{json_dumps_safe(candidate_profile)}

Produce the ATS-friendly resume HTML fragment for the target direction."""

    resp = await llm.ainvoke(
        [
            SystemMessage(content=PATH_RESUME_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return content


async def generate_tailored_html(
    *,
    llm: ChatOpenAI,
    candidate_profile: dict[str, Any],
    job: dict[str, Any],
    template: str,
) -> str:
    """LLM generates tailored resume HTML."""
    prompt = f"""Template style: {template}

Candidate profile:
{json_dumps_safe(candidate_profile)}

Job:
Title: {job.get("title")}
Company: {job.get("company_name", "Company")}
Description: {(job.get("description") or "")[:4000]}

Produce tailored resume HTML."""

    resp = await llm.ainvoke(
        [
            SystemMessage(content=TAILOR_SYSTEM),
            HumanMessage(content=prompt),
        ]
    )
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    # Strip accidental markdown fences
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return content


def json_dumps_safe(obj: Any) -> str:
    import json

    return json.dumps(obj, default=str, indent=2)[:8000]


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
    return _PRINT_DOC_TEMPLATE.format(
        title=html.escape(title or "Resume"),
        body=inner,
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
