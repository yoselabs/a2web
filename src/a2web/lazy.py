"""The `Lazy[T]` tool-seam shape, owned outright.

`Lazy[T] = Callable[[], Awaitable[T]]`: a zero-arg async thunk that resolves
`T` only if awaited. Heavy resources (browser, LLM) reach the tool seam this
way so cold start never pays for a path it does not take.

Until the sunset this alias was **re-exported from a2kit by identity**, because
a2kit's dispatcher matched on that exact alias object when deciding whether a
tool parameter was injected or agent-facing. That matching is gone — the
parameter lists in `routers.py` are the wire contract now — so the alias is
declared here and means only what it says.

Nothing else changed: the type is structurally identical, so every `await
thunk()` call site in `fetcher.py` and the phases below it is untouched. Two
implementations of `Lazy` are supplied against it — `lazy(value)` below for a
pre-built value, and `scope.memoized(factory)` for a real resource that must be
constructed at most once.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeVar

_T = TypeVar("_T")

Lazy: TypeAlias = Callable[[], Awaitable[_T]]

__all__ = ["Lazy", "lazy"]


def lazy(value: _T) -> Lazy[_T]:
    """Wrap an already-built `value` in a thunk matching `Lazy[T]`.

    For injecting a pre-built fake where a tool expects `Lazy[T]`. The thunk
    yields `value` by identity on every call — no copy, no caching wrapper.
    Callers needing per-call freshness build their own.
    """

    async def _thunk() -> _T:
        return value

    return _thunk
