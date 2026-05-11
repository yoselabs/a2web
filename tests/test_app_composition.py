"""App composition tests — router shape and server wiring.

PR3 replaced the stub fetch with the real orchestrator; behavioural tests
for fetch live in `test_fetcher.py`. This module only covers the
composition-level invariants (one tool named `fetch`, AppState provider
registered, no connections CLI).
"""

from __future__ import annotations

from a2web.server import app, main
from a2web.state import AppState


def test_web_router_registers_fetch_tool() -> None:
    """`WebRouter.fetch` is the sole user-facing tool (plus a2kit's _meta.health)."""
    names = {tool.__name__ for tool in app.tools()}
    # _meta.health (aggregated_health) is auto-registered when health_tool=True
    assert "fetch" in names


def test_app_has_no_connections_subcommand() -> None:
    """Option B from PR1 — no connections CLI surface."""
    extras = list(app.cli_extras())
    assert all(getattr(extra, "name", "") != "connections" for extra in extras)


def test_server_app_has_appstate_singleton() -> None:
    """Server composition registers AppState via `app.singleton`."""
    assert app.has_singleton(AppState) is True


def test_main_entrypoint_exists_and_callable() -> None:
    """`a2web.server.main` is the script entrypoint."""
    assert callable(main)
