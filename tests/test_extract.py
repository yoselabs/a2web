"""Extraction tests — trafilatura with bundled metadata + date."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

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
async def test_extract_returns_published_date() -> None:
    html = (_FIX / "blog.html").read_text()
    result = await extract_markdown(html, "https://example.org/post/x")
    assert result.published == datetime.date(2026, 4, 1)


@pytest.mark.asyncio
async def test_extract_no_date_yields_none() -> None:
    result = await extract_markdown("<html><body><p>no date</p></body></html>", "https://x/y")
    assert result.published is None
