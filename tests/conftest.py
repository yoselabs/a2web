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
import os
from typing import TYPE_CHECKING

import aiosqlite.core
import pytest
from a2kit.testing import ambient_for_tests_autouse  # noqa: F401 — autouse fixture by import (v0.39.3+)

# --- Hermetic settings: scrub ambient A2WEB_* BEFORE any a2web import -------- #
# The a2web imports below build the tier REGISTRY from `AppSettings()`, which
# reads `A2WEB_*` env vars and `~/.a2web/config.yaml`. A developer's real keys
# (`A2WEB_ZYTE_KEY`, `A2WEB_FIRECRAWL_KEY`, `A2WEB_JINA_KEY`, ...) would
# otherwise register paid tiers at import and let block-page tests reach the live
# network — so the suite passes in key-free CI but fails on a keyed dev machine
# (the `make check` local-vs-CI divergence). Pop every `A2WEB_*` var and point
# `A2WEB_CONFIG` at a path that cannot exist so the home config is never
# consulted. Tests that WANT a key present set it via `monkeypatch` after this.
for _leaked_key in [_k for _k in os.environ if _k.startswith("A2WEB_")]:
    del os.environ[_leaked_key]
os.environ["A2WEB_CONFIG"] = "/nonexistent/a2web-hermetic-test-config.yaml"

from a2web.cache import SqliteResource
from a2web.cookie_jar import build_cookie_jar
from a2web.models import OperatorHint, Verdict
from a2web.settings import AppSettings
from a2web.state import (
    AppState,
    Resources,
    _provider_lazy,
    build_breakers,
    build_browser_backend,
    build_browser_robust_backend,
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


# --- SqliteResource lifecycle in tests (ADR-0008) -------------------------- #
# A connection opened by a test and never closed leaves its aiosqlite worker
# thread alive past the test's function-scoped event loop; when that loop
# closes, the thread's next `call_soon_threadsafe(...)` raises
# `RuntimeError: Event loop is closed`. We track every SqliteResource (any
# construction path — `make_default_bundle` or a direct `SqliteResource(...)`)
# by wrapping __init__, so two test-infra concerns can act on the set:
#   1. close them in-loop before teardown (the structural fix), and
#   2. assert none were left open (the deterministic fitness function).
# The registry is NOT consumed by the close fixture — the guard needs the full
# set to verify closure.
#
# Why a STATE invariant, not a thread/symptom check: aiosqlite's worker thread
# stays PARKED and `is_alive()` even after a clean `close()` (it dies at process
# exit), so thread-liveness can't tell parked-closed from leaked. And the
# `Event loop is closed` symptom is itself timing-dependent (it only fires when
# the thread is mid-operation at teardown), so it flakes — promoting it to an
# error was tried and removed (it added ~1/15 flakiness; see pyproject note).
# The one fact that isolates the leak deterministically is `_conn is not None`
# at test end — the connection is open, period.
_TRACKED_SQLITE: list[SqliteResource] = []
_orig_sqlite_init = SqliteResource.__init__


def _tracking_sqlite_init(self: SqliteResource, *args: object, **kwargs: object) -> None:
    _orig_sqlite_init(self, *args, **kwargs)
    _TRACKED_SQLITE.append(self)


SqliteResource.__init__ = _tracking_sqlite_init  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
async def _sqlite_lifecycle(request: pytest.FixtureRequest) -> object:
    """Drive teardown of every test-constructed SqliteResource, then assert none
    was left open (the deterministic fitness function).

    One fixture so the order is guaranteed: a separate sync guard + async close
    finalize in a pytest-asyncio-determined order we cannot rely on. Teardown
    here: (1) close each tracked resource in-loop — `close()` prevents the
    pending-op-on-closed-loop error and is a no-op when never opened; (2) assert
    `_conn is None` everywhere — a deterministic STATE fact, unlike the flaky
    `Event loop is closed` symptom; (3) clear the registry for the next test.

    `set_close` lets the instrument-proof reproduce the leak by skipping (1)."""
    yield
    if _SKIP_SQLITE_CLOSE[0]:  # instrument-proof toggle; always False in normal runs
        leaked = [r for r in _TRACKED_SQLITE if getattr(r, "_conn", None) is not None]
        _TRACKED_SQLITE.clear()
        _assert_no_open_resource(request, leaked)
        return
    for resource in _TRACKED_SQLITE:
        with contextlib.suppress(Exception):
            await resource.close()
    leaked = [r for r in _TRACKED_SQLITE if getattr(r, "_conn", None) is not None]
    _TRACKED_SQLITE.clear()
    _assert_no_open_resource(request, leaked)


def _assert_no_open_resource(request: pytest.FixtureRequest, leaked: list[SqliteResource]) -> None:
    if leaked:
        pytest.fail(
            f"{request.node.nodeid} left {len(leaked)} SqliteResource(s) open past its event "
            "loop — a lifecycle resource was constructed but never closed, which leaks its "
            "aiosqlite worker thread. Build state via the `default_state` / `default_bundle` "
            "fixture (which drives teardown), or `async with` the resource directly."
        )


# Instrument-proof toggle (ADR-0008 task 2.3): set the env var in a throwaway
# run to skip the close and confirm the fitness assertion fails DETERMINISTICALLY.
# Unset in normal/committed runs, so the default is always False.
_SKIP_SQLITE_CLOSE = [os.environ.get("A2WEB_PROOF_SKIP_SQLITE_CLOSE") == "1"]


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
        browser_backend=build_browser_backend(s),
        browser_robust_backend=build_browser_robust_backend(s),
        # Mirror bootstrap_state's default: provider deferred to select_provider
        # (tests that exercise `ask` inject their own provider/extractor).
        llm_extractor=build_llm_extractor(s, sqlite, _provider_lazy(None, s)),
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
