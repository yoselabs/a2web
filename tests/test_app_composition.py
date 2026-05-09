"""App composition tests — router shape, fetch stub, server entrypoint."""

from __future__ import annotations

import pytest

from a2web.models import CacheState, Confidence, FetchResponse, FetchStatus
from a2web.routers import WebRouter
from a2web.server import app, main


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
    result = await router.fetch(url="https://example.com")

    assert isinstance(result, FetchResponse)
    assert result.url == "https://example.com"
    assert result.status == FetchStatus.ok
    assert result.tier == "stub"
    assert result.confidence == Confidence.low
    assert result.cache == CacheState.miss
    assert result.started_at is not None


def test_main_entrypoint_exists_and_callable() -> None:
    """`a2web.server.main` is the script entrypoint."""
    assert callable(main)
