"""Recall-based escalation trigger — `trafilatura_under_extracted`.

The trigger escalates when trafilatura under-extracted relative to the
substantive content present in the raw HTML, NOT on absolute output length.
"""

from __future__ import annotations

from a2web.domain import trafilatura_under_extracted

_ARTICLE = "This is a complete short article sentence with real prose content. " * 12

# A clean page: the article IS almost all the visible text.
_ARTICLE_HTML = (
    "<html><body><nav>Home About Contact</nav>"
    f"<article>{_ARTICLE}</article>"
    "<footer>Privacy Terms</footer></body></html>"
)

# A gutted-listing page: 25 substantive records, lots of visible text.
_RECORDS = "".join(
    f"<article>Record number {i} with a fairly long description of what this "
    f"item is about and why a reader would care about it today</article>"
    for i in range(25)
)
_LISTING_HTML = f"<html><body><nav>Home</nav>{_RECORDS}</body></html>"


def test_complete_short_article_does_not_escalate() -> None:
    """trafilatura kept ~all the visible text — high recall, no escalation."""
    assert trafilatura_under_extracted(_ARTICLE, _ARTICLE_HTML) is False


def test_gutted_listing_escalates() -> None:
    """Short content_md but a large discarded record region — escalate."""
    gutted = "Record number 0 description. Record number 1 description. " * 7  # ~400 chars
    assert len(gutted) > 200  # above the near-empty floor — tests the recall path
    assert trafilatura_under_extracted(gutted, _LISTING_HTML) is True


def test_near_empty_escalates_regardless_of_recall() -> None:
    """Near-empty output escalates even when the raw HTML is also tiny
    (the JS-shell case — recall alone would falsely pass it)."""
    assert trafilatura_under_extracted("", "<html><body>x</body></html>") is True
    assert trafilatura_under_extracted("short text " * 8, "<html><body>x</body></html>") is True


def test_no_raw_html_trusts_content_md() -> None:
    """No raw HTML to compare against (pre-rendered path) — trust content_md."""
    assert trafilatura_under_extracted("x" * 500, "") is False
