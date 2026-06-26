## Context

`BrowserTier.fetch` (`tiers/browser.py`) reaches directly into a Playwright `Page`: `page.context.add_cookies`, `page.goto(wait_until="networkidle")`, `page.content()`, `page.evaluate(scroll)`, `page.url`. `BrowserPool` (`packages/browser_pool.py`) owns the Camoufox launch, the per-host LRU context pool, and (as of `surface-browser-internal-errors-as-hints`) the driver-stderr capture. The engine is therefore hard-wired to Camoufox/Firefox.

The repo already solved this exact shape for LLMs: a tight `Provider` Protocol (`packages/llm_extract/providers/base.py`), per-backend implementations, a plugin manifest per backend (`_manifests/llm_providers/`), a `select_provider(settings)` selector, and `Lazy[Provider]` at the tool seam. This change is a second instance of that pattern for browser engines.

## Goals / Non-Goals

**Goals:**
- A `BrowserBackend` Protocol whose single method returns **data, not a Playwright object**, so any engine (Playwright-family or CDP) can satisfy it.
- Move every Playwright-specific mechanic behind `PlaywrightBackend`; the tier becomes engine-agnostic.
- Settings-driven selection + manifest + optional-extra degradation, mirroring `select_provider`.
- **Zero behavior change.** All existing browser-tier tests and the real-browser smoke check stay green; `TierResult` (hence the response envelope) is byte-identical.

**Non-Goals:**
- No new engine (Patchright/rebrowser = change 2; zendriver = change 4).
- No comparison harness (change 3).
- No per-host backend routing (single global backend this change; routing is a later enhancement).
- No response-envelope or wire change.

## Decisions

### 1. The interface is package-owned and domain-free (refined during apply)
The `packages/` boundary forbids importing domain types (`Cookie`, `OperatorHint`, `Verdict`). So — exactly like `Provider`/`ProviderResponse` — the interface and its value objects are **package-owned and domain-free**:
```python
class RenderOutcome(StrEnum):           # package enum
    ok = "ok"; timeout = "timeout"; error = "error"; unavailable = "unavailable"

@dataclass(slots=True)
class BackendCookie:                    # neutral cookie; tier converts domain Cookie → this
    name: str; value: str; domain: str; path: str
    expires: float | None; secure: bool; http_only: bool; samesite: str | None

@dataclass(slots=True)
class RenderedPage:
    outcome: RenderOutcome
    html: str = ""; final_url: str = ""; status_code: int = 0
    js_executed: bool = False; wall_ms: int = 0; bytes_transferred: int = 0
    detail: str = ""                    # one-line msg for error/unavailable; NOT an OperatorHint

@runtime_checkable
class BrowserBackend(Protocol):
    name: str
    async def render(self, url: str, *, cookies: list[BackendCookie],
                     budget_s: float, js_heavy: bool) -> RenderedPage: ...
    async def __aenter__(self) -> BrowserBackend: ...
    async def __aexit__(self, *exc: object) -> None: ...
```
The **tier** (domain) owns the mapping `RenderOutcome → Verdict/OperatorHint` and the domain `Cookie → BackendCookie` conversion. Everything downstream of `render()` — trafilatura → markdown, the gate, `TierResult` assembly — stays in the tier and is shared across engines.

*Why this differs from the original sketch (`render(cookies: list[Cookie]) -> RenderedPage{html,...}`):* that sketch put domain types (`Cookie`, and implicitly `OperatorHint`/`Verdict` for the failure channel) on a package interface, which the packages-independence invariant forbids. The neutral `BackendCookie` + `RenderOutcome` + `detail` are the boundary-correct expression of the same intent. The failure channel (timeout / internal-error / unavailable) rides `outcome` + `detail`, mapped to domain hints by the tier.

*Alternative considered:* make the backends domain-coupled (like `llm_resource.py`) so they can use `Cookie`/`OperatorHint` directly — rejected: the LLM seam keeps the **Protocol + response** package-owned (`providers/base.py`) and only the *resource wrapper* domain-coupled; mirroring that keeps the engine adapters microsofware-pure and testable without the domain.

### 2. `PlaywrightBackend(launch_fn)` — one body, per-engine launch
Camoufox, Patchright, and rebrowser all expose the Playwright API; only the *launch* differs (`AsyncCamoufox(...).__aenter__()` vs `patchright.async_api.async_playwright().start().chromium.launch(...)`). So `PlaywrightBackend` holds the shared body (pool, cookies, goto, scroll, content, stderr capture) and takes a `launch_fn` that yields a `Browser`. This change wires only the Camoufox `launch_fn`; change 2 adds two more. Mirrors how the LLM providers share `base.py`.

### 3. The pool is an implementation detail of `PlaywrightBackend`, not a shared concept
Per-host LRU `BrowserContext` reuse is Playwright-specific. It moves *inside* `PlaywrightBackend`. `BrowserBackend` becomes the registered, lazily-entered resource (`__aenter__`/`__aexit__`), replacing `BrowserPool`. A future CDP backend manages its own tabs and shares none of this. The driver-stderr fileno-shim capture (Playwright-driver-specific) and the `browser_internal_error` hint move here too — they have no meaning for a CDP engine.

### 4. Selection mirrors `select_provider`
`settings.browser_backend` (default `"camoufox"`) + `select_backend(settings)` resolving via `load_surface` over `_manifests/browser_backends/`. `build_browser_backend(settings)` replaces `build_browser_pool` in the `app.provide(...)` registration. Unknown/unavailable backend degrades through the existing `ResourceUnavailable` seam, exactly like the LLM provider.

### 5. The tool-seam type rename is internal
`routers.py` declares `browser_pool: Lazy[BrowserPool]`. It becomes `browser: Lazy[BrowserBackend]`. This is an internal DI kwarg type — the MCP **wire** (tool name, args, response) is unchanged. Flagged under CLAUDE.md's "ask before tool-signature changes" out of caution, but no client-visible contract moves.

## Risks / Trade-offs

- **A refactor this size can silently change behavior** → the fitness function is the existing suite: every browser-tier test, the pool tests, and the opt-in real-browser smoke check (`make test-browser`) must stay green, and `tests/contracts/` must not move (proves the envelope is byte-identical). TDD the move; no logic edits, only relocation.
- **Spec churn — many `browser-tier` requirements describe behavior that's relocating** → MOVE the pool/cookie/scroll/stderr/internal-error requirements into the new `browser-backend` capability and MODIFY `browser-tier` to "delegates to the selected backend." Net behavior preserved; the delta is a reorganization, not a removal.
- **`PlaywrightBackend(launch_fn)` over-abstracting before the second engine exists** → keep the `launch_fn` seam minimal (yield a `Browser`); resist generalizing for hypothetical engines until change 2/4 prove what actually varies.

## Migration Plan

Pure internal refactor; one release. No wire/envelope change, no new dependency. Rollback = revert. The `app.provide` swap (`build_browser_pool` → `build_browser_backend`) and the `Lazy[]` type rename are the only wiring touches; lifecycle (lazy `__aenter__`/LIFO `__aexit__`) is unchanged because the backend keeps the same CM protocol the pool already exposes.

## Open Questions

- Package name: `packages/browser_backends/` (parallel to `llm_extract/providers/`) vs keeping `browser_pool.py` and adding a sibling. Lean `browser_backends/` for symmetry; confirm the packages-boundary frozen `__all__` test is updated accordingly.
- Whether `js_heavy` belongs on the `render()` signature or should be read by the backend from settings. Lean: pass it (the tier owns the host policy; the backend owns the scroll mechanism).
