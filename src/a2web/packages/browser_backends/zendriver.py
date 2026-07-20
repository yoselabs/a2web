"""ZendriverBackend — a CDP rendering engine behind the `BrowserBackend` seam.

TRANSIENT (browser-backend-bakeoff): the bake-off's CDP candidate, and the
proof the interface spans engine *families*, not just the Playwright API.
zendriver drives Chromium directly over CDP (its own `Browser`/`Tab` objects,
no Playwright `Page`), so unlike Patchright/rebrowser it can't be a
`PlaywrightBackend` launch_fn — it implements `render(...)` itself and shapes
CDP navigation / content / cookies into the same domain-free `RenderedPage`.

v1 (design D3 + open question): **per-render browser launch**, no host pool —
the simplest correct shape, perfect per-render isolation. The speed axis of the
bake-off decides whether a shared-browser pool is worth adding; if zendriver
loses only on speed, that's the optimization to try before discarding it.

Domain-free: only `RenderedPage` crosses the boundary — never a `Tab`, CDP
session, or domain type. Reuses the engine-neutral helpers from `playwright.py`
(that module survives the bake-off regardless of winner — gated Camoufox keeps
it), so the one-line summary + thin-floor heuristic stay identical across
engines and the bake-off compares engines, not helper drift.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from .base import BackendCookie, RenderedPage, RenderOutcome
from .playwright import _SCROLL_STABLE_MAX_PASSES, _THIN_FLOOR, _ms, _summarize_exc

_SAMESITE = {"strict": "STRICT", "lax": "LAX", "none": "NONE"}

# Explicit override for the Chromium binary zendriver should drive.
_EXECUTABLE_ENV = "A2WEB_BROWSER_EXECUTABLE_PATH"
# Where the published image parks its baked Chromium (Dockerfile sets this).
_PLAYWRIGHT_PATH_ENV = "PLAYWRIGHT_BROWSERS_PATH"

# Flags a containerized Chromium needs. Without them the process dies during
# startup and the CDP socket never opens, which surfaces only as zendriver's
# generic "Failed to connect to browser" — the symptom that made this rung look
# like a connection bug rather than a launch bug.
_CONTAINER_ARGS = ("--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu")


def _resolve_executable() -> str | None:
    """Locate a Chromium binary for zendriver, or None to let it auto-discover.

    zendriver's default is to search for a SYSTEM Chrome install. The published
    image has no system Chrome — its only Chromium lives under
    `PLAYWRIGHT_BROWSERS_PATH`, installed for patchright — so auto-discovery
    finds nothing and the robust rung is dead on arrival in every container.
    Resolution order: explicit override → the Playwright-managed Chromium →
    None (auto-discover, the developer-machine path).
    """
    explicit = os.environ.get(_EXECUTABLE_ENV, "").strip()
    if explicit:
        return explicit
    root = os.environ.get(_PLAYWRIGHT_PATH_ENV, "").strip()
    if not root:
        return None
    base = Path(root)
    if not base.is_dir():
        return None
    # Layout: <root>/chromium-<build>/chrome-linux64/chrome (and the -headless-
    # shell variant). Take the highest build number so an image carrying two
    # installs uses the newer one.
    candidates = sorted(
        (p for p in base.glob("chromium*/chrome-linux*/chrome") if p.is_file() and os.access(p, os.X_OK)),
        key=lambda p: p.parts,
    )
    return str(candidates[-1]) if candidates else None


def _cookie_to_cdp(cookie: BackendCookie, cdp: Any) -> Any:
    """Engine-neutral `BackendCookie` → CDP `Network.CookieParam`."""
    same_site = None
    if cookie.samesite is not None:
        enum_name = _SAMESITE.get(cookie.samesite.lower())
        if enum_name is not None:
            same_site = getattr(cdp.network.CookieSameSite, enum_name)
    return cdp.network.CookieParam(
        name=cookie.name,
        value=cookie.value,
        domain=cookie.domain,
        path=cookie.path,
        expires=cookie.expires,
        secure=cookie.secure,
        http_only=cookie.http_only,
        same_site=same_site,
    )


async def _scroll_and_retry_cdp(tab: Any, original_html: str) -> str:
    """Scroll-to-bottom + brief settle + re-snapshot; keep the larger capture.

    The CDP-side mirror of `playwright._scroll_and_retry` — same intent (a
    sub-floor first paint on a JS-heavy host often grows after scroll), zendriver
    methods. Never raises.
    """
    larger = original_html
    with suppress(Exception):
        for _ in range(4):
            await tab.scroll_down(150)
        await asyncio.sleep(2.0)
        retry_html = await tab.get_content()
        if len(retry_html) > len(original_html):
            larger = retry_html
    return larger


async def _scroll_to_stable_cdp(tab: Any, original_html: str, *, max_passes: int = _SCROLL_STABLE_MAX_PASSES) -> str:
    """CDP mirror of `playwright._scroll_to_stable` — scroll to listing completion.

    Scroll → settle → re-snapshot, keeping the largest capture, until a pass adds
    nothing (fully materialised) or `max_passes` is reached. Never raises.
    """
    best = original_html
    for _ in range(max_passes):
        try:
            await tab.scroll_down(150)
            await asyncio.sleep(2.0)
            html = await tab.get_content()
        except Exception:
            break
        if len(html) <= len(best):
            break
        best = html
    return best


def _stat_binary(path: str) -> tuple[bool, bool]:
    """`(exists, executable)` for `path`. Sync — call via `asyncio.to_thread`."""
    return os.path.isfile(path), os.access(path, os.X_OK)


async def _launch_diagnostics(executable: str | None) -> str:
    """Probe the resolved Chromium and return a short ` (…)` suffix, or "".

    zendriver swallows the child's stderr, so a Chromium that dies on startup
    (missing shared library, unwritable HOME, sandbox denied) is indistinguishable
    from a slow CDP handshake. Re-run the binary with `--version` and surface
    what it says. Best-effort and strictly bounded: any failure here degrades to
    a plain empty suffix rather than masking the original launch error.
    """
    if not executable:
        return " (no Chromium resolved: set A2WEB_BROWSER_EXECUTABLE_PATH, or PLAYWRIGHT_BROWSERS_PATH to a Playwright-managed install)"
    exists, runnable = await asyncio.to_thread(_stat_binary, executable)
    if not exists:
        return f" (resolved binary does not exist: {executable})"
    if not runnable:
        return f" (resolved binary is not executable: {executable})"
    try:
        proc = await asyncio.create_subprocess_exec(
            executable,
            "--version",
            *_CONTAINER_ARGS,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        except TimeoutError:
            with suppress(ProcessLookupError):
                proc.kill()
            return f" (probe timed out running {executable} --version)"
    except Exception as exc:  # probing must never mask the real launch failure
        return f" (probe failed: {_summarize_exc(exc)})"
    text = (out or b"").decode("utf-8", "replace").strip()
    if proc.returncode == 0:
        # Binary is fine on its own — the failure is in the CDP handshake or the
        # runtime environment (HOME/user-data-dir writability, seccomp, IPC).
        return f" (binary OK: {text or executable}; failure is in the CDP handshake, not the binary)"
    return f" (binary exited {proc.returncode}: {text[:400] or '<no output>'})"


class ZendriverBackend:
    """CDP rendering engine. Per-render launch (v1). Satisfies `BrowserBackend`."""

    def __init__(self, *, name: str = "zendriver", page_budget_s: int = 30) -> None:
        self.name = name
        self.page_budget_s = page_budget_s

    async def render(
        self,
        url: str,
        *,
        cookies: list[BackendCookie],
        budget_s: float,
        js_heavy: bool,
        scroll_to_stable: bool = False,
    ) -> RenderedPage:
        try:
            import zendriver as zd
        except ImportError as exc:
            return RenderedPage(outcome=RenderOutcome.unavailable, final_url=url, detail=f"engine not installed: {exc}")

        wall_start = time.perf_counter()
        browser: Any | None = None
        try:
            executable = _resolve_executable()
            try:
                # zendriver's default connection handshake (0.25s x 10 tries
                # ~2.5s) gives up before Chromium's CDP socket is ready on a
                # cold/loaded host — the browser launches fine, the connect just
                # races it. Widen the window (1s x 15 ~15s headroom); it returns
                # as soon as the socket answers, so the common path stays fast.
                config = zd.Config(headless=True)
                if executable:
                    config.browser_executable_path = executable
                for arg in _CONTAINER_ARGS:
                    config.add_argument(arg)
                config.browser_connection_timeout = 1.0
                config.browser_connection_max_tries = 15
                browser = await zd.start(config=config)
            except Exception as exc:  # launch failed (no binary, sandbox, etc.)
                # zendriver reports every startup failure as the same opaque
                # "Failed to connect to browser", which conflates "no binary",
                # "binary died on startup", and "socket never opened". Attach
                # what we resolved plus Chromium's own stderr so the operator
                # sees the real cause instead of a connect-timeout story.
                return RenderedPage(
                    outcome=RenderOutcome.unavailable,
                    final_url=url,
                    detail=f"browser launch failed: {exc}{await _launch_diagnostics(executable)}",
                )

            if cookies:
                # Seed cookies on the browser jar BEFORE navigation so the
                # request goes out logged-in (parity with the Playwright path).
                await browser.cookies.set_all([_cookie_to_cdp(c, zd.cdp) for c in cookies])

            try:
                html, final_url = await asyncio.wait_for(
                    self._navigate(browser, url, js_heavy, scroll_to_stable),
                    timeout=budget_s,
                )
            except TimeoutError:
                return RenderedPage(outcome=RenderOutcome.timeout, final_url=url, js_executed=True, wall_ms=_ms(wall_start))
        except Exception as exc:  # navigation / CDP / driver errors
            return RenderedPage(
                outcome=RenderOutcome.error,
                final_url=url,
                js_executed=True,
                wall_ms=_ms(wall_start),
                detail=_summarize_exc(exc),
            )
        finally:
            if browser is not None:
                with suppress(Exception):
                    await browser.stop()

        return RenderedPage(
            outcome=RenderOutcome.ok,
            html=html,
            final_url=final_url,
            # CDP doesn't surface the main-frame nav status as cheaply as
            # Playwright's response object; v1 reports 200 on a successful
            # content capture and leans on content-side block detection. If
            # zendriver wins, capture it via a Network.responseReceived handler.
            status_code=200,
            js_executed=True,
            wall_ms=_ms(wall_start),
            bytes_transferred=len(html),
        )

    async def _navigate(self, browser: Any, url: str, js_heavy: bool, scroll_to_stable: bool = False) -> tuple[str, str]:
        tab = await browser.get(url)
        await tab.wait_for_ready_state("complete", timeout=int(self.page_budget_s))
        html = await tab.get_content()
        if len(html) < _THIN_FLOOR and js_heavy:
            html = await _scroll_and_retry_cdp(tab, html)
        if scroll_to_stable:
            html = await _scroll_to_stable_cdp(tab, html)
        return html, tab.url or url

    async def __aenter__(self) -> ZendriverBackend:
        # Per-render launch (v1) — nothing persistent to enter.
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        # No persistent browser to unwind; each render owns its own lifecycle.
        return None
