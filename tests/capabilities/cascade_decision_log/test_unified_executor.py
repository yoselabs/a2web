"""The single unified executor dispatches the full Action union.

unify-escalation-executor (Finding 1): `_execute_tier_action` (tier-walk) and the
inline post-gate loop each handled a different SUBSET of the 5-member `Action`
union, and neither handled all five — so the escalation ladder was physically
trapped in the post-gate phase. This change collapses both into one
`_dispatch_action(fc, action, *, state, post_gate)`. These tests assert that one
executor handles every `Action` type — no action is a silent no-op where the
planner can legally return it — and that `RewriteUrl` still restarts the tier
walk with the 1-rewrite cap (design D2).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from a2web import fetcher
from a2web.actions import Continue, EscalateBrowser, EscalatePaid, RetryViaArchive, RewriteUrl
from a2web.fetcher import FetchContext, _ArchiveOutcome, _dispatch_action, _Exec
from a2web.state import AppState
from tests.conftest import make_default_state


def _fc() -> FetchContext:
    return FetchContext(
        started_at=datetime.now(UTC),
        start_perf=0.0,
        profile_hash="x",
        sqlite=None,
        bypass_cache=True,
        url="https://example.com/",
        final_url="https://example.com/",
    )


def _state() -> AppState:
    return make_default_state()


async def test_rewrite_url_returns_restart_and_mutates_url() -> None:
    """RewriteUrl is a first-class RESTART control outcome (D2), url + cap updated."""
    fc = _fc()
    result = await _dispatch_action(fc, RewriteUrl(new_url="https://example.com/abs"), state=_state(), post_gate=False)
    assert result is _Exec.RESTART
    assert fc.url == "https://example.com/abs"
    assert fc.final_url == "https://example.com/abs"
    assert fc.url_rewrites == 1


async def test_continue_is_a_noop_continue() -> None:
    """The no-op Continue action dispatches to _Exec.CONTINUE with no side effects."""
    fc = _fc()
    result = await _dispatch_action(fc, Continue(), state=_state(), post_gate=False)
    assert result is _Exec.CONTINUE
    assert fc.url_rewrites == 0
    assert fc.archive_dispatches == 0


async def test_escalate_browser_is_dispatched_by_the_single_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """EscalateBrowser — a no-op in the OLD in-band executor — now dispatches."""
    called: list[str] = []

    async def _fake_browser(fc: FetchContext, *, state: AppState, scroll: bool = False) -> None:
        del fc, state, scroll
        called.append("browser")

    monkeypatch.setattr(fetcher, "_escalate_browser", _fake_browser)
    fc = _fc()
    result = await _dispatch_action(fc, EscalateBrowser(), state=_state(), post_gate=True)
    assert called == ["browser"]
    assert result is _Exec.CONTINUE


async def test_escalate_paid_is_dispatched_by_the_single_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    """EscalatePaid is a full member of the union the single executor dispatches."""
    called: list[str] = []

    async def _fake_paid(fc: FetchContext, *, state: AppState, scroll: bool = False) -> None:
        del fc, state, scroll
        called.append("paid")

    monkeypatch.setattr(fetcher, "_escalate_paid", _fake_paid)
    fc = _fc()
    result = await _dispatch_action(fc, EscalatePaid(), state=_state(), post_gate=True)
    assert called == ["paid"]
    assert result is _Exec.CONTINUE


async def test_retry_via_archive_tier_walk_variant_stops_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """post_gate=False: a successful archive installs the body and STOPs the walk."""

    async def _fake_archive(url: str, **kwargs: object) -> _ArchiveOutcome:
        del url, kwargs
        return _ArchiveOutcome(success=True, body=b"<html>archived</html>", content_type="text/html", final_url="u", status_code=200)

    monkeypatch.setattr(fetcher, "_dispatch_archive", _fake_archive)
    fc = _fc()
    result = await _dispatch_action(fc, RetryViaArchive(url="https://example.com/"), state=_state(), post_gate=False)
    assert result is _Exec.STOP
    assert fc.archive_dispatches == 1
    assert fc.tier_used == "archive"


async def test_retry_via_archive_post_gate_variant_regates_and_continues(monkeypatch: pytest.MonkeyPatch) -> None:
    """post_gate=True: archive installs extracted fields, regates, and CONTINUEs the loop."""

    async def _fake_archive(url: str, **kwargs: object) -> _ArchiveOutcome:
        del url, kwargs
        return _ArchiveOutcome(
            success=True,
            body=b"archived body with enough real content to pass the length floor " * 10,
            content_type="text/html",
            final_url="u",
            status_code=200,
            pre_rendered=fetcher.Rendered(content_md="archived markdown content " * 40),
        )

    monkeypatch.setattr(fetcher, "_dispatch_archive", _fake_archive)
    fc = _fc()
    before = len(fc.observations)
    result = await _dispatch_action(fc, RetryViaArchive(url="https://example.com/"), state=_state(), post_gate=True)
    assert result is _Exec.CONTINUE  # post-gate loop reconsults, never STOPs on archive
    assert fc.archive_dispatches == 1
    # _regate_after_escalation appended a fresh gate_outcome observation.
    assert len(fc.observations) > before
