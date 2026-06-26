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

### 1. The interface returns `RenderedPage` (data), not a `Page`
```python
@dataclass(slots=True)
class RenderedPage:
    html: str
    final_url: str
    status_code: int
    js_executed: bool

@runtime_checkable
class BrowserBackend(Protocol):
    name: str
    async def render(self, url: str, *, cookies: list[Cookie],
                     budget_s: float, js_heavy: bool) -> RenderedPage: ...
```
The tier passes the *domain* `Cookie` type (the backend translates to its engine's shape), the budget, and a `js_heavy` policy bit (the tier computes it from `JS_HEAVY_HOSTS`; the backend decides whether to run scroll-on-thin). Everything downstream of `render()` — trafilatura → markdown, the quality gate, `TierResult` assembly — stays in the tier and is shared across engines.

*Alternative considered:* return a Playwright `Page` and let the tier keep driving it — rejected: that *is* the coupling we're removing, and it's unsatisfiable by a CDP backend.

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
