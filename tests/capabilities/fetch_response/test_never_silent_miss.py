"""Never-silently-miss envelope + late-hint contract (tasks 1.5 + 2.4).

The floor from ADR-0009: a walled fetch is a loud, explicit incompleteness —
`status: failed` + `retrieval_incomplete: true` + a critical, capability-generic
`try_user_browser` operator hint — and success omits the flag from the wire.
"""

from __future__ import annotations

import pytest

from a2web.decision_log import _verdict_rank
from a2web.fetcher import fetch
from a2web.models import FetchStatus, Verdict, try_user_browser_hint
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, Rendered, TierResult
from tests.conftest import make_default_state

_BLOCK_HTML = (
    b"<html><head><title>Just a moment...</title></head><body><h1>Just a moment...</h1>"
    b"<noscript>cf-chl-bypass</noscript></body></html>"
)


class _BlockedRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(body=_BLOCK_HTML, content_type="text/html", status_code=200, final_url=url)


class _OkRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        md = "# Fine\n\n" + ("Real readable body content here. " * 80)
        return TierResult(
            body=md.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered(content_md=md, title="Fine"),
            verdict=Verdict.ok,
        )


# --------------------------------------------------------------------- #
# 1.5 — envelope contract
# --------------------------------------------------------------------- #


def test_try_user_browser_hint_is_critical_and_generic() -> None:
    """The escalation hint is critical, imperative, and names no product."""
    hint = try_user_browser_hint("https://walled.example/x")
    assert hint.code == "try_user_browser"
    assert hint.severity == "critical"
    # severity serializes on the wire only when non-default.
    assert hint.model_dump().get("severity") == "critical"
    # Capability-generic: never names a concrete browser or agent product.
    blob = (hint.message + " " + (hint.fix or "")).lower()
    for product in ("chrome", "firefox", "safari", "edge", "claude", "playwright", "camoufox"):
        assert product not in blob
    # Imperative "not retrieved" is the load-bearing part.
    assert "not retrieved" in hint.message.lower()


def test_paid_auth_error_ranks_as_hardest_failure() -> None:
    """A keyed paid service failing auth outranks every other failure verdict."""
    others = [v for v in Verdict if v not in (Verdict.paid_auth_error, Verdict.ok)]
    assert all(_verdict_rank(Verdict.paid_auth_error) > _verdict_rank(v) for v in others)


@pytest.mark.asyncio
async def test_success_omits_retrieval_incomplete_from_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _OkRawTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://fine.example/", state=make_default_state())

    assert result.status == FetchStatus.ok
    assert result.retrieval_incomplete is False
    # Omitted from the wire (False lands in the omit-when-empty bucket).
    assert "retrieval_incomplete" not in result.model_dump()


# --------------------------------------------------------------------- #
# 2.4 — late critical hint for an unknown walled host
# --------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unknown_walled_host_fails_loud_with_late_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-Reddit host that walls after the full ladder emits the late critical
    hint + sets retrieval_incomplete — the miss can never look like success."""
    monkeypatch.setitem(REGISTRY, "raw", _BlockedRawTier())
    monkeypatch.setattr("a2web.fetcher.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://unknown-walled.example/article", state=make_default_state())

    assert result.status == FetchStatus.failed
    assert result.retrieval_incomplete is True
    hints = [h for h in result.operator_hints if h.code == "try_user_browser"]
    assert len(hints) == 1  # emitted exactly once (no eager+late double-emit)
    assert hints[0].severity == "critical"
