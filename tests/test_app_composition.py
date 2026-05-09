"""App composition tests — router shape, fetch stub, server entrypoint."""

from __future__ import annotations

import pytest

from a2web.models import CacheState, Confidence, FetchResponse, FetchStatus
from a2web.routers import WebRouter
from a2web.server import app, main
from a2web.settings import AppSettings
from a2web.state import AppState


def test_web_router_registers_one_tool() -> None:
    """`WebRouter` exposes exactly one tool, named `fetch`."""
    tools = list(app.tools())
    assert len(tools) == 1
    assert tools[0].__name__ == "fetch"


def test_app_has_no_connections_subcommand() -> None:
    """Option B from the proposal — no connections CLI surface."""
    extras = list(app.cli_extras())
    assert all(getattr(extra, "name", "") != "connections" for extra in extras)


@pytest.mark.asyncio
async def test_fetch_stub_returns_typed_envelope() -> None:
    """Stub returns a populated `FetchResponse` with `tier='stub'`."""
    router = WebRouter()
    state = AppState(settings=AppSettings())
    result = await router.fetch(url="https://example.com", state=state)

    assert isinstance(result, FetchResponse)
    assert result.url == "https://example.com"
    assert result.status == FetchStatus.ok
    assert result.tier == "stub"
    assert result.confidence == Confidence.low
    assert result.cache == CacheState.miss
    assert result.started_at is not None


@pytest.mark.asyncio
async def test_fetch_narrative_includes_diagnostics_default() -> None:
    """Narrative reads `state.settings.diagnostics_default` to confirm DI."""
    router = WebRouter()
    state = AppState(settings=AppSettings())  # default: "off"
    result = await router.fetch(url="https://example.com", state=state)
    assert "diagnostics_default=off" in result.narrative


def test_server_app_has_appstate_provider() -> None:
    """Server composition registers AppState via `register_state`."""
    assert app.has_provider(AppState) is True


def test_main_entrypoint_exists_and_callable() -> None:
    """`a2web.server.main` is the script entrypoint."""
    assert callable(main)
