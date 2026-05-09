"""Pruning filter tests — block-density scoring against fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.extract.pruning_filter import prune_html, prune_markdown

_FIX = Path(__file__).parent / "fixtures"


def test_prune_html_removes_navigation_blocks() -> None:
    html = """
    <html><body>
    <nav><a href="/">Home</a> <a href="/about">About</a></nav>
    <article>
    <h1>Article Title</h1>
    <p>This is a substantial paragraph with enough text to score above the
    density threshold and survive pruning. It carries the actual signal of the
    document.</p>
    <p>Another well-formed paragraph with real content. The pruning filter
    should preserve both of these blocks while dropping navigation and
    footer chrome around them.</p>
    </article>
    <footer><p>Tiny footer</p></footer>
    </body></html>
    """
    pruned = prune_html(html)
    assert pruned  # non-empty
    assert "Home" not in pruned and "About" not in pruned
    assert "Article Title" in pruned
    assert "substantial paragraph" in pruned


def test_prune_html_empty_input_returns_empty() -> None:
    assert prune_html("") == ""


def test_prune_html_unparseable_returns_empty() -> None:
    # selectolax is permissive; truly unparseable inputs are rare. Use
    # empty/whitespace to confirm the empty-body fallback path.
    assert prune_html("   ") == ""


@pytest.mark.asyncio
async def test_prune_markdown_against_blog_fixture() -> None:
    html = (_FIX / "blog.html").read_text()
    md = await prune_markdown(html, "https://example.org/post")
    assert md
    assert len(md) > 100  # non-trivially small
    # Should keep at least one of the article's signal phrases
    assert "fetch" in md.lower() or "agent" in md.lower()
