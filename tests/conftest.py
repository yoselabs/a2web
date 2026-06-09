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

import contextlib
from typing import TYPE_CHECKING

import aiosqlite.core
import pytest
from a2kit.testing import ambient_for_tests_autouse  # noqa: F401 — autouse fixture by import (v0.39.3+)

from a2web.cookie_jar import build_cookie_jar
from a2web.models import OperatorHint, Verdict
from a2web.packages.http_cache import SqliteResource
from a2web.settings import AppSettings
from a2web.state import (
    AppState,
    Resources,
    build_breakers,
    build_browser_pool,
    build_llm_extractor,
    build_proxy_pool,
    build_state,
)
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


def _daemon_aiosqlite_connection_init(self: aiosqlite.core.Connection, *args: object, **kwargs: object) -> None:
    _orig_aiosqlite_connection_init(self, *args, **kwargs)
    self._thread.daemon = True


aiosqlite.core.Connection.__init__ = _daemon_aiosqlite_connection_init  # type: ignore[method-assign]


# --- close every SqliteResource within its own test's event loop ----------- #
# The daemon patch above stops the parked worker thread from hanging process
# exit, but a connection opened by a test and never closed leaves its worker
# thread alive *during* the session. When the test's function-scoped event loop
# closes, that thread's next `call_soon_threadsafe(...)` hits a closed loop and
# raises `RuntimeError: Event loop is closed` — surfaced as a
# `PytestUnhandledThreadExceptionWarning` (and, under coverage / unlucky timing,
# an intermittent hard failure attributed to whichever test was running). The
# fix is to close each `SqliteResource` *inside* the loop it was opened on:
# aiosqlite's `close()` drains and joins the worker thread cleanly, so no orphan
# callback survives teardown. We track every instance (any construction path —
# `make_default_bundle` or a direct `SqliteResource(...)`) by wrapping __init__.
_OPENED_SQLITE: list[SqliteResource] = []
_orig_sqlite_init = SqliteResource.__init__


def _tracking_sqlite_init(self: SqliteResource, *args: object, **kwargs: object) -> None:
    _orig_sqlite_init(self, *args, **kwargs)
    _OPENED_SQLITE.append(self)


SqliteResource.__init__ = _tracking_sqlite_init  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
async def _close_sqlite_resources() -> object:
    """Close every SqliteResource constructed during the test, in this test's
    event loop, before pytest-asyncio tears the loop down. `close()` is a no-op
    when the connection was never opened, so sync tests pay nothing."""
    yield
    while _OPENED_SQLITE:
        resource = _OPENED_SQLITE.pop()
        with contextlib.suppress(Exception):
            await resource.close()


def make_default_state(settings: AppSettings | None = None) -> AppState:
    """Test-only convenience — build an `AppState` via the same per-resource
    factories `bootstrap_state` composes (single source of truth).

    Production code resolves AppState via the DI container; tests that
    bypass DI and exercise `fetch()` directly use this helper. NOT a
    back-compat shim — calls the same `build_*` factories so a new
    always-on resource only needs wiring in `state.py`.

    Tests that also need the Lazy-eligible resources should call
    `make_default_bundle(...)` instead.
    """
    state, _ = make_default_bundle(settings)
    return state


def make_default_bundle(settings: AppSettings | None = None) -> tuple[AppState, Resources]:
    """Test-only convenience — full (AppState, Resources) bundle from the
    same per-resource factories as `bootstrap_state`. Sync — does not need
    a running event loop, matches the cheap-construction contract."""
    s = settings or AppSettings()
    sqlite = SqliteResource()
    state = build_state(
        settings=s,
        breakers=build_breakers(),
        proxy_pool=build_proxy_pool(s),
        sqlite=sqlite,
    )
    resources = Resources(
        browser_pool=build_browser_pool(s),
        llm_extractor=build_llm_extractor(s, sqlite),
        cookie_jar=build_cookie_jar(s, sqlite),
    )
    return state, resources


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
