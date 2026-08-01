"""HN declares Algolia's `nbHits`, not the size of the page it asked for.

The handler requests `hitsPerPage=30` and then rendered `min(len(hits), 30)`
against a total of `len(hits)`. Those are the same number by construction, so
`truncation_note` returned `""` for every input that can physically arrive —
the declaration existed, read as coverage, and was STRUCTURALLY UNREACHABLE.

The consequence is the ADR-0015 harm. A search matching 912 stories and a search
matching 30 produced an identical body and an identically silent envelope, and
`query` withholds the body, so the caller — itself an agent that never sees it —
had nothing at all to tell the two apart. Algolia reports the real total in
`nbHits`; the handler was throwing it away.

Same defect as `arxiv-listing-partial` (`test_handler_listing_sufficiency.py`),
one handler over: the page states its own incompleteness and the structured
signal says everything is fine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from a2web.handlers.hn import _FRONT_PAGE_CAP, _render_front_page, _source_total
from tests.fixtures import FIXTURES_DIR


def _captured() -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / "hn_front_page.json").read_text(encoding="utf-8"))


def test_the_captured_fixture_cannot_see_the_shortfall() -> None:
    """Why the synthetic payloads below exist, stated rather than assumed.

    `hn_front_page.json` carries `nbHits == len(hits) == 3`. Every existing HN
    front-page test asserts against it, so all of them pass identically whether
    the total is read from `nbHits`, from `len(hits)`, or not at all — which is
    how the unreachable note survived. A count-controlling payload is the right
    instrument; the shape is copied from the capture.
    """
    payload = _captured()
    assert payload["nbHits"] == len(payload["hits"]), (
        "the fixture now carries a shortfall and could exercise this directly — assert against it and delete the synthetic payloads below"
    )


def _payload(*, hits: int, nb_hits: int) -> dict[str, Any]:
    """An Algolia `search` body in the captured fixture's shape."""
    return {
        "nbHits": nb_hits,
        "hits": [
            {
                "objectID": str(9000 + i),
                "title": f"Story number {i}",
                "points": 100 - i,
                "num_comments": 10,
                "url": f"https://example.com/story-{i}",
            }
            for i in range(hits)
        ],
    }


def test_a_search_over_a_far_larger_total_declares_the_shortfall() -> None:
    """THE regression. Pre-fix this rendered 30 of 912 in total silence."""
    rendered = _render_front_page(_payload(hits=_FRONT_PAGE_CAP, nb_hits=912), is_search=True)
    body = rendered["content_md"]

    assert f"{_FRONT_PAGE_CAP} of 912" in body, f"no partial-view declaration in:\n{body[:400]}"
    assert "partial view" in body


def test_the_bare_front_page_never_declares_a_shortfall() -> None:
    """The false-positive this nearly shipped, measured against the live API.

        tags=front_page&hitsPerPage=30  -> nbHits 171, hits 30   (2026-08-01)

    `front_page` tags a rolling window of recently-front-paged stories; THE
    front page is the 30 currently on it. "Showing 30 of 171" would tell the
    caller it is missing 141 front-page stories that do not exist as such.

    A false "incomplete" is worse than none — it teaches the caller to ignore
    the signal, costing every TRUE partial that follows. This is precisely why
    `fix-cache-ttl-and-listing-sufficiency` §4.7 left hn open rather than guess.
    """
    rendered = _render_front_page(_payload(hits=_FRONT_PAGE_CAP, nb_hits=171), is_search=False)
    assert "partial view" not in rendered["content_md"]


def test_a_search_total_equal_to_what_was_rendered_stays_silent() -> None:
    """Anti-vacuity: a note that always fires is not a note.

    If every listing carried a partial-view warning the signal would be worth
    nothing, and "25 of 25" is noise at best.
    """
    rendered = _render_front_page(_payload(hits=12, nb_hits=12), is_search=True)
    assert "partial view" not in rendered["content_md"]


@pytest.mark.parametrize("payload", [{}, {"nbHits": "many"}, [], None])
def test_a_missing_or_malformed_total_is_absence_not_zero(payload: object) -> None:
    """An upstream that stops reporting `nbHits` must not be read as "no results".

    `truncation_note` treats `None` as "unknown" and stays silent; reading a
    malformed total as `0` would instead claim a shortfall of everything.
    """
    assert _source_total(payload, is_search=True) is None


def test_the_render_bound_and_the_requested_page_size_are_one_constant() -> None:
    """The two must not drift.

    `nbHits` is now the only total the declaration reads, so if the handler ever
    requested 30 and rendered 25, five stories would vanish with no note and no
    way to notice — the exact silence this file exists to close.
    """
    source = Path(__file__).resolve().parents[3] / "src" / "a2web" / "handlers" / "hn.py"
    text = source.read_text(encoding="utf-8")
    assert "hitsPerPage={_FRONT_PAGE_CAP}" in text, "the front-page request must ask for exactly what it renders"
