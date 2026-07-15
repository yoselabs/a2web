"""End-to-end: the single systematic never-silently-miss floor (ADR-0009).

prescribe-browser-on-any-wall. The `try_user_browser` prescription is no longer a
per-verdict whitelist — ANY fetch that ends non-ok and is not a genuine-gone
terminal carries the critical hint + `retrieval_incomplete`. This locks the
verdicts that fell through the retired whitelists (`length_floor`,
`proxy_unavailable`, `other`), the motivating `length_floor`-after-403 cascade,
and confirms `content_type_mismatch` stays a genuine terminal (a retrieved
non-HTML resource is not a wall a browser passes).
"""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict
from a2web.state import AppState
from a2web.tiers import REGISTRY, Rendered, TierResult
from tests.conftest import make_default_state


def _thin_pre_rendered_tier(name: str) -> object:
    """A tier that installs a short-but-real body → gate resolves `length_floor`.

    ~190 visible chars: above `BLANK_HTML_THRESHOLD` (32) so it is NOT `blank_page`,
    below `LENGTH_FLOOR` (500) so the gate calls it `length_floor`.
    """
    md = "Short but real content. " * 8

    class _ThinTier:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(
                body=md.encode("utf-8"),
                content_type="text/html",
                status_code=200,
                final_url=url,
                pre_rendered=Rendered(content_md=md, title="Thin"),
                verdict=Verdict.ok,
            )

    _ThinTier.name = name  # type: ignore[attr-defined]
    return _ThinTier()


def _verdict_tier(name: str, *, verdict: Verdict, status_code: int) -> object:
    """A tier that returns a fixed bodyless failure verdict."""

    class _FailTier:
        async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
            del state, kwargs
            return TierResult(
                body=b"",
                content_type="",
                status_code=status_code,
                final_url=url,
                verdict=verdict,
            )

    _FailTier.name = name  # type: ignore[attr-defined]
    return _FailTier()


@pytest.mark.asyncio
async def test_bare_length_floor_is_thin_unverified_not_walled(monkeypatch: pytest.MonkeyPatch) -> None:
    """A thin page that ends `length_floor` with NO wall evidence anywhere is an
    honest thin miss (thin-not-wall), not the anti-bot klaxon: status=failed +
    retrieval_incomplete + a WARNING `content_thin`, NEVER critical `try_user_browser`."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _thin_pre_rendered_tier("raw"))

    result = await fetch("https://thin.example/x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True  # still a loud miss, not silent
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)
    hints = {h.code: h for h in result.operator_hints}
    assert "content_thin" in hints and hints["content_thin"].severity == "warning"


@pytest.mark.asyncio
async def test_length_floor_after_bare_403_is_thin_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    """raw 403 (bodyless, no wall MARKERS) → a later tier returns a thin body.

    A bare status 403 is NOT reliable wall evidence — an empty result behind a
    CDN produces the same raw-403-then-thin shape. So with no hard-wall gate
    marker anywhere, this is `thin_unverified` (a loud thin miss with the body
    attached), not the critical klaxon. The reliable wall signal is gate markers
    (see `test_thin_downstream_of_wall_stays_walled`), not a status code."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw", "jina"))
    monkeypatch.setitem(REGISTRY, "raw", _verdict_tier("raw", verdict=Verdict.connection_error, status_code=403))
    monkeypatch.setitem(REGISTRY, "jina", _thin_pre_rendered_tier("jina"))

    result = await fetch("https://g2.example/categories/crm", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True  # loud miss preserved
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)
    assert any(h.code == "content_thin" for h in result.operator_hints)


@pytest.mark.parametrize("verdict", [Verdict.proxy_unavailable, Verdict.other])
@pytest.mark.asyncio
async def test_fallthrough_verdicts_prescribe_browser(monkeypatch: pytest.MonkeyPatch, verdict: Verdict) -> None:
    """`proxy_unavailable` and `other` fell through both retired whitelists; the
    systematic floor now covers them — the caller's own browser bypasses our proxy."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _verdict_tier("raw", verdict=verdict, status_code=0))

    result = await fetch("https://blocked.example/x", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    assert any(h.code == "try_user_browser" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_content_type_mismatch_is_genuine_gone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A retrieved non-HTML resource (`content_type_mismatch`) is NOT a wall — a
    browser won't extract it better — so it carries no `try_user_browser` and is
    not `retrieval_incomplete`."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _verdict_tier("raw", verdict=Verdict.content_type_mismatch, status_code=200))

    result = await fetch("https://files.example/report.pdf", state=make_default_state(), debug=True)

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is False
    assert not any(h.code == "try_user_browser" for h in result.operator_hints)


@pytest.mark.asyncio
async def test_hint_emitted_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The floor is a single emission — a persistent wall carries exactly one
    `try_user_browser` hint, never a duplicate."""
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", ("raw",))
    monkeypatch.setitem(REGISTRY, "raw", _verdict_tier("raw", verdict=Verdict.connection_error, status_code=403))

    result = await fetch("https://walled.example/x", state=make_default_state(), debug=True)

    assert sum(1 for h in result.operator_hints if h.code == "try_user_browser") == 1
