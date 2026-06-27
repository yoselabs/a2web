# browser-backend Specification

## Purpose

A swappable rendering-engine seam: the browser tier delegates JS-capable
rendering to a selected `BrowserBackend` rather than driving a Playwright
`Page` directly. The Protocol and its value objects are package-owned and
domain-free (mirroring the `Provider`/`ProviderResponse` LLM seam), so any
engine — Playwright-family today, CDP-family later — can satisfy one method.
Created by archiving change `browser-backend-interface`.
## Requirements
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

The system SHALL select the active backend from `settings.browser_backend` via a `select_backend(settings)` function resolving over manifests in `_manifests/browser_backends/`, each declaring `MANIFEST = PluginManifest(name, protocol=BrowserBackend, factory=..., requires=...)`. An unknown or unavailable backend SHALL degrade through the existing `ResourceUnavailable` seam (the same path the LLM provider uses), never crash the app. Backends requiring an optional dependency SHALL surface as `Unavailable` when the extra is absent.

The registry SHALL retain **two** engines after the bake-off — a fast Chromium engine (`patchright`) selected by `settings.browser_backend` and a robust CDP engine (`zendriver`) selected by `settings.browser_backend_robust` — resolved by a shared `select_backend_named(settings, name)`. The default `settings.browser_backend` SHALL be `"patchright"`, NOT `"camoufox"`. The Camoufox manifest SHALL be gated to surface `Unavailable` — its code is retained behind the gate (it is the one known fingerprint-strong engine) but it is unselectable until a Camoufox build ships juggler commit `b05563291d` (PR #625), at which point the gate is lifted. Both retained engines SHALL be installed out-of-the-box (their dependencies are non-optional) so a fresh install renders both rungs without extra setup.

#### Scenario: default selects the fast engine, not camoufox

- **WHEN** `settings.browser_backend` is unset
- **THEN** `select_backend` resolves `patchright`, and that backend is available (its dependency is installed by default)

#### Scenario: robust engine resolves from its own setting

- **WHEN** `settings.browser_backend_robust` is unset
- **THEN** `select_backend_named` resolves `zendriver`, available out-of-the-box

#### Scenario: camoufox is gated until #625 ships

- **WHEN** `settings.browser_backend` names `"camoufox"`
- **THEN** resolution surfaces `Unavailable` carrying the #625-unreleased reason, and the app does not crash

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

### Requirement: The retained engines are the recorded outcome of a live three-candidate bake-off

The system's rendering engines SHALL be selected by a live bake-off — not by assumption — across three candidates wired behind the `BrowserBackend` interface: `patchright` and `rebrowser-playwright` (Chromium drop-ins realized as `PlaywrightBackend(launch_fn)`), and `zendriver` (a CDP engine realized as a dedicated adapter). The candidates SHALL be scored on **SPA-read success, robustness, and speed** (stealth as a secondary tiebreaker) against a browser-stress URL set (the eval corpus does not exercise the browser tier). The outcome SHALL be recorded to a dated findings file (`eval/findings_<date>.md`) as the audit trail. The bake-off MAY conclude that the candidates are complementary rather than strictly ranked; in that case the system SHALL retain the fast Chromium engine (`patchright`) and the robust CDP engine (`zendriver`) as a fast→robust pair and prune only the strict loser (`rebrowser`). After selection, no non-retained candidate's backend, manifest, or dependency extra SHALL remain in the tree.

#### Scenario: retained engines are chosen on recorded numbers

- **WHEN** the bake-off completes
- **THEN** the retained engines and the prune decision match the recorded SPA-read + robustness + speed profile in `eval/findings_<date>.md`

#### Scenario: pruned candidate leaves no residue

- **WHEN** the change is archived
- **THEN** the tree contains exactly the two retained non-Camoufox backends (`patchright`, `zendriver`) plus the gated Camoufox — no `rebrowser` backend module, manifest, or dependency extra remains

### Requirement: The interface is proven engine-family-agnostic by a CDP adapter

The `BrowserBackend` contract SHALL be demonstrated to span engine families, not just the Playwright API: the `zendriver` candidate SHALL be realized as a `ZendriverBackend` adapter that shapes CDP navigation, content capture, and cookie seeding into the same `render(url, *, cookies, budget_s, js_heavy) -> RenderedPage` method the Playwright-family backends satisfy. The adapter SHALL emit the same domain-free `RenderedPage` value object (carrying no Playwright `Page`/CDP session/domain type) so the tier's `RenderOutcome` → `Verdict`/`OperatorHint` mapping is identical regardless of engine family. This proof SHALL hold for the bake-off even if `zendriver` does not win and its adapter is subsequently removed.

#### Scenario: a CDP backend satisfies the same render contract

- **WHEN** `ZendriverBackend.render(...)` completes during the bake-off
- **THEN** it returns a `RenderedPage` carrying no Playwright/CDP/domain object, and the tier maps its `RenderOutcome` to `Verdict`/`OperatorHint` with no engine-family-specific branch

