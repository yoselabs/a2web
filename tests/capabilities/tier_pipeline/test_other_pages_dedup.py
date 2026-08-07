"""a2web-7bj.6: `other_pages` deduped by URL across its three producers.

`_compose_other_pages` merges handler continuation (`fr.next_links`), LLM
structural, and LLM drilldown pointers — three producers that do not know
about each other, so the same URL surfaced by two of them shipped twice, once
per kind. Observed on a DHL tracking page: `login.html` and the DHL commerce
host each appeared once as `structural` and again as `drilldown`, the
`structural` copy carrying the generic `reason="discussed page"`.
"""

from __future__ import annotations

import pytest

from a2web.fetcher_response import _compose_other_pages, _dedupe_other_pages
from a2web.models import FetchResponse, FetchStatus, NextLink, OtherPage, RouterPayload

pytestmark = pytest.mark.protects("spec:ask-response", "Requirement: other_pages is deduped by URL across its producers")


def _fr(next_links: list[NextLink] | None = None) -> FetchResponse:
    return FetchResponse(
        url="https://dhl.example/track",
        status=FetchStatus.ok,
        tier="raw",
        confidence="high",  # type: ignore[arg-type]
        next_links=next_links or [],
    )


def test_dedupe_prefers_specific_reason_over_generic() -> None:
    """A generic catalog-classifier reason loses to a page-specific one for the SAME URL."""
    generic = OtherPage(url="https://dhl.example/login.html", reason="discussed page", kind="structural")
    specific = OtherPage(url="https://dhl.example/login.html", reason="sign in to view your shipment", kind="drilldown")

    deduped = _dedupe_other_pages([generic, specific])

    assert len(deduped) == 1
    assert deduped[0].reason == "sign in to view your shipment"


def test_dedupe_breaks_reason_tie_on_kind_precedence() -> None:
    """Two equally-generic (or equally-specific) rows for one URL: structural wins."""
    drill_first = OtherPage(url="https://dhl.example/x", reason="discussed page", kind="drilldown")
    structural_second = OtherPage(url="https://dhl.example/x", reason="item page", kind="structural")

    deduped = _dedupe_other_pages([drill_first, structural_second])

    assert len(deduped) == 1
    assert deduped[0].kind == "structural"


def test_dedupe_preserves_first_seen_order_and_distinct_urls() -> None:
    a = OtherPage(url="https://dhl.example/a", reason="r", kind="drilldown")
    b = OtherPage(url="https://dhl.example/b", reason="r", kind="drilldown")
    a_dup = OtherPage(url="https://dhl.example/a", reason="better", kind="structural")

    deduped = _dedupe_other_pages([a, b, a_dup])

    assert [row.url for row in deduped] == ["https://dhl.example/a", "https://dhl.example/b"]
    assert deduped[0].reason == "better"


def test_compose_other_pages_dedupes_the_dhl_shape() -> None:
    """End-to-end through `_compose_other_pages`: the exact reported shape —
    login.html and a commerce host each named once by the handler
    (`fr.next_links`, folded to kind=drilldown) and once by the LLM router
    (kind=structural, generic reason) — collapses to one row per URL."""
    fr = _fr(
        next_links=[
            NextLink(anchor="login", url="https://dhl.example/login.html", reason="sign-in gate", kind="drilldown"),
            NextLink(anchor="commerce", url="https://dhlexpresscommerce.example/", reason="commerce portal", kind="related"),
        ]
    )
    routing = RouterPayload(
        answer="",
        other_pages=[
            OtherPage(url="https://dhl.example/login.html", reason="discussed page", kind="structural"),
            OtherPage(url="https://dhlexpresscommerce.example/", reason="discussed page", kind="structural"),
        ],
    )

    composed = _compose_other_pages(fr, routing)

    urls = [row.url for row in composed]
    assert urls.count("https://dhl.example/login.html") == 1
    assert urls.count("https://dhlexpresscommerce.example/") == 1
    # The handler's page-specific reasons survive over the LLM's generic "discussed page".
    by_url = {row.url: row for row in composed}
    assert by_url["https://dhl.example/login.html"].reason == "sign-in gate"
    assert by_url["https://dhlexpresscommerce.example/"].reason == "commerce portal"
