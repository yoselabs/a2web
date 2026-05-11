"""a2web seam over `packages.content_extract.trafilatura_ext`.

Calls the package's `extract_markdown`, then maps the package's
boundary types (`ExtractedHeading`, `ExtractedLink`) onto the pydantic
`Heading` / `Link` models used in the response envelope.

Preserves the existing `ExtractResult` shape so `fetcher.py` and tests
keep working unmodified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..models import Heading, Link
from ..packages.content_extract import (
    extract_markdown as _package_extract_markdown,
)

__all__ = ("ExtractResult", "extract_markdown")


@dataclass(slots=True)
class ExtractResult:
    content_md: str
    title: str | None = None
    byline: str | None = None
    published: date | None = None
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    score: float | None = None


async def extract_markdown(html: str, url: str) -> ExtractResult:
    """Async-facing extraction — only public entry into this module.

    Forwards to `packages.content_extract.extract_markdown`, then adapts
    the package's frozen `ExtractedHeading`/`ExtractedLink` dataclasses
    onto the response envelope's pydantic `Heading`/`Link` models.
    """
    raw = await _package_extract_markdown(html, url)
    return ExtractResult(
        content_md=raw.content_md,
        title=raw.title,
        byline=raw.byline,
        published=raw.published,
        headings=[Heading(level=h.level, text=h.text) for h in raw.headings],
        links=[Link(anchor=lk.anchor, href=lk.href) for lk in raw.links],
        score=raw.score,
    )
