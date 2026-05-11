"""Trafilatura wrapper — sync extraction, single async chokepoint.

Trafilatura is sync, blocking. We wrap it once via `asyncio.to_thread`
here so async paths in the caller never call blocking code directly.

Boundary types: `ExtractedHeading`, `ExtractedLink`, `ExtractedContent`
— package-owned dataclasses. The seam adapts to the caller's preferred
shape (e.g. pydantic `Heading`/`Link`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime

import trafilatura
from selectolax.parser import HTMLParser


@dataclass(slots=True, frozen=True)
class ExtractedHeading:
    level: int  # 1..6
    text: str


@dataclass(slots=True, frozen=True)
class ExtractedLink:
    anchor: str
    href: str


@dataclass(slots=True)
class ExtractedContent:
    content_md: str
    title: str | None = None
    byline: str | None = None
    published: date | None = None
    headings: list[ExtractedHeading] = field(default_factory=list)
    links: list[ExtractedLink] = field(default_factory=list)
    score: float | None = None


def _parse_date(value: str | None) -> date | None:
    """Parse trafilatura's date field (YYYY-MM-DD or ISO timestamp) → date."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _extract_sync(html: str, url: str) -> ExtractedContent:
    """Blocking extraction — never call from async paths directly.

    `trafilatura.extract_metadata(html)` provides title / author / date /
    image / pagetype / sitename in a single pass — replaces the prior
    separate `htmldate.find_date()` call.
    """
    md = (
        trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            favor_recall=False,
        )
        or ""
    )

    title: str | None = None
    byline: str | None = None
    published: date | None = None
    metadata = trafilatura.extract_metadata(html)
    if metadata is not None:
        title = metadata.title or None
        byline = metadata.author or None
        published = _parse_date(getattr(metadata, "date", None))

    headings: list[ExtractedHeading] = []
    links: list[ExtractedLink] = []
    try:
        tree = HTMLParser(html)
        for node in tree.css("h1, h2, h3, h4, h5, h6"):
            level = int(node.tag[1])
            text = (node.text() or "").strip()
            if text:
                headings.append(ExtractedHeading(level=level, text=text))
        for a in tree.css("a[href]"):
            href = a.attributes.get("href") or ""
            anchor = (a.text() or "").strip()
            if href and anchor:
                links.append(ExtractedLink(anchor=anchor, href=href))
    except Exception:  # noqa: S110
        # selectolax parse errors are non-fatal — extraction's primary output is content_md
        pass

    return ExtractedContent(
        content_md=md,
        title=title,
        byline=byline,
        published=published,
        headings=headings,
        links=links,
        score=None,
    )


async def extract_markdown(html: str, url: str) -> ExtractedContent:
    """Async-facing extraction — only public entry into this module."""
    return await asyncio.to_thread(_extract_sync, html, url)
