"""Reddit declares no partial-view note, and the reason is checkable.

A note WAS added here on 2026-08-01 and removed the same day. Reddit's `.rss`
listing feeds carry exactly 25 entries and `_LISTING_CAP` is 25, so the rendered
count and the received count are equal for every input that can arrive — the
note was structurally unreachable.

That is the identical defect diagnosed in `hn._source_total` (which compared
what it rendered against what it had REQUESTED, the same number by
construction), shipped in the very commit that fixed it. Catching it needed the
question asked of both handlers, not just the one whose comment happened to
admit the shape.

There is genuinely nothing for Reddit to declare: it reports no total, and
nothing was dropped from what the feed returned. Inventing a denominator would
be a fabricated claim — worse than silence, because a caller cannot audit it.

So this file guards the PRECONDITION rather than a note: if Reddit's page size
ever exceeds the cap, entries start being dropped silently and a note becomes
both possible and required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from a2web.handlers.reddit import _LISTING_CAP, _all_post_entries, _parse_atom, _post_entries

_FIX = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "reddit"


@pytest.mark.parametrize("name", ["listing.rss", "search.rss"])
def test_reddit_cap_and_page_size_still_coincide(name: str) -> None:
    """THE guard. When this fails, Reddit changed and the silence is no longer safe.

    Driven from CAPTURED feeds — a hand-written fixture would encode whatever
    page size its author assumed, which is precisely the assumption under test.
    """
    feed = _parse_atom((_FIX / name).read_text(encoding="utf-8"))
    received = _all_post_entries(feed)

    assert received, f"{name} parsed to zero posts — the fixture or the parser is broken"
    assert len(received) <= _LISTING_CAP, (
        f"{name} carries {len(received)} posts against a cap of {_LISTING_CAP}. "
        "Reddit's page size now EXCEEDS the render cap, so posts are being "
        "dropped silently. Declare the truncation (see `_common.truncation_note`) "
        "or raise the cap — the current silence is only correct while these "
        "coincide."
    )


@pytest.mark.parametrize("name", ["listing.rss", "search.rss"])
def test_nothing_is_dropped_today(name: str) -> None:
    """The claim the silence rests on, asserted rather than assumed."""
    feed = _parse_atom((_FIX / name).read_text(encoding="utf-8"))
    assert len(_post_entries(feed)) == len(_all_post_entries(feed))
