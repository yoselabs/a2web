"""The Google/Bing captcha policy is two halves, and nothing tested the pair.

One policy, split across a package boundary and linked by comment only:

- `domain.rewrite_captcha_host` — the UPFRONT half. A Google/Bing `/search` URL
  is pre-routed to DuckDuckGo's HTML endpoint before any tier runs, because
  those hosts serve a captcha to unauthenticated scrapers.
- `block_detector._SEARCH_CAPTCHA_MARKER` — the SECOND-LINE half. A redirect
  that escapes the pre-routing and lands on `/sorry/index` is detected in the
  body and reported as `subsystem="captcha_redirect"`.

`block_detector.py:214` says it is "second-line defense for captcha redirects
that escape the upfront `rewrite_captcha_host` pre-routing in `domain.py`". That
comment is the ONLY thing holding the two together — a package may not import
from the domain, so nothing structural can. Written now (2026-08-01) because the
renderer lift moved the surrounding code and the halves were listed as an
anti-seam: do not separate them.

The failure this guards is directional and quiet. Widen the pre-routing without
the markers and nothing breaks. NARROW it — drop a host, stop matching a path —
and the second line is all that remains: the fetch reaches a captcha page, and
whether the caller learns that depends on a regex in a different package that
nobody thought about. Both halves must be alive, and each must be checkable
without the other.
"""

from __future__ import annotations

import pytest

from a2web.domain import _CAPTCHA_SEARCH_HOSTS, rewrite_captcha_host
from a2web.packages.block_detector import BlockVerdict, evaluate

_SORRY_PAGE = (
    "<html><head><title>https://www.google.com/sorry/index</title></head>"
    "<body><h1>We're sorry...</h1><p>Our systems have detected unusual traffic "
    "from your computer network.</p></body></html>"
)


@pytest.mark.parametrize("host", sorted(_CAPTCHA_SEARCH_HOSTS))
def test_every_declared_captcha_host_is_pre_routed(host: str) -> None:
    """Half one, over the declared set rather than a sample.

    A host added to `_CAPTCHA_SEARCH_HOSTS` without the rewrite working is the
    quiet failure: the constant reads as coverage and the fetch still walks into
    the captcha.
    """
    rewritten = rewrite_captcha_host(f"https://{host}/search?q=laptop+deals")
    assert rewritten is not None, f"{host} is declared a captcha host but was not pre-routed"
    assert rewritten.startswith("https://duckduckgo.com/html/?q=")
    assert "laptop" in rewritten


def test_a_non_search_path_on_the_same_host_is_untouched() -> None:
    """Anti-vacuity: the pre-routing must be a rewrite, not a blanket redirect.

    Google Maps, Drive and Images are on these hosts and are not search pages;
    rewriting them all to DuckDuckGo would be a silent wrong answer rather than
    a captcha.
    """
    assert rewrite_captcha_host("https://www.google.com/maps/place/Istanbul") is None
    assert rewrite_captcha_host("https://www.bing.com/images/search") is None


def test_a_search_url_with_no_query_is_untouched() -> None:
    """There is nothing to carry over, so there is nothing to route to."""
    assert rewrite_captcha_host("https://www.google.com/search") is None


def test_the_second_line_catches_what_the_pre_routing_missed() -> None:
    """Half two, standing alone.

    An inbound redirect a2web does not recognise lands on `/sorry/index` with a
    200 and a page full of prose. Without this the caller gets a plausible
    "no results" body — the empty-vs-wall confusion the product forbids.
    """
    result = evaluate(content_md="We're sorry... " * 40, raw_html=_SORRY_PAGE, content_type="text/html")

    assert result.verdict is BlockVerdict.block_page_detected
    assert result.subsystem == "captcha_redirect"


def test_the_second_line_does_not_fire_on_an_ordinary_page() -> None:
    """Anti-vacuity: a detector that always fires reports nothing."""
    ordinary = "<html><body><h1>Laptop deals</h1><p>" + ("Real content about laptops. " * 40) + "</p></body></html>"
    result = evaluate(content_md="Laptop deals. " * 40, raw_html=ordinary, content_type="text/html")
    assert result.verdict is not BlockVerdict.block_page_detected


def test_both_halves_are_reachable_for_the_same_host() -> None:
    """The pair, asserted as a pair — the point of this file.

    Each half above is independently checkable. This one states the relationship
    the comment claims: the same host is pre-routed AND, when a redirect escapes
    that, recognised in the body. Deleting either half leaves this red.
    """
    assert rewrite_captcha_host("https://www.google.com/search?q=x") is not None

    escaped = evaluate(content_md="We're sorry... " * 40, raw_html=_SORRY_PAGE, content_type="text/html")
    assert escaped.subsystem == "captcha_redirect"
