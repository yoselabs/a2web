"""ZendriverBackend — a CDP rendering engine behind the `BrowserBackend` seam.

**The robust rung, and permanent.** The `browser-backend-bakeoff` (archived
2026-06-27) kept TWO engines rather than crowning one: patchright is the fast
rung (`browser` tier), zendriver the robust rung (`browser_robust`), escalated
to only when the fast render comes back thin/blocked. They are complementary,
not ranked — the Chromium Playwright drop-ins fail the Trendyol/Hepsiburada
SPAs zendriver reads. `rebrowser` was the engine that lost and was deleted.

This is also the proof the interface spans engine *families*, not just the
Playwright API. zendriver drives Chromium directly over CDP (its own
`Browser`/`Tab` objects, no Playwright `Page`), so unlike Patchright it cannot
be a `PlaywrightBackend` launch_fn — it implements `render(...)` itself and
shapes CDP navigation / content / cookies into the same domain-free
`RenderedPage`.

**Per-render browser launch**, no host pool (design D3) — the simplest correct
shape, perfect per-render isolation, ~4-5x slower than the pooled fast rung
(~6.7s vs ~1.4s measured in the bake-off). A shared pool is a known, deferred
optimization (`BACKLOG.md`), low urgency because the cost only bites once the
fast rung has already failed to read the page.

Domain-free: only `RenderedPage` crosses the boundary — never a `Tab`, CDP
session, or domain type. Reuses the engine-neutral helpers from `playwright.py`
so the one-line summary + thin-floor heuristic stay identical across engines.
"""

from __future__ import annotations

import asyncio
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from .base import BackendCookie, RenderedPage, RenderOutcome
from .playwright import _CHALLENGE_STATUSES, _SCROLL_STABLE_MAX_PASSES, _THIN_FLOOR, _ms, _summarize_exc

_SAMESITE = {"strict": "STRICT", "lax": "LAX", "none": "NONE"}

# Explicit override for the Chromium binary zendriver should drive.
_EXECUTABLE_ENV = "A2WEB_BROWSER_EXECUTABLE_PATH"
# Where the published image parks its baked Chromium (Dockerfile sets this).
_PLAYWRIGHT_PATH_ENV = "PLAYWRIGHT_BROWSERS_PATH"

# Flags a containerized Chromium needs. Without them the process dies during
# startup and the CDP socket never opens, which surfaces only as zendriver's
# generic "Failed to connect to browser" — the symptom that made this rung look
# like a connection bug rather than a launch bug. This full tuple is for the
# raw `chrome --version` probe in `_launch_diagnostics`, where every entry is a
# valid CLI flag.
_CONTAINER_ARGS = ("--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu")
# The subset that may be passed to `zd.Config.add_argument`. zendriver (0.15.3)
# REJECTS `--no-sandbox` there with a ValueError — it insists you set the
# `Config.sandbox` attribute instead — and the backend adds these unconditionally
# on every launch, so passing the full tuple raised before Chromium was ever
# spawned and left the robust rung dead on arrival on this version, the
# container most of all (where --no-sandbox is mandatory). Sandbox is disabled
# via `config.sandbox = False`; only these two go through add_argument.
_CONFIG_ADDABLE_ARGS = ("--disable-dev-shm-usage", "--disable-gpu")


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


def _is_challenged_cdp_response(event: Any) -> bool:
    """CDP mirror of `playwright._is_challenged_subresource`: a challenged XHR/fetch.

    A `Network.responseReceived` event carries `type_` (a `ResourceType` enum)
    and `response.status` (an int). Read the enum by `.name` so no `cdp` module
    reference is needed at the call site. Best-effort: any shape surprise counts
    as "not challenged", so this telemetry can never fail a render — the same
    contract the Playwright side keeps.
    """
    try:
        rtype = getattr(event, "type_", None)
        name = (getattr(rtype, "name", None) or str(rtype)).upper()
        return name in ("XHR", "FETCH") and event.response.status in _CHALLENGE_STATUSES
    except Exception:  # best-effort telemetry — never fail the render on a shape quirk
        return False


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
        # Challenged-subresource counter, populated by a CDP handler registered
        # in `_navigate` before navigation. Defined here so every return path
        # (ok / timeout / error) can report it — the fast rung already does, and
        # the robust rung was permanently blind to the walled-API fake-empty
        # signal until this was threaded through. A launch failure leaves it 0,
        # which is correct: no render happened, so nothing was observed.
        blocked: list[int] = []
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
                # Disable the sandbox via the attribute, NOT add_argument — the
                # latter raises on "--no-sandbox" (see `_CONFIG_ADDABLE_ARGS`).
                config.sandbox = False
                for arg in _CONFIG_ADDABLE_ARGS:
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
                    self._navigate(browser, url, js_heavy, scroll_to_stable, blocked),
                    timeout=budget_s,
                )
            except TimeoutError:
                return RenderedPage(
                    outcome=RenderOutcome.timeout,
                    final_url=url,
                    js_executed=True,
                    wall_ms=_ms(wall_start),
                    subresource_blocks=len(blocked),
                )
        except Exception as exc:  # navigation / CDP / driver errors
            return RenderedPage(
                outcome=RenderOutcome.error,
                final_url=url,
                js_executed=True,
                wall_ms=_ms(wall_start),
                detail=_summarize_exc(exc),
                subresource_blocks=len(blocked),
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
            # content capture and leans on content-side block detection.
            # Subresource challenges ARE now captured (the `_navigate` handler);
            # main-frame status is the remaining gap and would use the same
            # Network.responseReceived stream, matched to the final document.
            status_code=200,
            js_executed=True,
            wall_ms=_ms(wall_start),
            bytes_transferred=len(html),
            subresource_blocks=len(blocked),
        )

    async def _navigate(
        self,
        browser: Any,
        url: str,
        js_heavy: bool,
        scroll_to_stable: bool = False,
        blocked: list[int] | None = None,
    ) -> tuple[str, str]:
        import zendriver as zd

        # Open a blank tab, arm the challenged-subresource counter, THEN navigate
        # — the same ordering the Playwright path uses (`page.on("response")`
        # before `page.goto`). Registering after navigation would miss the very
        # XHR/fetch this exists to catch: an SPA shell that 200s while its data
        # API is 403'd fires that request during load. Best-effort — a driver
        # missing the CDP surface degrades to a 0 count, never a failed render.
        tab = await browser.get("about:blank")
        if blocked is not None:

            def _on_response(event: Any) -> None:
                if _is_challenged_cdp_response(event):
                    blocked.append(1)

            with suppress(Exception):
                await tab.send(zd.cdp.network.enable())
                tab.add_handler(zd.cdp.network.ResponseReceived, _on_response)
        await tab.get(url)
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
