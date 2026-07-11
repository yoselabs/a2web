"""End-to-end: transport/status tier failures escalate through the ladder.

escalate-on-status-derived-walls (Step 2 of the escalation-architecture arc).
A bare 403 / 5xx / timeout / uncorroborated-404 from a free tier is ambiguous —
a WAF forges any of them to shed anonymous scrapers — so the planner now routes
each into the browser rung mid-walk (reachable since unify-escalation-executor).
On recovery the fetch succeeds via browser; on a persistent wall it ends in the
loud ADR-0009 terminal (status=failed + retrieval_incomplete + try_user_browser).
Two failures stay genuine terminals and do NOT escalate: a DNS NXDOMAIN and an
authoritative not_found.
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, Rendered, TierResult
from tests.conftest import make_default_state


def _raw_failure(*, verdict: Verdict, status_code: int) -> type:
    """Build a raw-tier stub returning a fixed transport failure."""

    class _FailingRawTier:
        name = "raw"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(
                body=b"",
                content_type="",
                status_code=status_code,
                final_url=url,
                verdict=verdict,
            )

    return _FailingRawTier


class _RecoveringBrowserTier:
    name = "browser"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        md = "# Recovered\n\n" + ("Real rendered body content. " * 80)
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            from_browser=True,
            js_executed=True,
            pre_rendered=Rendered(content_md=md, title="Recovered"),
            verdict=Verdict.ok,
        )


def _only_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the raw→browser path — no site_handler, no jina noise."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))


@pytest.mark.parametrize(
    ("verdict", "status_code"),
    [
        (Verdict.connection_error, 403),  # anti-bot 403
        (Verdict.connection_error, 502),  # 5xx server error
        (Verdict.connection_error, 451),  # other 4xx
        (Verdict.timeout, 0),  # tarpit
        (Verdict.connection_error, 0),  # network / TLS drop (not dns_error)
        (Verdict.not_found, 404),  # uncorroborated 404
        (Verdict.rate_limited, 429),  # exhausted 429
    ],
)
@pytest.mark.asyncio
async def test_transport_failure_escalates_to_browser_and_recovers(
    monkeypatch: pytest.MonkeyPatch, verdict: Verdict, status_code: int
) -> None:
    """Each ambiguous transport/status failure dispatches the browser, which recovers."""
    _only_raw(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _raw_failure(verdict=verdict, status_code=status_code)())
    monkeypatch.setitem(REGISTRY, "browser", _RecoveringBrowserTier())

    result = await fetch("https://walled.example/article", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "browser"
    assert result.title == "Recovered"


@pytest.mark.asyncio
async def test_persistent_transport_wall_ends_in_loud_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 403 that the (unavailable) browser cannot recover ends LOUD, not bare:
    status=failed + retrieval_incomplete + the critical try_user_browser hint."""
    _only_raw(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _raw_failure(verdict=Verdict.connection_error, status_code=403)())
    # conftest autouse leaves browser unavailable + archive not-found.

    result = await fetch("https://walled.example/article", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert any(h.code == "try_user_browser" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_dns_error_stays_terminal_without_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """A genuine NXDOMAIN is a terminal — no browser escalation (a real browser
    cannot resolve a dead domain), and it is NOT dressed as a 'behind a wall' miss."""
    _only_raw(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _raw_failure(verdict=Verdict.dns_error, status_code=0)())
    # A recovering browser would flip this to ok IF it were dispatched — it must not be.
    monkeypatch.setitem(REGISTRY, "browser", _RecoveringBrowserTier())

    result = await fetch("https://nonexistent.invalid/x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed  # browser NOT dispatched → still failed
    assert result.retrieval_incomplete is False  # genuine gone, not a wall
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_authoritative_not_found_stays_terminal_without_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """A site handler modelling the site's real 'gone' semantics (authoritative
    not_found) is terminal — no browser escalation, no 'behind a wall' framing."""

    class _GoneSiteTier:
        name = "site_handler"

        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(
                body=b"",
                content_type="",
                status_code=404,
                final_url=url,
                handler_name="site_handler:hn",
                verdict=Verdict.not_found,
            )

    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("site_handler",))
    monkeypatch.setitem(REGISTRY, "site_handler", _GoneSiteTier())
    monkeypatch.setitem(REGISTRY, "browser", _RecoveringBrowserTier())

    result = await fetch("https://news.ycombinator.com/item?id=1", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed  # browser NOT dispatched → still failed
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)
