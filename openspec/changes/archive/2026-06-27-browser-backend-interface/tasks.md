## 1. Define the interface

- [x] 1.1 Add `packages/browser_backends/base.py` with `RenderedPage` (`dataclass(slots=True)`: html, final_url, status_code, js_executed) and the `@runtime_checkable BrowserBackend` Protocol (`render(url, *, cookies, budget_s, js_heavy) -> RenderedPage` + `name` + `__aenter__`/`__aexit__`).
- [x] 1.2 Update `packages/browser_backends/__init__.py` `__all__` and the `tests/architecture/test_packages_boundary_frozen.py` frozen list accordingly.

## 2. Move Playwright mechanics behind PlaywrightBackend

- [x] 2.1 Create `packages/browser_backends/playwright.py` with `PlaywrightBackend(launch_fn)` — absorb the current `BrowserPool` (per-host LRU context, idle eviction, `__aenter__`/`__aexit__`) and the driver-stderr capture (the `sys.stderr` fileno shim + on-loop drain) verbatim.
- [x] 2.2 Move the tier's render mechanics into `PlaywrightBackend.render`: cookie seeding (`_cookie_to_playwright`), `goto(networkidle, budget_s)`, scroll-on-thin (`js_heavy` gated), `content()` capture, the `browser_internal_error` hint path → return `RenderedPage` (carry the internal-error hint via the backend's result surface so the tier can attach it).
- [x] 2.3 Add the Camoufox `launch_fn` (`AsyncCamoufox(headless=True).__aenter__()`); `CamoufoxBackend = PlaywrightBackend(camoufox_launch)` or a thin manifest factory.
- [x] 2.4 Delete `packages/browser_pool.py` once its content is relocated; keep the injected `stderr_sink` wiring.

## 3. Slim the tier to delegation

- [x] 3.1 Rewrite `tiers/browser.py::BrowserTier.fetch` to call `backend.render(...)`, then trafilatura → markdown + gate + `TierResult` assembly. Remove all Playwright/`BrowserPool` references and imports.
- [x] 3.2 Compute `js_heavy` in the tier via the existing `_host_is_js_heavy` helper and pass it to `render`.
- [x] 3.3 Preserve the disabled/unavailable/timeout/internal-error result shapes exactly (map backend outcomes → the same `TierResult` verdicts/hints as today).

## 4. Selection + wiring

- [x] 4.1 Add `settings.browser_backend: str = "camoufox"`.
- [x] 4.2 Add `_manifests/browser_backends/camoufox.py` (`MANIFEST = PluginManifest(name="camoufox", protocol=BrowserBackend, factory=..., requires=...)`).
- [x] 4.3 Add `select_backend(settings)` (mirror `select_provider`) and `build_browser_backend(settings)`; replace `build_browser_pool` in `state.py` and the `app.provide(...)` registration in `server.py`.
- [x] 4.4 Rename the tool-seam kwarg `browser_pool: Lazy[BrowserPool]` → `browser: Lazy[BrowserBackend]` in `routers.py` and thread the resolved backend into `fetcher.fetch` / the browser dispatch. **Confirm with the user (tool-signature touch) before landing.**

## 5. Preserve behavior (the fitness function)

- [x] 5.1 Relocate `tests/packages/test_browser_pool.py` → backend tests; update imports/targets, keep every assertion.
- [x] 5.2 Confirm all `tests/capabilities/browser_tier/` + `test_browser_escalation.py` tests pass unchanged (the tier's external behavior is identical).
- [x] 5.3 Confirm the opt-in real-browser smoke check (`make test-browser`) still launches Camoufox and returns content.
- [x] 5.4 Confirm `tests/contracts/` is unchanged (no envelope move) — do NOT re-bless.
- [x] 5.5 Spec-ownership cleanup: relocate the moved `browser-tier` requirements (pool/cookie/scroll/stderr/internal-error/no-cookie-logging) into the `browser-backend` capability spec so the archived specs have single ownership.

## 6. Gate

- [x] 6.1 `make check` green (lint + ty + test-cov ≥85% + arch); `make test-browser` green locally.
- [x] 6.2 CHANGELOG entry (refactor: extract `BrowserBackend`; no behavior/envelope change).
