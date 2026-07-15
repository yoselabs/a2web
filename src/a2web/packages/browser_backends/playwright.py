"""PlaywrightBackend — the Playwright-API engine family (Camoufox today).

One backend body parameterized by a `launch_fn` that yields a Playwright
`Browser`; only the launch differs across Playwright-API engines (Camoufox,
and later Patchright / rebrowser). Absorbs the former `BrowserPool` (per-host
LRU context reuse, idle eviction, driver-stderr capture) plus the page-driving
render mechanics that used to live in the browser tier.

Domain-free: emits diagnostics via stdlib logging on the `a2kit` logger
(scroll-retry) or an injected async `stderr_sink` (driver stderr); the domain
wires the typed-event side. Returns the engine-neutral `RenderedPage`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .base import BackendCookie, RenderedPage, RenderOutcome

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Coroutine

_A2KIT_LOG = logging.getLogger("a2kit")

# First-snapshot length below which a JS-heavy host triggers scroll-on-thin.
_THIN_FLOOR = 4_096

# Safety bound on the scroll-to-stable loop (listing-completeness Slice 2b) —
# the number of scroll passes before giving up on an ever-growing (or
# non-terminating) infinite-scroll page.
_SCROLL_STABLE_MAX_PASSES = 8


def camoufox_launcher() -> Any:
    """Yield an async-CM that launches headless Camoufox.

    DORMANT (browser-backend-bakeoff): the `camoufox` dep was dropped (its build
    lacks juggler #625) and the manifest is gated, so this never runs today. Kept
    for one-line re-enable when a fixed Camoufox build ships + the dep returns.
    The import is intentionally unresolvable until then.
    """
    from camoufox.async_api import AsyncCamoufox  # ty: ignore[unresolved-import]

    return AsyncCamoufox(headless=True)


@asynccontextmanager
async def chromium_launch(async_playwright_fn: Callable[[], Any]) -> AsyncIterator[Any]:
    """Two-step Playwright launch flattened into a one-shot CM yielding a Browser.

    Drop-in Chromium engines (Patchright, rebrowser-playwright) expose
    `async_playwright()` returning the *API object*, not a Browser — unlike
    `AsyncCamoufox`, whose `__aenter__` returns a Browser directly. This wrapper
    enters playwright, launches headless Chromium, and yields the Browser so the
    drop-ins satisfy the same `launch_fn` contract `PlaywrightBackend` expects
    (`__aenter__` → Browser). The driver spawns inside this `__aenter__`, so it
    lands within the backend's stderr-capture window like Camoufox's does.
    Cleanup closes the browser then exits playwright.
    """
    async with async_playwright_fn() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            with suppress(Exception):
                await browser.close()


def _cookie_to_playwright(cookie: BackendCookie) -> dict[str, Any]:
    """Engine-neutral `BackendCookie` → Playwright `add_cookies` shape."""
    out: dict[str, Any] = {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path,
        "expires": cookie.expires if cookie.expires is not None else -1,
        "secure": cookie.secure,
        "httpOnly": cookie.http_only,
    }
    if cookie.samesite is not None:
        out["sameSite"] = cookie.samesite.capitalize()
    return out


_CHALLENGE_STATUSES = (401, 403, 429)


def _is_challenged_subresource(response: Any) -> bool:
    """True if a page subresource (XHR/fetch) returned a bot-challenge status.

    The walled-API fake-empty detector: a shell can 200 and render an authentic
    "0 results" while its data API is 403'd. Best-effort — any driver quirk while
    reading the response returns False so the render can never be failed by it.
    """
    try:
        return response.request.resource_type in ("xhr", "fetch") and response.status in _CHALLENGE_STATUSES
    except Exception:  # best-effort telemetry — never fail the render on a driver quirk
        return False


def _summarize_exc(exc: BaseException) -> str:
    """One-line `Type: first-message-line` summary — never a multi-line dump.

    The full driver stack (when leaked) rides the captured stderr log events;
    the `detail` the tier turns into a wire hint stays terse.
    """
    name = type(exc).__name__
    lines = str(exc).strip().splitlines()
    first = lines[0].strip() if lines else ""
    return f"{name}: {first}" if first else name


async def _scroll_and_retry(page: Any, original_html: str) -> str:
    """Scroll-to-bottom + 2s networkidle wait + re-snapshot.

    Returns whichever capture (original or post-scroll) is longer. Never
    raises. Emits `browser_scroll_retry` diagnostics on the `a2kit` logger
    (typed-record shape: message = event name, payload on `a2kit_fields`) so
    operators measure firing rate without coupling this package to the domain
    event types.
    """
    _A2KIT_LOG.info("StageStarted", extra={"a2kit_fields": {"t_ms": 0, "step": "browser_scroll_retry"}})
    start = time.perf_counter()
    larger = original_html
    outcome = "smaller"
    try:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            await page.wait_for_load_state("networkidle", timeout=2_000)
        except Exception:
            # networkidle never settled — try a brief sleep then snapshot anyway
            await asyncio.sleep(0.5)
        retry_html = await page.content()
        if len(retry_html) > len(original_html):
            larger = retry_html
            outcome = "larger"
    except Exception:
        outcome = "timeout"
    dur_ms = int((time.perf_counter() - start) * 1000)
    fields = {"t_ms": 0, "step": "browser_scroll_retry", "verdict": "ok", "dur_ms": dur_ms, "extra": {"outcome": outcome}}
    _A2KIT_LOG.info("StageEnded", extra={"a2kit_fields": fields})
    return larger


async def _scroll_to_stable(page: Any, original_html: str, *, max_passes: int = _SCROLL_STABLE_MAX_PASSES) -> str:
    """Scroll repeatedly until the captured HTML stops growing (listing Slice 2b).

    Unlike `_scroll_and_retry` (one thin-triggered pass), this drives an
    infinite-scroll listing to completion: scroll → settle → re-snapshot, keeping
    the largest capture, terminating when a pass adds nothing (the list is fully
    materialised) OR `max_passes` is reached (the safety bound for an
    ever-growing / virtualised page). Never raises — a page error ends the loop
    and returns the best capture so far. Emits `browser_scroll_stable` diagnostics
    on the `a2kit` logger (typed-record shape) so operators measure firing rate.
    """
    _A2KIT_LOG.info("StageStarted", extra={"a2kit_fields": {"t_ms": 0, "step": "browser_scroll_stable"}})
    start = time.perf_counter()
    best = original_html
    passes = 0
    for _ in range(max_passes):
        passes += 1
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            try:
                await page.wait_for_load_state("networkidle", timeout=2_000)
            except Exception:
                await asyncio.sleep(0.5)
            html = await page.content()
        except Exception:
            break
        if len(html) <= len(best):
            break  # no growth this pass → the listing is fully materialised.
        best = html
    dur_ms = int((time.perf_counter() - start) * 1000)
    fields = {"t_ms": 0, "step": "browser_scroll_stable", "verdict": "ok", "dur_ms": dur_ms, "extra": {"passes": passes}}
    _A2KIT_LOG.info("StageEnded", extra={"a2kit_fields": fields})
    return best


class _StderrFilenoShim:
    """Stand-in for ``sys.stderr`` that lies only about its file descriptor.

    Playwright spawns its Node driver with ``stderr=_get_stderr_fileno()``,
    which reads ``sys.stderr.fileno()`` at spawn time (see playwright
    ``_impl/_transport.py``). Swapping ``sys.stderr`` for this shim around the
    launch makes the driver subprocess inherit our pipe's write end — and
    nothing else: every attribute except ``fileno`` delegates to the real
    stream, so Python-level ``sys.stderr.write``/``flush`` and any
    ``StreamHandler`` still reach the genuine terminal. Confines the redirect
    to the spawned child; the parent's fd 2 is never touched.
    """

    def __init__(self, real: Any, fileno: int) -> None:
        self._real = real
        self._fileno = fileno

    def fileno(self) -> int:
        return self._fileno

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class PlaywrightBackend:
    """Playwright-API rendering engine with per-host LRU contexts.

    Not thread-safe; assumes a single asyncio event loop (the standard a2web
    invariant). `launch_fn` yields an async-CM whose `__aenter__` returns a
    Playwright `Browser` (Camoufox today).
    """

    def __init__(
        self,
        launch_fn: Callable[[], Any],
        *,
        name: str = "camoufox",
        max_pool: int = 4,
        idle_timeout_s: int = 300,
        page_budget_s: int = 30,
        launch_budget_s: float = 30.0,
        reaper_interval_s: float = 30.0,
        stderr_sink: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.name = name
        self._launch_fn = launch_fn
        self.max_pool = max_pool
        self.idle_timeout_s = idle_timeout_s
        self.page_budget_s = page_budget_s
        # Hard ceiling on the browser LAUNCH — a stuck engine spawn must return
        # `unavailable` and unblock the caller, never hang the tool call forever.
        self.launch_budget_s = launch_budget_s
        # How often the idle reaper checks whether the launched browser has gone
        # idle past `idle_timeout_s` and should be shut down (bounds resident
        # browser processes on a long-lived server — the leak this fixes).
        self.reaper_interval_s = reaper_interval_s
        # Insertion order = LRU (move-to-end on touch).
        self._contexts: OrderedDict[str, _HostContext] = OrderedDict()
        self._launch_cm: Any | None = None
        self._browser: Any | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._eviction_tasks: set[asyncio.Task[None]] = set()
        # Idle-reaper bookkeeping: last render activity + in-flight page count so
        # the reaper never shuts an engine that is mid-render.
        self._last_activity = time.monotonic()
        self._active_pages = 0
        self._reaper_task: asyncio.Task[None] | None = None
        # Driver-stderr capture (opt-in via injected async sink — keeps this
        # package domain-free; the domain wires emission of typed log events).
        self._stderr_sink = stderr_sink
        self._stderr_read_fd: int | None = None
        self._stderr_write_fd: int = -1
        self._stderr_buf = b""
        self._stderr_loop: asyncio.AbstractEventLoop | None = None
        self._stderr_tasks: set[asyncio.Task[None]] = set()

    async def render(
        self,
        url: str,
        *,
        cookies: list[BackendCookie],
        budget_s: float,
        js_heavy: bool,
        scroll_to_stable: bool = False,
    ) -> RenderedPage:
        """Launch (lazily), navigate, capture rendered HTML. Never raises for
        routine failures — returns a `RenderedPage` with the matching outcome.

        `scroll_to_stable` (listing-completeness Slice 2b) drives an
        infinite-scroll listing to completion after navigation — scroll until the
        captured HTML stops growing — instead of the single thin-triggered pass.
        """
        try:
            await asyncio.wait_for(self._ensure(), timeout=self.launch_budget_s)
        except TimeoutError:
            # A wedged engine spawn: tear down the half-open launch so it can't
            # leak, and unblock the caller with `unavailable` (the never-hang
            # guarantee). A truly-wedged subprocess is best-effort here — the
            # point is the tool call returns instead of hanging indefinitely.
            await self._abort_launch()
            detail = f"browser launch timed out after {self.launch_budget_s:.0f}s"
            return RenderedPage(outcome=RenderOutcome.unavailable, final_url=url, detail=detail)
        except ImportError as exc:
            return RenderedPage(outcome=RenderOutcome.unavailable, final_url=url, detail=f"engine not installed: {exc}")
        except Exception as exc:  # launch failed
            return RenderedPage(outcome=RenderOutcome.unavailable, final_url=url, detail=f"browser launch failed: {exc}")

        wall_start = time.perf_counter()
        # Count page subresources (XHR/fetch) challenged during render — the
        # walled-API fake-empty signal. Best-effort: the listener swallows every
        # error (via the module-level predicate) so a driver quirk can never fail
        # the render.
        blocked: list[int] = []

        def _on_response(response: Any) -> None:
            if _is_challenged_subresource(response):
                blocked.append(1)

        try:
            async with self.acquire(url) as page:
                with suppress(Exception):
                    page.on("response", _on_response)
                if cookies:
                    # Seed cookies on the BrowserContext BEFORE navigation so
                    # the request goes out logged-in. add_cookies upserts by
                    # (name, domain, path) — refreshed values override warm state.
                    await page.context.add_cookies([_cookie_to_playwright(c) for c in cookies])
                try:
                    response = await asyncio.wait_for(page.goto(url, wait_until="networkidle"), timeout=budget_s)
                    status_code = response.status if response is not None else 200
                    final_url = page.url or url
                    # `content()` can hang on a page that never settles the DOM;
                    # bound it by the remaining budget so a stuck snapshot times
                    # out instead of blocking the caller indefinitely.
                    remaining = max(1.0, budget_s - (time.perf_counter() - wall_start))
                    html = await asyncio.wait_for(page.content(), timeout=remaining)
                except TimeoutError:
                    return RenderedPage(
                        outcome=RenderOutcome.timeout,
                        final_url=url,
                        js_executed=True,
                        wall_ms=_ms(wall_start),
                        subresource_blocks=len(blocked),
                    )
                # Scroll-on-thin: sub-floor first snapshot on a JS-heavy host →
                # scroll + 2s networkidle, keep the larger snapshot (Trendyol).
                if len(html) < _THIN_FLOOR and js_heavy:
                    html = await _scroll_and_retry(page, html)
                # Explicit listing completion: scroll to stable (Slice 2b).
                if scroll_to_stable:
                    html = await _scroll_to_stable(page, html)
        except Exception as exc:  # navigation/network/driver errors
            return RenderedPage(
                outcome=RenderOutcome.error,
                final_url=url,
                js_executed=True,
                wall_ms=_ms(wall_start),
                detail=_summarize_exc(exc),
                subresource_blocks=len(blocked),
            )

        return RenderedPage(
            outcome=RenderOutcome.ok,
            html=html,
            final_url=final_url,
            status_code=status_code,
            js_executed=True,
            wall_ms=_ms(wall_start),
            bytes_transferred=len(html),
            subresource_blocks=len(blocked),
        )

    async def _ensure(self) -> None:
        """Lazy-init: launch the engine under lock if not yet opened.

        Idempotent under concurrent first calls (double-checked locking).
        Raises ImportError if the optional engine dep is missing — `render`
        catches and reports `unavailable`.
        """
        if self._browser is not None:
            return
        async with self._lock:
            if self._browser is not None:
                return
            # launch_fn does the (possibly optional) engine import and returns
            # an async-CM; ImportError bubbles up to render().
            self._launch_cm = self._launch_fn()
            # Redirect the driver's inherited stderr into a pipe across the
            # launch so raw Node.js traces never hit the operator's terminal
            # (no-op without a sink).
            saved_stderr = self._install_stderr_capture()
            try:
                self._browser = await self._launch_cm.__aenter__()
            finally:
                self._restore_stderr(saved_stderr)
            self._begin_stderr_drain()
            self._last_activity = time.monotonic()
            self._start_reaper_locked()

    def _install_stderr_capture(self) -> Any:
        """Swap `sys.stderr` for a pipe-backed shim across the driver launch.

        Returns the real `sys.stderr` to restore, or None when capture is off
        (no sink injected — test backends keep their inherited stderr).
        """
        if self._stderr_sink is None:
            return None
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        self._stderr_read_fd = read_fd
        self._stderr_write_fd = write_fd
        real = sys.stderr
        sys.stderr = _StderrFilenoShim(real, write_fd)  # type: ignore[assignment]
        return real

    def _restore_stderr(self, saved: Any) -> None:
        """Restore `sys.stderr` and drop the parent's copy of the pipe writer."""
        if self._stderr_sink is None or self._stderr_read_fd is None:
            return
        sys.stderr = saved  # type: ignore[assignment]
        with suppress(OSError):
            os.close(self._stderr_write_fd)

    def _begin_stderr_drain(self) -> None:
        """Register an on-loop reader that forwards driver stderr lines."""
        if self._stderr_sink is None or self._stderr_read_fd is None:
            return
        self._stderr_loop = asyncio.get_running_loop()
        self._stderr_loop.add_reader(self._stderr_read_fd, self._on_stderr_readable)

    def _on_stderr_readable(self) -> None:
        """Drain available driver stderr bytes; emit each complete line."""
        read_fd = self._stderr_read_fd
        if read_fd is None:
            return
        try:
            chunk = os.read(read_fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            self._stop_stderr_capture()
            return
        if not chunk:  # EOF — driver subprocess exited and closed its stderr.
            self._stop_stderr_capture()
            return
        self._stderr_buf += chunk
        *lines, self._stderr_buf = self._stderr_buf.split(b"\n")
        for raw in lines:
            line = raw.decode("utf-8", "replace").rstrip("\r")
            if line:
                self._emit_stderr_line(line)

    def _emit_stderr_line(self, line: str) -> None:
        sink = self._stderr_sink
        loop = self._stderr_loop
        if sink is None or loop is None:
            return
        task = loop.create_task(sink(line))
        self._stderr_tasks.add(task)
        task.add_done_callback(self._stderr_tasks.discard)

    def _stop_stderr_capture(self) -> None:
        """Tear down the reader and close the pipe read end. Idempotent."""
        read_fd = self._stderr_read_fd
        if read_fd is None:
            return
        if self._stderr_buf:  # flush a trailing unterminated line
            line = self._stderr_buf.decode("utf-8", "replace").rstrip("\r")
            self._stderr_buf = b""
            if line:
                self._emit_stderr_line(line)
        if self._stderr_loop is not None:
            with suppress(Exception):
                self._stderr_loop.remove_reader(read_fd)
        with suppress(OSError):
            os.close(read_fd)
        self._stderr_read_fd = None

    async def start(self) -> None:
        """Alias for `_ensure()` — kept for the resource-pattern tests."""
        await self._ensure()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._cancel_reaper()
        self._stop_stderr_capture()
        async with self._lock:
            await self._teardown_engine_locked()

    async def _teardown_engine_locked(self) -> None:
        """Close all host contexts + the browser process. Leaves the backend
        RE-OPENABLE (does not set `_closed`) — shared by terminal `close()` and
        the idle reaper, which sleeps the engine so the next render re-launches.
        Caller holds `self._lock`.
        """
        for host_ctx in list(self._contexts.values()):
            with suppress(Exception):
                await host_ctx.context.close()
        self._contexts.clear()
        if self._launch_cm is not None:
            with suppress(Exception):
                await self._launch_cm.__aexit__(None, None, None)
        self._launch_cm = None
        self._browser = None

    async def _abort_launch(self) -> None:
        """Tear down a half-open launch after a launch-budget timeout so the
        dangling CM/subprocess can't leak and a later render can retry cleanly."""
        async with self._lock:
            await self._teardown_engine_locked()

    def _start_reaper_locked(self) -> None:
        """Start the idle reaper if not already running. Caller holds the lock."""
        if self._reaper_task is not None and not self._reaper_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._reaper_task = loop.create_task(self._reap_idle_loop())

    async def _cancel_reaper(self) -> None:
        task = self._reaper_task
        self._reaper_task = None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task

    async def _reap_idle_loop(self) -> None:
        """Close the launched browser once it has been idle past `idle_timeout_s`.

        Bounds resident browser processes on a long-lived server: without this
        the chromium/Camoufox process lives until the whole server exits, so a
        leaked/wedged server orphans hours-old browsers. The reaper sleeps the
        engine (re-openable) rather than terminally closing the backend.
        """
        while not self._closed:
            await asyncio.sleep(self.reaper_interval_s)
            async with self._lock:
                if self._closed or self._browser is None:
                    return
                idle_for = time.monotonic() - self._last_activity
                if self._active_pages > 0 or idle_for <= self.idle_timeout_s:
                    continue
                await self._teardown_engine_locked()
                return  # engine slept; next _ensure re-launches + restarts the reaper

    # Framework-facing async-CM protocol. Thin wrappers around the idempotent
    # `_ensure` / `close` internal surface.
    async def __aenter__(self) -> PlaywrightBackend:
        await self._ensure()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    @asynccontextmanager
    async def acquire(self, url: str) -> AsyncIterator[Any]:
        """Yield a fresh page for `url`'s host. Closes the page on exit.

        The host's BrowserContext is reused across fetches (cookie jar warm);
        only the Page is per-fetch (1:1 to avoid state leak).
        """
        host = urlparse(url).hostname or "_default"
        page = await self._open_page(host)
        # Mark in-flight so the idle reaper never shuts an engine mid-render.
        self._active_pages += 1
        self._last_activity = time.monotonic()
        try:
            yield page
        finally:
            self._active_pages -= 1
            self._last_activity = time.monotonic()
            with suppress(Exception):
                await page.close()

    async def _open_page(self, host: str) -> Any:
        async with self._lock:
            self._evict_idle_locked()
            host_ctx = self._contexts.get(host)
            if host_ctx is None:
                host_ctx = await self._create_host_context_locked(host)
            else:
                self._contexts.move_to_end(host)
            host_ctx.last_used = time.monotonic()
            page = await host_ctx.context.new_page()
            return page

    async def _create_host_context_locked(self, host: str) -> _HostContext:
        if self._browser is None:
            raise RuntimeError("PlaywrightBackend not started")
        # LRU evict if at cap.
        while len(self._contexts) >= self.max_pool:
            evicted_host, evicted = self._contexts.popitem(last=False)
            with suppress(Exception):
                await evicted.context.close()
            del evicted_host
        context = await self._browser.new_context()
        host_ctx = _HostContext(context=context, last_used=time.monotonic())
        self._contexts[host] = host_ctx
        return host_ctx

    def _evict_idle_locked(self) -> None:
        now = time.monotonic()
        stale = [h for h, c in self._contexts.items() if now - c.last_used > self.idle_timeout_s]
        for host in stale:
            ctx = self._contexts.pop(host)
            # Close-fire-and-forget; we're under the lock so can't await.
            # Keep a reference so the task is not garbage-collected mid-close.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                continue
            task = loop.create_task(_safe_close(ctx.context))
            self._eviction_tasks.add(task)
            task.add_done_callback(self._eviction_tasks.discard)


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class _HostContext:
    __slots__ = ("context", "last_used")

    def __init__(self, *, context: Any, last_used: float) -> None:
        self.context = context
        self.last_used = last_used


async def _safe_close(context: Any) -> None:
    with suppress(Exception):
        await context.close()
