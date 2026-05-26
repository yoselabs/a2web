"""Per-host site handlers — tier-0, dispatched by URL match.

A `Handler` is a `Tier` (carries `name` + async `fetch`) plus a synchronous
`matches(url) -> bool` discriminator. Adding a new handler:

  1. Drop a module under `handlers/` implementing the `Handler` protocol.
  2. Drop a manifest under `_manifests/handlers/<name>.py` (priority sets
     dispatch order — higher fires first).

The concrete handler classes still re-export here for tests / type-narrowing
imports; live dispatch goes through `match_handler` which reads the plugin
registry on first call (cached thereafter).
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


_REGISTRY_CACHE: tuple[Handler, ...] | None = None


def _registry(settings: AppSettings | None) -> tuple[Handler, ...]:
    """Load handlers from `_manifests/handlers/` once and cache the
    priority-sorted tuple. Handler factories all ignore settings today, so
    the cache key is global; rebuild via `_reset_registry()` in tests if
    needed."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    from .._plugin import load_surface_sorted
    from ..settings import AppSettings as _AppSettings

    sorted_pairs = load_surface_sorted(
        "a2web._manifests.handlers", Handler, settings or _AppSettings()
    )
    _REGISTRY_CACHE = tuple(handler for _name, handler in sorted_pairs)
    return _REGISTRY_CACHE


def _reset_registry() -> None:
    """Test-only: clear the handler registry cache so the next call re-walks
    the manifests. Used by handler-suite tests that monkeypatch matches/fetch."""
    global _REGISTRY_CACHE
    _REGISTRY_CACHE = None


def match_handler(url: str, settings: AppSettings | None = None) -> Handler | None:
    """Return the first registered handler whose `matches` is True, else None.

    `settings` is forwarded to each handler's `matches` — config-driven
    handlers need it; pure URL-shape handlers ignore it. Manifest registration
    order is priority-desc (see `_manifests/handlers/*.py`).
    """
    for handler in _registry(settings):
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
