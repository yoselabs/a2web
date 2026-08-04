"""Listing sufficiency must run on the handler path, not only the record-miner's.

The check reads `fc.record_count`, which only `_escalate_via_records` ever set.
A handler that renders a listing ITSELF — arXiv builds its own "Showing 25 of
445" markdown — produced no record set, so `record_count` stayed `None` and the
phase returned immediately. The rendered prose told the caller the view was
partial while `operator_hints` carried nothing and `items_loaded`/`items_total`
were absent from the wire.

That split is the defect: the page states its own incompleteness in the body,
and the structured signal a caller would act on says everything is fine. arXiv
already computed both numbers to write that sentence, and discarded them.

Driven against a CAPTURED arXiv listing (`tests/fixtures/captured/`), not a
hand-written one — a fixture authored alongside the parser cannot falsify it.
"""

from __future__ import annotations

from pathlib import Path

from a2web import content_expectations
from a2web.fetcher import _phase_listing_completeness
from a2web.handlers.arxiv import _LISTING_RENDER_CAP
from a2web.listing_oracle import listing_oracle

_FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "captured" / "arxiv_list_cs_CL_recent.html"


def _listing_html() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


class _Ctx:
    """The fields `_phase_listing_completeness` reads and writes."""

    def __init__(self, record_count: int | None) -> None:
        self.record_count = record_count
        self.regex_oracle_total: int | None = None
        self.items_loaded: int | None = None
        self.items_total: int | None = None
        self.items_more = False


def test_the_captured_page_really_advertises_more_than_is_rendered() -> None:
    """Non-vacuity for everything below: the fixture must carry the shortfall.

    If the capture ever rotates to a page advertising ≤25 entries, the tests
    below would pass by describing nothing.
    """
    advertised = listing_oracle(_listing_html())
    assert advertised is not None, "the captured page carries no advertised total — recapture it"
    assert advertised > _LISTING_RENDER_CAP, f"advertised {advertised} vs cap {_LISTING_RENDER_CAP}: no shortfall to detect"


def test_a_handler_rendered_listing_is_assessed_as_partial() -> None:
    """THE regression. Pre-fix `record_count` was None here and the phase returned."""
    fc = _Ctx(record_count=_LISTING_RENDER_CAP)
    _phase_listing_completeness(fc, raw_html=_listing_html())  # type: ignore[arg-type]

    assert fc.items_loaded == _LISTING_RENDER_CAP, "the wire must carry what was actually rendered"
    assert fc.items_total == listing_oracle(_listing_html()), "and the total the page advertises"


def test_the_structured_signal_agrees_with_the_rendered_prose() -> None:
    """The anti-drift clause (task 4.6).

    The handler writes "Showing N of M" into the markdown from the same two
    numbers it now declares. If the render and the declaration ever diverge, the
    body and the wire would tell the caller different stories — which is the
    original defect in a subtler form, and harder to notice.
    """
    from a2web.handlers.arxiv import _render_listing

    html = _listing_html()
    advertised = listing_oracle(html)
    entries = tuple({"title": f"Paper {i}", "authors": "A. Author", "id": f"2601.{i:05d}"} for i in range(40))

    rendered = _render_listing("cs.CL", "recent", entries, advertised_total=advertised)
    prose = rendered["content_md"]

    fc = _Ctx(record_count=min(len(entries), _LISTING_RENDER_CAP))
    _phase_listing_completeness(fc, raw_html=html)  # type: ignore[arg-type]

    assert f"{fc.items_loaded} of {fc.items_total}" in prose, (
        f"prose and wire disagree: markdown says something other than '{fc.items_loaded} of {fc.items_total}'.\n{prose[:300]}"
    )


def test_a_complete_listing_emits_no_signal() -> None:
    """Anti-vacuity: a check that always fires is not a check.

    A page whose advertised total matches what was rendered must stay silent —
    otherwise every listing carries a partial-view warning and the signal is
    worth nothing.
    """
    html = _listing_html()
    advertised = listing_oracle(html)
    assert advertised is not None

    fc = _Ctx(record_count=advertised)
    _phase_listing_completeness(fc, raw_html=html)  # type: ignore[arg-type]

    assert fc.items_loaded is None and fc.items_total is None, "a complete listing must emit nothing"
    assert content_expectations.assess(loaded=advertised, total=advertised) != "partial"


def test_a_non_listing_page_is_untouched() -> None:
    """`record_count is None` still means "not a listing" and returns early."""
    fc = _Ctx(record_count=None)
    _phase_listing_completeness(fc, raw_html=_listing_html())  # type: ignore[arg-type]
    assert fc.items_loaded is None and fc.items_total is None and not fc.items_more


def test_the_handler_declaration_actually_reaches_the_context() -> None:
    """The wiring, not just the phase — and the reason this test exists.

    The tests above call `_phase_listing_completeness` with `record_count`
    already set, so they pass whether or not anything SUPPLIES it. Reverting
    the install in `_install_won_tier` left the whole file green, which is
    precisely the defect being fixed: the phase always worked, nothing on the
    handler path ever fed it.

    So this drives the real install and asserts the handoff.
    """
    from a2web.fetcher import FetchContext, FetchInputs, FetchResources, _install_won_tier
    from a2web.tiers import TierResult

    fc = FetchContext(
        inputs=FetchInputs(
            started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            start_perf=0.0,
            profile_hash="x",
            bypass_cache=True,
        ),
        resources=FetchResources(
            sqlite=None,
        ),
        url="https://arxiv.org/list/cs.CL/recent",
        final_url="https://arxiv.org/list/cs.CL/recent",
    )
    assert fc.record_count is None, "precondition: nothing has fed the sufficiency check yet"

    result = TierResult(
        body=b"",
        content_type="text/html",
        status_code=200,
        final_url=fc.url,
        volatility="live",
        items_rendered=25,
        items_advertised=408,
    )

    class _Tier:
        name = "site_handler"

    _install_won_tier(fc, result, "site_handler", _Tier())  # type: ignore[arg-type]

    assert fc.record_count == 25, "the handler's rendered count must reach the sufficiency check"
    assert fc.regex_oracle_total == 408, "and its advertised total must reach the oracle input"
    assert fc.volatility == "live", "the cache TTL declaration must ride along too"
