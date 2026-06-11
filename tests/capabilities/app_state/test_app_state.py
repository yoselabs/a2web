"""AppState DI tests — slots, factory shape, per-App singleton (canary).

a2kit v0.36+: each resource is its own provider; AppState is a thin bundle
of the four always-on resources (settings, breakers, proxy_pool, sqlite).
Heavy resources (browser_pool, llm_extractor) live as independent providers
and are surfaced at the tool seam via `Lazy[T]` — not on AppState.
"""

from __future__ import annotations

import dataclasses

import a2kit
import a2kit.testing
import pytest
from purgatory import AsyncCircuitBreakerFactory

from a2web.packages.http_cache import SqliteResource
from a2web.packages.proxy_routing import ProxyPool
from a2web.routers import WebRouter
from a2web.settings import AppSettings
from a2web.state import AppState, build_state


def _build_probe_app() -> a2kit.App:
    """Build an App with the same provider topology as `server.py` for tests."""
    from a2web.server import build_breakers, build_proxy_pool
    from a2web.settings import get_settings

    app = a2kit.testing.app_of("test-probe", WebRouter)
    app.provide(get_settings)
    app.provide(build_breakers)
    app.provide(build_proxy_pool)
    app.provide(SqliteResource)
    app.provide(build_state)
    return app


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
    """Canary: browser_pool / llm_extractor were intentionally removed from AppState.

    They're provided independently via `app.provide(build_browser_pool)` and
    `app.provide(build_llm_extractor)`; tools surface them as `Lazy[T]`.
    """
    field_names = {f.name for f in dataclasses.fields(AppState)}
    assert "browser_pool" not in field_names
    assert "llm_extractor" not in field_names


def test_provider_registered() -> None:
    app = _build_probe_app()
    assert app.has_provider(AppState)


def test_peek_returns_resolved_state() -> None:
    """`peek` resolves a singleton once and caches it for the app's lifetime."""
    app = _build_probe_app()
    s1 = a2kit.testing.peek(app, AppState)
    s2 = a2kit.testing.peek(app, AppState)
    assert s1 is s2
    assert s1.settings is not None


def test_two_apps_have_independent_states() -> None:
    """Canary: two App instances must NOT share AppState."""
    app1 = _build_probe_app()
    app2 = _build_probe_app()
    s1 = a2kit.testing.peek(app1, AppState)
    s2 = a2kit.testing.peek(app2, AppState)
    assert s1 is not s2
