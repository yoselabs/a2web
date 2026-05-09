"""AppState DI tests — slots, registration, per-App singleton (canary)."""

from __future__ import annotations

import dataclasses

import a2kit
import pytest

from a2web.routers import WebRouter
from a2web.settings import AppSettings
from a2web.state import AppState, register_state


def test_app_state_is_dataclass_with_slots() -> None:
    assert dataclasses.is_dataclass(AppState)
    assert AppState.__slots__  # truthy non-empty


def test_app_state_rejects_unknown_attributes() -> None:
    s = AppState(settings=AppSettings())
    with pytest.raises(AttributeError):
        s.bogus = 1  # type: ignore[attr-defined]


def test_app_state_initializes_with_none_placeholders() -> None:
    s = AppState(settings=AppSettings())
    assert s.sqlite is None
    assert s.log_writer is None
    assert s.proxy_pool is None
    assert s.breakers is None
    assert s.browser_pool is None


def test_register_state_registers_provider() -> None:
    app = a2kit.App("test").add_router(WebRouter())
    register_state(app)
    assert app.has_provider(AppState) is True


@pytest.mark.asyncio
async def test_repeated_dispatches_share_state() -> None:
    """Same App, two dispatches → same AppState instance."""
    app = a2kit.App("t1").add_router(WebRouter())
    register_state(app)
    s1 = await app.container().resolve(AppState, connection=None)
    s2 = await app.container().resolve(AppState, connection=None)
    assert s1 is s2


@pytest.mark.asyncio
async def test_two_apps_have_independent_states() -> None:
    """Canary: two App instances must NOT share AppState."""
    app1 = a2kit.App("a1").add_router(WebRouter())
    app2 = a2kit.App("a2").add_router(WebRouter())
    register_state(app1)
    register_state(app2)

    s1 = await app1.container().resolve(AppState, connection=None)
    s2 = await app2.container().resolve(AppState, connection=None)
    assert s1 is not s2


@pytest.mark.asyncio
async def test_register_state_accepts_custom_settings() -> None:
    custom = AppSettings(stealth=True)
    app = a2kit.App("custom").add_router(WebRouter())
    register_state(app, settings=custom)

    state = await app.container().resolve(AppState, connection=None)
    assert state.settings is custom
    assert state.settings.stealth is True
