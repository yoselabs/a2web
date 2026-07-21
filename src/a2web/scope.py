"""The composition substrate: `ResourceScope` (lifecycle) + `memoized` (lazy).

This is everything a2web needed from a2kit's 599-line DI container. The
container exists to resolve *unknown* dependency graphs; a2web has one scope,
ten types, and a graph fully known where it is written. What survives is the
two behaviours that were genuinely load-bearing:

**LIFO teardown, recorded only after a successful `__aenter__`.** A resource
whose entry raised was never entered, so exiting it would call `__aexit__` on
a half-built object. The `enter()` call appends to the stack *after* the await
returns, never before.

**Memoized async thunks under a construction lock.** `Lazy[T]` is
`Callable[[], Awaitable[T]]` — awaiting it the first time builds, every later
await returns the same instance. The lock makes concurrent first-callers
collapse to one construction; without it, twenty concurrent `query` calls on a
cold server race to launch twenty browsers.

Both are deliberately small enough to read in one sitting. If either grows a
resolution order, a graph, or a registry, the wrong thing is being solved.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any, TypeVar

from .lazy import Lazy

_T = TypeVar("_T")

__all__ = ["ResourceScope", "memoized"]


class ResourceScope:
    """Owns entered resources and unwinds them LIFO.

    Not a `contextlib.AsyncExitStack` subclass on purpose: the stack's
    `enter_async_context` is the right shape, but a2web needs `aclose()` to be
    idempotent and to keep unwinding after a failing `__aexit__` — one
    resource refusing to close must not strand the ones beneath it.
    """

    def __init__(self) -> None:
        self._entered: list[Any] = []
        self._closed = False

    async def enter(self, resource: _T) -> _T:
        """Enter `resource` if it is an async context manager, and record it.

        Recording happens only after `__aenter__` returns. A resource that
        raises on entry is not on the teardown stack, because it was never
        entered.
        """
        aenter = getattr(resource, "__aenter__", None)
        if aenter is None:
            return resource
        entered = await aenter()
        self._entered.append(resource)
        return entered  # type: ignore[no-any-return]

    async def aclose(self) -> None:
        """Unwind LIFO. Idempotent, and does not stop at the first failure."""
        if self._closed:
            return
        self._closed = True
        first: BaseException | None = None
        while self._entered:
            resource = self._entered.pop()
            try:
                await resource.__aexit__(None, None, None)
            except Exception as exc:
                first = first or exc
        if first is not None:
            raise first

    async def __aenter__(self) -> ResourceScope:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()


def memoized(factory: Callable[[], Awaitable[_T]]) -> Lazy[_T]:
    """Wrap an async `factory` as a `Lazy[T]` that builds at most once.

    The double check around the lock is not superstition: the fast path (the
    overwhelmingly common one, after first use) must not pay for lock
    acquisition on every resolution inside the fetch pipeline.
    """
    lock = asyncio.Lock()
    slot: list[_T] = []

    async def _thunk() -> _T:
        if slot:
            return slot[0]
        async with lock:
            if not slot:
                slot.append(await factory())
        return slot[0]

    return _thunk
