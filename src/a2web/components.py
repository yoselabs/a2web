"""The one composition root — every a2web resource is built exactly here.

Replaces a2kit's `app.provide(...)` registry. The graph is written out as
plain calls in dependency order, because a2web's graph is *known*: ten types,
one scope, no runtime resolution. The container's value was resolving unknown
graphs; a2web never had one.

**What the framework used to guarantee, and now this module does:**

- *Lazy first-use.* Only `settings` and the cheap always-on constructors run
  eagerly. `browser_backend`, `browser_robust_backend`, `llm_extractor`,
  `cookie_jar` and `sqlite` are `Lazy[T]` thunks; nothing is constructed or
  entered until something awaits one. A `query` served from cache must leave
  the browser and LLM thunks untouched — pinned by
  `tests/architecture/test_cold_start_laziness.py`, because hand-wiring turns
  that guarantee from structural into a convention.
- *LIFO teardown.* Entry is recorded on `ResourceScope` only after a
  successful `__aenter__`; the scope unwinds in reverse on `aclose()`.

**Overrides replace the a2kit test seam.** Tests used to swap a resource with
`app.provide(T, fake)` last-write-wins. Here they pass a factory override —
same effect, but the substitution points are a visible parameter list rather
than a registry mutation, so there is no such thing as overriding a key that
no longer exists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from any_browser import BrowserBackend
from async_scope import Lazy, ResourceScope, memoized
from purgatory import AsyncCircuitBreakerFactory

from .cache import SqliteResource
from .cookie_jar import CookieJarResource, build_cookie_jar
from .llm_resource import LlmExtractorResource
from .packages.llm_extract import Provider
from .settings import AppSettings, get_settings
from .state import (
    AppState,
    build_breakers,
    build_browser_backend,
    build_browser_robust_backend,
    build_llm_extractor,
    build_proxy_pool,
    build_selected_provider,
    build_state,
)

__all__ = ["Components", "build_components"]


@dataclass(frozen=True, slots=True)
class Components:
    """The resolved object graph handed to the tool functions.

    Always-on members are values; heavy or fallible members are `Lazy[T]`
    thunks with the same call shape a2kit's DI produced (`await thunk()`), so
    `fetcher.py` and every phase below it are unchanged by the substrate swap.
    """

    settings: AppSettings
    scope: ResourceScope
    state: Lazy[AppState]
    sqlite: Lazy[SqliteResource]
    browser_backend: Lazy[BrowserBackend]
    browser_robust_backend: Lazy[BrowserBackend]
    llm_extractor: Lazy[LlmExtractorResource]
    cookie_jar: Lazy[CookieJarResource]

    async def aclose(self) -> None:
        await self.scope.aclose()


def build_components(
    *,
    settings: AppSettings | None = None,
    sqlite_factory: Callable[[], SqliteResource] | None = None,
    browser_factory: Callable[[AppSettings], BrowserBackend] | None = None,
    browser_robust_factory: Callable[[AppSettings], BrowserBackend] | None = None,
    provider_factory: Callable[[AppSettings], Provider] | None = None,
    breakers_factory: Callable[[], AsyncCircuitBreakerFactory] | None = None,
) -> Components:
    """Build the whole graph. Cheap — no I/O, nothing entered.

    Every `*_factory` override exists for tests and the eval harness. They
    default to the production factories in `state.py`, which remain the single
    source of truth for *how* each resource is constructed; this module only
    decides *when*.
    """
    resolved = settings if settings is not None else get_settings()
    scope = ResourceScope()

    _sqlite = sqlite_factory or SqliteResource
    _browser = browser_factory or build_browser_backend
    _browser_robust = browser_robust_factory or build_browser_robust_backend
    _provider = provider_factory or build_selected_provider
    _breakers = breakers_factory or build_breakers

    async def _make_sqlite() -> SqliteResource:
        return await scope.enter(_sqlite())

    sqlite = memoized(_make_sqlite)

    async def _make_state() -> AppState:
        return build_state(
            settings=resolved,
            breakers=_breakers(),
            proxy_pool=build_proxy_pool(resolved),
            sqlite=await sqlite(),
        )

    async def _make_browser() -> BrowserBackend:
        return await scope.enter(_browser(resolved))

    async def _make_browser_robust() -> BrowserBackend:
        return await scope.enter(_browser_robust(resolved))

    async def _make_provider() -> Provider:
        # Raises `ResourceUnavailable` on a keyless install. That is the whole
        # reason this seam is lazy: eager resolution would turn a
        # degraded-but-serving deploy (fetch_raw works fine without an LLM)
        # into a boot crash.
        return _provider(resolved)

    provider_thunk = memoized(_make_provider)

    async def _make_llm() -> LlmExtractorResource:
        return await scope.enter(build_llm_extractor(resolved, await sqlite(), provider_thunk))

    async def _make_cookie_jar() -> CookieJarResource:
        return await scope.enter(build_cookie_jar(resolved, await sqlite()))

    return Components(
        settings=resolved,
        scope=scope,
        state=memoized(_make_state),
        sqlite=sqlite,
        browser_backend=memoized(_make_browser),
        browser_robust_backend=memoized(_make_browser_robust),
        llm_extractor=memoized(_make_llm),
        cookie_jar=memoized(_make_cookie_jar),
    )
