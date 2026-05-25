"""Live console sink for the bench LDD event stream.

Subscribes to `CellStarted` / `CellEnded` emissions and renders one line per
event under an asyncio lock. Also runs a 30s heartbeat task that summarizes
in-flight cells while the run is active.

Console-only by design: bench is internal tooling. Sinks elsewhere (OTel,
file-based traces) are unaffected — this drains the same emissions in
parallel.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from types import TracebackType

    from a2kit.packages.ldd import LddEmission

_HEARTBEAT_INTERVAL_S = 30.0

_GLYPH_START = "▶"
_GLYPH_OK = "✓"
_GLYPH_FAIL = "✗"
_ASCII_START = ">"
_ASCII_OK = "+"
_ASCII_FAIL = "!"

_COLOR_RESET = "\x1b[0m"
_COLOR_GREEN = "\x1b[32m"
_COLOR_RED = "\x1b[31m"
_COLOR_DIM = "\x1b[2m"


class LiveSink:
    """Async-callable sink rendering bench-cell events to stdout.

    Construct once per suite run; subscribe by passing into
    `ldd_state_for_call(..., sinks=(sink,))`. The sink owns the counter,
    cost accumulator, and the heartbeat task lifecycle.
    """

    def __init__(self, *, total: int, stream: TextIO | None = None, heartbeat_interval_s: float = _HEARTBEAT_INTERVAL_S) -> None:
        self._total = total
        self._stream = stream if stream is not None else sys.stdout
        self._heartbeat_interval_s = heartbeat_interval_s
        self._lock = asyncio.Lock()
        self._running = 0
        self._done = 0
        self._cost = 0.0
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._tty = bool(getattr(self._stream, "isatty", lambda: False)())
        self._unicode = _stream_supports_unicode(self._stream)

    async def __aenter__(self) -> LiveSink:
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def __call__(self, emission: LddEmission) -> None:
        """Sink entrypoint — a2kit dispatches every `event(...)` here."""
        if emission.name == "CellStarted":
            await self._on_started(emission.payload)
        elif emission.name == "CellEnded":
            await self._on_ended(emission.payload)

    async def _on_started(self, payload: dict[str, object]) -> None:
        slug = str(payload.get("slug", "?"))
        system = str(payload.get("system_name", "?"))
        async with self._lock:
            self._running += 1
            self._write_line(self._format_start(slug, system))

    async def _on_ended(self, payload: dict[str, object]) -> None:
        slug = str(payload.get("slug", "?"))
        system = str(payload.get("system_name", "?"))
        verdict = str(payload.get("verdict", "ok"))
        failure_reason = payload.get("failure_reason")
        total_ms = _to_int(payload.get("total_ms"))
        cost = _to_float(payload.get("cost_usd"))
        cache_hit = bool(payload.get("cache_hit", False))
        tier = payload.get("tier")
        async with self._lock:
            self._done += 1
            self._running = max(0, self._running - 1)
            self._cost += cost
            counter = self._done
            line = self._format_end(
                counter=counter,
                slug=slug,
                system=system,
                verdict=verdict,
                failure_reason=failure_reason if isinstance(failure_reason, str) else None,
                total_ms=total_ms,
                cost=cost,
                cache_hit=cache_hit,
                tier=tier if isinstance(tier, str) else None,
            )
            self._write_line(line)

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval_s)
            except asyncio.CancelledError:
                return
            async with self._lock:
                if self._running == 0:
                    continue
                line = f"  …  running: {self._running}, done: {self._done}/{self._total}, cost: ${self._cost:.2f}"
                if self._tty:
                    line = f"{_COLOR_DIM}{line}{_COLOR_RESET}"
                self._write_line(line)

    def _format_start(self, slug: str, system: str) -> str:
        marker = _GLYPH_START if self._unicode else _ASCII_START
        return f"          {marker}  {_truncate(slug, 22):<22}  {_truncate(system, 18):<18}  start"

    def _format_end(
        self,
        *,
        counter: int,
        slug: str,
        system: str,
        verdict: str,
        failure_reason: str | None,
        total_ms: int,
        cost: float,
        cache_hit: bool,
        tier: str | None,
    ) -> str:
        ok = verdict == "ok"
        if self._unicode:
            marker = _GLYPH_OK if ok else _GLYPH_FAIL
        else:
            marker = _ASCII_OK if ok else _ASCII_FAIL
        if self._tty:
            color = _COLOR_GREEN if ok else _COLOR_RED
            marker = f"{color}{marker}{_COLOR_RESET}"
        counter_str = f"[{counter}/{self._total}]"
        verdict_text = "ok" if ok else (failure_reason or "fail")
        dur = f"{total_ms / 1000:.1f}s"
        cost_str = f"${cost:.3f}"
        trailers: list[str] = []
        trailers.append(f"cache={'hit' if cache_hit else 'miss'}")
        if tier:
            trailers.append(f"tier={tier}")
        trailing = "  ".join(trailers)
        slug_col = f"{_truncate(slug, 22):<22}"
        sys_col = f"{_truncate(system, 18):<18}"
        return f"{counter_str:<10}{marker}  {slug_col}  {sys_col}  {verdict_text:<5}  {dur:>6}  {cost_str:>7}  {trailing}"

    def _write_line(self, line: str) -> None:
        self._stream.write(line + "\n")
        self._stream.flush()


def _truncate(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    if width <= 1:
        return s[:width]
    return s[: width - 1] + "…"


def _to_int(v: object) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    return 0


def _to_float(v: object) -> float:
    if isinstance(v, int | float):
        return float(v)
    return 0.0


def _stream_supports_unicode(stream: TextIO) -> bool:
    encoding = getattr(stream, "encoding", None) or ""
    return "utf" in encoding.lower()


__all__ = ("LiveSink",)
