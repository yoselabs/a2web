"""AppState — slots, factory shape, and the memoization canaries.

`AppState` is a thin bundle of the four always-on resources (settings,
breakers, proxy_pool, sqlite). Heavy resources (browser, llm_extractor,
cookie_jar) are NOT here — they reach the tool seam as `Lazy[T]` off
`Components`.

The three DI-registry tests at the bottom used to assert against a2kit's
container (`has_provider`, `a2kit.testing.peek`). Two of them were asserting
something real underneath the framework noise — that resolving state twice
yields ONE instance, and that two servers do not share one — so they are
ported onto `Components` rather than deleted. `has_provider` had nothing left
to ask: with the graph hand-wired, "is a provider registered" is answered by
the field existing on a frozen dataclass, which the type checker already
enforces.
"""

from __future__ import annotations

import dataclasses

import pytest
from purgatory import AsyncCircuitBreakerFactory

from a2web.cache import SqliteResource
from a2web.components import build_components
from a2web.packages.proxy_routing import ProxyPool
from a2web.settings import AppSettings
from a2web.state import AppState, build_state


def test_app_state_is_dataclass_with_slots() -> None:
    assert dataclasses.is_dataclass(AppState)
    assert AppState.__slots__  # truthy non-empty


def test_app_state_rejects_unknown_attributes() -> None:
    s = AppState(
        settings=AppSettings(),
        breakers=AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0),
        proxy_pool=ProxyPool(routes=[], proxies={}),
        sqlite=SqliteResource(),
    )
    with pytest.raises(AttributeError):
        s.bogus = 1  # type: ignore[attr-defined]


def test_build_state_returns_complete_non_optional_bundle() -> None:
    """build_state populates every always-on field non-Optional.

    Heavy resources (browser_pool, llm_extractor) moved off AppState in
    a2kit v0.36+ migration — they live as independent providers surfaced
    at the tool seam via Lazy[T].
    """
    settings = AppSettings()
    breakers = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)
    proxy_pool = ProxyPool(routes=[], proxies={})
    sqlite = SqliteResource()
    s = build_state(settings=settings, breakers=breakers, proxy_pool=proxy_pool, sqlite=sqlite)
    assert s.settings is settings
    assert s.breakers is breakers
    assert s.proxy_pool is proxy_pool
    assert s.sqlite is sqlite


def test_app_state_no_longer_has_heavy_fields() -> None:
    """Canary: browser_backend / llm_extractor were intentionally removed from AppState.

    They are separate `Lazy[T]` thunks on `Components`; tools pass the thunk
    down without awaiting it, so a cache-served fetch builds neither.
    """
    field_names = {f.name for f in dataclasses.fields(AppState)}
    assert "browser_pool" not in field_names
    assert "browser_backend" not in field_names
    assert "llm_extractor" not in field_names


@pytest.mark.asyncio
async def test_state_thunk_resolves_once() -> None:
    """The thunk memoizes: awaiting twice yields the SAME state.

    Not pedantry — `AppState` carries the sqlite handle and the circuit
    breakers. A second instance would mean a second connection and a fresh set
    of breakers, so a host that had just tripped would appear healthy again.
    """
    parts = build_components()
    assert await parts.state() is await parts.state()


@pytest.mark.asyncio
async def test_two_component_graphs_have_independent_states() -> None:
    """Canary: two `build_components()` calls must NOT share AppState."""
    assert await build_components().state() is not await build_components().state()
