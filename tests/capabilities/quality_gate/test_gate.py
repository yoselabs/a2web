"""Quality-gate domain wrapper (`fetcher.evaluate`): jina paywall stub
recognition and thin-browser-response on JS-heavy hosts.
"""

from __future__ import annotations

from a2web.fetcher import evaluate, js_heavy_hosts
from a2web.models import Verdict
from a2web.settings import AppSettings

# --------------------------------------------------------------------- #
# jina paywall stub recognition
# --------------------------------------------------------------------- #

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
    assert r.escalation is None  # archive playbook drives the next step


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


# --------------------------------------------------------------------- #
# thin-browser-response on JS-heavy hosts
# --------------------------------------------------------------------- #

# The X.com noscript stub we captured in the harsh-test session.
_X_NOSCRIPT_STUB = (
    "We've detected that JavaScript is disabled in this browser. "
    "Please enable JavaScript or switch to a supported browser to continue "
    "using x.com.\n\nHelp Center\n\nTerms of Service Privacy Policy "
)


def test_x_com_thin_browser_response_is_length_floor() -> None:
    r = evaluate(
        content_md=_X_NOSCRIPT_STUB,
        raw_html=f"<html><body>{_X_NOSCRIPT_STUB}</body></html>",
        content_type="text/html",
        tier="browser",
        host="x.com",
    )
    assert r.verdict == Verdict.length_floor
    assert r.subsystem == "thin_browser_response"


def test_thin_browser_response_from_unknown_host_not_downgraded() -> None:
    """Non-JS-heavy host: gate uses normal classifier path."""
    r = evaluate(
        content_md=_X_NOSCRIPT_STUB,
        raw_html=f"<html><body>{_X_NOSCRIPT_STUB}</body></html>",
        content_type="text/html",
        tier="browser",
        host="someblog.example.com",
    )
    # Will be length_floor by the normal classifier (body <1KB), but NOT for
    # the thin_browser_response reason — subsystem differs.
    assert r.subsystem != "thin_browser_response"


def test_fat_browser_response_from_js_heavy_host_passes() -> None:
    """Browser tier returns a real DOM (10KB) from x.com: rule doesn't fire."""
    body = "<html><body>" + "Lorem ipsum dolor sit amet. " * 200 + "</body></html>"
    md = "Lorem ipsum dolor sit amet. " * 200
    r = evaluate(
        content_md=md,
        raw_html=body,
        content_type="text/html",
        tier="browser",
        host="x.com",
    )
    assert r.verdict == Verdict.ok


def test_settings_override_extends_js_heavy_hosts() -> None:
    """Operator can add custom hosts via A2WEB_JS_HEAVY_HOSTS_EXTRA."""
    s = AppSettings(js_heavy_hosts_extra=["custom.example.com"])
    hosts = js_heavy_hosts(s)
    assert "x.com" in hosts  # seed retained
    assert "custom.example.com" in hosts  # extra merged

    r = evaluate(
        content_md=_X_NOSCRIPT_STUB,
        raw_html=_X_NOSCRIPT_STUB,
        content_type="text/html",
        tier="browser",
        host="custom.example.com",
        settings=s,
    )
    assert r.verdict == Verdict.length_floor
    assert r.subsystem == "thin_browser_response"


def test_non_browser_tier_not_subject_to_thin_browser_rule() -> None:
    """The rule keys off tier == 'browser' — raw thin from x.com (rare)
    would use normal classifier path, not this rule."""
    r = evaluate(
        content_md="x",
        raw_html="<html><body>x</body></html>",
        content_type="text/html",
        tier="raw",
        host="x.com",
    )
    assert r.subsystem != "thin_browser_response"
