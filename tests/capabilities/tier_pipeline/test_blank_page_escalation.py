"""End-to-end: a blank (near-empty raw HTML) page escalates through the ladder.

escalate-on-thin-page-walls. A server that answers with an essentially empty
document (`<html></html>`, an empty shell) is emitting a silent-block signal —
so the gate flags `blank_page` and the orchestrator escalates browser → paid
scraper before conceding. On recovery the fetch succeeds via the rendered tier;
on a persistent blank it ends in a LOUD but HONEST terminal: status=failed +
retrieval_incomplete + a distinct `blank_page` hint (NOT `try_user_browser` — a
genuinely empty source is not a browser-passable wall). An `ask` over a blank
page spends NO LLM tokens (extraction is gated on an `ok` verdict).
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, Rendered, TierResult
from tests.conftest import make_default_state

_BLANK_BODY = b"<html><head></head><body></body></html>"


class _BlankRawTier:
    """Raw tier returning a 200 with an essentially empty body (verdict ok —
    the gate, not the tier, is what recognizes the blankness)."""

    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_BLANK_BODY, content_type="text/html", status_code=200, final_url=url, verdict=Verdict.ok)


def _recovering_tier(name: str) -> type:
    """A rendered tier (browser or paid) that fills the empty shell with content."""

    class _RecoveringTier:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            md = "# Recovered\n\n" + ("Real rendered body content. " * 80)
            return TierResult(
                body=md.encode("utf-8"),
                content_type="text/html",
                status_code=200,
                final_url=url,
                from_browser=(name == "browser"),
                pre_rendered=Rendered(content_md=md, title="Recovered"),
                verdict=Verdict.ok,
            )

    _RecoveringTier.name = name  # type: ignore[attr-defined]
    return _RecoveringTier


class _BlankBrowserTier:
    """Browser tier that ALSO returns an empty shell — forces escalation to paid."""

    name = "browser"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_BLANK_BODY, content_type="text/html", status_code=200, final_url=url, from_browser=True, verdict=Verdict.ok)


def _only_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))


@pytest.mark.asyncio
async def test_blank_page_recovers_via_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """A blank raw body escalates to the browser, which fills it → ok."""
    _only_raw(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _BlankRawTier())
    monkeypatch.setitem(REGISTRY, "browser", _recovering_tier("browser")())

    result = await fetch("https://empty.example/x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "browser"
    assert result.title == "Recovered"


@pytest.mark.asyncio
async def test_blank_page_recovers_via_paid_scraper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank raw AND blank browser → the paid scraper is dispatched and recovers."""
    _only_raw(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _BlankRawTier())
    monkeypatch.setitem(REGISTRY, "browser", _BlankBrowserTier())
    monkeypatch.setitem(REGISTRY, "zyte", _recovering_tier("zyte")())

    result = await fetch("https://empty.example/x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.ok
    assert result.tier == "zyte"


@pytest.mark.asyncio
async def test_persistent_blank_page_ends_in_loud_wall_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank everywhere (browser + paid unavailable) → failed + retrieval_incomplete
    + the critical `try_user_browser` hint. A surviving blank body is treated as a
    likely silent anti-bot wall (e.g. g2.com: 403 to bots, full content in a real
    browser), not assumed genuinely empty — reporting a walled page as 'empty' is
    the worse false-negative error (ADR-0009)."""
    _only_raw(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _BlankRawTier())
    # conftest autouse leaves browser + zyte unavailable.

    result = await fetch("https://empty.example/x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert "verdict=blank_page" in result.diagnostics_summary
    assert result.retrieval_incomplete is True
    assert any(h.code == "try_user_browser" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_blank_page_ask_spends_no_llm_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """An `ask` over a blank page must NOT invoke the LLM extractor — extraction
    is gated on an `ok` verdict, so a blank_page terminal short-circuits it. The
    response is a small failed envelope with the blank hint and no fabricated
    answer (and no `llm_unavailable` hint, which would prove extraction ran)."""
    _only_raw(monkeypatch)
    monkeypatch.setitem(REGISTRY, "raw", _BlankRawTier())

    result = await fetch("https://empty.example/x", ask="What is the price?", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert any(h.code == "try_user_browser" for h in result.operator_hints)
    assert not any(h.code == "llm_unavailable" for h in result.operator_hints)
    assert result.extraction is None  # the extractor never ran
