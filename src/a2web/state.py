"""Per-App shared state — always-on bundle + Lazy-eligible resource bundle.

`AppState` carries the four resources every fetch needs: settings, breakers,
proxy_pool, sqlite. `Resources` carries the three Lazy-eligible resources
(browser_pool, llm_extractor, cookie_jar) that are surfaced at the tool seam
via `Lazy[T]` so cold-start cost is paid only when the path needs them.

`bootstrap_state(settings)` is the single source of truth for constructing
both bundles. Production (`server.py`), the eval harness
(`llm_eval/__main__.py`), and test fixtures (`tests/conftest.py`) all
delegate to this factory so a new resource added to either bundle reaches
every construction path automatically (closes the v0.22 bench-harness gap).

Lifecycle is owned by a2kit v0.36+: each resource registered via
`app.provide(...)` enters on first resolution (lazy first-use) and exits in
LIFO order on app shutdown. `bootstrap_state` does NOT call `__aenter__` on
any resource — it returns cheap unstarted instances. Callers that bypass DI
(eval CLI, direct-call tests) own the lifecycle via `async with` blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar, cast

from a2kit import Lazy
from purgatory import AsyncCircuitBreakerFactory

from .cookie_jar import CookieJarResource, build_cookie_jar
from .llm_resource import _PROVIDER_ORDER, LlmExtractorResource, select_provider
from .packages.browser_pool import BrowserPool
from .packages.http_cache import SqliteResource
from .packages.llm_extract import Provider  # runtime: a2kit introspects factory annotations (Lazy[Provider]) via get_type_hints
from .packages.proxy_routing import ProxyEntryShape, ProxyPool, RouteRuleShape
from .settings import AppSettings


@dataclass(slots=True)
class AppState:
    """Always-on resources for the fetch pipeline. Per-App singleton.

    `browser_pool` / `llm_extractor` / `cookie_jar` are NOT here — they live
    on `Resources` and reach the tool seam as `Lazy[T]`.
    """

    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    proxy_pool: ProxyPool
    sqlite: SqliteResource


@dataclass(frozen=True, slots=True)
class Resources:
    """Heavy/conditional resources surfaced at the tool seam via `Lazy[T]`.

    Frozen because the bundle itself is a value (no in-place mutation); the
    resources it holds carry their own internal mutable state.
    """

    browser_pool: BrowserPool
    llm_extractor: LlmExtractorResource
    cookie_jar: CookieJarResource


# --------------------------------------------------------------------- #
# Per-resource factories — single source of truth for construction.
# Production providers in `server.py` call these; `bootstrap_state` calls
# these; tests / eval call `bootstrap_state`. No duplication.
# --------------------------------------------------------------------- #


def build_breakers() -> AsyncCircuitBreakerFactory:
    """Per-host / per-proxy / global circuit breakers."""
    return AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


def build_proxy_pool(settings: AppSettings) -> ProxyPool:
    """Route table + proxies map from settings."""
    return ProxyPool(
        routes=cast("list[RouteRuleShape]", settings.routes),
        proxies=cast("dict[str, ProxyEntryShape]", settings.proxies),
    )


def build_browser_pool(settings: AppSettings) -> BrowserPool:
    """Camoufox pool — does NOT launch the browser at construction."""
    return BrowserPool(
        max_pool=settings.browser_max_pool,
        idle_timeout_s=settings.browser_idle_timeout_s,
        page_budget_s=settings.browser_page_budget_s,
    )


def build_selected_provider(settings: AppSettings) -> Provider:
    """DI factory for the `Provider` type: pick the best backend via the shared
    `select_provider`, or raise `ResourceUnavailable` when none is configured.

    Registered in `server.py` as `app.provide(Provider, build_selected_provider)`.
    The LLM resource depends on `Lazy[Provider]`; awaiting it runs this factory,
    so "no provider" surfaces as `ResourceUnavailable` at the extract seam — the
    same path browser/cookie resources use.
    """
    selection = select_provider(settings)
    if selection is None:
        tried = settings.llm_provider if settings.llm_provider != "auto" else ", ".join(_PROVIDER_ORDER)
        raise ResourceUnavailable(f"no LLM provider available (tried: {tried})")
    _, provider = selection
    return provider


def build_llm_extractor(settings: AppSettings, sqlite: SqliteResource, provider: Lazy[Provider]) -> LlmExtractorResource:
    """LLM extractor — the provider is injected (DI resolves `Lazy[Provider]`
    via `build_selected_provider`); Extractor construction stays deferred to
    first use."""
    return LlmExtractorResource(settings, sqlite, provider)


def _provider_lazy(provider: Provider | None, settings: AppSettings) -> Lazy[Provider]:
    """Wrap a pre-resolved provider as a `Lazy[Provider]` thunk, or defer to
    `build_selected_provider(settings)` when none was supplied. Used by
    `bootstrap_state` (bench/tests), which don't run inside the DI container."""
    if provider is not None:
        given = provider

        async def _given() -> Provider:
            return given

        return _given

    async def _selected() -> Provider:
        return build_selected_provider(settings)

    return _selected


