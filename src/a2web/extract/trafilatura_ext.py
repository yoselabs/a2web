"""Trafilatura wrapper — sync extraction, single async chokepoint.

Trafilatura is sync, blocking. We wrap it once via `asyncio.to_thread` here
so async paths in the orchestrator never call blocking code directly. Lint
ASYNC100/210/230 enforces.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import trafilatura
from selectolax.parser import HTMLParser

from ..models import Heading, Link


@dataclass(slots=True)
class ExtractResult:
    content_md: str
    title: str | None = None
    byline: str | None = None
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    score: float | None = None


def _extract_sync(html: str, url: str) -> ExtractResult:
    """Blocking extraction — never call from async paths directly."""
    md = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        favor_recall=False,
    ) or ""

    title: str | None = None
    byline: str | None = None
    metadata = trafilatura.extract_metadata(html)
    if metadata is not None:
        title = metadata.title or None
        byline = metadata.author or None

    headings: list[Heading] = []
    links: list[Link] = []
    try:
        tree = HTMLParser(html)
        for node in tree.css("h1, h2, h3, h4, h5, h6"):
            level = int(node.tag[1])
            text = (node.text() or "").strip()
            if text:
                headings.append(Heading(level=level, text=text))
        for a in tree.css("a[href]"):
            href = a.attributes.get("href") or ""
            anchor = (a.text() or "").strip()
            if href and anchor:
                links.append(Link(anchor=anchor, href=href))
    except Exception:  # noqa: S110
        # selectolax parse errors are non-fatal — extraction's primary output is content_md
        pass

    return ExtractResult(
        content_md=md,
        title=title,
        byline=byline,
        headings=headings,
        links=links,
        score=None,
    )


async def extract_markdown(html: str, url: str) -> ExtractResult:
    """Async-facing extraction — only public entry into this module."""
    return await asyncio.to_thread(_extract_sync, html, url)
