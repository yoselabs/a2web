"""Quality gate — closed-enum verdicts on extracted content + headers."""

from __future__ import annotations

from pathlib import Path

from a2web.gate.block_detector import evaluate
from a2web.models import Verdict

_FIX = Path(__file__).parent / "fixtures"


def test_ok_on_well_formed_blog() -> None:
    html = (_FIX / "blog.html").read_text()
    long_md = "Hello world. " * 200  # >500 chars
    result = evaluate(content_md=long_md, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.ok


def test_block_page_detected_on_cloudflare_fixture() -> None:
    html = (_FIX / "cloudflare_block.html").read_text()
    long_md = "Just a moment please " * 30
    result = evaluate(content_md=long_md, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.block_page_detected


def test_length_floor_on_short_extraction() -> None:
    result = evaluate(content_md="hi", raw_html="<html></html>", content_type="text/html")
    assert result.verdict == Verdict.length_floor


def test_content_type_mismatch_on_non_html() -> None:
    result = evaluate(content_md="ignored", raw_html="{}", content_type="application/json")
    assert result.verdict == Verdict.content_type_mismatch


def test_anubis_marker_with_short_content() -> None:
    html = "<html><script src='/.well-known/anubis/check.js'></script></html>"
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.anti_bot
    assert result.subsystem == "anubis"
    assert result.suggested_tier == "browser"


def test_turnstile_marker_suggests_browser() -> None:
    html = '<html><div class="cf-turnstile" data-sitekey="abc"></div></html>'
    result = evaluate(content_md="x" * 600, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.anti_bot
    assert result.subsystem == "turnstile"
    assert result.suggested_tier == "browser"


def test_akamai_bmp_marker_suggests_browser() -> None:
    html = "<html>Set-Cookie: _abck=ABC123; bm_sz=DEF</html>"
    result = evaluate(content_md="x" * 600, raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.anti_bot
    assert result.subsystem == "akamai_bmp"
    assert result.suggested_tier == "browser"


def test_cf_interstitial_suggests_tls_impersonate() -> None:
    html = "<html><title>Just a moment...</title><body>cf-chl-bypass</body></html>"
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.block_page_detected
    assert result.subsystem == "cf_iuam"
    assert result.suggested_tier == "tls_impersonate"


def test_noscript_shell_suggests_browser() -> None:
    html = (
        "<html><head>"
        "<script src='a.js'></script><script src='b.js'></script><script src='c.js'></script>"
        "</head><body><noscript>Please enable JavaScript to continue</noscript></body></html>"
    )
    result = evaluate(content_md="hi", raw_html=html, content_type="text/html")
    assert result.verdict == Verdict.length_floor
    assert result.subsystem == "js_required"
    assert result.suggested_tier == "browser"


def test_clean_article_has_no_suggested_tier() -> None:
    long_md = "Hello world. " * 200
    result = evaluate(content_md=long_md, raw_html="<html><body>article</body></html>", content_type="text/html")
    assert result.verdict == Verdict.ok
    assert result.suggested_tier is None
