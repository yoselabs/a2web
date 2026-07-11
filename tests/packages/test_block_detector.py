"""Block-detector unit tests — pattern catalogue + captcha second-line defense.

v0.7: search-engine captcha markers are the new addition. They serve as a
second-line defense behind `domain.rewrite_captcha_host` — any Google or
Bing captcha page that escapes the upfront URL rewrite gets flagged here
with `subsystem="captcha_redirect"` so the gate surfaces an actionable hint.
"""

from __future__ import annotations

from a2web.packages.block_detector import BlockVerdict, evaluate, looks_like_unrendered_spa


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
    """Short content without any block markers → length_floor, not block_page.
    Thin-but-present (above the blank visible-text threshold) so this stays a
    length_floor about block-pattern absence, not a near-empty blank_page."""
    body = "<html><body><p>A short paragraph of real text, thin but present.</p></body></html>"
    result = _eval(body, content_md="A short paragraph of real text, thin but present.")
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
    text = "A thin but present body with real visible words here."
    body = f'<html><body><div data-foo="x-y-z" class="my-cmp">{text}</div><script>noop()</script></body></html>'
    result = _eval(body, content_md=text)
    # length_floor still fires (body IS thin), but no js_required signal —
    # so no `suggested_tier` and the planner does not escalate to browser.
    # Thin-but-present (above the blank threshold) so this isolates the marker
    # false-positive check from blank-page detection.
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
    text = "Answer this short but real quiz question below:"
    body = f'<html><body><form><label>{text}</label><input name="solution" /></form><script>noop()</script></body></html>'
    result = _eval(body, content_md=text)
    assert result.verdict == BlockVerdict.length_floor
    assert result.subsystem is None
    assert result.escalation is None


# --------------------------------------------------------------------- #
# Alibaba Baxia "punish" anti-bot (block-detector-recognize-alibaba-baxia)
# --------------------------------------------------------------------- #


def test_aliexpress_baxia_punish_url_token_escalates_to_browser() -> None:
    """The AliExpress punish interstitial (raw curl_cffi lands on the punish
    page, which references its own `_____tmd_____` path + `x5secdata`) → the
    gate emits an anti_bot verdict with a browser escalation, instead of the
    prior silent bare length_floor."""
    body = (
        "<html><head><title>Captcha Interception</title></head><body>"
        '<script>window.x5secdata="...";location="//wholesale/_____tmd_____/punish?x5secdata=abc&x5step=1"</script>'
        "</body></html>"
    )
    result = _eval(body, content_md="")  # trafilatura extracts nothing
    assert result.verdict == BlockVerdict.anti_bot
    assert result.subsystem == "alibaba_punish"
    assert result.escalation is not None and result.escalation.next_tier == "browser"
    assert result.escalation.reason == "alibaba_punish"


def test_baxia_slide_phrase_recognized_regardless_of_length() -> None:
    """A short punish body carrying the AliExpress slide phrase is recognized
    on the marker alone (no `_____tmd_____` URL token, no length gate)."""
    body = "<html><body><p>Sorry, we have detected unusual traffic from your network. Please slide to verify.</p></body></html>"
    result = _eval(body, content_md="")
    assert result.verdict == BlockVerdict.anti_bot
    assert result.subsystem == "alibaba_punish"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_baxia_russian_locale_punish_recognized() -> None:
    """The aliexpress.ru variant: Russian heading + the `_____tmd_____` token
    (e.g. when the browser tier itself lands on the punish page)."""
    body = (
        "<html><head><title>Пройдите проверку</title></head><body>"
        '<div class="nc_iconfont"></div>'
        '<script src="//g.alicdn.com/sd/baxia/_____tmd_____/punish.js"></script>'
        "</body></html>"
    )
    result = _eval(body, content_md="")
    assert result.verdict == BlockVerdict.anti_bot
    assert result.subsystem == "alibaba_punish"
    assert result.escalation is not None and result.escalation.next_tier == "browser"


def test_prose_mentioning_captcha_is_not_a_false_positive() -> None:
    """A thin page that merely mentions the word `captcha` in prose, with none
    of the Baxia URL tokens / phrases / markers, stays plain length_floor —
    no alibaba_punish, no escalation."""
    body = (
        "<html><body><p>This short quiz uses a captcha to check that real "
        "people are answering. Slide the puzzle below to begin.</p></body></html>"
    )
    md = "This short quiz uses a captcha to check that real people are answering."
    result = _eval(body, content_md=md)
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


# --------------------------------------------------------------------- #
# looks_like_unrendered_spa — length-independent SPA-shell detection
# (obstacle-driven-render false-positive guard)
# --------------------------------------------------------------------- #


def test_spa_shell_with_root_and_script_is_detected() -> None:
    html = (
        '<html><head><script src="/app.js"></script></head><body><div id="root"></div>' + ("lots of chrome text " * 40) + "</body></html>"
    )
    assert looks_like_unrendered_spa(html)


def test_next_root_marker_detected() -> None:
    assert looks_like_unrendered_spa('<html><body><div id="__next"></div><script src="/a.js"></script></body></html>')


def test_plain_static_page_is_not_a_spa() -> None:
    # A complete document (RFC / book) with real prose and no root mount → not a shell.
    assert not looks_like_unrendered_spa("<html><body><article>A complete static document with real prose.</article></body></html>")


def test_root_marker_without_script_is_not_flagged() -> None:
    # A root mount alone (no scripts) is not evidence of client-side rendering.
    assert not looks_like_unrendered_spa('<html><body><div id="root">already has server-rendered content here</div></body></html>')


def test_script_without_root_marker_is_not_flagged() -> None:
    # Analytics/ad scripts on a static page must not read as an unrendered SPA.
    assert not looks_like_unrendered_spa('<html><body><article>Static prose.</article><script src="/analytics.js"></script></body></html>')


def test_noscript_plus_analytics_is_not_a_spa() -> None:
    # The RFC-editor false positive: a complete static doc with a <noscript>
    # block + an analytics <script> but NO framework mount must NOT be a shell.
    html = (
        '<html><head><script src="/ga.js"></script></head><body><noscript>Enable JS</noscript><pre>Full RFC text here.</pre></body></html>'
    )
    assert not looks_like_unrendered_spa(html)


def test_custom_element_without_mount_is_not_a_spa() -> None:
    # Web components on an otherwise-static page are not evidence of CSR.
    assert not looks_like_unrendered_spa("<html><body><my-widget>rendered</my-widget><script>x()</script></body></html>")
