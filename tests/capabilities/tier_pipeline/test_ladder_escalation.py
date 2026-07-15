"""Escalate to a paid site render — search-retrieval-and-confabulation-guard P4.

A handler sets `escalate_to_render` when its rewritten fetch fails (HN's Algolia
API) or its surface is walled (Reddit search 403). The orchestrator STOPS the
free ladder (raw/jina get fooled by SPA shells / block pages) and renders the
ORIGINAL url directly via the paid tier (Zyte browserHtml). If no paid tier is
keyed, the empty body falls through to the never-silently-miss guarantee.
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult
from tests.conftest import make_default_state


class _EscalatingSiteTier:
    """A site_handler asking for a direct paid render (its converted fetch failed)."""

    name = "site_handler"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=b"",
            content_type="",
            status_code=404,  # even a 404 (normally authoritative) must not end the run
            final_url=url,
            handler_name="site_handler:hn",
            verdict=Verdict.not_found,
            escalate_to_render=True,
        )


class _ShellRawTier:
    """A raw tier that returns a passing-but-useless shell — proves it is NOT used."""

    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        md = "# Shell\n\n" + ("nav footer chrome " * 60)  # >500 chars: would pass the gate
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Shell"),
            verdict=Verdict.ok,
        )


class _OkPaidTier:
    name = "zyte"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        md = "# Rendered by Zyte\n\n" + ("Real rendered result content. " * 80)
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Rendered by Zyte"),
            verdict=Verdict.ok,
        )


@pytest.mark.asyncio
async def test_escalate_to_render_dispatches_paid_and_skips_free_tiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "site_handler", _EscalatingSiteTier())
    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    monkeypatch.setitem(REGISTRY, "zyte", _OkPaidTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://hn.algolia.com/?q=claude", state=make_default_state(), debug=True)

    # Paid render won on the original URL...
    assert result.status == FetchStatus.ok
    assert result.tier == "zyte"
    assert result.title == "Rendered by Zyte"
    # ...and the free ladder was stopped — the shell-returning raw tier never ran.
    assert not any(d.step == "raw" for d in result.diagnostics)
    # The failed handler attempt is still recorded.
    assert any(d.step == "site_handler" for d in result.diagnostics)


class _OkBrowserTier:
    """An own-browser rung that renders the walled surface — proves it is tried
    as the rung BETWEEN the (absent) paid tier and the never-silently-miss hint."""

    name = "browser"

    async def fetch(self, url: str, *, state: AppState, backend: object = None, scroll: bool = False, **kwargs: object) -> TierResult:
        del state, backend, scroll, kwargs
        md = "# Rendered by browser\n\n" + ("Real browser-rendered content. " * 80)
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Rendered by browser"),
            verdict=Verdict.ok,
        )


class _UnavailableBrowserTier:
    """An own-browser rung that can't run (no backend provisioned)."""

    name = "browser"

    async def fetch(self, url: str, *, state: AppState, backend: object = None, scroll: bool = False, **kwargs: object) -> TierResult:
        del state, backend, scroll, kwargs
        return TierResult(body=b"", content_type="", status_code=0, final_url=url, verdict=Verdict.other, skipped=True)


class _WalledBrowserTier:
    """An own-browser rung that renders, but the page is itself a block wall —
    the browser passed the anti-bot but the SITE walls it (Reddit login gate).
    Returns `ok` with a block-page body so the GATE flags it walled."""

    name = "browser"

    async def fetch(self, url: str, *, state: AppState, backend: object = None, scroll: bool = False, **kwargs: object) -> TierResult:
        del state, backend, scroll, kwargs
        md = "# Blocked\n\nwhoa there, pardner — you are attempting to access a blocked page. " * 6
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Blocked"),
            verdict=Verdict.ok,  # the browser fetch itself succeeded; the gate must catch the wall
        )


