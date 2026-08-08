"""The option shelf is bounded in bytes, not only in entries.

`_OPTIONS_CAP = 50` bounded the COUNT and nothing bounded the size, so a shelf
could carry 50 x 240 = 12K of `detail`. Measured on the `arxiv-listing-partial`
bench cell (2026-08-01, `eval/findings_2026-08-01.md` §3): the shelf reached
17KB against 255 bytes of `answer` and 819 of `other_pages`, taking that cell
from 460 to 4730 envelope tokens.

That is ADR-0015's remedy defeating its own premise. `query` withholds the page
body FOR TOKEN ECONOMY and owes the caller an index of what it withheld; an
index carrying most of the body back is not a cheaper answer, it is the same
answer with an extra hop.

The trade is resolved toward COVERAGE: thin each entry rather than drop entries.
A dropped option is invisible to a caller that never saw the body; a shorter
`detail` is visibly shorter.
"""

from __future__ import annotations

from record_mine import Record, RecordSet

from a2web.fetcher_response import (
    _OPTION_DETAIL_CAP,
    _OPTION_DETAIL_FLOOR,
    _OPTIONS_CAP,
    _OPTIONS_DETAIL_BUDGET,
    _records_to_options,
)

_LONG = "word " * 200  # ~1000 chars, far past any per-option cap


def _record_set(*, count: int, text: str = _LONG) -> RecordSet:
    """A flat record set of `count` verbose records, as a listing page mines."""
    return RecordSet(
        records=[
            Record(
                text=f"Item number {i} {text}",
                links=[],
                heading_text=f"Item number {i}",
                heading_link=(f"Item number {i}", f"https://example.com/item/{i}"),
                depth=0,
                markdown="",
            )
            for i in range(count)
        ],
        container="ul",
        child_signature="li",
        max_depth=0,
    )


def test_a_full_verbose_shelf_stays_inside_the_budget() -> None:
    """THE regression. Pre-fix: 50 x 240 chars of detail, unbounded in total."""
    options = _records_to_options(_record_set(count=_OPTIONS_CAP))
    total = sum(len(o.detail or "") for o in options)

    assert total <= _OPTIONS_DETAIL_BUDGET, f"shelf detail is {total} chars against a budget of {_OPTIONS_DETAIL_BUDGET}"


def test_the_budget_thins_entries_rather_than_dropping_them() -> None:
    """The ADR-0015 trade, asserted rather than assumed.

    Coverage is the shelf's job — it names what the answer skipped. A caller that
    never saw the body cannot notice a missing option, but can plainly see a
    short `detail`.
    """
    options = _records_to_options(_record_set(count=_OPTIONS_CAP))
    assert len(options) == _OPTIONS_CAP, "every fetched option must still be named"
    assert all(o.detail for o in options), "thinning must not empty an entry"


def test_a_small_shelf_keeps_the_full_per_option_cap() -> None:
    """Anti-vacuity: the budget must bind only when it has to.

    Three options cannot approach the budget, so they must be unaffected —
    otherwise this is a blanket truncation wearing a budget's name.
    """
    options = _records_to_options(_record_set(count=3))
    longest = max(len(o.detail or "") for o in options)
    assert longest > _OPTION_DETAIL_FLOOR, "a small shelf was thinned as if it were a large one"
    assert longest <= _OPTION_DETAIL_CAP


def test_detail_never_thins_past_the_floor() -> None:
    """Below the floor an entry stops distinguishing anything.

    At that point the count cap is the honest bound; a `detail` of six characters
    is coverage in name only.
    """
    options = _records_to_options(_record_set(count=_OPTIONS_CAP))
    assert all(len(o.detail or "") >= _OPTION_DETAIL_FLOOR - 1 for o in options), "thinned past the floor"


def test_short_details_are_not_padded_or_altered() -> None:
    """The budget caps; it does not rewrite. A brief entry passes through whole."""
    options = _records_to_options(_record_set(count=_OPTIONS_CAP, text="cheap"))
    assert all("…" not in (o.detail or "") for o in options), "a short detail was truncated"
    assert sum(len(o.detail or "") for o in options) < _OPTIONS_DETAIL_BUDGET


def test_typed_commerce_fields_stay_small_against_a_full_shelf() -> None:
    """type-listing-commerce-fields: a full 50-entry shelf where every option
    also carries all five typed fields must not meaningfully add to the
    existing `detail` budget — they're short scalars (a price, a 3-letter
    currency, a rating), not a second free-text payload."""
    row = {"price": "1999", "currency": "TRY", "rating": "4.5", "stock": "InStock", "seller": "Acme Store"}
    rows = tuple(row for _ in range(_OPTIONS_CAP))
    options = _records_to_options(_record_set(count=_OPTIONS_CAP), rows)

    def _typed_len(o: object) -> int:
        return len(o.price or "") + len(o.currency or "") + len(o.rating or "") + len(o.stock or "") + len(o.seller or "")  # type: ignore[attr-defined]

    typed_total = sum(_typed_len(o) for o in options)
    # Generous ceiling: ~40 bytes/option x 50 options — the point is this stays
    # a small fraction of `_OPTIONS_DETAIL_BUDGET` (4000), not an exact figure.
    assert typed_total < _OPTIONS_DETAIL_BUDGET // 2, f"typed fields alone cost {typed_total} chars — no longer a small scalar addition"
