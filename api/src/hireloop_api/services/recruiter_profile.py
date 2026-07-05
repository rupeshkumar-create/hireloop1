"""Derive recruiter profile display fields from posted job roles."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_PLACEHOLDER_COMPANY = "my company"


def _first_line(text: str | None, *, max_len: int = 140) -> str:
    if not text:
        return ""
    line = text.strip().split("\n", 1)[0].strip()
    if len(line) > max_len:
        return line[: max_len - 1].rstrip() + "…"
    return line


def build_hiring_focus_from_roles(role_rows: list[dict[str, Any]]) -> str | None:
    if not role_rows:
        return None
    lines: list[str] = []
    for row in role_rows:
        title = (row.get("title") or "").strip()
        if not title:
            continue
        parts = [title]
        city = (row.get("location_city") or "").strip()
        state = (row.get("location_state") or "").strip()
        loc = ", ".join(part for part in (city, state) if part)
        if loc:
            parts.append(f"({loc})")
        brief = _first_line(row.get("hiring_brief")) or _first_line(
            row.get("jd_text"), max_len=100
        )
        if brief:
            parts.append(f"— {brief}")
        lines.append(" ".join(parts))
    return "\n".join(lines) if lines else None


def resolve_company_name_from_roles(
    company_row: asyncpg.Record | dict[str, Any] | None,
    role_rows: list[dict[str, Any]],
) -> str | None:
    for row in role_rows:
        name = (row.get("company_name") or "").strip()
        if name and name.lower() != _PLACEHOLDER_COMPANY:
            return name
    if company_row:
        return company_row.get("name")
    return None


async def fetch_recruiter_role_rows(
    db: asyncpg.Connection,
    recruiter_id: UUID,
) -> list[dict[str, Any]]:
    rows = await db.fetch(
        """
        SELECT r.id, r.title, r.location_city, r.location_state, r.status,
               r.hiring_brief, r.jd_text, co.name AS company_name
        FROM public.roles r
        LEFT JOIN public.companies co ON co.id = r.company_id
        WHERE r.recruiter_id = $1
          AND r.deleted_at IS NULL
          AND r.status <> 'closed'
        ORDER BY r.updated_at DESC
        LIMIT 12
        """,
        recruiter_id,
    )
    return [dict(row) for row in rows]


def serialize_active_roles(role_rows: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    out: list[dict[str, str | None]] = []
    for row in role_rows:
        out.append(
            {
                "id": str(row["id"]),
                "title": row.get("title"),
                "location_city": row.get("location_city"),
                "status": row.get("status"),
            }
        )
    return out