@pytest.mark.asyncio
async def test_escalate_to_render_falls_to_browser_when_no_paid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """No paid tier keyed → try the own-browser BEFORE conceding.

    The intended ladder is paid-scraper → real-browser → hint. A real
    (anti-detect) browser passes soft per-IP walls the HTTP client cannot
    (Reddit RSS throttling), so the own-browser is the rung between the absent
    paid tier and the never-silently-miss hint — not a skip straight to the hint.
    """
    monkeypatch.setitem(REGISTRY, "site_handler", _EscalatingSiteTier())
    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    monkeypatch.delitem(REGISTRY, "zyte", raising=False)
    monkeypatch.delitem(REGISTRY, "firecrawl", raising=False)
    monkeypatch.setitem(REGISTRY, "browser", _OkBrowserTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://hn.algolia.com/?q=claude", state=make_default_state(), debug=True)

    # The own-browser rendered the walled surface — no paid key needed.
    assert result.status == FetchStatus.ok
    assert result.tier == "browser"
    assert result.title == "Rendered by browser"
    assert not any(d.step == "raw" for d in result.diagnostics)  # free ladder still skipped


@pytest.mark.asyncio
async def test_escalate_to_render_without_paid_or_browser_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """No paid tier AND no working browser → the render can't happen → the
    own-browser rung is still ATTEMPTED, then never-silently-miss fires."""
    monkeypatch.setitem(REGISTRY, "site_handler", _EscalatingSiteTier())
    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    monkeypatch.delitem(REGISTRY, "zyte", raising=False)
    monkeypatch.delitem(REGISTRY, "firecrawl", raising=False)
    monkeypatch.setitem(REGISTRY, "browser", _UnavailableBrowserTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://hn.algolia.com/?q=claude", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert not any(d.step == "raw" for d in result.diagnostics)  # free ladder still skipped
    # The own-browser rung was tried before conceding.
    assert any(d.step == "browser" for d in result.diagnostics)


class _ThinJinaTier:
    """A jina rung that WON (200 ok) but returned STRIPPED, sub-floor markdown.

    ~120 chars: above BLANK_HTML_THRESHOLD (not blank_page) and — crucially —
    with no `<script>`/root HTML markers (jina strips them), so the gate cannot
    fingerprint it as js_required. It falls to the bare `length_floor` bucket.
    """

    name = "jina"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        md = "No results shown here. " * 5  # sub-500, marker-less
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/markdown",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Thin"),
            verdict=Verdict.ok,
        )


@pytest.mark.asyncio
async def test_bare_length_floor_jina_recovers_via_own_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """The incehesap hole: jina wins with sub-floor stripped markdown → a BARE
    `length_floor` with no fingerprint. a2web must try its OWN browser before
    conceding, not merely prescribe the caller's. The browser render recovers the
    page to `ok` (ADR-0009: a wall is an unfinished job)."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("jina",))
    monkeypatch.setitem(REGISTRY, "jina", _ThinJinaTier())
    monkeypatch.setitem(REGISTRY, "browser", _OkBrowserTier())

    result = await fetch(
        "https://www.incehesap.com/arama/?kelime=deepcool+ch160+plus",
        state=make_default_state(),
        debug=True,
    )

    assert result.status == FetchStatus.ok
    assert result.tier == "browser"
    assert result.title == "Rendered by browser"
    # The browser was rendered on the TARGET url, never a r.jina.ai wrapper.
    assert "r.jina.ai" not in (result.url or "")


@pytest.mark.asyncio
async def test_bare_length_floor_jina_no_browser_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare-length_floor jina terminal (no wall markers) is still a LOUD miss —
    the browser was attempted, then the caller is told — but as an honest thin
    hedge (`content_thin` warning + attached body), not the anti-bot klaxon."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("jina",))
    monkeypatch.setitem(REGISTRY, "jina", _ThinJinaTier())
    monkeypatch.setitem(REGISTRY, "browser", _UnavailableBrowserTier())

    result = await fetch("https://www.incehesap.com/arama/?kelime=x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert any(d.step == "browser" for d in result.diagnostics)  # own-browser tried first
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)
    assert any(h.code == "content_thin" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_escalate_to_render_browser_walled_still_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    """The browser rung renders, but the SITE walls the page (Reddit login gate).

    The browser fetch succeeds yet the gate flags the rendered body as a block
    wall. This MUST still be a loud miss: `failed` + `retrieval_incomplete` + the
    critical `try_user_browser` hint (never-silently-miss, ADR-0009). Regression
    guard: installing walled browser content must not skip the hint.
    """
    monkeypatch.setitem(REGISTRY, "site_handler", _EscalatingSiteTier())
    monkeypatch.setitem(REGISTRY, "raw", _ShellRawTier())
    monkeypatch.delitem(REGISTRY, "zyte", raising=False)
    monkeypatch.delitem(REGISTRY, "firecrawl", raising=False)
    monkeypatch.setitem(REGISTRY, "browser", _WalledBrowserTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://www.reddit.com/r/x/", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert any(d.step == "browser" for d in result.diagnostics)  # browser was tried
    # ...and the miss is LOUD — the caller is told to open a real browser.
    assert any(h.code == "try_user_browser" for h in result.operator_hints)
