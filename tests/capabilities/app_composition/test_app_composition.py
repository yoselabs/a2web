"""App composition tests — router shape and server wiring.

PR3 replaced the stub fetch with the real orchestrator; behavioural tests
for fetch live in `test_fetcher.py`. This module only covers the
composition-level invariants (one tool named `fetch`, AppState provider
registered, no connections CLI).
"""

from __future__ import annotations

from a2web.server import A2Web, _A2WebServer, _app_class_for, app, main
from a2web.settings import AppSettings
from a2web.state import AppState


def test_web_router_registers_ask_and_fetch_raw_tools() -> None:
    """v0.7 split: `ask` (primary) + `fetch_raw` (fallback) are the user-facing web tools."""
    # v0.36+: app.tools() returns list[ToolDescriptor]; tool fn is `descriptor.fn`.
    names = {desc.name for desc in app.tools()}
    # _meta.health is auto-installed by the @app.health_check decorator.
    assert "ask" in names
    assert "fetch_raw" in names
    assert "fetch" not in names  # renamed in v0.7


def test_canonical_tool_names_pinned_under_flat_naming() -> None:
    """ADR-0028 derives canonical names as `{slug}_{leaf}`; we pin the bare
    names via `canonical_name_override` so the MCP wire contract is unchanged.

    Backs specs/app-composition `Canonical MCP tool names pinned under flat
    naming` (a2kit-v043-migration). `app.tools()` exposes the descriptors whose
    `.name` is the canonical identity used on the MCP wire.
    """
    # The default (server-safe) app: ask/fetch_raw pinned to bare names.
    names = {desc.name for desc in app.tools()}
    assert {"ask", "fetch_raw"} <= names
    assert names.isdisjoint({"web_ask", "web_fetch_raw"})
    # The cookies-enabled app pins `refresh` (not `cookies_refresh`).
    cookie_names = {desc.name for desc in A2Web().tools()}
    assert "refresh" in cookie_names
    assert "cookies_refresh" not in cookie_names


def test_cookies_tool_gated_off_by_default() -> None:
    """`expose_cookies_tool` defaults False → the local-only `refresh` tool is NOT
    on the served surface (a server has no local browser to mirror). The module
    `app` is built with default settings, so it uses the server-safe class."""
    assert _app_class_for(AppSettings()) is _A2WebServer
    assert "refresh" not in {desc.name for desc in app.tools()}


def test_cookies_tool_exposed_when_toggled_on() -> None:
    """`expose_cookies_tool=True` (local serve) selects the cookies-enabled class,
    exposing `refresh`."""
    assert _app_class_for(AppSettings(expose_cookies_tool=True)) is A2Web
    assert "refresh" in {desc.name for desc in A2Web().tools()}


def test_app_has_no_connections_subcommand() -> None:
    """Option B from PR1 — no connections CLI surface."""
    extras = list(app.cli_extras())
    assert all(getattr(extra, "name", "") != "connections" for extra in extras)


def test_server_app_has_appstate_provider() -> None:
    """Server composition registers AppState via `app.provide` (v0.36+)."""
    assert app.has_provider(AppState) is True


def test_main_entrypoint_exists_and_callable() -> None:
    """`a2web.server.main` is the script entrypoint."""
    assert callable(main)
