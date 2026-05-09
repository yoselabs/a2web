"""Block-density pruning — Crawl4AI-style content filter, no crawl4ai dep.

Walks the DOM, scores each block element by text density and tag class,
drops below-threshold blocks, returns the trimmed HTML's markdown form
via trafilatura. Sync; the orchestrator wraps in `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio

import trafilatura
from selectolax.parser import HTMLParser, Node

# Tags whose content is almost always navigation/chrome, never article body.
_PENALIZED_TAGS = frozenset({"nav", "aside", "footer", "header", "script", "style", "form"})

# Block tags we score (any descendant of a penalized tag is dropped wholesale).
_BLOCK_TAGS = frozenset({"p", "div", "article", "section", "li", "blockquote", "pre"})


def _tag_class_score(node: Node) -> float:
    """Penalty multiplier based on tag and class hints."""
    if node.tag in _PENALIZED_TAGS:
        return 0.0
    cls = (node.attributes.get("class") or "").lower()
    if any(token in cls for token in ("nav", "menu", "sidebar", "footer", "ad", "promo", "share")):
        return 0.2
    if any(token in cls for token in ("article", "post", "content", "entry", "main")):
        return 1.5
    return 1.0


def _text_density(node: Node) -> float:
    """Text length normalized by descendant tag count. Higher = denser."""
    text = (node.text() or "").strip()
    if not text:
        return 0.0
    descendants = sum(1 for _ in node.iter())  # excludes the node itself
    if descendants == 0:
        return float(len(text))
    return len(text) / (1.0 + descendants)


def _score_block(node: Node) -> float:
    return _text_density(node) * _tag_class_score(node)


def _has_penalized_ancestor(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag in _PENALIZED_TAGS:
            return True
        parent = parent.parent
    return False


def prune_html(html: str, *, threshold: float = 0.5) -> str:
    """Score blocks, drop below-threshold, return remaining HTML.

    Threshold is a relative ratio against the median block score. Empty or
    unparseable input returns "" (caller handles fit_md fallback).
    """
    if not html:
        return ""
    try:
        tree = HTMLParser(html)
    except Exception:
        return ""

    body = tree.body or tree.root
    if body is None:
        return ""

    blocks: list[tuple[Node, float]] = []
    for node in body.iter():
        if node.tag not in _BLOCK_TAGS:
            continue
        if _has_penalized_ancestor(node):
            continue
        score = _score_block(node)
        if score > 0:
            blocks.append((node, score))

    if not blocks:
        return ""

    scores = sorted(score for _, score in blocks)
    median = scores[len(scores) // 2]
    cutoff = median * threshold

    kept_html_parts: list[str] = []
    for node, score in blocks:
        if score >= cutoff:
            html_chunk = node.html
            if html_chunk:
                kept_html_parts.append(html_chunk)

    if not kept_html_parts:
        return ""

    # Surviving blocks already carry their headings (when wrapped in
    # <article>/<section>). Re-emit them as a minimal article shell so
    # trafilatura sees a clean structure.
    pruned = f"<html><body><article>{''.join(kept_html_parts)}</article></body></html>"
    return pruned


def _to_markdown_sync(pruned_html: str, url: str) -> str:
    if not pruned_html:
        return ""
    md = trafilatura.extract(
        pruned_html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
    )
    return md or ""


async def prune_markdown(html: str, url: str, *, threshold: float = 0.5) -> str:
    """Async-facing pruning: HTML → pruned HTML → markdown. May return ""."""
    return await asyncio.to_thread(_prune_markdown_sync, html, url, threshold)


def _prune_markdown_sync(html: str, url: str, threshold: float) -> str:
    pruned_html = prune_html(html, threshold=threshold)
    return _to_markdown_sync(pruned_html, url)
