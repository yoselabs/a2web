"""The post-gate archive path reads what it installed. It did not, for five copies.

`_install_rendered_fields`'s docstring records the first four: one field-copy
written in four places that disagreed. The SEQUENCE around it diverged the same
way and was never collapsed — of the five paths that install content, the
post-gate archive one ran neither the extraction ladder nor the sufficiency
check, and then re-gated anyway, reporting a verdict over content nothing had
read.

The consumer list is not hypothetical. `eval/findings_2026-07-28.md` measured
exactly this shape on the tier-loop path and named four starved consumers:
`content_candidates` (the ADR-0005 menu collapses to one item),
`json_synth`/`record_synth` (so `_build_link_digest`'s gate is unsatisfiable and
`other_pages` can never be emitted), `record_count` (so `listing_partial` can
never fire — ADR-0009's sufficiency axis off on exactly the population that
forced an escalation), and `record_set` (the option shelf stays empty).

These are behavioural: they drive a real archive outcome through the real
`escalate` seam and assert the consumers are fed. The structural half — that no
caller can install without comprehending — lives in
`tests/architecture/test_fetcher_phase_ordering.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from a2web.actions import RetryViaArchive
from a2web.fetcher import FetchContext, Rung, _ArchiveOutcome, _dispatch_action, escalate

# Patched on the OWNING module, not on `a2web.fetcher`. The package re-exports
# every name for compatibility, but a re-export is a second binding: setting it
# leaves the definition — and every caller's view of it — untouched. The seam
# moved with the tree (`decompose-fetcher-into-files` §4); the fake has to move
# with the seam.
from a2web.fetcher.retrieval.escalate import archive as archive_mod
from a2web.state import AppState
from a2web.tiers import Rendered
from tests.conftest import make_default_state

#: A snapshot with a JSON-LD ItemList — the shape the ladder turns into records.
#: Written in the real markup shape (a `<script type="application/ld+json">` in a
#: document) rather than as a bare payload, so it cannot pass a parser that would
#: reject the real thing.
_ARCHIVED_LISTING = """<!doctype html>
<html><head><title>Widgets</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"ItemList","numberOfItems":3,
 "itemListElement":[
  {"@type":"ListItem","position":1,"url":"https://example.com/a","name":"Widget A"},
  {"@type":"ListItem","position":2,"url":"https://example.com/b","name":"Widget B"},
  {"@type":"ListItem","position":3,"url":"https://example.com/c","name":"Widget C"}]}
</script></head>
<body><h1>Widgets</h1><p>Three widgets, archived.</p></body></html>
"""


def _fc() -> FetchContext:
    return FetchContext(
        started_at=datetime.now(UTC),
        start_perf=0.0,
        profile_hash="x",
        sqlite=None,
        bypass_cache=True,
        url="https://example.com/widgets",
        final_url="https://example.com/widgets",
    )


def _archive_outcome() -> _ArchiveOutcome:
    return _ArchiveOutcome(
        success=True,
        body=_ARCHIVED_LISTING.encode(),
        content_type="text/html",
        final_url="https://web.archive.org/web/2020/https://example.com/widgets",
        pre_rendered=Rendered(content_md="# Widgets\n\nThree widgets, archived."),
        status_code=200,
    )


@pytest.fixture
def archive_returns_a_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_dispatch(url: str, **kwargs: object) -> _ArchiveOutcome:
        del url, kwargs
        return _archive_outcome()

    monkeypatch.setattr(archive_mod, "_dispatch_archive", _fake_dispatch)


def _state() -> AppState:
    return make_default_state()


async def test_the_post_gate_archive_path_runs_the_extraction_ladder(archive_returns_a_listing: None) -> None:
    """The four consumers `eval/findings_2026-07-28.md` named, on the fifth copy of the bug."""
    del archive_returns_a_listing
    fc = _fc()

    installed = await escalate(fc, Rung.archive, state=_state())

    assert installed is True
    assert fc.tier_used == "archive"
    assert len(fc.content_candidates) > 1, (
        "the ADR-0005 candidate menu collapsed to the pre-rendered item — the ladder did not run. "
        "A pre-rendering tier has paid for extraction; it has NOT paid for json/record synthesis."
    )
    assert fc.record_set is not None, "the option shelf is empty — record synthesis did not run"
    assert fc.record_count == 3, f"expected 3 archived records, got {fc.record_count}"


async def test_the_post_gate_archive_path_runs_the_sufficiency_check(archive_returns_a_listing: None) -> None:
    """H1: escalators re-entered at comprehension and skipped sufficiency entirely.

    The archived snapshot advertises 3 items and carries 3, so the honest answer
    is "complete" — asserted as `items_total is None`. The load-bearing half is
    `record_count`: with it set, `_phase_listing_completeness` has an input to
    assess, which is precisely what it never had on this path.
    """
    del archive_returns_a_listing
    fc = _fc()

    await escalate(fc, Rung.archive, state=_state())

    assert fc.record_count is not None, (
        "sufficiency has no input — `_phase_listing_completeness` cannot fire on a path "
        "whose record count was never derived, so `listing_partial` is off by construction"
    )
    assert fc.items_total is None, "a complete listing must not be reported as partial"


async def test_the_planner_route_reaches_the_same_seam(archive_returns_a_listing: None) -> None:
    """Not just the seam in isolation — the way the planner actually gets there.

    `_dispatch_action(post_gate=True)` is the only production caller. Asserting
    only on `escalate` would leave the path that had the bug untested.
    """
    del archive_returns_a_listing
    fc = _fc()

    await _dispatch_action(fc, RetryViaArchive(url=fc.final_url), state=_state(), post_gate=True)

    assert fc.archive_dispatches == 1, "the post-gate archive budget was not spent exactly once"
    assert fc.record_count == 3, "the planner route did not comprehend what it installed"


async def test_a_failed_archive_dispatch_installs_and_comprehends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The anti-vacuity half: the assertions above must be able to fail.

    If `escalate` comprehended unconditionally, every test here would pass on a
    context that had been handed nothing — reading green while proving that a
    failed archive dispatch leaves the previous content in place.
    """

    async def _fake_dispatch(url: str, **kwargs: object) -> _ArchiveOutcome:
        del url, kwargs
        return _ArchiveOutcome(success=False)

    monkeypatch.setattr(archive_mod, "_dispatch_archive", _fake_dispatch)
    fc = _fc()

    installed = await escalate(fc, Rung.archive, state=_state())

    assert installed is False
    assert fc.tier_used == "none"
    assert fc.record_count is None
    assert fc.content_candidates == []
