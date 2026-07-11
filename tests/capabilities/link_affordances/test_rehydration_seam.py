"""Domain seam: `{{n}}` handles in `other_pages` rehydrate against the closed digest.

Proves the wiring between the parsed router payload (handles) and the digest
(closed set): known handles become real hrefs + off_domain; unknown handles are
dropped, never guessed; legacy url-bearing entries pass through.
"""

from __future__ import annotations

from a2web.fetcher import _rehydrate_routing_handles
from a2web.link_digest import build_digest
from a2web.models import Link
from a2web.packages.llm_extract import OtherPageBoundary, RouterPayload

PAGE = "https://shop.example.com/p/widget"


def _digest() -> object:
    return build_digest(
        [
            Link(anchor="reviews", href="/p/widget-yorumlari"),
            Link(anchor="partner", href="https://other.example.org/x"),
        ],
        page_url=PAGE,
    )


def _payload(*entries: OtherPageBoundary) -> RouterPayload:
    return RouterPayload(answer="a", structural_form="product", shape="key-value", other_pages=tuple(entries))


def test_known_handle_rehydrates_with_off_domain() -> None:
    digest = _digest()  # handle 1 = same-domain reviews, handle 2 = off-domain
    routing = _payload(
        OtherPageBoundary(url="", reason="reviews here", handle=1),
        OtherPageBoundary(url="", reason="partner", handle=2),
    )
    out = _rehydrate_routing_handles(routing, digest)
    assert out is not None
    assert out.other_pages[0].url == "https://shop.example.com/p/widget-yorumlari"
    assert out.other_pages[0].off_domain is False
    assert out.other_pages[0].handle is None
    assert out.other_pages[1].url == "https://other.example.org/x"
    assert out.other_pages[1].off_domain is True


def test_unknown_handle_dropped() -> None:
    digest = _digest()
    routing = _payload(OtherPageBoundary(url="", reason="nope", handle=99))
    out = _rehydrate_routing_handles(routing, digest)
    assert out is not None
    assert out.other_pages == ()


def test_legacy_url_entry_passes_through() -> None:
    digest = _digest()
    routing = _payload(OtherPageBoundary(url="https://x.example/", reason="legacy"))
    out = _rehydrate_routing_handles(routing, digest)
    assert out is not None
    assert len(out.other_pages) == 1
    assert out.other_pages[0].url == "https://x.example/"


def test_handle_with_no_digest_is_dropped() -> None:
    routing = _payload(OtherPageBoundary(url="", reason="orphan", handle=1))
    out = _rehydrate_routing_handles(routing, None)
    assert out is not None
    assert out.other_pages == ()


def test_none_routing_passes_through() -> None:
    assert _rehydrate_routing_handles(None, _digest()) is None
