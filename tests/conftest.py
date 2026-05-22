"""Shared test fixtures.

Auto-stubs the archive tier so existing tests that trigger paywall /
block_page gate verdicts don't accidentally hit the live network when
the playbook escalation runs. Tests that exercise archive recovery
explicitly opt in by re-monkeypatching `REGISTRY["archive"]`.

Imports `a2kit.testing.ambient_for_tests_autouse` (v0.39.3+) so direct
`fetch()` calls (bypassing TestClient) don't trip `AmbientContextMissing`.
The fixture is autouse by virtue of being imported into conftest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite.core
import pytest
from a2kit.testing import ambient_for_tests_autouse  # noqa: F401 — autouse fixture by import (v0.39.3+)
from purgatory import AsyncCircuitBreakerFactory

from a2web.models import OperatorHint, Verdict
from a2web.packages.http_cache import SqliteResource
from a2web.packages.proxy_routing import ProxyEntryShape, ProxyPool, RouteRuleShape
from a2web.settings import AppSettings
from a2web.state import AppState, build_state
from a2web.tiers import REGISTRY, TierResult

if TYPE_CHECKING:
    pass


# --- aiosqlite worker threads must be daemon in the test process ----------- #
# aiosqlite >=0.21 creates each connection's worker thread as NON-daemon (an
# upstream change for write-durability). A `SqliteResource` opened by a test
# that does not run through the a2kit `async with app:` lifecycle is never
# explicitly closed, so its worker thread parks on an empty queue forever and
# `threading._shutdown()` hangs the interpreter at process exit. Test
# databases are throwaway temp / in-memory files with no exit-durability
# need, so the worker thread is safe to daemonize here. Production keeps the
# non-daemon default and closes the connection via `SqliteResource.__aexit__`.
_orig_aiosqlite_connection_init = aiosqlite.core.Connection.__init__


def _daemon_aiosqlite_connection_init(
    self: aiosqlite.core.Connection, *args: object, **kwargs: object
) -> None:
    _orig_aiosqlite_connection_init(self, *args, **kwargs)
    self._thread.daemon = True


aiosqlite.core.Connection.__init__ = _daemon_aiosqlite_connection_init  # type: ignore[method-assign]


def make_default_state(settings: AppSettings | None = None) -> AppState:
    """Test-only convenience — build an `AppState` with the four always-on
    resources constructed directly (no DI).

    Production code resolves AppState via `app.container().get(AppState)` /
    `a2kit.testing.peek(app, AppState)`. Tests that bypass DI and exercise
    `fetch()` directly use this helper. NOT a back-compat shim — `build_state`
    requires its four deps as kwargs per the v0.38 DI architecture.
    """
    from typing import cast

    s = settings or AppSettings()
    return build_state(
        settings=s,
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        proxy_pool=ProxyPool(
            routes=cast("list[RouteRuleShape]", s.routes),
            proxies=cast("dict[str, ProxyEntryShape]", s.proxies),
        ),
        sqlite=SqliteResource(),
    )


class _NotFoundArchiveTier:
    """Default archive stub: always reports not_found, no network."""

    name: str = "archive"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state
        return TierResult(
            body=b"",
            content_type="text/html",
            status_code=404,
            final_url=url,
            from_archive=True,
            verdict=Verdict.not_found,
        )


class _UnavailableBrowserTier:
    """Default browser stub: never launch Camoufox in unit tests."""

    name: str = "browser"

    async def fetch(self, url: str, *, state: AppState, **kwargs: object) -> TierResult:
        del state
        return TierResult(
            body=b"",
            content_type="text/html",
            status_code=0,
            final_url=url,
            from_browser=True,
            operator_hint=OperatorHint(code="browser_unavailable", message="test stub", fix="n/a"),
            verdict=Verdict.connection_error,
        )


@pytest.fixture(autouse=True)
def _stub_archive_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(REGISTRY, "archive", _NotFoundArchiveTier())
    monkeypatch.setitem(REGISTRY, "browser", _UnavailableBrowserTier())
