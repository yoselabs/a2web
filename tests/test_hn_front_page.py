"""HN front-page rendering — dual article + discussion URLs (ask-response-diet)."""

from __future__ import annotations

import json
from pathlib import Path

from a2web.handlers.hn import _front_page_candidates, _render_front_page

_FIX = Path(__file__).parent / "fixtures"
_PAYLOAD = json.loads((_FIX / "hn_front_page.json").read_text())


def test_external_story_renders_both_urls() -> None:
    """An external-link story's line carries both the article and discussion URL."""
    md = _render_front_page(_PAYLOAD)["content_md"]
    assert "[article](https://blog.example.com/flipper-one) · [discussion](https://news.ycombinator.com/item?id=101)" in md


def test_text_only_story_renders_discussion_url() -> None:
    """A text-only story (no `url`) carries the HN discussion URL, no article link."""
    md = _render_front_page(_PAYLOAD)["content_md"]
    ask_line = next(line for line in md.splitlines() if "item?id=103" in line)
    assert "[discussion](https://news.ycombinator.com/item?id=103)" in ask_line
    assert "[article]" not in ask_line


def test_next_links_one_entry_per_story() -> None:
    """`next_links` carries exactly one candidate per story — no discussion duplicate."""
    candidates = _front_page_candidates(_PAYLOAD)
    assert len(candidates) == 3
    urls = [c.url for c in candidates]
    # external stories → article URL; text-only → discussion URL
    assert "https://blog.example.com/flipper-one" in urls
    assert "https://blog.example.com/python-315" in urls
    assert "https://news.ycombinator.com/item?id=103" in urls
