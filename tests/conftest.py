"""Shared test fixtures.

Auto-stubs the archive tier so existing tests that trigger paywall /
block_page gate verdicts don't accidentally hit the live network when
the playbook escalation runs. Tests that exercise archive recovery
explicitly opt in by re-monkeypatching `REGISTRY["archive"]`.

a2web emits through its own `a2web.log`, which needs no ambient call scope —
the MCP forward resolves the in-flight FastMCP Context directly and simply
skips when there is none. So the former `a2kit.testing.ambient_for_tests_autouse`
import is gone: it existed only to stop direct `fetch()` calls (bypassing the
test client) from tripping a2kit's `AmbientContextMissing`.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

import aiosqlite.core
import pytest

# --- Hermetic settings: scrub ambient A2WEB_* BEFORE any a2web import -------- #
# The a2web imports below build the tier REGISTRY from `AppSettings()`, which
# reads `A2WEB_*` env vars and `~/.a2web/config.yaml`. A developer's real keys
# (`A2WEB_ZYTE_KEY`, `A2WEB_FIRECRAWL_KEY`, `A2WEB_JINA_KEY`, ...) would
# otherwise register paid tiers at import and let block-page tests reach the live
# network — so the suite passes in key-free CI but fails on a keyed dev machine
# (the `make check` local-vs-CI divergence). Pop every `A2WEB_*` var and point
# `A2WEB_CONFIG` at a path that cannot exist so the home config is never
# consulted. Tests that WANT a key present set it via `monkeypatch` after this.
#
# `A2WEB_BLESS_EVAL` is a TEST-HARNESS control (regression-replay re-blessing),
# not a settings key — it must survive the scrub. Same for
# `A2WEB_ACCEPT_WIRE_DELTA`, the reason-slug that accepts a wire-contract
# change (tests/contracts/wire_harness.py).
_HARNESS_CONTROL_ENV = {"A2WEB_BLESS_EVAL", "A2WEB_BLESS_CONTRACTS", "A2WEB_ACCEPT_WIRE_DELTA"}
for _leaked_key in [_k for _k in os.environ if _k.startswith("A2WEB_") and _k not in _HARNESS_CONTROL_ENV]:
    del os.environ[_leaked_key]
os.environ["A2WEB_CONFIG"] = "/nonexistent/a2web-hermetic-test-config.yaml"

from a2web.cache import SqliteResource
from a2web.components import Components, build_components
from a2web.hints import OperatorHint
from a2web.models import Verdict
from a2web.settings import AppSettings
from a2web.state import (
    AppState,
    build_breakers,
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
    """Test-only convenience — an `AppState` for tests that call `fetch()`
    directly, bypassing the MCP seam entirely.

    Deliberately **sync**, so a test needing only always-on state does not have
    to become a coroutine. It builds the same three factories `components.py`
    builds, and it is the ONLY place in the tree allowed to — see
    `tests/architecture/test_one_composition_root.py`; that guard walks `src/`,
    so this helper is out of its reach and stays a reviewed exception rather
    than an enforced one.

    Tests that also need the lazy resources want `make_default_components(...)`.
    """
    s = settings or AppSettings()
    return build_state(
        settings=s,
        breakers=build_breakers(),
        proxy_pool=build_proxy_pool(s),
        sqlite=SqliteResource(),
    )


async def make_default_components(settings: AppSettings | None = None) -> tuple[AppState, Components]:
    """Test-only convenience — the full graph through the one composition root.

    Async because resolving `AppState` enters sqlite, which is what production
    does too. Callers own teardown via `await components.aclose()`.
    """
    parts = build_components(settings=settings or AppSettings())
    return await parts.state(), parts


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


# --- Your machine is not an oracle ----------------------------------------- #
# The A2WEB_* scrub at the top of this file runs ONCE, at import, and covers
# a2web's own settings. It does not cover the LLM environment, and that gap cost
# three releases: 0.47.0 and 0.47.1 died on provider-selection tests, 0.48.0 on
# the CLI-contract goldens. In every case a test read whether the DEVELOPER'S
# MACHINE had a provider — green on a laptop with a Claude Code session, red on
# a bare runner, with no code difference between the two runs.
#
# Each was fixed one test at a time, and none of the fixes made the next
# occurrence impossible. As of 2026-08-01 a credential-stripped `pytest` is
# green (measured: 1441 passed, identical to the keyed run, with the strip
# verified non-vacuous — `ClaudeCodeSdkAdapter().available()` goes True → False
# under it). So this fixture reveals nothing today. That is the point: it holds
# a property the suite currently has BY ACCIDENT of having been patched
# repeatedly, and converts it into one the suite has by construction.
#
# Autouse rather than opt-in, deliberately. An opt-in version defends only the
# authors who already know the defect exists, which is precisely the set that
# would not have written it.
_SCRUBBED_LLM_ENV = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "A2WEB_LLM_PROVIDER",
    "CLAUDE_CODE_OAUTH_TOKEN",
)


@pytest.fixture(autouse=True)
def _hermetic_llm_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the host's LLM availability invisible; a test SHALL configure its own.

    **Reach, stated so it is not over-read.** This establishes that the named
    variables are absent and that the two subscription backends report
    unavailable. It does NOT establish that no test reaches the host by some
    unanticipated route — a new provider adapter with its own probe, or a
    library reading a config file, would both pass straight through. The CI
    runner remains the exogenous witness; this fixture makes the local run agree
    with it more often, not redundant with it.
    """
    if request.node.get_closest_marker("ambient_llm") is not None:
        return

    for name in _SCRUBBED_LLM_ENV:
        monkeypatch.delenv(name, raising=False)

    # The key-env NAMES are themselves configurable, so a settings change that
    # renamed them would route around a hardcoded list without failing anything.
    defaults = AppSettings()
    for configured in (defaults.llm_api_key_env, defaults.llm_openai_api_key_env):
        monkeypatch.delenv(configured, raising=False)

    # `raising=True` (the default) on purpose: if anyllm renames or drops either
    # adapter, this fails loudly rather than silently reopening the hole it was
    # written to close.
    from anyllm.providers.claude_code_cli import ClaudeCodeCliAdapter
    from anyllm.providers.claude_code_sdk import ClaudeCodeSdkAdapter

    monkeypatch.setattr(ClaudeCodeSdkAdapter, "available", lambda self: False)
    monkeypatch.setattr(ClaudeCodeCliAdapter, "available", lambda self: False)
