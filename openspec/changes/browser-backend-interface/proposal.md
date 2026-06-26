## Why

The browser tier is coupled directly to Playwright's `Page` object (`page.goto`, `page.content`, `page.context.add_cookies`, `page.evaluate`). That coupling means the engine is fixed to Camoufox/Firefox — which the Trendyol incident exposed as doubly fragile: it's hostage to a single fork's version-skew (a Playwright 1.60 bump crashed the whole tier through no fault of our code), and it can't read Chromium-only SPAs that a Chromium engine reads trivially.

This change extracts a `BrowserBackend` interface so the rendering engine becomes swappable — a second instance of the proven LLM-provider seam (`Provider` Protocol + `providers/` + `_manifests/llm_providers/` + `select_provider` + `Lazy[T]`). It is the **keystone refactor**: it ships **no new engine and no behavior change**, only the seam that the next changes plug engines into. The contract the tier emits (`TierResult`) is frozen.

## Roadmap (this is change 1 of 4)

1. **`browser-backend-interface`** (this change) — extract the interface; move Camoufox behind it. Pure refactor; Playwright stays pinned `<1.60`; Camoufox remains the working default *transitionally* (gated off in change 2).
2. **`browser-backend-patchright`** — add Patchright (+ rebrowser) Chromium backends; **flip the default to patchright**; **gate the Camoufox manifest** to `Unavailable` with a note (pip pins stale FF135; #625 merged-but-unreleased — re-enable when a build ships commit `b05563291d`); **bump engine deps to latest and DROP the now-unused `playwright` + `camoufox` direct deps** (patchright vendors its own modern playwright-core). This is where modernization lands — only after a Chromium backend is proven green, so the tier is never engine-less.
3. **`browser-backend-comparison`** — run the eval corpus through every enabled backend; score **SPA-read success + robustness + speed** (stealth a secondary tiebreaker); confirm the default.
4. **`browser-backend-zendriver`** — a CDP backend (zendriver), **gated** on change 3 finding Playwright-family stealth insufficient for targets we care about.

## What Changes

- Add a `BrowserBackend` Protocol with a single narrow method `render(url, *, cookies, budget_s, js_heavy) -> RenderedPage`, returning **data** (`html`, `final_url`, `status_code`, `js_executed`) — never a Playwright object. This data-not-object return is what lets a future CDP backend satisfy the same method.
- Add `PlaywrightBackend`, parameterized by a `launch_fn`, holding today's Playwright mechanics: per-host LRU context pool, cookie seeding (`Cookie` → Playwright shape), navigation + budget timeout, scroll-on-thin re-capture, content capture, the driver-stderr capture and `browser_internal_error` hint shipped in `surface-browser-internal-errors-as-hints`. Camoufox becomes `PlaywrightBackend(camoufox_launch)`.
- Refactor `BrowserTier` to delegate to `backend.render(...)` and own only the engine-agnostic tail (trafilatura → markdown, quality gate, `TierResult` assembly). **`TierResult` shape is unchanged.**
- Add `settings.browser_backend: str = "camoufox"`, a `select_backend(settings)` selector, and `_manifests/browser_backends/camoufox.py`.
- `BrowserBackend` replaces `BrowserPool` as the registered resource (`build_browser_pool` → `build_browser_backend`); the per-host pool is now an internal detail of `PlaywrightBackend`. The tool-seam kwarg type changes `Lazy[BrowserPool]` → `Lazy[BrowserBackend]` (internal kwarg, not the MCP wire).
- **Non-goals:** no new engine (change 2), no comparison (change 3), no behavior or response-envelope change. Camoufox stays the only backend and the default.

## Capabilities

### New Capabilities
- `browser-backend`: the swappable rendering-engine seam — the `BrowserBackend` Protocol + `RenderedPage` boundary type, `select_backend` settings-driven selection, the plugin manifest surface, and optional-extra availability degradation.

### Modified Capabilities
- `browser-tier`: the tier no longer drives a Playwright `Page` directly — it delegates rendering to the selected `BrowserBackend` and owns only markdown extraction + gating + `TierResult` assembly. The pool / cookie-seeding / scroll-on-thin / driver-stderr / internal-error-hint behaviors move into `PlaywrightBackend` but are preserved verbatim.

## Impact

- `src/a2web/tiers/browser.py` — shrinks to backend-delegation + markdown/gate.
- `src/a2web/packages/browser_pool.py` → `src/a2web/packages/browser_backends/` — `base.py` (Protocol + `RenderedPage`), `playwright.py` (`PlaywrightBackend` + launch fns), absorbing the current pool + stderr capture.
- `src/a2web/state.py` — `build_browser_backend` + `select_backend`; `_emit_browser_stderr` sink stays.
- `src/a2web/settings.py` — `browser_backend` setting.
- `src/a2web/routers.py` — tool kwarg type `Lazy[BrowserPool]` → `Lazy[BrowserBackend]` (internal; **ask-first per CLAUDE.md tool-signature rule**, though the wire is unaffected).
- `src/a2web/_manifests/browser_backends/camoufox.py` — new manifest.
- `tests/` — pool tests move under the Playwright backend; the real-browser smoke check and all browser-tier tests must stay green (the refactor's fitness function). No envelope/contract change → `tests/contracts/` untouched.
- No new top-level dependency in this change (Camoufox only).
