"""a2web-7bj.5: a web-server default/placeholder vhost page reaches the caller
as an honest `default_vhost_page` hint, not the generic thin/wall framing."""

from __future__ import annotations

import pytest

from a2web.fetcher import fetch
from a2web.state import AppState
from a2web.tiers import REGISTRY, TIER_ORDER, TierResult
from tests.conftest import make_default_state

_NGINX_WELCOME_HTML = (
    b"<html><head><title>Welcome to nginx!</title></head><body>"
    b"<h1>Welcome to nginx!</h1>"
    b"<p>If you see this page, the nginx web server is successfully installed and "
    b"working. Further configuration is required.</p>"
    b"</body></html>"
)


class _DefaultVhostRawTier:
    name = "raw"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state, kwargs
        return TierResult(
            body=_NGINX_WELCOME_HTML,
            content_type="text/html",
            status_code=200,
            final_url=url,
        )


@pytest.mark.asyncio
@pytest.mark.protects(
    "spec:quality-gate", "Requirement: A web-server default/placeholder vhost page is fingerprinted as non-content, not thin"
)
async def test_nginx_welcome_page_surfaces_default_vhost_hint_not_content_thin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "raw", _DefaultVhostRawTier())
    # conftest's _UnavailableBrowserTier is in place — no browser dispatch needed
    # (the fingerprint carries no escalation).
    monkeypatch.setattr("a2web.fetcher.retrieval.tier_walk.TIER_ORDER", TIER_ORDER)

    result = await fetch("https://example.com/utapi", state=make_default_state())

    assert any(h.code == "default_vhost_page" for h in result.operator_hints)
    assert not any(h.code == "content_thin" for h in result.operator_hints)
