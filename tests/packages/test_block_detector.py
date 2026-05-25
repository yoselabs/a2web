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


# --------------------------------------------------------------------- #
# v0.22 — web-component SPA recognition (expand-js-shell-markers)
# --------------------------------------------------------------------- #


def test_reddit_js_challenge_marker_triggers_browser_escalation() -> None:
    """Reddit's hidden JS-challenge form (the real anti-bot interstitial
    Reddit serves to unauth raw clients) should route to browser escalation,
    not silent length_floor."""
    body = (
        "<html><body>"
        '<main><div class="logo">Snoo</div></main>'
        '<form hidden method="GET" action="/r/x/">'
        '<input type="hidden" name="solution" />'
        '<input type="hidden" name="js_challenge" value="1"/>'
        '<input type="hidden" name="jsc_orig_r" value=""/>'
        "</form>"
        '<script src="/static/challenge.js"></script>'
        "</body></html>"
    )
    result = _eval(body, content_md="")
    assert result.verdict == BlockVerdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_generic_custom_element_marker_triggers_browser_escalation() -> None:
    """Any HTML5 custom element (hyphenated tag) with thin content + script
    should route to browser — covers Lit, web-components-in-general, etc."""
    body = "<html><body><my-widget><lit-element></lit-element></my-widget><script>console.log('hydrating')</script></body></html>"
    result = _eval(body, content_md="tiny")
    assert result.verdict == BlockVerdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_hyphenated_attributes_alone_do_not_trigger() -> None:
    """Static HTML with `data-foo="x-y-z"` / `class="my-cmp"` but NO
    hyphenated tag names AND no challenge form must not be misclassified."""
    body = '<html><body><div data-foo="x-y-z" class="my-cmp">tiny</div><script>noop()</script></body></html>'
    result = _eval(body, content_md="tiny")
    # length_floor still fires (body IS thin), but no js_required signal —
    # so no `suggested_tier` and the planner does not escalate to browser.
    assert result.verdict == BlockVerdict.length_floor
    assert result.subsystem is None
    assert result.escalation is None


def test_above_length_floor_with_custom_elements_is_ok() -> None:
    """Progressive-enhancement case: a server-rendered page with substantial
    body that ALSO uses custom elements is NOT a JS shell — verdict ok."""
    body = (
        "<html><body>"
        "<my-comments>" + ("<p>Real rendered comment body content goes here. </p>" * 200) + "</my-comments>"
        '<script src="/x.js"></script>'
        "</body></html>"
    )
    md = "Real rendered comment body content goes here. " * 200
    result = _eval(body, content_md=md)
    assert result.verdict == BlockVerdict.ok
    assert result.escalation is None


def test_generic_solution_field_alone_does_not_trigger() -> None:
    """A thin page with `<input name="solution">` (legitimate quiz/exam shape)
    must NOT trigger js_required on its own. We deliberately scoped the
    Reddit markers tightly (`js_challenge` / `jsc_orig_r`) to avoid this
    false positive."""
    body = '<html><body><form><label>Answer:</label><input name="solution" /></form><script>noop()</script></body></html>'
    result = _eval(body, content_md="tiny")
    assert result.verdict == BlockVerdict.length_floor
    assert result.subsystem is None
    assert result.escalation is None


def test_reddit_shreddit_fixture_routes_to_browser() -> None:
    """End-to-end on the captured Reddit anti-bot fixture (the real ~8KB
    JS-challenge body Reddit serves to unauth raw curl_cffi clients)."""
    from tests.fixtures import FIXTURES_DIR

    body = (FIXTURES_DIR / "reddit_shreddit_shell.html").read_text(encoding="utf-8")
    # trafilatura would extract essentially nothing from this shell — feed it
    # an empty content_md to simulate that outcome.
    result = _eval(body, content_md="")
    assert result.verdict == BlockVerdict.length_floor
    assert result.subsystem == "js_required"
    assert result.escalation is not None and result.escalation.next_tier == "browser"
