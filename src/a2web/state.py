"""Always-on shared state, plus the per-resource construction factories.

`AppState` carries the four resources every fetch needs: settings, breakers,
proxy_pool, sqlite. The heavy, conditional ones (browser, llm_extractor,
cookie_jar) are not here — they reach the tool seam as `Lazy[T]` thunks off
`Components`.

**This module owns HOW each resource is constructed; `components.py` owns
WHEN.** The split matters: the factories below are called from exactly one
place, so a new resource is wired once and reaches production, the eval CLI
and the tests together. `bootstrap_state` and the `Resources` bundle used to
be a second assembly point here; the sunset absorbed them into
`build_components`, and `tests/architecture/test_one_composition_root.py`
keeps a third from appearing.

Nothing here enters a resource — every factory returns a cheap, unstarted
instance. Entry and LIFO teardown belong to `scope.ResourceScope`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar, cast

from any_browser import BrowserBackend
from purgatory import AsyncCircuitBreakerFactory

from .cache import SqliteResource
from .lazy import Lazy
from .llm_resource import _PROVIDER_ORDER, LlmExtractorResource, select_provider
from .packages.llm_extract import Provider  # runtime: a2kit introspects factory annotations (Lazy[Provider]) via get_type_hints
from .packages.proxy_routing import ProxyEntryShape, ProxyPool, RouteRuleShape
from .settings import AppSettings


@dataclass(slots=True)
class AppState:
    """Always-on resources for the fetch pipeline. Per-App singleton.

    `browser_backend` / `llm_extractor` / `cookie_jar` are NOT here — they are
    `Lazy[T]` thunks on `Components` and reach the tool seam unresolved.
    """

    settings: AppSettings
    breakers: AsyncCircuitBreakerFactory
    proxy_pool: ProxyPool
    sqlite: SqliteResource


# --------------------------------------------------------------------- #
# Per-resource factories — single source of truth for construction.
# `components.build_components()` is their only caller.
# --------------------------------------------------------------------- #


def build_breakers() -> AsyncCircuitBreakerFactory:
    """**Per-host** circuit breakers. Not per-proxy, not global.

    This docstring used to claim "per-host / per-proxy / global", and neither
    of the last two has ever had a call site: the only keys handed to
    `get_breaker` are a bare `host` (`tiers/raw.py`) and `nitter:{instance}`
    (`handlers/twitter.py`).

    The correction matters beyond tidiness. Proxy health degradation IS
    implemented — by `ProxyPool._ProxyHealth`, on a consecutive-failure
    quarantine, keyed on proxy id — so a reader who believed the old docstring
    would conclude a2web runs TWO overlapping health mechanisms over the same
    thing. It does not. The two are orthogonal axes: breakers degrade a
    *destination host*, the pool quarantines an *egress proxy*. A host that
    fails through a healthy proxy and a proxy that fails across many hosts are
    different failures and want different responses.
    """
    return AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


def build_proxy_pool(settings: AppSettings) -> ProxyPool:
    """Route table + proxies map from settings."""
    return ProxyPool(
        routes=cast("list[RouteRuleShape]", settings.routes),
        proxies=cast("dict[str, ProxyEntryShape]", settings.proxies),
    )


async def _emit_browser_stderr(line: str) -> None:
    """Domain sink for captured browser-driver stderr lines.

    Injected into the (domain-free) `PlaywrightBackend`; emits one typed log
    event per line so raw Node.js driver traces surface in the logging
    substrate instead of on the operator's terminal.
    """
    from . import log as a2web_log
    from .events import BrowserSubprocessStderr

    await a2web_log.info(BrowserSubprocessStderr(line=line))


_BACKEND_SURFACE = "a2web._manifests.browser_backends"


def select_backend_named(settings: AppSettings, name: str) -> BrowserBackend:
    """Pick the named rendering engine from the manifest registry.

    Mirrors `select_provider`: `_manifests/browser_backends/` decides *what can
    be built*; `name` picks the one to use. An unknown or unavailable backend
    raises `ResourceUnavailable`, degrading at the tool seam (the same path the
    LLM provider uses) rather than crashing.
    """
    from plugin_surface import load_surface

    from .log import get_logger

    registry = load_surface(_BACKEND_SURFACE, BrowserBackend, settings, logger=get_logger())
    backend = registry.get(name)
    if backend is None:
        available = ", ".join(sorted(registry)) or "(none)"
        raise ResourceUnavailable(f"browser backend '{name}' unavailable (registered: {available})")
    return backend


def select_backend(settings: AppSettings) -> BrowserBackend:
    """Pick the fast rung (`settings.browser_backend`)."""
    return select_backend_named(settings, settings.browser_backend)


def build_browser_backend(settings: AppSettings) -> BrowserBackend:
    """DI factory for the fast browser rung — selects the engine; does NOT launch
    it at construction (launch is lazy on first `render`)."""
    return select_backend(settings)


def build_browser_robust_backend(settings: AppSettings) -> BrowserBackend:
    """Factory for the robust browser rung (`settings.browser_backend_robust`, a
    CDP engine). Until the sunset this needed a distinct `RobustBrowserBackend`
    return type purely so a2kit's type-keyed container could tell the two
    browser providers apart; hand-wired, they are simply two named thunks and
    the marker protocol is deleted (design D5)."""
    return select_backend_named(settings, settings.browser_backend_robust)


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
