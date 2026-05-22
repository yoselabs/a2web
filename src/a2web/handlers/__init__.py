"""Per-host site handlers — tier-0, dispatched by URL match.

A `Handler` is a `Tier` (carries `name` + async `fetch`) plus a synchronous
`matches(url) -> bool` discriminator. Adding a new handler: drop a module
under `handlers/`, implement the `Handler` protocol, then add an instance
to `_HANDLERS` below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .arxiv import ArxivHandler
from .discourse import DiscourseHandler
from .github import GitHubHandler
from .habr import HabrHandler
from .hn import HNHandler
from .reddit import RedditHandler
from .twitter import TwitterHandler
from .v2ex import V2EXHandler
from .wikipedia import WikipediaHandler

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


class Handler(Protocol):
    """A Tier with a URL-pattern match discriminator.

    `matches` takes an optional `settings` — config-driven handlers
    (e.g. `DiscourseHandler`'s host allowlist) consult it; pure URL-shape
    handlers ignore it. `SiteHandlerTier` passes `state.settings`.
    """

    name: str

    def matches(self, url: str, settings: AppSettings | None = None) -> bool: ...

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult: ...


_HANDLERS: tuple[Handler, ...] = (
    RedditHandler(),
    HNHandler(),
    ArxivHandler(),
    WikipediaHandler(),
    GitHubHandler(),
    TwitterHandler(),
    DiscourseHandler(),
    HabrHandler(),
    V2EXHandler(),
)


def match_handler(url: str, settings: AppSettings | None = None) -> Handler | None:
    """Return the first registered handler whose `matches` is True, else None.

    `settings` is forwarded to each handler's `matches` — config-driven
    handlers need it; pure URL-shape handlers ignore it.
    """
    for handler in _HANDLERS:
        if handler.matches(url, settings):
            return handler
    return None


__all__ = [
    "ArxivHandler",
    "DiscourseHandler",
    "GitHubHandler",
    "HNHandler",
    "HabrHandler",
    "Handler",
    "RedditHandler",
    "TwitterHandler",
    "V2EXHandler",
    "WikipediaHandler",
    "match_handler",
]
