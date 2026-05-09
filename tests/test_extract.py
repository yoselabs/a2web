"""Extraction tests — trafilatura + htmldate against the blog fixture."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from a2web.extract.htmldate_ext import find_published, find_updated
from a2web.extract.trafilatura_ext import extract_markdown

_FIX = Path(__file__).parent / "fixtures"


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
async def test_find_published_present() -> None:
    html = (_FIX / "blog.html").read_text()
    result = await find_published(html, "https://example.org/post/x")
    assert result == datetime.date(2026, 4, 1)


@pytest.mark.asyncio
async def test_find_published_absent() -> None:
    result = await find_published(
        "<html><body><p>no date</p></body></html>", "https://x/y"
    )
    assert result is None


@pytest.mark.asyncio
async def test_find_updated_returns_date_or_none() -> None:
    html = (_FIX / "blog.html").read_text()
    result = await find_updated(html, "https://example.org/post/x")
    assert result is None or isinstance(result, datetime.date)
