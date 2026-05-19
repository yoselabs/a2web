"""Quality-gate rule: jina paywall stub recognition.

Covers openspec/changes/harsh-test-session-fixes/specs/quality-gate/spec.md.
"""

from __future__ import annotations

from a2web.fetcher import evaluate
from a2web.models import Verdict

_NYT_JINA_STUB = (
    "Title: nytimes.com\n\n"
    "URL Source: https://www.nytimes.com/2026/03/15/technology/x.html\n\n"
    "Warning: Target URL returned error 403: Forbidden\n"
    "Warning: This page maybe requiring CAPTCHA, please make sure you are authorized to access this page.\n\n"
    "Markdown Content:\n# nytimes.com\n\n"
)
_WSJ_JINA_STUB_401 = (
    "Title: wsj.com\n\n"
    "URL Source: https://www.wsj.com/articles/x\n\n"
    "Warning: Target URL returned error 401: Unauthorized\n\n"
    "Markdown Content:\n# wsj.com\n\n"
)


def test_jina_403_stub_promoted_to_paywall() -> None:
    r = evaluate(
        content_md=_NYT_JINA_STUB,
        raw_html=_NYT_JINA_STUB,
        content_type="text/markdown",
        tier="jina",
    )
    assert r.verdict == Verdict.paywall
    assert r.subsystem == "jina_stub"
    assert r.suggested_tier is None  # archive playbook drives the next step


def test_jina_401_stub_promoted_to_paywall() -> None:
    r = evaluate(
        content_md=_WSJ_JINA_STUB_401,
        raw_html=_WSJ_JINA_STUB_401,
        content_type="text/markdown",
        tier="jina",
    )
    assert r.verdict == Verdict.paywall
    assert r.subsystem == "jina_stub"


def test_long_jina_response_with_quoted_error_text_not_misclassified() -> None:
    """A normal 10KB+ jina markdown that happens to mention 'error 403' in
    quoted text must not be promoted (length floor guards against this)."""
    body = (
        "Title: x\n\n"
        "Markdown Content:\n"
        + "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 200
        + "\nThe paper mentioned a `Target URL returned error 403` example.\n"
    )
    r = evaluate(content_md=body, raw_html=body, content_type="text/markdown", tier="jina")
    assert r.verdict != Verdict.paywall


def test_raw_tier_with_error_403_text_not_promoted() -> None:
    """The rule keys off `tier == 'jina'` — raw-tier output with the same
    substring (e.g., a forum post discussing 403s) must not be promoted."""
    body = "Some forum reply: 'Target URL returned error 403: Forbidden — what to do?'"
    r = evaluate(content_md=body, raw_html=body, content_type="text/html", tier="raw")
    assert r.verdict != Verdict.paywall


def test_jina_stub_without_error_pattern_not_promoted() -> None:
    """Short jina response without the warning marker stays length_floor."""
    body = "Title: x\n\nMarkdown Content:\n\n"
    r = evaluate(content_md=body, raw_html=body, content_type="text/markdown", tier="jina")
    assert r.verdict != Verdict.paywall
