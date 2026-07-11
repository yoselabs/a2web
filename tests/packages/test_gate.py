"""Quality gate — closed-enum verdicts on extracted content + headers."""

from __future__ import annotations

from a2web.models import Verdict
from a2web.packages.block_detector import evaluate
from tests.fixtures import FIXTURES_DIR

_FIX = FIXTURES_DIR


def test_ok_on_well_formed_blog() -> None:
    html = (_FIX / "blog.html").read_text()
    long_md = "Hello world. " * 200  # >500 chars
    result = evaluate(content_md=long_md, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.ok


def test_block_page_detected_on_cloudflare_fixture() -> None:
    """v0.3: real CF block pages render no body — content_md stays tiny.
    The fixture is a "Just a moment..." interstitial; trafilatura extracts
    essentially nothing from it, which is the correct signal to flag.
    """
    html = (_FIX / "cloudflare_block.html").read_text()
    thin_md = "Just a moment"  # what trafilatura actually extracts from a CF challenge
    result = evaluate(content_md=thin_md, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.block_page_detected


def test_empty_page_is_blank_not_length_floor() -> None:
    # A genuinely empty document (`<html></html>`, near-zero visible text) is now
    # a blank_page that escalates — NOT a bare length_floor (escalate-on-thin-page-walls).
    result = evaluate(content_md="hi", raw_html="<html></html>", content_type="text/html")
    assert result.verdict == Verdict.blank_page


def test_thin_but_present_page_stays_length_floor() -> None:
    # Above the blank visible-text threshold but below the extraction floor → the
    # thin-but-present page stays a plain length_floor with no escalation.
    text = "This stub has a little real visible text but is under the floor."
    html = f"<html><body><p>{text}</p></body></html>"
    result = evaluate(content_md=text, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor


def test_content_type_mismatch_on_non_html() -> None:
    result = evaluate(content_md="ignored", raw_html="{}", content_type="application/json")
    assert result.verdict == Verdict.content_type_mismatch


def test_anubis_marker_with_short_content() -> None:
    html = "<html><script src='/.well-known/anubis/check.js'></script></html>"
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.anti_bot
    assert result.subsystem == "anubis"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_turnstile_marker_suggests_browser() -> None:
    html = '<html><div class="cf-turnstile" data-sitekey="abc"></div></html>'
    result = evaluate(content_md="x" * 600, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.anti_bot
    assert result.subsystem == "turnstile"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_akamai_bmp_marker_suggests_browser() -> None:
    html = "<html>Set-Cookie: _abck=ABC123; bm_sz=DEF</html>"
    result = evaluate(content_md="x" * 600, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.anti_bot
    assert result.subsystem == "akamai_bmp"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_cf_interstitial_suggests_tls_impersonate() -> None:
    """A real CF interstitial: matching marker + thin extracted body."""
    html = "<html><title>Just a moment...</title><body>cf-chl-bypass</body></html>"
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.block_page_detected
    assert result.subsystem == "cf_iuam"
    assert result.escalation is not None and result.escalation.next_tier == "tls_impersonate"


def test_cf_marker_with_substantive_content_is_NOT_a_block() -> None:
    """v0.3 Linear FP fix: cf-chl-bypass / 'Just a moment' strings embedded
    in marketing or compliance copy don't make the page a block when the
    extractor pulled out real content. Same length-gated rule Anubis uses.
    """
    html = (
        "<html><body>"
        + "<p>Welcome to our security page. We use cf-chl-bypass cookies.</p>"
        + ("Real content paragraph. " * 100)
        + "</body></html>"
    )
    # >= 500 chars of substantive extracted content
    long_md = "We use cf-chl-bypass cookies. " + ("Real content paragraph. " * 100)
    assert len(long_md) >= 500
    result = evaluate(content_md=long_md, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.ok
    assert result.subsystem is None
    assert result.escalation is None


def test_noscript_shell_suggests_browser() -> None:
    html = (
        "<html><head>"
        "<script src='a.js'></script><script src='b.js'></script><script src='c.js'></script>"
        "</head><body><noscript>Please enable JavaScript to continue</noscript></body></html>"
    )
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_clean_article_has_no_suggested_tier() -> None:
    long_md = "Hello world. " * 200
    result = evaluate(content_md=long_md, raw_html="<html><body>article</body></html>", content_type="text/html")
    assert result.verdict == Verdict.ok
    assert result.escalation is None


# --------------------------------------------------------------------- #
# v0.3 broader JS-shell escalation — Next.js / React / Vue / Twitter
# --------------------------------------------------------------------- #


def test_next_js_shell_suggests_browser() -> None:
    """Thin extraction + Next.js __next root + script tag → escalate to browser."""
    html = '<html><head><script src="/_next/static/x.js"></script></head><body><div id="__next"></div></body></html>'
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_react_root_shell_suggests_browser() -> None:
    """CRA / Vite root + script + thin content."""
    html = '<html><body><div id="root"></div><script src="bundle.js"></script></body></html>'
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_twitter_react_root_suggests_browser() -> None:
    """X / Twitter SPA root marker."""
    html = '<html><body><div id="react-root"></div><script>__INITIAL_STATE__={};</script></body></html>'
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_vue_app_root_suggests_browser() -> None:
    """Vue / generic SPA root marker."""
    html = '<html><body><div id="app"></div><script src="vue.js"></script></body></html>'
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_substantive_spa_page_is_NOT_escalated() -> None:
    """Pages with framework roots BUT enough server-rendered content stay ok."""
    long_md = "Real SSR content. " * 100
    html = '<html><body><div id="__next">' + ("<p>article body</p>" * 100) + '</div><script src="hydrate.js"></script></body></html>'
    result = evaluate(content_md=long_md, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.ok
    assert result.escalation is None


def test_truly_empty_page_escalates_as_blank() -> None:
    """A truly empty page (near-zero visible text, no markers) now escalates as a
    blank_page (escalate-on-thin-page-walls) — the prior 'don't waste a browser on
    empty pages' stance is reversed: a blank body is a silent-block signal."""
    html = "<html><body><p>tiny</p></body></html>"
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.blank_page
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_thin_with_noscript_alone_suggests_browser() -> None:
    """Any <noscript> tag + thin content + a script tag → browser escalation."""
    html = "<html><script>x</script><noscript>fallback</noscript></html>"
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"
