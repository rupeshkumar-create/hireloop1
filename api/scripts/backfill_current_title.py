"""
Backfill candidates.current_title from work history — no token, no running server.

The résumé parser now falls back to the latest work-experience title when the
LLM leaves current_title null (e.g. "Founder, LimeDock" parsed as company-only).
This one-off applies the same fallback to EXISTING candidate rows whose
current_title is null but whose résumé already has a job title — so the profile
form stops re-asking, and the matching engine's title-affinity has a signal.

Run from the api/ directory:

    uv run python scripts/backfill_current_title.py            # apply
    uv run python scripts/backfill_current_title.py --dry-run  # preview only
"""

from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from hireloop_api.config import get_settings


def _title_from_parsed(parsed: object) -> str | None:
    """First non-empty work title (current role first) from parsed résumé JSON."""
    data = parsed
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    work = [w for w in data.get("work_experience", []) if isinstance(w, dict)]
    ordered = [w for w in work if w.get("is_current")] + [
        w for w in work if not w.get("is_current")
    ]
    for w in ordered:
        title = (w.get("title") or "").strip()
        if title:
            return title
    return None


async def main(dry_run: bool) -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set in api/.env")

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        # Candidates missing a title, but with a parsed résumé to recover one from.
        rows = await conn.fetch(
            """
            SELECT c.id, r.parsed_data
            FROM public.candidates c
            JOIN LATERAL (
                SELECT parsed_data FROM public.resumes
                WHERE candidate_id = c.id AND parsed_data IS NOT NULL
                ORDER BY is_primary DESC, version DESC, created_at DESC
                LIMIT 1
            ) r ON TRUE
            WHERE c.deleted_at IS NULL
              AND COALESCE(c.current_title, '') = ''
            """
        )

        updated = 0
        for row in rows:
            title = _title_from_parsed(row["parsed_data"])
            if not title:
                continue
            print(f"   {row['id']} → {title}")
            if not dry_run:
                await conn.execute(
                    "UPDATE public.candidates SET current_title = $2, updated_at = NOW() "
                    "WHERE id = $1",
                    row["id"],
                    title,
                )
            updated += 1

        verb = "Would update" if dry_run else "Updated"
        print(f"\n✅ {verb} {updated} candidate(s) of {len(rows)} missing a title.")
        if not dry_run and updated:
            print("Re-run scripts/recompute_matches.py so title-affinity re-ranks the feed.")
    finally:
        await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Backfill candidates.current_title from résumé work history."
    )
    ap.add_argument("--dry-run", action="store_true", help="preview changes without writing")
    args = ap.parse_args()
    asyncio.run(main(args.dry_run))
