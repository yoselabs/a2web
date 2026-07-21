"""The `Lazy[T]` tool-seam shape — a2web's single seam onto it.

`Lazy[T] = Callable[[], Awaitable[T]]`: a zero-arg async thunk that resolves
`T` only if awaited. Heavy resources (browser, LLM) reach the tool seam this
way so cold start never pays for a path it does not take.

**Why this module exists.** The alias is still a2kit's — a2kit's dispatcher
matches on that *exact* alias object when wiring a tool parameter, so it is
re-exported here by identity rather than redefined. Every a2web module now
imports `Lazy` from here, which turns ~5 scattered `from a2kit import Lazy`
lines into one seam to flip when the sunset lands its own memoized
implementation (`sunset-a2kit-dependency` task 4.1).

`lazy(value)` is owned outright — it is three lines, it was only ever a test
convenience, and depending on a framework's *testing* package for it is the
kind of tie that makes a substrate look load-bearing when it is not.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from a2kit import Lazy

__all__ = ["Lazy", "lazy"]

_T = TypeVar("_T")


def lazy(value: _T) -> Callable[[], Awaitable[_T]]:
    """Wrap an already-built `value` in a thunk matching `Lazy[T]`.

    For injecting a pre-built fake where a tool expects `Lazy[T]`. The thunk
    yields `value` by identity on every call — no copy, no caching wrapper.
    Callers needing per-call freshness build their own.
    """

    async def _thunk() -> _T:
        return value

    return _thunk
