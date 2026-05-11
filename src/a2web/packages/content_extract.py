"""HTML → markdown extraction + metadata parsing — in-tree microsofware.

Trafilatura wrapper (sync, blocking — exposed via an async chokepoint
that punts to `asyncio.to_thread`) + OG/Twitter/JSON-LD metadata
extractor. Zero a2web-domain imports.

Boundary types (`ExtractedHeading`, `ExtractedLink`, `ExtractedContent`)
are package-owned dataclasses. The a2web seam maps them to whatever
the response envelope uses.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import trafilatura
from selectolax.parser import HTMLParser

# --------------------------------------------------------------------- #
# Boundary types
# --------------------------------------------------------------------- #


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


# --------------------------------------------------------------------- #
# Trafilatura wrapper (sync, async-chokepointed)
# --------------------------------------------------------------------- #


def _parse_date(value: str | None) -> date | None:
    """Parse trafilatura's date field (YYYY-MM-DD or ISO timestamp) → date."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _extract_sync(html: str, url: str) -> ExtractedContent:
    """Blocking extraction — never call from async paths directly."""
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


# --------------------------------------------------------------------- #
# Metadata (OG / Twitter / JSON-LD)
# --------------------------------------------------------------------- #


def _flatten_jsonld(obj: Any, prefix: str, out: dict[str, str]) -> None:
    """Best-effort flatten of one JSON-LD object into dot-keyed strings.

    Only top-level scalar fields end up in `out`. Nested objects/arrays are
    skipped — agents and the renderer rarely need deep traversal.
    """
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        if isinstance(value, str | int | float | bool):
            out[f"{prefix}.{key}"] = str(value)


def parse_metadata(html: str) -> dict[str, str]:
    """Return a flat dot-keyed dict of OG, Twitter, and JSON-LD metadata.

    Missing fields are simply omitted from the dict (no `None` values).
    Only the first JSON-LD block is parsed (`jsonld[0].*`). Pure function.
    """
    out: dict[str, str] = {}
    tree = HTMLParser(html)

    for meta in tree.css("meta[property^='og:']"):
        prop = meta.attributes.get("property") or ""
        content = meta.attributes.get("content") or ""
        if prop and content:
            key = prop.replace(":", ".", 1)
            out[key] = content

    for meta in tree.css("meta[name^='twitter:']"):
        name = meta.attributes.get("name") or ""
        content = meta.attributes.get("content") or ""
        if name and content:
            key = name.replace(":", ".", 1)
            out[key] = content

    jsonld_nodes = tree.css("script[type='application/ld+json']")
    if jsonld_nodes:
        raw = (jsonld_nodes[0].text() or "").strip()
        if raw:
            try:
                obj = json.loads(raw)
                first = obj[0] if isinstance(obj, list) and obj else obj
                _flatten_jsonld(first, "jsonld[0]", out)
            except (ValueError, IndexError):
                pass

    return out


__all__ = (
    "ExtractedContent",
    "ExtractedHeading",
    "ExtractedLink",
    "extract_markdown",
    "parse_metadata",
)
