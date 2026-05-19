"""Quality-gate rule: thin-browser-response on JS-heavy hosts.

Covers openspec/changes/harsh-test-session-fixes/specs/quality-gate/spec.md.
"""

from __future__ import annotations

from a2web.fetcher import evaluate, js_heavy_hosts
from a2web.models import Verdict
from a2web.settings import AppSettings

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
        content_md="x", raw_html="<html><body>x</body></html>",
        content_type="text/html", tier="raw", host="x.com",
    )
    assert r.subsystem != "thin_browser_response"
