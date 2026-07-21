"""Quality-gate domain wrapper (`fetcher.evaluate`): thin-browser-response on
JS-heavy hosts.

Reader-wrapper (jina stub) decoding is NO LONGER a gate concern — it moved to
the jina tier (see `tests/capabilities/tier_pipeline/test_jina_tier.py`). The
gate no longer branches on `tier == "jina"`.
"""

from __future__ import annotations

from a2web.fetcher import evaluate, js_heavy_hosts
from a2web.models import Verdict
from a2web.settings import AppSettings

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


# --------------------------------------------------------------------- #
# structured-answer small-but-complete exemption (structured-data-answers)
# --------------------------------------------------------------------- #

# A thin static contact page: below LENGTH_FLOOR, no SPA/anti-bot markers.
_THIN_CONTACT_HTML = (
    "<html><head><title>Contact</title>"
    '<script type="application/ld+json">'
    '{"@type":"LocalBusiness","name":"VEITO","telephone":"444 3 061","email":"destek@veito.com"}'
    "</script></head><body><p>Contact us.</p></body></html>"
)

# A JS-required SPA shell: below the floor, <script> + a React root marker.
_SPA_SHELL_HTML = '<html><body><div id="__next"></div><script>1</script></body></html>'


def test_blank_page_escalates_to_browser() -> None:
    """An essentially-empty raw body (near-zero visible text, no marker, no
    JSON-LD) → blank_page with a browser escalation signal."""
    r = evaluate(content_md="", raw_html="<html><head></head><body></body></html>", content_type="text/html")
    assert r.verdict == Verdict.blank_page
    assert r.escalation is not None and r.escalation.next_tier == "browser" and r.escalation.reason == "blank_page"


def test_short_but_present_stub_is_not_blank() -> None:
    """A short body carrying a real visible sentence stays length_floor, not blank."""
    stub = "<html><body><p>JavaScript is disabled in this browser. Enable it to continue.</p></body></html>"
    r = evaluate(content_md="JavaScript is disabled in this browser. Enable it to continue.", raw_html=stub, content_type="text/html")
    assert r.verdict == Verdict.length_floor
    assert r.verdict != Verdict.blank_page


def test_json_ld_card_is_not_blank() -> None:
    """A near-empty-visible-text page carrying JSON-LD structured data is NOT
    blank (its answer lives in the markup) → length_floor, not blank_page."""
    r = evaluate(content_md="Contact us.", raw_html=_THIN_CONTACT_HTML, content_type="text/html")
    assert r.verdict == Verdict.length_floor
    assert r.verdict != Verdict.blank_page


def test_blank_page_with_structured_answer_promotes_to_ok() -> None:
    """A JSON-LD page (never blank) with an answer-bearing candidate still
    rides the existing structured-answer exemption to ok — blank detection
    does not preempt it."""
    r = evaluate(content_md="Contact us.", raw_html=_THIN_CONTACT_HTML, content_type="text/html", tier="raw", structured_answer=True)
    assert r.verdict == Verdict.ok


def test_bare_length_floor_promoted_with_structured_answer() -> None:
    """A thin page carrying an answer-bearing structured candidate is
    small-but-complete → promoted to ok (mirrors the is_json exemption)."""
    r = evaluate(
        content_md="Contact us.",  # < LENGTH_FLOOR, no markers → bare length_floor
        raw_html=_THIN_CONTACT_HTML,
        content_type="text/html",
        tier="raw",
        structured_answer=True,
    )
    assert r.verdict == Verdict.ok
    assert r.subsystem is None


def test_bare_length_floor_stays_failed_without_structured_answer() -> None:
    """No answer-bearing candidate (weak-only payload) → behavior unchanged."""
    r = evaluate(
        content_md="Contact us.",
        raw_html=_THIN_CONTACT_HTML,
        content_type="text/html",
        tier="raw",
        structured_answer=False,
    )
    assert r.verdict == Verdict.length_floor
    assert r.subsystem == "thin_fallthrough"  # bare no-evidence fallthrough, positively marked


def test_js_required_shell_not_masked_by_structured_answer() -> None:
    """A genuine SPA shell keeps its js_required subsystem + browser escalation
    even when structured_answer is set — no wall is masked."""
    r = evaluate(
        content_md="",  # thin
        raw_html=_SPA_SHELL_HTML,
        content_type="text/html",
        tier="raw",
        structured_answer=True,
    )
    assert r.verdict == Verdict.length_floor
    assert r.subsystem == "js_required"
    assert r.escalation is not None and r.escalation.next_tier == "browser"


# --------------------------------------------------------------------- #
# akamai_bmp/turnstile exemption for above-floor answer-bearing content
# (answer-bearing-gate-exemption, 2026-07-09 Koçtaş re-probe)
# --------------------------------------------------------------------- #

# Above-LENGTH_FLOOR content with an Akamai Bot Manager Premium cookie marker —
# the shape a2web hit live on koctas.com.tr: a real, complete page, not a
# challenge shell.
_AKAMAI_BMP_HTML = "<html>Set-Cookie: _abck=ABC123; bm_sz=DEF</html>"
_TURNSTILE_HTML = '<html><div class="cf-turnstile" data-sitekey="abc"></div></html>'
_ABOVE_FLOOR_MD = "Real page content. " * 30  # > LENGTH_FLOOR (500)


def test_akamai_bmp_above_floor_promoted_with_structured_answer() -> None:
    r = evaluate(
        content_md=_ABOVE_FLOOR_MD,
        raw_html=_AKAMAI_BMP_HTML,
        content_type="text/html",
        tier="raw",
        structured_answer=True,
    )
    assert r.verdict == Verdict.ok
    assert r.subsystem is None
    assert r.escalation is None


def test_turnstile_above_floor_promoted_with_structured_answer() -> None:
    r = evaluate(
        content_md=_ABOVE_FLOOR_MD,
        raw_html=_TURNSTILE_HTML,
        content_type="text/html",
        tier="raw",
        structured_answer=True,
    )
    assert r.verdict == Verdict.ok
    assert r.subsystem is None
    assert r.escalation is None


def test_akamai_bmp_above_floor_without_structured_answer_still_escalates() -> None:
    """No answer-bearing candidate → unchanged from today: forced escalation."""
    r = evaluate(
        content_md=_ABOVE_FLOOR_MD,
        raw_html=_AKAMAI_BMP_HTML,
        content_type="text/html",
        tier="raw",
        structured_answer=False,
    )
    assert r.verdict == Verdict.anti_bot
    assert r.subsystem == "akamai_bmp"
    assert r.escalation is not None and r.escalation.next_tier == "browser"


def test_akamai_bmp_below_floor_with_structured_answer_still_escalates() -> None:
    """The exemption is scoped to above-floor content — a thin akamai_bmp
    response with a (possibly stub) structured candidate keeps escalating,
    orthogonal to the separate bare-length_floor promotion (which never
    touches an akamai_bmp/turnstile-classified verdict)."""
    r = evaluate(
        content_md="hi",  # below LENGTH_FLOOR
        raw_html=_AKAMAI_BMP_HTML,
        content_type="text/html",
        tier="raw",
        structured_answer=True,
    )
    assert r.verdict == Verdict.anti_bot
    assert r.subsystem == "akamai_bmp"
    assert r.escalation is not None and r.escalation.next_tier == "browser"
