"""AppState DI tests — slots, build_state factory, per-App singleton (canary)."""

from __future__ import annotations

import dataclasses

import a2kit
import a2kit.testing
import pytest

from a2web.routers import WebRouter
from a2web.settings import AppSettings
from a2web.state import AppState, build_state


def test_app_state_is_dataclass_with_slots() -> None:
    assert dataclasses.is_dataclass(AppState)
    assert AppState.__slots__  # truthy non-empty


def test_app_state_rejects_unknown_attributes() -> None:
    s = build_state()
    with pytest.raises(AttributeError):
        s.bogus = 1  # type: ignore[attr-defined]


def test_build_state_returns_complete_state_minus_sqlite() -> None:
    """build_state populates everything except sqlite (opened in @on_startup)."""
    s = build_state()
    assert s.settings is not None
    assert s.breakers is not None
    assert s.log_writer is not None
    assert s.proxy_pool is not None
    assert s.sqlite is None  # filled by startup hook
    assert s.browser_pool is None  # stays lazy


def test_build_state_accepts_custom_settings() -> None:
    custom = AppSettings(stealth=True)
    s = build_state(settings=custom)
    assert s.settings is custom
    assert s.settings.stealth is True


def test_singleton_registered() -> None:
    app = a2kit.App("test").add_router(WebRouter())
    app.singleton(AppState, factory=build_state)
    assert app.has_singleton(AppState)


@pytest.mark.asyncio
async def test_repeated_dispatches_share_state() -> None:
    """Same App, two resolves → same AppState instance."""
    app = a2kit.App("t1").add_router(WebRouter())
    app.singleton(AppState, factory=build_state)
    s1 = await app.container().resolve(AppState, connection=None)
    s2 = await app.container().resolve(AppState, connection=None)
    assert s1 is s2


@pytest.mark.asyncio
async def test_two_apps_have_independent_states() -> None:
    """Canary: two App instances must NOT share AppState."""
    app1 = a2kit.App("a1").add_router(WebRouter())
    app2 = a2kit.App("a2").add_router(WebRouter())
    app1.singleton(AppState, factory=build_state)
    app2.singleton(AppState, factory=build_state)

    s1 = await app1.container().resolve(AppState, connection=None)
    s2 = await app2.container().resolve(AppState, connection=None)
    assert s1 is not s2


def test_peek_returns_resolved_singleton() -> None:
    """a2kit.testing.peek gives sync access to a resolved singleton."""
    app = a2kit.App("peek").add_router(WebRouter())
    app.singleton(AppState, factory=build_state)
    # peek triggers resolution; calling twice returns the same instance
    s1 = a2kit.testing.peek(app, AppState)
    s2 = a2kit.testing.peek(app, AppState)
    assert s1 is s2
    assert s1.settings is not None
