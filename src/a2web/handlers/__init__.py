"""Per-host site handlers — tier-0, dispatched by URL match.

A `Handler` is a `Tier` (carries `name` + async `fetch`) plus a synchronous
`matches(url) -> bool` discriminator. Adding a new handler: drop a module
under `handlers/`, implement the `Handler` protocol, then add an instance
to `_HANDLERS` below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .hn import HNHandler
from .reddit import RedditHandler

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


@runtime_checkable
class Handler(Protocol):
    """A Tier with a URL-pattern match discriminator."""

    name: str

    def matches(self, url: str) -> bool: ...

    async def fetch(self, url: str, *, state: AppState) -> TierResult: ...


_HANDLERS: tuple[Handler, ...] = (RedditHandler(), HNHandler())


def match_handler(url: str) -> Handler | None:
    """Return the first registered handler whose `matches(url)` is True, else None."""
    for handler in _HANDLERS:
        if handler.matches(url):
            return handler
    return None


__all__ = ["HNHandler", "Handler", "RedditHandler", "match_handler"]
