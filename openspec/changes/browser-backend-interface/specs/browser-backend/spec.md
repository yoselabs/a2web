## ADDED Requirements

### Requirement: BrowserBackend is a narrow, domain-free data interface

The system SHALL define a `@runtime_checkable` `BrowserBackend` Protocol in `packages/browser_backends/` whose single rendering method returns a `RenderedPage` value object, never a Playwright `Page` or any engine-specific object:

```
async def render(self, url: str, *, cookies: list[BackendCookie],
                 budget_s: float, js_heavy: bool) -> RenderedPage
```

Because the package boundary forbids importing domain types (`Cookie`, `OperatorHint`, `Verdict`), the interface and its value objects SHALL be **package-owned and domain-free** — mirroring how `Provider`/`ProviderResponse` carry no domain types:

- `BackendCookie` — a `dataclass(slots=True)` neutral cookie (`name`, `value`, `domain`, `path`, `expires: float | None`, `secure: bool`, `http_only: bool`, `samesite: str | None`). The **caller** (the tier) converts the domain `Cookie` → `BackendCookie`; the **backend** converts `BackendCookie` → its engine's cookie shape.
- `RenderOutcome` — a package `StrEnum`: `ok | timeout | error | unavailable`.
- `RenderedPage` — a `dataclass(slots=True)`: `outcome: RenderOutcome`, `html: str`, `final_url: str`, `status_code: int`, `js_executed: bool`, `wall_ms: int`, `bytes_transferred: int`, `detail: str` (one-line message for `error`/`unavailable`; no `OperatorHint` — that's domain).

`js_heavy: bool` is a policy bit the caller computes from `JS_HEAVY_HOSTS`; the backend decides whether to run scroll-on-thin. `BrowserBackend` SHALL expose the async-CM protocol (`__aenter__`/`__aexit__`) and be the lazily-entered registered resource that replaces `BrowserPool`. The **tier** maps `RenderOutcome` → domain `Verdict`/`OperatorHint` (`ok` → trafilatura → `ok`/`length_floor`; `timeout` → `Verdict.timeout`; `error` → `connection_error` + `browser_internal_error` hint; `unavailable` → `connection_error` + `browser_unavailable` hint).

#### Scenario: render returns domain-free data

- **WHEN** any `BrowserBackend.render(...)` completes
- **THEN** it returns a `RenderedPage` (package-owned value object) carrying no `OperatorHint`/`Verdict`/`Cookie`, and exposes no Playwright `Page`/`BrowserContext` to the caller

#### Scenario: backend is the registered, lazily-entered resource

- **WHEN** the app provides the browser resource
- **THEN** a `BrowserBackend` (not a `BrowserPool`) is registered, entered on first tool resolution via `__aenter__`, and unwound via `__aexit__` on app exit

### Requirement: Browser backend is selected from settings via a plugin manifest

The system SHALL select the active backend from `settings.browser_backend` (default `"camoufox"`) via a `select_backend(settings)` function resolving over manifests in `_manifests/browser_backends/`, each declaring `MANIFEST = PluginManifest(name, protocol=BrowserBackend, factory=..., requires=...)`. An unknown or unavailable backend SHALL degrade through the existing `ResourceUnavailable` seam (the same path the LLM provider uses), never crash the app. Backends requiring an optional dependency SHALL surface as `Unavailable` when the extra is absent.

#### Scenario: default selects camoufox

- **WHEN** `settings.browser_backend` is unset
- **THEN** `select_backend` resolves the `camoufox` backend

#### Scenario: unavailable backend degrades, not crashes

- **WHEN** `settings.browser_backend` names a backend whose optional dependency is not installed
- **THEN** resolution surfaces `ResourceUnavailable` at the tool seam and the app does not crash

### Requirement: PlaywrightBackend realizes the Playwright-family engine behaviors

The system SHALL provide `PlaywrightBackend`, parameterized by a `launch_fn` that yields a Playwright `Browser`, realizing the behaviors previously owned by `BrowserTier`/`BrowserPool` for any Playwright-API engine: per-host LRU `BrowserContext` reuse with idle eviction; per-fetch cookie seeding (domain `Cookie` → Playwright shape, before navigation); navigation with a `budget_s` network-idle cap; scroll-on-thin re-capture when `js_heavy` and the first snapshot is sub-floor; rendered-HTML capture; the driver-subprocess-stderr capture (the `sys.stderr` fileno shim emitting `BrowserSubprocessStderr` events); and the `browser_internal_error` `OperatorHint` on internal navigation failure. These behaviors SHALL be preserved verbatim from the pre-refactor tier — this change moves them, it does not alter them. The Camoufox backend SHALL be `PlaywrightBackend` with the Camoufox `launch_fn`.

#### Scenario: Camoufox behavior is byte-identical after the move

- **WHEN** the Camoufox backend renders a page that the pre-refactor browser tier rendered
- **THEN** the resulting `TierResult` (markdown, verdict, hints, timing fields) is identical to the pre-refactor output

#### Scenario: driver-stderr capture and internal-error hint live in the Playwright backend

- **WHEN** the Playwright driver leaks stderr or `render` hits an internal navigation exception
- **THEN** the stderr is captured as `BrowserSubprocessStderr` events (no terminal leak) and the failure surfaces as a `browser_internal_error` `OperatorHint` — exactly as before, now owned by `PlaywrightBackend`
