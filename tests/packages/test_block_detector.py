"""Block-detector unit tests — pattern catalogue + captcha second-line defense.

v0.7: search-engine captcha markers are the new addition. They serve as a
second-line defense behind `domain.rewrite_captcha_host` — any Google or
Bing captcha page that escapes the upfront URL rewrite gets flagged here
with `subsystem="captcha_redirect"` so the gate surfaces an actionable hint.
"""

from __future__ import annotations

from a2web.packages.block_detector import BlockVerdict, evaluate


def _eval(raw_html: str, content_md: str = "", content_type: str = "text/html"):
    return evaluate(content_md=content_md, raw_html=raw_html, content_type=content_type)


# --------------------------------------------------------------------- #
# v0.7 search-engine captcha second-line defense
# --------------------------------------------------------------------- #


def test_google_sorry_body_marker_flags_captcha_redirect() -> None:
    """Google's `/sorry/index` page body markers flag as captcha_redirect."""
    body = """
    <html><body>
    <h1>About this page</h1>
    <p>Our systems have detected unusual traffic from your computer network.
    This page checks to see if it's really you sending the requests, and not
    a robot.</p>
    </body></html>
    """
    result = _eval(body)
    assert result.verdict == BlockVerdict.block_page_detected
    assert result.subsystem == "captcha_redirect"


def test_google_sorry_path_in_html_flags_captcha_redirect() -> None:
    """A leaked `/sorry/index` reference in the body (e.g. inline JS redirect)."""
    body = '<html><body><script>location="/sorry/index?continue=..."</script></body></html>'
    result = _eval(body)
    assert result.verdict == BlockVerdict.block_page_detected
    assert result.subsystem == "captcha_redirect"


def test_google_sorry_heading_flags_captcha_redirect() -> None:
    """The 'We're sorry...' heading variant."""
    body = "<html><body><h1>We're sorry...</h1><p>but your request looks unusual.</p></body></html>"
    result = _eval(body)
    assert result.verdict == BlockVerdict.block_page_detected
    assert result.subsystem == "captcha_redirect"


def test_bing_captcha_intermediate_flags_captcha_redirect() -> None:
    """Bing's `/Block/CaptchaChallenge` intermediate response."""
    body = '<html><body><a href="/Bing/Block/CaptchaChallenge?id=...">verify</a></body></html>'
    result = _eval(body)
    assert result.verdict == BlockVerdict.block_page_detected
    assert result.subsystem == "captcha_redirect"


def test_normal_long_article_does_not_trigger_captcha_marker() -> None:
    """Long article body without the markers passes cleanly."""
    body = "<html><body>" + ("<p>Real article content goes here. </p>" * 200) + "</body></html>"
    md = "Real article content goes here. " * 200
    result = _eval(body, content_md=md)
    assert result.verdict == BlockVerdict.ok


# --------------------------------------------------------------------- #
# Pre-existing pattern catalogue still works
# --------------------------------------------------------------------- #


def test_cloudflare_just_a_moment_still_detected() -> None:
    body = "<html><body><h1>Just a moment...</h1></body></html>"
    result = _eval(body)
    assert result.verdict == BlockVerdict.block_page_detected
    assert result.subsystem == "cf_iuam"


def test_length_floor_without_block_markers() -> None:
    """Short content without any block markers → length_floor, not block_page."""
    body = "<html><body><p>tiny</p></body></html>"
    result = _eval(body, content_md="tiny")
    assert result.verdict == BlockVerdict.length_floor
    assert result.subsystem is None
