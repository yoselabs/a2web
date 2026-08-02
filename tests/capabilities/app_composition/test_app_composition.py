"""App composition — which tools reach the MCP surface, and under what names.

Rewritten for the a2kit sunset. The old assertions read a2kit's descriptor
registry (`app.tools()`, `app.has_provider(AppState)`, `app.cli_extras()`);
those objects are gone, and asking a registry what it contains was always a
weaker question than asking the server what it serves. These go through
`list_tools()` on the real server instead.

Two of the old tests died with their subject rather than being ported:

- *canonical names pinned under flat naming* — ADR-0028 derived
  `{slug}_{leaf}` and a2web pinned the bare names back with
  `canonical_name_override`. There is no derivation now; `name="query"` in
  `routers.py` is the name. The surviving half (the bare names ARE the wire)
  is asserted below.
- *no connections subcommand* — a2kit's CLI-extras surface no longer exists.
"""

from __future__ import annotations

import pytest

from a2web.server import build_mcp_server, main
from a2web.settings import AppSettings


async def _tool_names(**settings_kwargs: object) -> set[str]:
    server = build_mcp_server(settings=AppSettings(**settings_kwargs))
    return {tool.name for tool in await server.list_tools()}


@pytest.mark.asyncio
async def test_web_tools_are_query_and_fetch_raw() -> None:
    """v0.7 split: `query` (primary, renamed from `ask` in v0.23) + `fetch_raw`."""
    names = await _tool_names()
    assert {"query", "fetch_raw"} <= names
    assert "ask" not in names  # renamed to `query` in v0.23
    assert "fetch" not in names  # renamed in v0.7


@pytest.mark.asyncio
async def test_tool_names_are_bare_not_slug_prefixed() -> None:
    """The installed MCP contract is `query` / `fetch_raw`, never `web_*`."""
    names = await _tool_names()
    assert names.isdisjoint({"web_query", "web_fetch_raw", "cookies_refresh"})


@pytest.mark.asyncio
async def test_cookies_tool_gated_off_by_default() -> None:
    """`expose_cookies_tool` defaults False — a served a2web has no local
    browser to mirror cookies from, so the tool is absent, not
    present-and-failing."""
    assert "cookies_refresh" not in await _tool_names()


@pytest.mark.asyncio
async def test_cookies_tool_exposed_when_toggled_on() -> None:
    assert "cookies_refresh" in await _tool_names(expose_cookies_tool=True)


def test_main_entrypoint_exists_and_callable() -> None:
    """`a2web.server.main` is the script entrypoint."""
    assert callable(main)
