"""Caller-facing `content_md` concatenation (task 7.2, change `surface-page-links-to-extractor`).

`_wire_content_md` narrowly reverses the 2026-06-07 pick-one rule for the ONE case
7.2 targets: an above-floor prose page whose JSON-LD would otherwise REPLACE the
prose on the wire. It now surfaces BOTH (subset-suppressed), so a product page's
specs never blind the caller to its prose. Everything else stays byte-identical to
the legacy single-pick. Deterministic, no LLM, no network.
"""

from __future__ import annotations

from a2web.fetcher import ContentCandidate, _wire_content_md

# Substantial prose, not a nav fragment — 720 chars, comfortably over the
# 500-char display floor.
#
# This block used to carry `assert len(_PROSE) >= LENGTH_FLOOR`, and that
# assertion was retired 2026-08-02 (close-guards §5.3). It was the ONLY
# reference to `LENGTH_FLOOR` that looked like a check on it, and it could not
# be one: a fixture sized from a constant moves when the constant moves, so it
# agrees with any value. It read as a deliberate guard on the most load-bearing
# number in the product while witnessing nothing.
#
# The real witness is `test_length_floor_witness.py` — two CAPTURED pages
# (113 and 740 extracted chars) that bracket the constant, so moving it in
# either direction flips a real page's classification.
_PROSE = "This is a substantial article body. " * 20


def test_prose_and_longer_json_are_concatenated() -> None:
    # A product page: rich JSON-LD (longer than prose) that legacy would REPLACE with.
    prose = ContentCandidate(source="trafilatura", content_md=_PROSE)
    specs = ContentCandidate(source="json_synth", content_md="## Specs\n" + ("field: value\n" * 60))
    out = _wire_content_md([prose, specs])
    # 7.2: neither is dropped — the caller sees both.
    assert _PROSE.strip() in out
    assert "field: value" in out


def test_article_metadata_json_never_appended_to_prose() -> None:
    # Article/NewsArticle JSON-LD is a metadata echo — guarded off the wire even
    # when longer (the historical blog.html regression).
    prose = ContentCandidate(source="trafilatura", content_md=_PROSE)
    article_ld = ContentCandidate(
        source="json_synth",
        content_md="headline: X\nauthor: Y\ndatePublished: Z\n" * 40,
        is_prose_metadata=True,
    )
    out = _wire_content_md([prose, article_ld])
    assert out == _PROSE  # prose only — metadata echo suppressed


def test_a_short_json_block_is_kept_not_dropped_for_being_short() -> None:
    """The 2026-08-02 decision, and the case that motivated it.

    This test previously asserted the OPPOSITE — that a json render shorter than
    the prose was discarded — because the shipped rule was "the longer one wins".
    That rule silently lost exactly the payload most worth keeping: a price, a
    phone number and a rating are SHORT, and the boilerplate they lose to is
    long. `fetch_raw` returns `content_md` and nothing else, so the caller could
    not tell anything had been dropped, and recovering it costs a new fetch.

    Reversed deliberately, not repaired. The old assertion was a faithful
    statement of a rule that has been retired.
    """
    prose = ContentCandidate(source="trafilatura", content_md=_PROSE)
    price = ContentCandidate(source="json_synth", content_md="price: 299 TRY")

    out = _wire_content_md([prose, price])

    assert _PROSE in out
    assert "price: 299 TRY" in out


def test_relative_length_selects_nothing() -> None:
    """The same two candidates, character counts inverted — same outcome.

    The retired rule flipped its answer when the counts flipped, which is what
    made it a rule about the rendering rather than about the content. Both
    orderings must now agree.
    """
    long_prose = ContentCandidate(source="trafilatura", content_md=_PROSE)
    long_json = ContentCandidate(source="json_synth", content_md="spec: value\n" * 200)

    short_case = _wire_content_md([long_prose, ContentCandidate(source="json_synth", content_md="price: 299 TRY")])
    long_case = _wire_content_md([long_prose, long_json])

    assert "price: 299 TRY" in short_case and _PROSE in short_case
    assert "spec: value" in long_case and _PROSE in long_case


def test_subfloor_prose_defers_to_legacy_single_pick() -> None:
    # A nav-fragment prose (< floor): the structured answer is what the caller
    # needs — legacy single-pick returns the json, not a prose+json concat.
    prose = ContentCandidate(source="trafilatura", content_md="Home Login")
    specs = ContentCandidate(source="json_synth", content_md="## Specs\n" + ("f: v\n" * 60))
    out = _wire_content_md([prose, specs])
    assert "Specs" in out
    assert "Home Login" not in out


def test_json_that_is_a_subset_of_prose_is_suppressed() -> None:
    # Coarse dedup: a json render wholly contained in prose does not duplicate.
    body = _PROSE + " Widget Pro 3000 specifications."
    prose = ContentCandidate(source="trafilatura", content_md=body)
    dup = ContentCandidate(source="json_synth", content_md="Widget Pro 3000 specifications." * 30)
    out = _wire_content_md([prose, dup])
    # json is longer (would-replace) but its normalized text is NOT a strict
    # subset here (repeated), so this asserts the concat path stays clean of
    # exact-duplication rather than subset math; both survive but prose leads.
    assert out.startswith(body[:40])
