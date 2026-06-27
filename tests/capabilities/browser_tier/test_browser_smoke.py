"""Opt-in real-browser smoke check — launches the actual browser binaries.

This is the "real check" the otherwise all-stubbed browser suite lacks: it
proves each browser rung launches a real engine, executes JavaScript, and
returns extracted content — the regression class ("the browser tier is
broken") that no stub can catch. Both rungs are covered:

  - `browser`        → patchright (fast Chromium, Playwright API)
  - `browser_robust` → zendriver  (robust CDP)

Excluded from `make check` (the `browser` marker is deselected by the
pyproject `addopts` default). Run it with `make test-browser`. Each test
auto-skips when its engine binary is unavailable, so CI without a browser
stays green. (Camoufox is gated off — see _manifests/browser_backends/camoufox.py.)
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from a2web.models import Verdict
from a2web.packages.browser_backends import BrowserBackend, PlaywrightBackend, ZendriverBackend, patchright_launcher
from a2web.settings import AppSettings
from a2web.tiers.browser import BrowserTier
from tests.conftest import make_default_state

pytestmark = pytest.mark.browser


# A page whose visible content exists ONLY after JavaScript runs — the raw
# HTML body is a single "loading" placeholder, so non-empty extracted markdown
# proves the browser actually executed the script (not just fetched HTML).
_JS_PAGE = """<!doctype html>
<html><head><title>Browser Smoke</title></head>
<body>
<div id="app">loading…</div>
<script>
  document.getElementById('app').innerHTML =
    '<article><h1>Browser Smoke OK</h1>' +
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


async def _assert_renders_js(backend: BrowserBackend, url: str) -> None:
    """Drive `backend` through the real BrowserTier; assert JS-rendered content."""
    state = make_default_state()
    state.settings = AppSettings(browser_enabled=True)
    result = await BrowserTier().fetch(url, state=state, backend=backend)
    assert result.verdict == Verdict.ok, result.operator_hint
    assert result.js_executed is True
    assert result.pre_rendered is not None
    assert "Browser Smoke OK" in result.pre_rendered.content_md


async def test_patchright_fast_rung_executes_js(js_fixture_url: str) -> None:
    """Fast rung (`browser` tier): real patchright Chromium executes JS."""
    try:
        import patchright.async_api  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"patchright not installed: {exc}")

    backend = PlaywrightBackend(patchright_launcher, name="patchright")
    try:
        await backend._ensure()
    except Exception as exc:  # binary missing / launch failed — environment, not a bug
        await backend.close()
        pytest.skip(f"patchright Chromium unavailable: {exc!r}")
    try:
        await _assert_renders_js(backend, js_fixture_url)
    finally:
        await backend.close()


async def test_zendriver_robust_rung_executes_js(js_fixture_url: str) -> None:
    """Robust rung (`browser_robust` tier): real zendriver CDP executes JS."""
    try:
        import zendriver  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"zendriver not installed: {exc}")

    backend = ZendriverBackend(name="zendriver")
    # zendriver launches per-render (no _ensure); a launch failure surfaces as
    # RenderOutcome.unavailable, which the tier maps to a hint — skip on that.
    result = await BrowserTier().fetch(js_fixture_url, state=_state(), backend=backend)
    if result.operator_hint is not None and result.operator_hint.code == "browser_unavailable":
        pytest.skip(f"zendriver Chromium unavailable: {result.operator_hint.message}")
    assert result.verdict == Verdict.ok, result.operator_hint
    assert result.js_executed is True
    assert result.pre_rendered is not None
    assert "Browser Smoke OK" in result.pre_rendered.content_md


def _state() -> object:
    state = make_default_state()
    state.settings = AppSettings(browser_enabled=True)
    return state
