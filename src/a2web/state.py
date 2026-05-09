"""Per-App shared state — typed DI container for long-lived resources.

`AppState` carries the resource handles tools and tiers depend on (sqlite
cache, NDJSON log writer, proxy pool, breaker registry, browser pool). PR2
ships only the seam — every resource field is `None` and fills in across
PR3+.

`register_state(app, *, settings=None)` registers a closure provider so the
container hands the same `AppState` to every dispatch on a given App. Two
independent App instances therefore see two independent states (the canary).
A process-wide `lru_cache` would break that invariant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import a2kit

from .settings import AppSettings, get_settings

if TYPE_CHECKING:
    # Forward-only references for fields populated in later PRs. Keeping the
    # annotations here lets `ty` flag typos the moment a PR3+ author touches
    # the field, without forcing PR2 to import unused modules.
    import aiosqlite


@dataclass(slots=True)
class AppState:
    """Shared resources for the fetch pipeline. Per-App singleton.

    All resource fields are typed Optionals defaulting to `None`. PR3 fills
    `sqlite`; PR4 fills `log_writer`; PR7 fills the pools and breakers.
    Tools never assign these directly — they're set during `register_state`
    or by a future lifespan hook.
    """

    settings: AppSettings
    sqlite: aiosqlite.Connection | None = None
    log_writer: Any | None = None
    proxy_pool: Any | None = None
    breakers: Any | None = None
    browser_pool: Any | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def register_state(app: a2kit.App, *, settings: AppSettings | None = None) -> a2kit.App:
    """Attach a per-App `AppState` singleton to `app`'s DI container.

    The factory is a closure capturing one `AppState` instance — repeated
    dispatches on the same App see the same state, but two App instances
    do not share. Pass `settings=` to inject test-scoped configuration;
    omit it to use the cached `get_settings()` result.
    """
    state = AppState(settings=settings or get_settings())
    app.provide(AppState, lambda: state)
    return app
