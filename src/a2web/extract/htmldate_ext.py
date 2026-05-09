"""htmldate wrapper — sync date detection, single async chokepoint."""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import htmldate


def _find_date_sync(html: str, url: str, *, original: bool) -> date | None:
    """Blocking date detection. `original=True` = published, `False` = updated."""
    try:
        result = htmldate.find_date(
            html,
            url=url,
            original_date=original,
            outputformat="%Y-%m-%d",
        )
    except Exception:
        return None
    if not result:
        return None
    try:
        return datetime.strptime(result, "%Y-%m-%d").date()
    except ValueError:
        return None


async def find_published(html: str, url: str) -> date | None:
    return await asyncio.to_thread(_find_date_sync, html, url, original=True)


async def find_updated(html: str, url: str) -> date | None:
    return await asyncio.to_thread(_find_date_sync, html, url, original=False)
