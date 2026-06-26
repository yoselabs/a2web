"""Opt-in real-browser smoke check — launches the actual Camoufox binary.

This is the "real check" the otherwise all-stubbed browser suite lacks: it
proves the browser tier launches a real browser, executes JavaScript, and
returns extracted content — the regression class ("the browser tier is
broken") that no stub can catch.

Excluded from `make check` (the `browser` marker is deselected by the
pyproject `addopts` default). Run it with `make test-browser`. Auto-skips
when the `[browser]` extra / Camoufox binary is unavailable, so CI without a
browser stays green.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from a2web.models import Verdict
from a2web.packages.browser_pool import BrowserPool
from a2web.settings import AppSettings
from a2web.tiers.browser import BrowserTier
from tests.conftest import make_default_state

pytestmark = pytest.mark.browser


# A page whose visible content exists ONLY after JavaScript runs — the raw
# HTML body is a single "loading" placeholder, so non-empty extracted markdown
# proves the browser actually executed the script (not just fetched HTML).
_JS_PAGE = """<!doctype html>
<html><head><title>Camoufox Smoke</title></head>
<body>
<div id="app">loading…</div>
<script>
  document.getElementById('app').innerHTML =
    '<article><h1>Camoufox Smoke OK</h1>' +
    '<p>' + 'The browser tier rendered this paragraph after executing JavaScript. '.repeat(8) + '</p>' +
    '<p>' + 'A second rendered paragraph ensures trafilatura keeps the article body. '.repeat(8) + '</p>' +
    '</article>';
</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = _JS_PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return  # silence the dev server


@pytest.fixture
def js_fixture_url() -> Iterator[str]:
    """Serve the JS-rendering page from a throwaway localhost server."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)


async def test_real_camoufox_executes_js(js_fixture_url: str) -> None:
    try:
        import camoufox.async_api  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"camoufox not installed: {exc}")

    state = make_default_state()
    state.settings = AppSettings(browser_enabled=True)
    pool = BrowserPool()
    try:
        await pool._ensure()
    except Exception as exc:  # binary missing / launch failed — environment, not a bug
        await pool.close()
        pytest.skip(f"Camoufox binary unavailable: {exc!r}")

    try:
        result = await BrowserTier().fetch(js_fixture_url, state=state, pool=pool)
    finally:
        await pool.close()

    assert result.verdict == Verdict.ok, result.operator_hint
    assert result.js_executed is True
    assert result.pre_rendered is not None
    assert "Camoufox Smoke OK" in result.pre_rendered.content_md
