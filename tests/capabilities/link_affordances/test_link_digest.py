"""Link digest: safe cuts, dedup, encoding, and collision-proof rehydration.

Offline, in `make check`. The sentinel-collision cases (design D2) are the
load-bearing ones: they prove `{{n}}` rehydration never corrupts identifier-like
substrings inside product names / SKUs the way bare `L1` handles did.
"""

from __future__ import annotations

from a2web.link_digest import build_digest
from a2web.models import Link

PAGE = "https://shop.example.com/p/widget-123"


def _links(*pairs: tuple[str, str]) -> list[Link]:
    return [Link(anchor=a, href=h) for a, h in pairs]


# --------------------------------------------------------------------- #
# Assembly: safe cuts, dedup, handles
# --------------------------------------------------------------------- #


def test_chrome_reviews_link_surfaces() -> None:
    """The originating case: a footer/tab reviews anchor reaches the digest."""
    digest = build_digest(
        _links(("Değerlendirmeler", "/p/widget-123-yorumlari")),
        page_url=PAGE,
    )
    assert len(digest.entries) == 1
    entry = digest.entries[0]
    assert entry.handle == 1
    assert entry.href == "https://shop.example.com/p/widget-123-yorumlari"
    assert not entry.off_domain
    assert "{{1}}" in digest.render()


def test_safe_cuts_drop_self_fragment_and_javascript() -> None:
    digest = build_digest(
        _links(
            ("self", PAGE),  # self-link
            ("self slash", PAGE + "/"),  # self, trailing slash
            ("jump", "#reviews"),  # fragment-only
            ("frag of self", PAGE + "#specs"),  # self + fragment
            ("js", "javascript:void(0)"),  # unfetchable
            ("empty", ""),  # empty
            ("real", "/p/other"),  # kept
        ),
        page_url=PAGE,
    )
    hrefs = [e.href for e in digest.entries]
    assert hrefs == ["https://shop.example.com/p/other"]


def test_dedup_by_target_unions_labels() -> None:
    digest = build_digest(
        _links(
            ("Gillette Proglide", "/p/proglide"),
            ("En çok satan", "/p/proglide"),  # same target, different label
            ("Gillette Proglide", "/p/proglide/"),  # trailing-slash dup
        ),
        page_url=PAGE,
    )
    assert len(digest.entries) == 1
    assert digest.entries[0].labels == ("Gillette Proglide", "En çok satan")


def test_query_string_distinguishes_targets() -> None:
    digest = build_digest(
        _links(
            ("red", "/p/shirt?variant=red"),
            ("blue", "/p/shirt?variant=blue"),
        ),
        page_url=PAGE,
    )
    assert len(digest.entries) == 2


def test_off_domain_flagged_and_shows_domain() -> None:
    digest = build_digest(
        _links(
            ("same", "/p/specs"),
            ("elsewhere", "https://evil.example.org/phish"),
        ),
        page_url=PAGE,
    )
    same = next(e for e in digest.entries if not e.off_domain)
    off = next(e for e in digest.entries if e.off_domain)
    assert "example.com" not in _line_for(digest, same.handle).split("·", 1)[1]
    assert "evil.example.org" in _line_for(digest, off.handle)


def test_www_subdomain_is_not_off_domain() -> None:
    digest = build_digest(
        _links(("bare", "https://example.com/x")),
        page_url="https://www.example.com/home",
    )
    assert not digest.entries[0].off_domain


def test_contact_links_retained_with_raw_value() -> None:
    digest = build_digest(
        _links(
            ("E-posta", "mailto:support@shop.example.com"),
            ("Ara", "tel:+900000000"),
        ),
        page_url=PAGE,
    )
    assert {e.href for e in digest.entries} == {
        "mailto:support@shop.example.com",
        "tel:+900000000",
    }
    assert all(e.is_contact and not e.off_domain for e in digest.entries)
    # Raw value present in the rendered digest (not placeholdered away).
    assert "support@shop.example.com" in digest.render()


# --------------------------------------------------------------------- #
# Rehydration: closed-set + collision-proofing (design D2)
# --------------------------------------------------------------------- #


def test_rehydrate_handle_closed_set() -> None:
    digest = build_digest(_links(("reviews", "/p/reviews")), page_url=PAGE)
    assert digest.rehydrate_handle(1) == "https://shop.example.com/p/reviews"
    assert digest.rehydrate_handle(9) is None  # not in the set → dropped


def test_rehydrate_text_replaces_known_drops_unknown() -> None:
    digest = build_digest(
        _links(("reviews", "/p/reviews"), ("specs", "/p/specs")),
        page_url=PAGE,
    )
    out = digest.rehydrate_text("see {{1}} and {{2}} but not {{7}}")
    assert "https://shop.example.com/p/reviews" in out
    assert "https://shop.example.com/p/specs" in out
    assert "{{7}}" not in out  # unknown handle removed, never leaked


def test_product_name_with_letter_number_not_corrupted() -> None:
    """`{{n}}` rehydration must never touch 'Xiaomi L1' / 'WH-L7' / a SKU."""
    digest = build_digest(_links(("reviews", "/p/reviews")), page_url=PAGE)
    answer = "The Xiaomi L1 Desk Lamp and Sony WH-L7 headphones (SKU HBCV0000ATJ8M2) are covered; full reviews at {{1}}."
    out = digest.rehydrate_text(answer)
    assert "Xiaomi L1 Desk Lamp" in out
    assert "Sony WH-L7" in out
    assert "HBCV0000ATJ8M2" in out
    assert "https://shop.example.com/p/reviews" in out
    assert "{{1}}" not in out


def test_empty_links_yield_falsy_digest() -> None:
    digest = build_digest([], page_url=PAGE)
    assert not digest
    assert digest.table() == {}


def _line_for(digest: object, handle: int) -> str:
    for line in digest.render().splitlines():  # type: ignore[attr-defined]
        if line.startswith(f"{{{{{handle}}}}}"):
            return line
    raise AssertionError(f"no line for handle {handle}")