def build_state(
    settings: AppSettings,
    breakers: AsyncCircuitBreakerFactory,
    proxy_pool: ProxyPool,
    sqlite: SqliteResource,
) -> AppState:
    """Bundle the four always-on resources into AppState."""
    return AppState(
        settings=settings,
        breakers=breakers,
        proxy_pool=proxy_pool,
        sqlite=sqlite,
    )


# --------------------------------------------------------------------- #
# Stub-on-unavailable — direct-call paths (eval w/o LLM, tests w/o
# browser) pass an `unavailable_lazy(...)` stub instead of `None`. Phases
# `await`-resolve uniformly and catch `ResourceUnavailable` to emit the
# operator-hint path. Keeps FetchContext.<resource> non-optional.
# --------------------------------------------------------------------- #


class ResourceUnavailable(RuntimeError):
    """Raised by an unavailable_lazy stub when a phase tries to resolve a
    resource the caller didn't provision. Carries a human-readable `reason`
    for operator-hint construction at the catch site."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_T = TypeVar("_T")


def unavailable_lazy(resource_cls: type[_T], *, reason: str) -> Lazy[_T]:
    """Return a Lazy thunk that raises `ResourceUnavailable(reason)` when
    awaited. Use at the seam where a caller doesn't have a real resource to
    pass — preserves the non-optional `Lazy[T]` contract on FetchContext.

    `resource_cls` is captured for type inference only; the body just raises.
    """
    _ = resource_cls

    async def _raise() -> _T:
        raise ResourceUnavailable(reason)

    return _raise


async def bootstrap_state(settings: AppSettings, *, provider: Provider | None = None) -> tuple[AppState, Resources]:
    """Construct the full resource bundle from `settings` — single source of truth.

    Production (`server.py`) uses the DI `app.provide(...)` chain; eval
    (`llm_eval/__main__.py`) and tests (`tests/conftest.py`) reach the same
    instances through this factory. `provider` injects a pre-resolved LLM
    provider into the extraction resource (the bench passes the one it picked
    for its judges); when omitted the resource defers to `select_provider`.

    Async by contract (Phase 1 of fetcher-orchestrator-refactor-v1) — body is
    sync today because all resource construction is cheap and `__aenter__` is
    deferred; the async signature is the seam future resources can lean on
    without changing every caller.
    """
    sqlite = SqliteResource()
    state = build_state(
        settings=settings,
        breakers=build_breakers(),
        proxy_pool=build_proxy_pool(settings),
        sqlite=sqlite,
    )
    resources = Resources(
        browser_pool=build_browser_pool(settings),
        llm_extractor=build_llm_extractor(settings, sqlite, _provider_lazy(provider, settings)),
        cookie_jar=build_cookie_jar(settings, sqlite),
    )
    return state, resources
