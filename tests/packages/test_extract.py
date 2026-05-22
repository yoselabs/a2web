"""Extraction tests — trafilatura with bundled metadata + date."""

from __future__ import annotations

import datetime

import pytest

from a2web.packages.content_extract import extract_markdown
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


@pytest.mark.asyncio
async def test_extract_blog_markdown() -> None:
    html = (_FIX / "blog.html").read_text()
    result = await extract_markdown(html, "https://example.org/post/x")
    assert result.title is not None
    assert "adaptive" in result.title.lower()
    assert len(result.content_md) > 500
    assert any("Why one fetch" in h.text for h in result.headings)
    assert any("github.com/example/a2web" in link.href for link in result.links)


@pytest.mark.asyncio
async def test_extract_returns_published_date() -> None:
    html = (_FIX / "blog.html").read_text()
    result = await extract_markdown(html, "https://example.org/post/x")
    assert result.published == datetime.date(2026, 4, 1)


@pytest.mark.asyncio
async def test_extract_no_date_yields_none() -> None:
    result = await extract_markdown("<html><body><p>no date</p></body></html>", "https://x/y")
    assert result.published is None


# --------------------------------------------------------------------- #
# Link role classification
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_link_in_nav_classified_nav() -> None:
    html = """<html><body>
        <nav><a href="https://x/home">Home</a></nav>
    </body></html>"""
    result = await extract_markdown(html, "https://x/")
    assert len(result.links) == 1
    assert result.links[0].role == "nav"


@pytest.mark.asyncio
async def test_link_in_footer_classified_footer() -> None:
    html = """<html><body>
        <footer><a href="https://x/about">About</a></footer>
    </body></html>"""
    result = await extract_markdown(html, "https://x/")
    assert result.links[0].role == "footer"


@pytest.mark.asyncio
async def test_link_in_article_classified_primary() -> None:
    html = """<html><body>
        <article><p>Read <a href="https://x/more">more here</a>.</p></article>
    </body></html>"""
    result = await extract_markdown(html, "https://x/")
    assert result.links[0].role == "primary"


@pytest.mark.asyncio
async def test_link_in_header_classified_meta() -> None:
    html = """<html><body>
        <header><a href="https://x/branding">Brand</a></header>
    </body></html>"""
    result = await extract_markdown(html, "https://x/")
    assert result.links[0].role == "meta"


@pytest.mark.asyncio
async def test_link_with_role_navigation_attr_classified_nav() -> None:
    """ARIA role='navigation' on a <div> should classify nav, not just <nav>."""
    html = """<html><body>
        <div role="navigation"><a href="https://x/menu">Menu</a></div>
    </body></html>"""
    result = await extract_markdown(html, "https://x/")
    assert result.links[0].role == "nav"


@pytest.mark.asyncio
async def test_link_unclassified_defaults_primary() -> None:
    """Bare anchor with no semantic ancestor falls back to 'primary'."""
    html = """<html><body>
        <div><a href="https://x/y">Anchor</a></div>
    </body></html>"""
    result = await extract_markdown(html, "https://x/")
    assert result.links[0].role == "primary"


@pytest.mark.asyncio
async def test_link_nested_inner_role_wins() -> None:
    """Closest ancestor wins — anchor in <nav> inside <article> is nav."""
    html = """<html><body>
        <article><nav><a href="https://x/inner">Inner</a></nav></article>
    </body></html>"""
    result = await extract_markdown(html, "https://x/")
    assert result.links[0].role == "nav"
