"""The index-loss hint — ADR-0015's "never *silently*" clause.

`query` withholds the page body, so the caller (itself an agent that never sees
that body) is blind to everything the answer did not surface. a2web makes up for
it with a cheap index: `also_here` for same-page content, `other_pages` for
pointers elsewhere, `options` for a listing's shelf. When the router envelope is
lost, the LLM's half of that index is lost with it — and an empty index on the
wire is indistinguishable from a page that genuinely had nothing to point at.

The gate is the whole design. It is on the DELIVERED index, not on routing loss,
because the index has three independent sources and routing loss removes only
one. Gating on routing loss fires on responses that carried a perfectly good
DOM-mined index — over-warning that would put this hint on the same road
`llm_wobble` went down.
"""

from __future__ import annotations

import pytest

from a2web.fetcher_response import build_ask_response
from a2web.models import (
    Confidence,
    FetchResponse,
    FetchStatus,
    NextLink,
    RouterPayload,
)
from a2web.packages.llm_extract import RoutingOutcome

_ANSWER = "The page explains how the borrow checker rejects aliased mutation."


def _fr(
    *,
    outcome: RoutingOutcome | None,
    routing: RouterPayload | None = None,
    next_links: list[NextLink] | None = None,
) -> FetchResponse:
    fr = FetchResponse(
        url="https://example.com/article",
        status=FetchStatus.ok,
        tier="raw",
        confidence=Confidence.high,
        extracted_answer=_ANSWER,
        routing=routing,
        next_links=next_links or [],
    )
    fr._routing_outcome = outcome
    return fr


def _hint_codes(fr: FetchResponse) -> list[str]:
    ask = build_ask_response(fr, include_content=False, debug=False)
    return [h.code for h in ask.operator_hints]


def _the_hint(fr: FetchResponse):
    ask = build_ask_response(fr, include_content=False, debug=False)
    return next(h for h in ask.operator_hints if h.code == "index_lost")


# --------------------------------------------------------------------- #
# It fires when the caller really was left with nothing
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("outcome", [RoutingOutcome.UNPARSABLE, RoutingOutcome.UNCLASSIFIED])
def test_degraded_routing_with_no_index_from_any_source_warns(outcome: RoutingOutcome) -> None:
    assert "index_lost" in _hint_codes(_fr(outcome=outcome))


def test_the_fix_names_the_cache_served_recovery() -> None:
    """The hint must be actionable, and the action must be honest about cost.

    `fetch_raw` on the same URL is served from the HTTP cache inside the TTL, so
    recovering the body costs one call and NO new proxy fetch. The scarce
    resource in a2web is the fetch, not the token — a hint that reads as "pay
    again" would deter the recovery it is recommending.
    """
    hint = _the_hint(_fr(outcome=RoutingOutcome.UNPARSABLE))
    assert "fetch_raw" in hint.fix
    assert "cache" in hint.fix


def test_severity_is_warning_and_never_the_wall_klaxon() -> None:
    """Extraction degraded; retrieval did not.

    `critical` + `try_user_browser` is the anti-bot wall signal (ADR-0009). A
    page that was fetched perfectly and answered correctly must never raise it —
    prescribing a browser escalation to repair an LLM formatting artifact sends
    the caller somewhere a re-fetch cannot help.
    """
    fr = _fr(outcome=RoutingOutcome.UNPARSABLE)
    assert _the_hint(fr).severity == "warning"
    assert "try_user_browser" not in _hint_codes(fr)


def test_status_and_retrieval_incomplete_are_untouched() -> None:
    """Status describes RETRIEVAL. This is an extraction fact and must not move it."""
    ask = build_ask_response(_fr(outcome=RoutingOutcome.UNPARSABLE), include_content=False, debug=False)
    assert ask.status == FetchStatus.ok
    assert ask.retrieval_incomplete is False
    assert ask.answer == _ANSWER


# --------------------------------------------------------------------- #
# It stays quiet everywhere else — the part that keeps it a signal
# --------------------------------------------------------------------- #


def test_no_hint_when_dom_mined_links_supplied_the_index() -> None:
    """The measured false positive, pinned.

    On HN the LLM supplied zero `other_pages` while the wire carried a populated
    block folded in from DOM-mined continuation links. Gating on routing loss
    would have warned about a lost index on a response that delivered one.
    """
    fr = _fr(
        outcome=RoutingOutcome.UNPARSABLE,
        next_links=[NextLink(anchor="Next", url="https://example.com/page/2", reason="next page", kind="related")],
    )
    assert "index_lost" not in _hint_codes(fr)


def test_no_hint_when_an_unclassified_envelope_still_carried_its_index() -> None:
    """The decoupling and the hint agree.

    An envelope that lost only its label keeps `also_here` / `other_pages`, so
    the caller is not blind and there is nothing to warn about.
    """
    fr = _fr(
        outcome=RoutingOutcome.UNCLASSIFIED,
        routing=RouterPayload(answer=_ANSWER, also_here=["what about lifetimes?"]),
    )
    assert "index_lost" not in _hint_codes(fr)


def test_no_hint_when_routing_was_recovered_and_the_page_had_nothing_to_index() -> None:
    """An empty index from a HEALTHY envelope is a finding, not a loss.

    The model read the whole page and reported nothing worth pointing at — the
    common case on a plain article. Warning here would fire on ordinary traffic
    and turn the hint into noise.
    """
    fr = _fr(
        outcome=RoutingOutcome.RECOVERED,
        routing=RouterPayload(answer=_ANSWER, structural_form="article", shape="prose"),
    )
    assert "index_lost" not in _hint_codes(fr)


def test_no_hint_on_a_provider_error() -> None:
    """Already reported as itself. Saying it twice in different words is noise."""
    assert "index_lost" not in _hint_codes(_fr(outcome=RoutingOutcome.PROVIDER_ERROR))


def test_no_hint_when_routing_was_never_requested() -> None:
    """`fetch_raw` runs no LLM and withholds nothing — ADR-0015 does not apply."""
    assert "index_lost" not in _hint_codes(_fr(outcome=None))
